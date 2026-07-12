"""Host API exposed to plugins - extracted from plugin_manager.py (2026-06-20)."""

from __future__ import annotations

import locale
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.background_tasks import start_background_thread
from core.command_action_safety import sanitize_command_actions
from core.command_registry import (
    COMMAND_INTERACTION_PANEL,
    CommandAction,
    CommandContext,
    CommandDefinition,
    CommandMetadata,
    CommandParam,
    CommandRegistry,
    CommandResult,
    limit_command_result_actions,
    register_search_source,
    remove_search_source,
)
from core.network_security import ResponseTooLargeError, safe_urlopen, sanitize_headers, validate_public_http_url
from core.path_security import UnsafePathError, resolve_under
from core.plugin.constants import (
    PLUGIN_API_HTTP_METHODS,
    PLUGIN_API_HTTP_TIMEOUT_SECONDS,
    PLUGIN_API_MAX_HTTP_HEADER_CHARS,
    PLUGIN_API_MAX_HTTP_HEADERS,
    PLUGIN_API_MAX_HTTP_REQUEST_BYTES,
    PLUGIN_API_MAX_HTTP_RESPONSE_BYTES,
    PLUGIN_API_MAX_TEXT_FILE_BYTES,
    PLUGIN_COMMAND_SOFT_TIMEOUT_SECONDS,
)
from infrastructure.process import runtime as process_runtime

from .executor_tracker import _track_executor, _untrack_executor
from .models import PluginManifest
from .validation import _safe_relative_plugin_path

logger = logging.getLogger(__name__)


class PluginAPI:
    def __init__(
        self,
        plugin_id: str,
        plugin_dir: str,
        permissions: list[str],
        registry: CommandRegistry,
        manifest: PluginManifest | None = None,
        failure_callback: Callable[[str, str, str, BaseException, str], str] | None = None,
        active_executors: dict[str, list[threading.Thread]] | None = None,
        theme_provider: Callable[[], str] | None = None,
        module_registry: Any = None,
    ):
        self._plugin_id = plugin_id
        self._plugin_dir = Path(plugin_dir)
        self._permissions = set(permissions)
        self._registry = registry
        self._manifest = manifest
        self._failure_callback = failure_callback
        self._plugin_active_executors = active_executors if active_executors is not None else {}
        self._theme_provider = theme_provider
        self._module_registry = module_registry
        self._registered_ids: list[str] = []
        self._staged_commands: list[CommandDefinition] = []
        self._staged_search_sources: list[str] = []
        self._staged_search_handlers: dict[str, Callable[[str], list[dict]] | None] = {}
        self._registered_modules: dict[str, str] = {}
        self._persistent_helpers: dict[str, Any] = {}
        self._persistent_helpers_lock = threading.Lock()
        self._committed = False

    def _check_permission(self, perm: str) -> None:
        if perm not in self._permissions:
            raise PermissionError(f"插件 {self._plugin_id} 缺少权限: {perm}")

    @property
    def logger(self) -> logging.Logger:
        return logging.getLogger(f"plugin.{self._plugin_id}")

    @property
    def data_dir(self) -> Path:
        d = (self._plugin_dir / "data").resolve(strict=False)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def check_data_path(self, path: str | Path) -> Path:
        """Validate and resolve a path, ensuring it's within the plugin's data directory.

        Raises PermissionError if the path points outside the plugin's data directory.
        This is a voluntary check — plugins using raw open() can bypass it.
        """
        data = self.data_dir.resolve(strict=False)
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = data / candidate
        try:
            return resolve_under(data, candidate, allow_root=True)
        except UnsafePathError as exc:
            raise PermissionError(f"path is outside plugin data directory: {path}") from exc

    def register_search_source(
        self,
        id: str,
        handler: Callable[[str], list[dict]] | None = None,
    ) -> None:
        source_id = self._plugin_scoped_id(id, separator="_")
        if not source_id:
            self.logger.warning("插件搜索源 ID 无效: %s", id)
            return
        self.logger.info("search source staged: %s", source_id)
        # Defer write to _search_sources until commit_staged is called.
        # This ensures rollback can clean up completely if registration fails.
        self._staged_search_sources.append(source_id)
        self._staged_search_handlers[source_id] = handler

    def register_module(self, module_id: str, manifest_path: str = "module.json") -> bool:
        """Register a host module manifest from this plugin package.

        This is the bridge for standalone module plugins. The manifest path is relative to the
        plugin directory and is validated before the host registry sees it.
        """

        safe_path = _safe_relative_plugin_path(manifest_path)
        if safe_path is None:
            return False
        module_manifest = self._plugin_dir / safe_path
        if not module_manifest.is_file():
            return False
        try:
            if self._module_registry is None:
                from core.module_registry import get_module_registry

                module_registry = get_module_registry()
            else:
                module_registry = self._module_registry
            ok = module_registry.register_external_manifest(module_id, module_manifest)
        except Exception:
            logger.debug("插件模块注册失败: %s -> %s", module_id, module_manifest, exc_info=True)
            return False
        if ok:
            self._registered_modules[str(module_id or "")] = str(module_manifest)
        return bool(ok)

    def register_command(
        self,
        id: str,
        title: str,
        handler: Callable[[CommandContext], CommandResult],
        aliases: list[str] | None = None,
        description: str = "",
        category: str = "",
        interaction_mode: str = COMMAND_INTERACTION_PANEL,
        icon_path: str = "",
        search_terms: list[str] | None = None,
        result_window_size: str = "",
        params: list[CommandParam | dict] | None = None,
        risk_level: str = "low",
        requires_admin: bool = False,
        uses_network: bool = False,
        modifies_system: bool = False,
        requires_confirmation: bool = False,
    ) -> bool:
        return self._stage_command(
            id=id,
            title=title,
            handler=handler,
            aliases=aliases,
            description=description,
            category=category,
            interaction_mode=interaction_mode,
            icon_path=icon_path,
            search_terms=search_terms,
            result_window_size=result_window_size,
            params=params,
            risk_level=risk_level,
            requires_admin=requires_admin,
            uses_network=uses_network,
            modifies_system=modifies_system,
            requires_confirmation=requires_confirmation,
            source=f"plugin:{self._plugin_id}",
            require_plugin_namespace=True,
        )

    def register_builtin_command(
        self,
        id: str,
        title: str,
        handler: Callable[[CommandContext], CommandResult],
        aliases: list[str] | None = None,
        description: str = "",
        category: str = "system",
        interaction_mode: str = COMMAND_INTERACTION_PANEL,
        icon_path: str = "",
        search_terms: list[str] | None = None,
        result_window_size: str = "",
        params: list[CommandParam | dict] | None = None,
        risk_level: str = "low",
        requires_admin: bool = False,
        uses_network: bool = False,
        modifies_system: bool = False,
        requires_confirmation: bool = False,
    ) -> bool:
        """Register a plugin-provided command into the host built-in command surface."""

        self._check_permission("builtin.command")
        return self._stage_command(
            id=id,
            title=title,
            handler=handler,
            aliases=aliases,
            description=description,
            category=category,
            interaction_mode=interaction_mode,
            icon_path=icon_path,
            search_terms=search_terms,
            result_window_size=result_window_size,
            params=params,
            risk_level=risk_level,
            requires_admin=requires_admin,
            uses_network=uses_network,
            modifies_system=modifies_system,
            requires_confirmation=requires_confirmation,
            source=f"plugin-builtin:{self._plugin_id}",
            require_plugin_namespace=False,
        )

    def _stage_command(
        self,
        id: str,
        title: str,
        handler: Callable[[CommandContext], CommandResult],
        aliases: list[str] | None = None,
        description: str = "",
        category: str = "",
        interaction_mode: str = COMMAND_INTERACTION_PANEL,
        icon_path: str = "",
        search_terms: list[str] | None = None,
        result_window_size: str = "",
        params: list[CommandParam | dict] | None = None,
        risk_level: str = "low",
        requires_admin: bool = False,
        uses_network: bool = False,
        modifies_system: bool = False,
        requires_confirmation: bool = False,
        source: str = "",
        require_plugin_namespace: bool = True,
    ) -> bool:
        if "." not in id:
            if require_plugin_namespace:
                self.logger.warning("插件命令 ID 必须包含点号: %s", id)
                return False
        if require_plugin_namespace:
            prefix = id.split(".")[0]
            expected_prefixes = {
                self._plugin_id,
                self._plugin_id.replace("-", "_").replace(" ", "_"),
            }
            if prefix not in expected_prefixes:
                self.logger.warning("命令 ID 命名空间不匹配: %s (期望 %s)", id, self._plugin_id)
                return False
        resolved_icon = self._resolve_icon_path(icon_path or (self._manifest.icon if self._manifest else ""))
        plugin_terms = self._plugin_search_terms()
        normalized_params = []
        for param in params or []:
            if isinstance(param, dict):
                # Already handled below — keep first for clarity
                pass
            elif isinstance(param, CommandParam):
                normalized_params.append(param)
                continue
            elif hasattr(param, "to_dict") and callable(param.to_dict):
                # SDK CommandParam (extensions.sdk.CommandParam) — convert to core type
                try:
                    d = param.to_dict()
                except Exception:
                    d = {}
                if isinstance(d, dict):
                    param = d  # fall through to dict handler below
                else:
                    self.logger.warning(
                        "SDK CommandParam.to_dict() 返回非 dict 类型，已忽略参数: %s", type(param).__name__
                    )
                    continue
            if isinstance(param, dict):
                valid_param_keys = {
                    "name",
                    "type",
                    "required",
                    "default",
                    "choices",
                    "sensitive",
                    "label",
                    "placeholder",
                    "help",
                    "multiline",
                    "remember",
                    "source",
                    "validator",
                    "pattern",
                    "min_value",
                    "max_value",
                    "advanced",
                }
                allowed = {key: value for key, value in param.items() if key in valid_param_keys}
                if "name" in allowed:
                    normalized_params.append(CommandParam(**allowed))
        cmd = CommandDefinition(
            id=id,
            title=title,
            aliases=aliases or [],
            description=description,
            category=category,
            handler=self._wrap_handler(handler, id),
            icon_path=resolved_icon,
            source=source or f"plugin:{self._plugin_id}",
            interaction_mode=interaction_mode,
            search_terms=plugin_terms + list(search_terms or []),
            result_window_size=result_window_size,
            params=normalized_params,
            metadata=CommandMetadata(
                category=category,
                risk_level=risk_level,
                requires_admin=requires_admin,
                uses_network=uses_network,
                modifies_system=modifies_system,
                requires_confirmation=requires_confirmation,
            ),
        )
        self._staged_commands.append(cmd)
        return True

    def commit_staged(self) -> bool:
        """Atomically register all staged commands and search sources. Rollback on any failure."""
        if self._committed:
            return True

        def rollback_modules():
            try:
                for module_id, manifest_path in self._registered_modules.items():
                    try:
                        if self._module_registry is None:
                            from core.module_registry import get_module_registry

                            module_registry = get_module_registry()
                        else:
                            module_registry = self._module_registry
                        module_registry.unregister_external_manifest(module_id, manifest_path)
                    except Exception:
                        logger.debug("插件模块回滚失败: %s -> %s", module_id, manifest_path, exc_info=True)
            except Exception:
                logger.debug("插件模块回滚失败: %s", self._plugin_id, exc_info=True)
            self._registered_modules.clear()

        staged_source_ids: set[str] = set()
        for sid in self._staged_search_sources:
            if sid in staged_source_ids:
                logger.error("插件 %s 重复注册搜索源: %s", self._plugin_id, sid)
                rollback_modules()
                self._staged_commands.clear()
                self._staged_search_sources.clear()
                self._staged_search_handlers.clear()
                self._registered_ids.clear()
                return False
            staged_source_ids.add(sid)
        # Write staged search sources to global dict
        written_sources: list[str] = []
        for sid in self._staged_search_sources:
            ok = register_search_source(
                sid,
                {
                    "handler": self._staged_search_handlers.get(sid),
                    "plugin_id": self._plugin_id,
                    "error_callback": self._failure_callback,
                },
            )
            if not ok:
                for written_sid in written_sources:
                    remove_search_source(written_sid, plugin_id=self._plugin_id)
                rollback_modules()
                self._staged_commands.clear()
                self._staged_search_sources.clear()
                self._staged_search_handlers.clear()
                self._registered_ids.clear()
                logger.error("插件 %s 搜索源 ID 冲突，注册已回滚: %s", self._plugin_id, sid)
                return False
            written_sources.append(sid)
        # Register staged commands
        committed_ids: list[str] = []
        for cmd in self._staged_commands:
            ok = self._registry.register(cmd)
            if ok:
                committed_ids.append(cmd.id)
            else:
                # Rollback: remove commands and search sources
                for cid in committed_ids:
                    self._registry.remove(cid)
                for sid in written_sources:
                    remove_search_source(sid, plugin_id=self._plugin_id)
                available_ids = [c.id for c in self._staged_commands]
                logger.error(
                    "插件 %s 命令注册失败，已回滚 %d 个已注册命令和 %d 个搜索源。失败命令: %s, 所有尝试: %s",
                    self._plugin_id,
                    len(committed_ids),
                    len(written_sources),
                    cmd.id,
                    available_ids,
                )
                rollback_modules()
                self._staged_commands.clear()
                self._staged_search_sources.clear()
                self._staged_search_handlers.clear()
                self._registered_ids.clear()
                return False
        self._registered_ids = committed_ids[:]
        self._staged_commands.clear()
        self._staged_search_sources.clear()
        self._staged_search_handlers.clear()
        self._committed = True
        return True

    def _resolve_icon_path(self, icon_path: str) -> str:
        raw = (icon_path or "").strip()
        if not raw:
            return ""
        safe_raw = _safe_relative_plugin_path(raw)
        if safe_raw is None:
            return ""
        path = (self._plugin_dir / safe_raw).resolve()
        try:
            plugin_root = self._plugin_dir.resolve()
            if path.exists() and (path == plugin_root or plugin_root in path.parents):
                return str(path)
        except Exception as exc:
            logger.debug("插件 API 读取剪贴板失败: %s", exc, exc_info=True)
            return ""
        return ""

    def _plugin_search_terms(self) -> list[str]:
        manifest = self._manifest
        terms = [
            self._plugin_id,
            self._plugin_id.replace("_", " "),
            self._plugin_id.replace("-", " "),
        ]
        if manifest is not None:
            terms.extend(
                [
                    manifest.name,
                    manifest.description,
                    manifest.author,
                    *list(manifest.keywords or []),
                ]
            )
        return [t for t in terms if t]

    def _plugin_scoped_id(self, raw_id: str, separator: str = "_") -> str:
        raw = str(raw_id or "").strip()
        if not raw:
            return ""
        safe_plugin = re.sub(r"[^a-zA-Z0-9_]+", "_", self._plugin_id).strip("_")
        safe_raw = re.sub(r"[^a-zA-Z0-9_\\.\\-]+", "_", raw).strip("._-")
        if not safe_plugin or not safe_raw:
            return ""
        accepted_prefixes = (
            self._plugin_id,
            self._plugin_id.replace("-", "_").replace(" ", "_"),
            safe_plugin,
        )
        if any(
            safe_raw == prefix or safe_raw.startswith((f"{prefix}_", f"{prefix}.", f"{prefix}-"))
            for prefix in accepted_prefixes
        ):
            return safe_raw
        return f"{safe_plugin}{separator}{safe_raw}"

    def _wrap_handler(
        self,
        handler: Callable[[CommandContext], CommandResult],
        command_id: str = "",
    ) -> Callable[[CommandContext], CommandResult]:
        def _validate(result: Any) -> CommandResult:
            def _normalize_actions(actions: Any) -> list[CommandAction]:
                return sanitize_command_actions(actions)

            if result is None:
                return CommandResult(success=False, message="插件未返回结果", error="返回值无效")
            if isinstance(result, dict):
                valid_keys = {
                    "success",
                    "message",
                    "display_type",
                    "payload",
                    "actions",
                    "error",
                    "is_async",
                    "progress",
                    "cancellable",
                }
                extra = set(result.keys()) - valid_keys
                if extra:
                    return CommandResult(
                        success=False,
                        message="插件返回数据无效",
                        error=f"未知字段: {', '.join(sorted(extra))}",
                    )
                result = dict(result)
                result["actions"] = _normalize_actions(result.get("actions"))
                return limit_command_result_actions(CommandResult(**result))
            if isinstance(result, CommandResult):
                result.actions = _normalize_actions(result.actions)
                return limit_command_result_actions(result)
            # SDK CommandResult (extensions.sdk.CommandResult) — same fields,
            # different class; convert via to_dict/attribute fallback.
            if hasattr(result, "to_dict") and callable(result.to_dict):
                try:
                    d = result.to_dict()
                except Exception:
                    d = {}
                if isinstance(d, dict):
                    result = d
            elif hasattr(result, "success") and hasattr(result, "message"):
                d = {}
                for k in (
                    "success",
                    "message",
                    "display_type",
                    "payload",
                    "actions",
                    "error",
                    "is_async",
                    "progress",
                    "cancellable",
                ):
                    try:
                        d[k] = getattr(result, k, None)
                    except Exception:
                        d[k] = None
                result = d
            if isinstance(result, dict):
                valid_keys = {
                    "success",
                    "message",
                    "display_type",
                    "payload",
                    "actions",
                    "error",
                    "is_async",
                    "progress",
                    "cancellable",
                }
                extra = set(result.keys()) - valid_keys
                if extra:
                    return CommandResult(
                        success=False,
                        message="插件返回数据无效",
                        error=f"未知字段: {', '.join(sorted(extra))}",
                    )
                result = dict(result)
                result["actions"] = _normalize_actions(result.get("actions"))
                return limit_command_result_actions(CommandResult(**result))
            return CommandResult(success=False, message="插件返回类型错误", error="类型错误")

        def _safe(context: CommandContext) -> CommandResult:
            done_event = threading.Event()
            result_holder: dict[str, Any] = {}
            worker: threading.Thread | None = None

            def _run_handler() -> None:
                try:
                    result_holder["result"] = handler(context)
                except Exception as exc:
                    logger.debug("Plugin handler failed: %s", exc, exc_info=True)
                    result_holder["error"] = exc
                    result_holder["trace"] = traceback.format_exc()
                finally:
                    done_event.set()
                    if worker is not None:
                        _untrack_executor(self._plugin_active_executors, self._plugin_id, worker)

            def _before_start(thread: threading.Thread) -> None:
                nonlocal worker
                worker = thread
                _track_executor(self._plugin_active_executors, self._plugin_id, thread)

            worker = start_background_thread(
                name=f"plugin-{self._plugin_id}",
                target=_run_handler,
                owner=f"plugin:{self._plugin_id}",
                before_start=_before_start,
            )

            if not done_event.wait(PLUGIN_COMMAND_SOFT_TIMEOUT_SECONDS):
                action = ""
                if self._failure_callback is not None:
                    action = self._failure_callback(
                        self._plugin_id,
                        "command_timeout",
                        command_id,
                        TimeoutError(f"plugin command timeout: {command_id}"),
                        "",
                    )
                message = f"插件命令执行超时: {command_id}"
                if action == "quarantined":
                    message = f"插件已因重复超时被隔离: {command_id}"
                logger.warning(
                    "插件命令超时: plugin=%s command=%s, 后台线程仍在运行",
                    self._plugin_id,
                    command_id,
                )
                return CommandResult(success=False, message=message, error="timeout")

            if "error" in result_holder:
                e = result_holder["error"]
                action = ""
                trace = str(result_holder.get("trace") or "")
                if self._failure_callback is not None:
                    action = self._failure_callback(self._plugin_id, "command", command_id, e, trace)
                if action == "quarantined":
                    return CommandResult(success=False, message=f"插件已因重复失败被隔离: {e}", error=str(e))
                self.logger.error(
                    "插件命令 %s 执行异常: %s", handler.__name__ if hasattr(handler, "__name__") else "?", e
                )
                return CommandResult(success=False, message=f"插件执行失败: {e}", error=str(e))
            return _validate(result_holder.get("result"))

        return _safe

    def read_clipboard(self) -> str:
        self._check_permission("clipboard.read")
        try:
            from qt_compat import QApplication

            cb = QApplication.clipboard()
            return cb.text() or ""  # type: ignore[unused-ignore, union-attr]
        except Exception:
            logger.debug("read_clipboard failed", exc_info=True)
            return ""

    def write_clipboard(self, text: str) -> None:
        self._check_permission("clipboard.write")
        try:
            from qt_compat import QApplication

            QApplication.clipboard().setText(text)  # type: ignore[unused-ignore, union-attr]
        except Exception as exc:
            logger.debug("写入剪贴板失败: %s", exc, exc_info=True)

    def get_selected_files(self) -> list[str]:
        self._check_permission("file.read")
        try:
            from core.file_selection import get_selected_files_for_process

            return get_selected_files_for_process() or []
        except Exception as exc:
            logger.debug("插件 API 获取选中文件失败: %s", exc, exc_info=True)
            return []

    def get_theme(self) -> str:
        """Return the current host theme without exposing the DataManager object."""
        try:
            if self._theme_provider is None:
                from core import get_data_manager

                theme = getattr(get_data_manager().get_settings(), "theme", "dark")
            else:
                theme = self._theme_provider()
            return theme if theme in ("dark", "light") else "dark"
        except Exception as exc:
            logger.debug("插件 API 获取主题失败: %s", exc, exc_info=True)
            return "dark"

    def get_app_version(self) -> str:
        """Return the host application version."""
        try:
            from core.version import APP_VERSION

            return str(APP_VERSION)
        except Exception as exc:
            logger.debug("插件 API 获取应用版本失败: %s", exc, exc_info=True)
            return ""

    def open_url(self, url: str) -> tuple[bool, str]:
        """Open an http(s) URL through the host-controlled API."""
        self._check_permission("open.url")
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return False, "only http(s) URLs are allowed"
        try:
            from core.shortcut_executor import ShortcutExecutor

            ok, error = ShortcutExecutor._launch_with_privilege(parsed.geturl(), run_as_admin=False)
            return bool(ok), str(error or "")
        except Exception as exc:
            logger.debug("Plugin open_url failed: url=%s, %s", url, exc, exc_info=True)
            return False, str(exc)

    def open_file(self, path: str | Path) -> tuple[bool, str]:
        """Open an existing file through Windows file association."""
        self._check_permission("open.file")
        target = Path(path).expanduser().resolve(strict=False)
        if not target.is_file():
            return False, f"file not found: {target}"
        try:
            from core.shortcut_executor import ShortcutExecutor

            ok, error = ShortcutExecutor._launch_with_privilege(str(target), run_as_admin=False)
            return bool(ok), str(error or "")
        except Exception as exc:
            logger.debug("Plugin open_file failed: path=%s, %s", target, exc, exc_info=True)
            return False, str(exc)

    def open_folder(self, path: str | Path) -> tuple[bool, str]:
        """Open an existing folder through Windows file association."""
        self._check_permission("open.file")
        target = Path(path).expanduser().resolve(strict=False)
        if not target.is_dir():
            return False, f"folder not found: {target}"
        try:
            from core.shortcut_executor import ShortcutExecutor

            ok, error = ShortcutExecutor._launch_with_privilege(str(target), run_as_admin=False)
            return bool(ok), str(error or "")
        except Exception as exc:
            logger.debug("Plugin open_folder failed: path=%s, %s", target, exc, exc_info=True)
            return False, str(exc)

    def read_text_file(
        self,
        path: str | Path,
        *,
        encoding: str = "utf-8",
        max_bytes: int = PLUGIN_API_MAX_TEXT_FILE_BYTES,
    ) -> str:
        """Read a bounded text file through the host API."""
        self._check_permission("file.read")
        target = Path(path).expanduser().resolve(strict=False)
        if not target.is_file():
            raise FileNotFoundError(str(target))
        limit = max(1, min(int(max_bytes or 0), PLUGIN_API_MAX_TEXT_FILE_BYTES))
        size = target.stat().st_size
        if size > limit:
            raise ValueError(f"file exceeds read limit: {size} > {limit} bytes")
        return target.read_text(encoding=encoding)

    def write_data_file(
        self,
        relative_path: str | Path,
        text: str,
        *,
        encoding: str = "utf-8",
        append: bool = False,
    ) -> Path:
        """Write text inside the plugin data directory only."""
        self._check_permission("file.write")
        target = self.check_data_path(relative_path)
        if target == self.data_dir.resolve(strict=False):
            raise PermissionError("refusing to write plugin data directory root")
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with target.open(mode, encoding=encoding) as handle:
            handle.write(str(text))
        return target

    def http_request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str | bytes | None = None,
        timeout: float = PLUGIN_API_HTTP_TIMEOUT_SECONDS,
        max_bytes: int = PLUGIN_API_MAX_HTTP_RESPONSE_BYTES,
    ) -> dict[str, Any]:
        """Perform a bounded HTTP request for plugins with network permission."""
        self._check_permission("network.request")
        safe_url = validate_public_http_url(str(url or "").strip())
        method_upper = str(method or "GET").upper()
        if method_upper not in PLUGIN_API_HTTP_METHODS:
            raise ValueError(f"HTTP method not allowed: {method_upper}")
        timeout_value = max(0.1, min(float(timeout or 0), PLUGIN_API_HTTP_TIMEOUT_SECONDS))
        limit = max(1, min(int(max_bytes or 0), PLUGIN_API_MAX_HTTP_RESPONSE_BYTES))

        from urllib.request import Request

        if isinstance(body, str):
            payload = body.encode("utf-8")
        elif isinstance(body, bytes | bytearray):
            payload = bytes(body)
        elif body is None:
            payload = None
        else:
            raise TypeError("HTTP request body must be str, bytes, or None")
        if payload is not None and len(payload) > PLUGIN_API_MAX_HTTP_REQUEST_BYTES:
            raise ValueError(f"request body exceeds limit: {PLUGIN_API_MAX_HTTP_REQUEST_BYTES} bytes")
        request = Request(safe_url, data=payload, method=method_upper)
        normalized_headers = self._normalize_http_headers(headers or {})
        for key, value in normalized_headers.items():
            key_text = str(key or "").strip()
            if key_text:
                request.add_header(key_text, str(value or ""))
        with safe_urlopen(request, timeout=timeout_value) as response:
            try:
                from core.network_security import read_limited_response

                raw = read_limited_response(response, limit)
            except ResponseTooLargeError as exc:
                raise ValueError(f"response exceeds read limit: {limit} bytes") from exc
            content_type = response.headers.get("content-type", "")
            charset = response.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
            return {
                "status": int(getattr(response, "status", 0) or response.getcode()),
                "url": response.geturl(),
                "headers": dict(response.headers.items()),
                "content_type": content_type,
                "text": text,
                "bytes": len(raw),
            }

    def run_process_capture(
        self,
        args: list[str] | tuple[str, ...],
        cwd: str = "",
        *,
        timeout: float = 30.0,
        max_bytes: int = PLUGIN_API_MAX_HTTP_RESPONSE_BYTES,
        inherit_environment: bool = False,
        helper_output_file: bool = False,
    ) -> dict[str, Any]:
        """Run a process through the host and return bounded captured output."""
        self._check_permission("process.run")
        if not isinstance(args, list | tuple) or not args:
            raise ValueError("args must be a non-empty list")
        argv = [str(part) for part in args if str(part or "")]
        if not argv:
            raise ValueError("args must contain a target")
        timeout_value = max(0.1, min(float(timeout or 0), 300.0))
        limit = max(1, min(int(max_bytes or 0), PLUGIN_API_MAX_HTTP_RESPONSE_BYTES))

        from core.shortcut_executor import ShortcutExecutor

        helper_output_path = ""
        if helper_output_file and "--plugin-helper" in argv:
            try:
                separator_index = argv.index("--")
            except ValueError:
                separator_index = len(argv)
            fd, helper_output_path = tempfile.mkstemp(prefix=f"ql_plugin_{self._plugin_id}_", suffix=".out")
            os.close(fd)
            argv = [*argv[:separator_index], "--plugin-output", helper_output_path, *argv[separator_index:]]

        env = os.environ.copy() if inherit_environment else ShortcutExecutor._sanitized_child_env()
        kwargs: dict[str, Any] = {
            "cwd": cwd or None,
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "shell": False,
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        }
        stdout_bytes = b""
        stderr_bytes = b""
        timed_out = False
        returncode = -1
        try:
            completed = process_runtime.run(argv, timeout=timeout_value, **kwargs)
            stdout_bytes = completed.stdout or b""
            stderr_bytes = completed.stderr or b""
            timed_out = False
            returncode = int(completed.returncode)
        except subprocess.TimeoutExpired as exc:
            stdout_bytes = exc.stdout or b""
            stderr_bytes = (exc.stderr or b"") + b"\nprocess timed out"
            timed_out = True
            returncode = -1
        finally:
            if helper_output_path:
                try:
                    path = Path(helper_output_path)
                    if path.is_file():
                        file_bytes = path.read_bytes()
                        if file_bytes:
                            stdout_bytes = stdout_bytes + (b"\n" if stdout_bytes else b"") + file_bytes
                except OSError:
                    logger.debug("读取插件 helper 输出文件失败: %s", helper_output_path, exc_info=True)
                finally:
                    try:
                        Path(helper_output_path).unlink(missing_ok=True)
                    except OSError:
                        logger.debug("删除插件 helper 输出文件失败: %s", helper_output_path, exc_info=True)

        truncated = len(stdout_bytes) > limit or len(stderr_bytes) > limit
        stdout_bytes = stdout_bytes[:limit]
        stderr_bytes = stderr_bytes[:limit]
        stdout = self._decode_process_output(stdout_bytes)
        stderr = self._decode_process_output(stderr_bytes)
        output = stdout
        if stderr:
            output = f"{output}\n{stderr}" if output else stderr
        return {
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "output": output,
            "timed_out": timed_out,
            "truncated": truncated,
        }

    def prewarm_persistent_helper(
        self,
        script_path: str | Path,
        *,
        site_paths: list[str | Path] | None = None,
        timeout: float = 45.0,
        inherit_environment: bool = True,
    ) -> bool:
        """Start a reusable plugin worker and wait until its heavy runtime is ready."""
        self._check_permission("process.run")
        worker = self._get_persistent_helper(
            script_path,
            site_paths=site_paths,
            inherit_environment=inherit_environment,
        )
        worker.start(timeout=timeout)
        return True

    def request_persistent_helper(
        self,
        script_path: str | Path,
        payload: dict[str, Any] | None = None,
        *,
        site_paths: list[str | Path] | None = None,
        timeout: float = 300.0,
        inherit_environment: bool = True,
    ) -> dict[str, Any]:
        """Send one request to a reusable plugin worker."""
        self._check_permission("process.run")
        worker = self._get_persistent_helper(
            script_path,
            site_paths=site_paths,
            inherit_environment=inherit_environment,
        )
        started = time.perf_counter()
        result = worker.request(dict(payload or {}), timeout=timeout)
        self.logger.info(
            "persistent worker request completed: worker=%s operation=%s elapsed=%.1f ms",
            script_path,
            str((payload or {}).get("operation") or ""),
            (time.perf_counter() - started) * 1000,
        )
        return result  # type: ignore[no-any-return]

    def stop_persistent_helper(self, script_path: str | Path) -> None:
        safe_path = _safe_relative_plugin_path(str(script_path))
        if safe_path is None:
            return
        key = str(safe_path).replace("\\", "/").lower()
        with self._persistent_helpers_lock:
            worker = self._persistent_helpers.pop(key, None)
        if worker is not None:
            worker.close()

    def close(self) -> None:
        """Release plugin-owned runtime resources."""
        with self._persistent_helpers_lock:
            workers = list(self._persistent_helpers.values())
            self._persistent_helpers.clear()
        for worker in workers:
            try:
                worker.close()
            except Exception:
                logger.debug("关闭插件常驻运行时失败: %s", self._plugin_id, exc_info=True)

    def _get_persistent_helper(
        self,
        script_path: str | Path,
        *,
        site_paths: list[str | Path] | None,
        inherit_environment: bool,
    ):
        safe_script = _safe_relative_plugin_path(str(script_path))
        if safe_script is None:
            raise ValueError(f"plugin worker path is unsafe: {script_path}")
        script = resolve_under(self._plugin_dir.resolve(strict=False), self._plugin_dir / safe_script)
        if not script.is_file():
            raise FileNotFoundError(str(script))

        resolved_sites: list[Path] = []
        for raw_path in site_paths or []:
            safe_site = _safe_relative_plugin_path(str(raw_path))
            if safe_site is None:
                raise ValueError(f"plugin site path is unsafe: {raw_path}")
            site = resolve_under(self._plugin_dir.resolve(strict=False), self._plugin_dir / safe_site)
            if site.is_dir():
                resolved_sites.append(site)

        key = str(safe_script).replace("\\", "/").lower()
        with self._persistent_helpers_lock:
            worker = self._persistent_helpers.get(key)
            if worker is None:
                from core.plugin_worker_runtime import PersistentPluginWorker

                worker = PersistentPluginWorker(
                    plugin_id=self._plugin_id,
                    script_path=script,
                    site_paths=resolved_sites,
                    cwd=self._plugin_dir,
                    inherit_environment=inherit_environment,
                )
                self._persistent_helpers[key] = worker
            return worker

    @staticmethod
    def _decode_process_output(data: bytes) -> str:
        if not data:
            return ""
        encodings: list[str] = []
        preferred = locale.getpreferredencoding(False)
        if preferred:
            encodings.append(preferred.lower())
        for encoding in ("utf-8", "gbk", "utf-16", "cp437"):
            if encoding not in encodings:
                encodings.append(encoding)
        for encoding in encodings:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode(encodings[0] if encodings else "utf-8", errors="replace")

    def is_user_admin(self) -> bool:
        """Return whether the current host process has administrator rights."""
        try:
            import ctypes

            return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[no-any-return]
        except (AttributeError, ImportError, OSError):
            return False

    def get_recycle_bin_info(self) -> dict[str, int]:
        """Return recycle bin item count and total size in bytes."""
        self._check_permission("file.read")
        try:
            import ctypes
            from ctypes import wintypes

            class SHQUERYRBINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("i64Size", ctypes.c_int64),
                    ("i64NumItems", ctypes.c_int64),
                ]

            info = SHQUERYRBINFO()
            info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
            ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
            return {"size": int(info.i64Size), "items": int(info.i64NumItems)}
        except (AttributeError, ImportError, OSError):
            logger.debug("插件 API 查询回收站失败", exc_info=True)
            return {"size": 0, "items": 0}

    def empty_recycle_bin(self) -> tuple[bool, str]:
        """Empty the recycle bin through the host API."""
        self._check_permission("file.write")
        try:
            import ctypes

            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0)
            return True, ""
        except (AttributeError, ImportError, OSError) as exc:
            return False, str(exc)

    @staticmethod
    def _normalize_http_headers(headers: dict[str, str]) -> dict[str, str]:
        if not isinstance(headers, dict):
            raise TypeError("HTTP headers must be a dict")
        if len(headers) > PLUGIN_API_MAX_HTTP_HEADERS:
            raise ValueError(f"too many HTTP headers: {len(headers)}")
        normalized: dict[str, str] = {}
        total_chars = 0
        for key, value in headers.items():
            key_text = str(key or "").strip()
            value_text = str(value or "")
            if not key_text:
                continue
            if any(ord(ch) < 32 or ord(ch) == 127 for ch in key_text):
                raise ValueError(f"invalid HTTP header name: {key_text!r}")
            if "\r" in value_text or "\n" in value_text:
                raise ValueError(f"invalid HTTP header value for: {key_text}")
            total_chars += len(key_text) + len(value_text)
            if total_chars > PLUGIN_API_MAX_HTTP_HEADER_CHARS:
                raise ValueError("HTTP headers exceed size limit")
            normalized[key_text] = value_text
        return sanitize_headers(normalized)

    def launch_target(
        self,
        target: str,
        parameters: str | list[str] = "",
        directory: str = "",
        *,
        show_window: bool = True,
        run_as_admin: bool = False,
    ) -> tuple[bool, str]:
        """Launch a file/program through the same privilege path as icons."""
        self._check_permission("process.run")
        if run_as_admin:
            self._check_permission("admin.required")
        if not target:
            return False, "target is empty"

        from core.shortcut_executor import ShortcutExecutor

        params = self._normalize_parameters(parameters)
        if not show_window and not run_as_admin:
            argv = [target]
            if params:
                argv.extend(ShortcutExecutor._safe_split_args(params))
            try:
                ShortcutExecutor._popen_silent(
                    argv,
                    cwd=directory or None,
                    env=ShortcutExecutor._sanitized_child_env(),
                    shell=False,
                )
                return True, ""
            except Exception as exc:
                logger.debug("Plugin read_text_file exec failed: %s", exc, exc_info=True)
                return False, str(exc)
        ok, error = ShortcutExecutor._launch_with_privilege(
            target,
            params or None,
            directory or None,
            show_cmd=1 if show_window else 0,
            run_as_admin=run_as_admin,
        )
        return bool(ok), str(error or "")

    def run_command(
        self,
        command: str,
        cwd: str = "",
        *,
        show_window: bool = False,
        run_as_admin: bool = False,
    ) -> tuple[bool, str]:
        """Run a shell command through the same privilege path as command icons."""
        self._check_permission("process.run")
        if run_as_admin:
            self._check_permission("admin.required")
        if not command:
            return False, "command is empty"

        comspec = os.environ.get("ComSpec") or os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "cmd.exe",
        )
        cmd_flag = "/k" if show_window else "/c"
        if not show_window and not run_as_admin:
            from core.shortcut_executor import ShortcutExecutor

            try:
                ShortcutExecutor._popen_silent(
                    [comspec, "/d", "/s", cmd_flag, command],
                    cwd=cwd or None,
                    env=ShortcutExecutor._sanitized_child_env(),
                    shell=False,
                )
                return True, ""
            except Exception as exc:
                logger.debug("Plugin write_text_file exec failed: %s", exc, exc_info=True)
                return False, str(exc)
        params = subprocess.list2cmdline(["/d", "/s", cmd_flag, command])
        return self.launch_target(
            comspec,
            params,
            cwd,
            show_window=show_window,
            run_as_admin=run_as_admin,
        )

    @staticmethod
    def _normalize_parameters(parameters: str | list[str] | tuple[str, ...]) -> str:
        if isinstance(parameters, str):
            return parameters
        try:
            return subprocess.list2cmdline([str(p) for p in parameters])
        except Exception:
            logger.debug("_normalize_parameters failed", exc_info=True)
            return str(parameters or "")


# ---------------------------------------------------------------------------
# ── Validation ─────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------
