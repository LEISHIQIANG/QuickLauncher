"""Plugin system v1 — local plugin scanning, loading, and lifecycle management."""

from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .command_action_safety import sanitize_command_actions
from .command_registry import (
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
from .path_security import UnsafePathError, resolve_under, safe_rmtree_child

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ── Data models ───────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

PERMISSIONS_KNOWN = frozenset(
    {
        "clipboard.read",
        "clipboard.write",
        "file.read",
        "file.write",
        "open.url",
        "open.file",
        "process.run",
        "network.request",
        "admin.required",
    }
)

HIGH_RISK_PERMISSIONS = frozenset(
    {
        "process.run",
        "file.write",
        "admin.required",
    }
)


PLUGIN_TRUST_LEVELS = ("builtin", "local-trusted", "community-unverified")
PLUGIN_PACKAGE_EXTENSION = ".qlzip"
PLUGIN_STATE_SCHEMA = 1
PLUGIN_FAILURE_WINDOW_SECONDS = 10 * 60
PLUGIN_FAILURE_THRESHOLD = 3
PLUGIN_COMMAND_SOFT_TIMEOUT_SECONDS = 10
PLUGIN_ERROR_LOG_MAX_BYTES = 1024 * 1024
PLUGIN_ERROR_LOG_BACKUPS = 3


def is_plugin_package_path(path: str | os.PathLike[str]) -> bool:
    return Path(path).suffix.lower() == PLUGIN_PACKAGE_EXTENSION


def _safe_relative_plugin_path(raw: str) -> str | None:
    value = str(raw or "").replace("\\", "/").strip()
    if not value or value.startswith("/") or value.startswith("//"):
        return None
    if len(value) >= 2 and value[1] == ":":
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return None
    return path.as_posix()


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    entry: str = "main.py"
    icon: str = ""
    keywords: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    trust_level: str = "local-trusted"

    @classmethod
    def from_dict(cls, data: dict) -> PluginManifest:
        trust = data.get("trust_level", "").lower().replace(" ", "-")
        if trust not in PLUGIN_TRUST_LEVELS:
            trust = "local-trusted"
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", ""),
            description=data.get("description", ""),
            author=data.get("author", ""),
            entry=data.get("entry", "main.py"),
            icon=data.get("icon", ""),
            keywords=data.get("keywords", []),
            permissions=data.get("permissions", []),
            commands=data.get("commands", []),
            trust_level=trust,
        )


@dataclass
class PluginInfo:
    manifest: PluginManifest
    directory: str
    status: str = "loaded"  # loaded | enabled | disabled | error | quarantined
    error: str = ""
    registered_commands: list[str] = field(default_factory=list)
    registered_search_sources: list[str] = field(default_factory=list)
    registered_modules: dict[str, str] = field(default_factory=dict)
    registered_chain_processors: list[str] = field(default_factory=list)
    enabled_at: float = 0.0
    last_error_at: float = 0.0
    last_run_at: float = 0.0
    failure_count: int = 0
    last_error_stage: str = ""
    last_error_trace: str = ""
    disabled_reason: str = ""
    quarantined: bool = False


# ---------------------------------------------------------------------------
# ── PluginAPI — controlled surface exposed to plugin main.py ──────────────
# ---------------------------------------------------------------------------


class PluginAPI:
    def __init__(
        self,
        plugin_id: str,
        plugin_dir: str,
        permissions: list[str],
        registry: CommandRegistry,
        manifest: PluginManifest | None = None,
        failure_callback: Callable[[str, str, str, BaseException, str], str] | None = None,
    ):
        self._plugin_id = plugin_id
        self._plugin_dir = Path(plugin_dir)
        self._permissions = set(permissions)
        self._registry = registry
        self._manifest = manifest
        self._failure_callback = failure_callback
        self._registered_ids: list[str] = []
        self._staged_commands: list[CommandDefinition] = []
        self._staged_search_sources: list[str] = []
        self._staged_search_handlers: dict[str, Callable[[str], list[dict]] | None] = {}
        self._registered_modules: dict[str, str] = {}
        self._registered_chain_processors: list[str] = []
        self._committed = False

    def _check_permission(self, perm: str) -> None:
        if perm not in self._permissions:
            raise PermissionError(f"插件 {self._plugin_id} 缺少权限: {perm}")

    @property
    def logger(self) -> logging.Logger:
        return logging.getLogger(f"plugin.{self._plugin_id}")

    @property
    def data_dir(self) -> Path:
        d = self._plugin_dir / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def check_data_path(self, path: str | Path) -> Path:
        """Validate and resolve a path, ensuring it's within the plugin's data directory.

        Raises PermissionError if the path points outside the plugin's data directory.
        This is a voluntary check — plugins using raw open() can bypass it.
        """
        data = self.data_dir.resolve(strict=False)
        try:
            return resolve_under(data, path, allow_root=True)
        except UnsafePathError as exc:
            raise PermissionError(f"path is outside plugin data directory: {path}") from exc

    def register_search_source(
        self,
        id: str,
        handler: Callable[[str], list[dict]] | None = None,
    ) -> None:
        self.logger.info("search source staged: %s", id)
        # Defer write to _search_sources until commit_staged is called.
        # This ensures rollback can clean up completely if registration fails.
        self._staged_search_sources.append(id)
        self._staged_search_handlers[id] = handler

    def register_module(self, module_id: str, manifest_path: str = "module.json") -> bool:
        """Register a host module manifest from this plugin package.

        This is the bridge for future standalone module plugins such as
        ``quicklauncher.action_chain``. The manifest path is relative to the
        plugin directory and is validated before the host registry sees it.
        """

        safe_path = _safe_relative_plugin_path(manifest_path)
        if safe_path is None:
            return False
        module_manifest = self._plugin_dir / safe_path
        if not module_manifest.is_file():
            return False
        try:
            from core.module_registry import module_registry

            ok = module_registry.register_external_manifest(module_id, module_manifest)
        except Exception:
            logger.debug("插件模块注册失败: %s -> %s", module_id, module_manifest, exc_info=True)
            return False
        if ok:
            self._registered_modules[str(module_id or "")] = str(module_manifest)
        return ok

    def register_chain_processor(self, definition: dict, handler: Callable[[dict], CommandResult | dict | str]) -> bool:
        """Register an action-chain processor supplied by this plugin.

        The processor uses the same schema as built-in action-chain batteries.
        IDs are automatically namespaced with the plugin id when no dotted id is
        provided, so ``{"id": "slug"}`` becomes ``my_plugin_slug``.
        """

        try:
            from core.chain_processors import register_external_processor

            ok = register_external_processor(definition, handler, owner=self._plugin_id)
        except Exception:
            logger.debug("插件动作链电池注册失败: %s", definition, exc_info=True)
            return False
        if ok:
            processor_id = str(definition.get("id") or "")
            if "." not in processor_id:
                safe_owner = re.sub(r"[^a-zA-Z0-9_]+", "_", self._plugin_id).strip("_")
                safe_id = re.sub(r"[^a-zA-Z0-9_\\.]+", "_", processor_id).strip("_")
                if safe_owner and safe_id and not safe_id.startswith(f"{safe_owner}_"):
                    processor_id = f"{safe_owner}_{safe_id}"
            self._registered_chain_processors.append(processor_id)
        return ok

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
        if "." not in id:
            self.logger.warning("插件命令 ID 必须包含点号: %s", id)
            return False
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
            if isinstance(param, CommandParam):
                normalized_params.append(param)
            elif isinstance(param, dict):
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
                allowed = {
                    key: value
                    for key, value in param.items()
                    if key in valid_param_keys
                }
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
            source=f"plugin:{self._plugin_id}",
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
        def rollback_chain_processors():
            try:
                from core.chain_processors import unregister_external_processors

                unregister_external_processors(self._plugin_id)
            except Exception:
                logger.debug("插件动作链电池回滚失败: %s", self._plugin_id, exc_info=True)
            self._registered_chain_processors.clear()

        staged_source_ids: set[str] = set()
        for sid in self._staged_search_sources:
            if sid in staged_source_ids:
                logger.error("插件 %s 重复注册搜索源: %s", self._plugin_id, sid)
                rollback_chain_processors()
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
                rollback_chain_processors()
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
                rollback_chain_processors()
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
        except Exception:
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
            if not isinstance(result, CommandResult):
                return CommandResult(success=False, message="插件返回类型错误", error="类型错误")
            result.actions = _normalize_actions(result.actions)
            return limit_command_result_actions(result)

        def _safe(context: CommandContext) -> CommandResult:
            pool = None
            try:
                pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = pool.submit(handler, context)
                result = future.result(timeout=PLUGIN_COMMAND_SOFT_TIMEOUT_SECONDS)
                return _validate(result)
            except concurrent.futures.TimeoutError as e:
                action = ""
                trace = traceback.format_exc()
                if self._failure_callback is not None:
                    action = self._failure_callback(self._plugin_id, "command_timeout", command_id, e, trace)
                message = f"插件命令执行超时: {command_id}"
                if action == "quarantined":
                    message = f"插件已因重复超时被隔离: {command_id}"
                return CommandResult(success=False, message=message, error="timeout")
            except Exception as e:
                action = ""
                trace = traceback.format_exc()
                if self._failure_callback is not None:
                    action = self._failure_callback(self._plugin_id, "command", command_id, e, trace)
                if action == "quarantined":
                    return CommandResult(success=False, message=f"插件已因重复失败被隔离: {e}", error=str(e))
                self.logger.error(
                    "插件命令 %s 执行异常: %s", handler.__name__ if hasattr(handler, "__name__") else "?", e
                )
                return CommandResult(success=False, message=f"插件执行失败: {e}", error=str(e))

            finally:
                if pool is not None:
                    pool.shutdown(wait=False, cancel_futures=True)

        return _safe

    def read_clipboard(self) -> str:
        self._check_permission("clipboard.read")
        try:
            from qt_compat import QApplication

            cb = QApplication.clipboard()
            return cb.text() or ""
        except Exception:
            return ""

    def write_clipboard(self, text: str) -> None:
        self._check_permission("clipboard.write")
        try:
            from qt_compat import QApplication

            QApplication.clipboard().setText(text)
        except Exception as exc:
            logger.debug("写入剪贴板失败: %s", exc, exc_info=True)

    def get_selected_files(self) -> list[str]:
        self._check_permission("file.read")
        try:
            from core.file_selection import get_selected_files_for_process

            return get_selected_files_for_process() or []
        except Exception:
            return []

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

        from .shortcut_executor import ShortcutExecutor

        params = self._normalize_parameters(parameters)
        return ShortcutExecutor._launch_with_privilege(
            target,
            params or None,
            directory or None,
            show_cmd=1 if show_window else 0,
            run_as_admin=run_as_admin,
        )

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
            return str(parameters or "")


# ---------------------------------------------------------------------------
# ── Validation ─────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def validate_manifest(m: PluginManifest) -> str:
    if not m.id:
        return "缺少 plugin.id"
    if not m.name:
        return "缺少 plugin.name"
    if not m.version:
        return "缺少 plugin.version"
    if not m.entry:
        return "缺少 plugin.entry"
    if _safe_relative_plugin_path(m.entry) is None:
        return f"plugin.entry 包含不安全路径: {m.entry}"
    if m.icon and _safe_relative_plugin_path(m.icon) is None:
        return f"plugin.icon 包含不安全路径: {m.icon}"
    if not m.id.isidentifier() and not all(c.isalnum() or c in "-_" for c in m.id):
        return f"plugin.id 包含非法字符: {m.id}"
    for perm in m.permissions:
        if perm not in PERMISSIONS_KNOWN:
            return f"未知权限: {perm}"
    for cmd in m.commands:
        cid = cmd.get("id", "")
        if "." not in cid:
            return f"命令 ID 必须包含点号: {cid}"
    return ""


def has_high_risk_permissions(permissions: list[str]) -> bool:
    return any(p in HIGH_RISK_PERMISSIONS for p in permissions)


# ---------------------------------------------------------------------------
# ── PluginManager ──────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


class PluginManager:
    def __init__(
        self, registry: CommandRegistry, plugins_dir: str = "", save_callback: Callable[[list[str]], None] | None = None
    ):
        self._registry = registry
        self._plugins_dir = plugins_dir or self._default_plugins_dir()
        self._plugins: dict[str, PluginInfo] = {}
        self._loaded_modules: dict[str, object] = {}
        self._active_apis: dict[str, PluginAPI] = {}
        self._save_callback = save_callback
        self._confirm_high_risk_callback: Callable[[PluginInfo], bool] | None = None
        plugins_root = Path(self._plugins_dir).resolve(strict=False)
        self._config_dir = (
            plugins_root.parent / "config" if plugins_root.name == "plugins" else plugins_root / ".config"
        )
        self._state_file = self._config_dir / "plugin_state.json"
        self._error_log_file = self._config_dir / "plugin_errors.jsonl"
        self._plugin_state = self._load_plugin_state()

    def set_save_callback(self, callback: Callable[[list[str]], None] | None) -> None:
        self._save_callback = callback

    def set_confirm_high_risk_callback(self, callback: Callable[[PluginInfo], bool] | None) -> None:
        self._confirm_high_risk_callback = callback

    def _load_plugin_state(self) -> dict:
        try:
            if not self._state_file.exists():
                return {"schema": PLUGIN_STATE_SCHEMA, "plugins": {}}
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"schema": PLUGIN_STATE_SCHEMA, "plugins": {}}
            plugins = data.get("plugins", {})
            if not isinstance(plugins, dict):
                plugins = {}
            return {"schema": PLUGIN_STATE_SCHEMA, "plugins": plugins}
        except Exception as exc:
            logger.debug("load plugin state failed: %s", exc)
            return {"schema": PLUGIN_STATE_SCHEMA, "plugins": {}}

    def _save_plugin_state(self) -> None:
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(self._plugin_state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("save plugin state failed: %s", exc)

    def _apply_persisted_state(self, info: PluginInfo) -> PluginInfo:
        state = self._plugin_state.get("plugins", {}).get(info.manifest.id, {})
        if not isinstance(state, dict):
            return info
        info.failure_count = int(state.get("failure_count") or 0)
        info.last_error_stage = str(state.get("last_error_stage") or "")
        info.disabled_reason = str(state.get("disabled_reason") or "")
        info.last_error_at = float(state.get("last_error_at") or 0)
        if state.get("status") == "quarantined":
            info.status = "quarantined"
            info.quarantined = True
            info.error = info.disabled_reason or "plugin quarantined"
        return info

    def _persist_info_state(self, info: PluginInfo) -> None:
        plugins = self._plugin_state.setdefault("plugins", {})
        plugins[info.manifest.id] = {
            "status": "quarantined" if info.quarantined else info.status,
            "failure_count": info.failure_count,
            "last_error_stage": info.last_error_stage,
            "last_error_at": info.last_error_at,
            "disabled_reason": info.disabled_reason,
        }
        self._save_plugin_state()

    def _record_plugin_failure(
        self, plugin_id: str, stage: str, operation_id: str, error: BaseException, trace: str = ""
    ) -> str:
        info = self._plugins.get(plugin_id)
        now = time.time()
        action = "recorded"
        if info is not None:
            if info.last_error_at and now - info.last_error_at > PLUGIN_FAILURE_WINDOW_SECONDS:
                info.failure_count = 0
            info.failure_count += 1
            info.last_error_at = now
            info.last_error_stage = stage
            info.last_error_trace = trace
            info.error = str(error)
            if info.failure_count >= PLUGIN_FAILURE_THRESHOLD:
                self._quarantine_plugin(plugin_id, f"{stage} failed repeatedly")
                action = "quarantined"
            else:
                self._persist_info_state(info)
        self._append_plugin_error(plugin_id, stage, operation_id, error, trace, action)
        return action

    def _quarantine_plugin(self, plugin_id: str, reason: str) -> None:
        info = self._plugins.get(plugin_id)
        if info is None:
            return
        if info.status == "enabled":
            self.disable_plugin(plugin_id, persist=True)
        info = self._plugins.get(plugin_id)
        if info is None:
            return
        info.status = "quarantined"
        info.quarantined = True
        info.disabled_reason = reason
        info.error = reason
        self._persist_info_state(info)
        self._save_enabled()
        try:
            from .event_log import log_event

            log_event("plugin.quarantined", f"Plugin {plugin_id} quarantined", {"reason": reason})
        except Exception as exc:
            logger.debug("记录插件隔离事件失败: %s", exc, exc_info=True)

    def clear_quarantine(self, plugin_id: str) -> bool:
        """Clear quarantine state and reset failure counters for a plugin."""
        info = self._plugins.get(plugin_id)
        if info is None:
            return False
        info.quarantined = False
        info.status = "disabled"
        info.failure_count = 0
        info.last_error_stage = ""
        info.last_error_trace = ""
        info.disabled_reason = ""
        info.error = ""
        self._persist_info_state(info)
        self._save_enabled()
        return True

    def _append_plugin_error(
        self, plugin_id: str, stage: str, operation_id: str, error: BaseException, trace: str, action: str
    ) -> None:
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            self._rotate_plugin_error_log()
            payload = {
                "time": datetime.now().isoformat(timespec="seconds"),
                "plugin_id": plugin_id,
                "stage": stage,
                "operation_id": operation_id,
                "error": str(error),
                "trace": trace,
                "action": action,
            }
            with self._error_log_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        except Exception as exc:
            logger.debug("append plugin error failed: %s", exc)

    def _rotate_plugin_error_log(self) -> None:
        try:
            if not self._error_log_file.exists() or self._error_log_file.stat().st_size < PLUGIN_ERROR_LOG_MAX_BYTES:
                return
            for index in range(PLUGIN_ERROR_LOG_BACKUPS - 1, 0, -1):
                src = self._error_log_file.with_name(f"{self._error_log_file.name}.{index}")
                dst = self._error_log_file.with_name(f"{self._error_log_file.name}.{index + 1}")
                if src.exists():
                    if dst.exists():
                        dst.unlink()
                    src.replace(dst)
            first = self._error_log_file.with_name(f"{self._error_log_file.name}.1")
            if first.exists():
                first.unlink()
            self._error_log_file.replace(first)
        except Exception as exc:
            logger.debug("rotate plugin error log failed: %s", exc)

    def _save_enabled(self) -> None:
        if self._save_callback is not None:
            enabled = [p.manifest.id for p in self._plugins.values() if p.status == "enabled"]
            try:
                self._save_callback(enabled)
            except Exception:
                logger.exception("保存插件启用状态失败")

    def save_enabled_state(self) -> None:
        """Persist the current enabled plugin ids without changing plugin state."""
        self._save_enabled()

    @staticmethod
    def _default_plugins_dir() -> str:
        return os.path.join(os.path.dirname(__file__), "..", "plugins")

    # ---- scanning ----

    def scan_plugins(self) -> list[PluginInfo]:
        """Rescan plugin directories.

        Enabled plugins are unloaded during the scan. Callers that want to
        preserve runtime state must snapshot enabled ids and call auto_enable().
        """
        for plugin_id in [p.manifest.id for p in self._plugins.values() if p.status == "enabled"]:
            self.disable_plugin(plugin_id, persist=False)
        self._plugins.clear()
        base = Path(self._plugins_dir).resolve(strict=False)
        if not base.is_dir():
            logger.info("插件目录不存在: %s", base)
            return []
        for entry in sorted(base.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "plugin.json"
            if not manifest_path.is_file():
                continue
            info = self._load_manifest(str(entry), manifest_path)
            if info:
                self._plugins[info.manifest.id] = info
        logger.info("扫描到 %d 个插件", len(self._plugins))
        return list(self._plugins.values())

    def _load_manifest(self, directory: str, manifest_path: Path) -> PluginInfo | None:
        try:
            with open(manifest_path, encoding="utf-8") as f:
                raw = json.load(f)
            m = PluginManifest.from_dict(raw)
            if m.id and Path(directory).name != m.id:
                return PluginInfo(
                    manifest=m,
                    directory=directory,
                    status="error",
                    error=f"plugin.id must match directory name: {m.id} != {Path(directory).name}",
                )
            err = validate_manifest(m)
            if err:
                return PluginInfo(
                    manifest=m,
                    directory=directory,
                    status="error",
                    error=err,
                )
            plugin_root = Path(directory).resolve(strict=False)
            safe_entry = _safe_relative_plugin_path(m.entry)
            if safe_entry is None:
                return PluginInfo(
                    manifest=m,
                    directory=directory,
                    status="error",
                    error=f"plugin.entry 包含不安全路径: {m.entry}",
                )
            try:
                entry_path = resolve_under(plugin_root, plugin_root / safe_entry)
            except UnsafePathError:
                return PluginInfo(
                    manifest=m,
                    directory=directory,
                    status="error",
                    error=f"plugin.entry 包含不安全路径: {m.entry}",
                )
            if not entry_path.is_file():
                return PluginInfo(
                    manifest=m,
                    directory=directory,
                    status="error",
                    error=f"插件入口文件不存在: {entry_path}",
                )
            return self._apply_persisted_state(PluginInfo(manifest=m, directory=directory, status="loaded"))
        except (json.JSONDecodeError, OSError) as e:
            return PluginInfo(
                manifest=PluginManifest(id="?", name="?", version="0"),
                directory=directory,
                status="error",
                error=str(e),
            )

    # ---- loading ----

    def load_plugin(self, plugin_id: str) -> bool:
        info = self._plugins.get(plugin_id)
        if info is None:
            logger.warning("插件未找到: %s", plugin_id)
            return False
        if info.status == "quarantined" or info.quarantined:
            logger.warning("插件已隔离，跳过加载: %s", plugin_id)
            return False
        if info.status == "error":
            logger.warning("插件状态异常，无法加载: %s — %s", plugin_id, info.error)
            return False
        if info.status == "enabled":
            return True
        try:
            self._do_load(info)
            info.status = "enabled"
            info.error = ""
            info.enabled_at = time.time()
            info.last_error_at = 0.0
            return True
        except Exception as e:
            info.status = "error"
            info.error = str(e)
            info.last_error_at = time.time()
            info.last_error_stage = "load"
            info.last_error_trace = traceback.format_exc()
            self._append_plugin_error(plugin_id, "load", plugin_id, e, info.last_error_trace, "error")
            self._persist_info_state(info)
            logger.error("插件加载失败 %s: %s", plugin_id, e)
            return False

    def _do_load(self, info: PluginInfo) -> None:
        m = info.manifest
        safe_entry = _safe_relative_plugin_path(m.entry)
        if safe_entry is None:
            raise ValueError(f"plugin.entry unsafe path: {m.entry}")
        plugin_root = Path(info.directory).resolve(strict=False)
        entry_path = resolve_under(plugin_root, plugin_root / safe_entry)
        if not os.path.isfile(entry_path):
            raise FileNotFoundError(f"插件入口文件不存在: {entry_path}")

        module_name = f"_plugin_{m.id}"
        if module_name in sys.modules:
            loader = sys.modules[module_name]
        else:
            spec = importlib.util.spec_from_file_location(module_name, entry_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载插件模块: {entry_path}")
            loader = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = loader
            try:
                spec.loader.exec_module(loader)
            except Exception:
                sys.modules.pop(module_name, None)
                raise

        if not hasattr(loader, "register"):
            raise AttributeError(f"插件 {m.id} 缺少 register(api) 函数")

        api = PluginAPI(
            plugin_id=m.id,
            plugin_dir=info.directory,
            permissions=m.permissions,
            registry=self._registry,
            manifest=m,
            failure_callback=self._record_plugin_failure,
        )
        loader.register(api)
        # Transactional commit — rollback on any registration failure.
        # Save pending info BEFORE commit because commit clears staging lists.
        pending_search_sources = list(api._staged_search_sources)
        if not api.commit_staged():
            raise RuntimeError(f"插件 {m.id} 命令注册事务失败，已回滚所有已注册命令和搜索源")
        info.registered_commands = list(api._registered_ids)
        info.registered_search_sources = pending_search_sources
        info.registered_modules = dict(getattr(api, "_registered_modules", {}) or {})
        info.registered_chain_processors = list(getattr(api, "_registered_chain_processors", []) or [])
        self._loaded_modules[m.id] = loader
        self._active_apis[m.id] = api

    # ---- lifecycle ----

    def enable_plugin(self, plugin_id: str, interactive: bool = True) -> bool:
        info = self._plugins.get(plugin_id)
        if info is None:
            return False
        if interactive and self._confirm_high_risk_callback is not None:
            try:
                confirmed = self._confirm_high_risk_callback(info)
            except TypeError:
                confirmed = self._confirm_high_risk_callback(info.manifest.name)
            if not confirmed:
                logger.info("用户取消启用插件: %s", info.manifest.name)
                return False
        ok = self.load_plugin(plugin_id)
        if ok:
            self._save_enabled()
        return ok

    def disable_plugin(self, plugin_id: str, persist: bool = True) -> bool:
        info = self._plugins.get(plugin_id)
        if info is None:
            return False
        if info.status != "enabled":
            return True

        # Clean up modules and invoke optional unregister/dispose lifecycle hooks
        loader = self._loaded_modules.pop(plugin_id, None)
        api = self._active_apis.pop(plugin_id, None)
        sys.modules.pop(f"_plugin_{plugin_id}", None)
        if loader is not None:
            for hook_name in ("unregister", "dispose"):
                if hasattr(loader, hook_name):
                    try:
                        hook = getattr(loader, hook_name)
                        try:
                            hook(api)
                        except TypeError:
                            hook()
                        logger.info("已执行插件 %s 的清理钩子 %s", plugin_id, hook_name)
                    except Exception as e:
                        logger.warning("执行插件 %s 的清理钩子 %s 失败: %s", plugin_id, hook_name, e)

        # Remove registered commands via owner index for consistency
        owner_id = f"plugin:{plugin_id}"
        self._registry.remove_by_owner(owner_id)
        info.registered_commands.clear()
        for module_id, manifest_path in dict(getattr(info, "registered_modules", {}) or {}).items():
            try:
                from core.module_registry import module_registry

                module_registry.unregister_external_manifest(module_id, manifest_path)
            except Exception:
                logger.debug("插件模块反注册失败: %s", module_id, exc_info=True)
        info.registered_modules.clear()
        try:
            from core.chain_processors import unregister_external_processors

            unregister_external_processors(plugin_id)
        except Exception:
            logger.debug("插件动作链电池反注册失败: %s", plugin_id, exc_info=True)
        info.registered_chain_processors.clear()
        # Clean up search sources
        for sid in info.registered_search_sources:
            remove_search_source(sid, plugin_id=plugin_id)
        info.registered_search_sources.clear()
        info.status = "disabled"
        if persist:
            self._save_enabled()
        return True

    def reload_plugin(self, plugin_id: str) -> bool:
        info = self._plugins.get(plugin_id)
        if info is None:
            return False
        was_enabled = info.status == "enabled"
        was_error = info.status == "error"

        self.disable_plugin(plugin_id)
        # Force re-import by removing from sys.modules
        module_name = f"_plugin_{plugin_id}"
        sys.modules.pop(module_name, None)
        # Re-scan manifest
        manifest_path = Path(info.directory) / "plugin.json"
        new_info = self._load_manifest(info.directory, manifest_path)
        if new_info and new_info.status == "error":
            self._plugins[plugin_id] = new_info
            self._save_enabled()
            return False
        if new_info:
            self._plugins[plugin_id] = new_info
        if not was_enabled and not was_error:
            self._save_enabled()
            return True

        ok = self.load_plugin(plugin_id)
        if ok:
            self._save_enabled()
        else:
            failed_info = self._plugins.get(plugin_id)
            if failed_info is not None and was_enabled:
                failed_info.status = "error"
                failed_info.error = (
                    f"reload failed after unloading previous commands: {failed_info.error or 'unknown error'}"
                )
                failed_info.registered_commands.clear()
                failed_info.registered_search_sources.clear()
                failed_info.registered_chain_processors.clear()
            self._save_enabled()
            logger.info("Plugin reload failed and plugin was left in error state: %s", plugin_id)
        return ok

    # ---- persistence ----

    def auto_enable(self, enabled_ids: list[str]) -> int:
        """Auto-enable plugins from a saved list (e.g. from AppSettings)."""
        count = 0
        failed: list[str] = []
        for pid in enabled_ids:
            info = self._plugins.get(pid)
            if info and (info.status == "quarantined" or info.quarantined):
                failed.append(f"{pid}({info.disabled_reason or 'quarantined'})")
                continue
            if info and info.status == "error":
                failed.append(f"{pid}({info.error})")
                continue
            if self.enable_plugin(pid, interactive=False):
                count += 1
            else:
                info = self._plugins.get(pid)
                err = info.error if info else "unknown"
                failed.append(f"{pid}({err})")
        if count:
            logger.info("已自动启用 %d 个插件", count)
        if failed:
            logger.warning("以下插件自动启用失败: %s", "; ".join(failed))
        return count

    # ---- installation ----

    def install_from_package(
        self,
        package_path: str,
        *,
        on_overwrite: Callable[[str], bool] | None = None,
    ) -> str | None:
        """Install a plugin from a .qlzip archive.

        Returns the ``plugin_id`` on success, or ``None`` if the user declined
        to overwrite an existing plugin (requires *on_overwrite*).

        Raises ``ValueError`` on any error (invalid package, manifest error,
        validation failure, no *on_overwrite* callback when target exists).
        """
        import zipfile

        if not is_plugin_package_path(package_path):
            raise ValueError(f"插件安装包必须使用 {PLUGIN_PACKAGE_EXTENSION} 扩展名")

        try:
            return self._install_zip_archive(package_path, on_overwrite=on_overwrite)
        except zipfile.BadZipFile as e:
            raise ValueError(f"无效的 {PLUGIN_PACKAGE_EXTENSION} 插件包:\n{e}") from e

    def install_from_zip(
        self,
        zip_path: str,
        *,
        on_overwrite: Callable[[str], bool] | None = None,
    ) -> str | None:
        """Compatibility wrapper for plugin package installation."""
        return self.install_from_package(zip_path, on_overwrite=on_overwrite)

    def _install_zip_archive(
        self,
        zip_path: str,
        *,
        on_overwrite: Callable[[str], bool] | None = None,
    ) -> str | None:
        import json as json_mod
        import re
        import shutil
        import sys
        import uuid
        import zipfile
        from pathlib import Path

        plugins_dir = Path(self._plugins_dir).resolve(strict=False)
        staging_base = resolve_under(plugins_dir, plugins_dir / ".staging")
        staging_base.mkdir(parents=True, exist_ok=True)

        staging_dir = resolve_under(staging_base, staging_base / f"install-{uuid.uuid4().hex[:12]}")
        backup_dir: Path | None = None
        plugin_id: str | None = None

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()

                has_root = "plugin.json" in names
                sub_manifest: str | None = None
                archive_root: str | None = None
                for n in names:
                    if n.endswith("/plugin.json") and len(n.split("/")) == 2:
                        sub_manifest = n
                        archive_root = n.split("/", 1)[0]
                        break
                if not has_root and not sub_manifest:
                    raise ValueError(
                        "Could not find a valid plugin.json in the plugin archive.\n"
                        "Please make sure the archive contains plugin.json."
                    )

                try:
                    mb = zf.read("plugin.json") if has_root else zf.read(sub_manifest)
                    manifest_data = json_mod.loads(mb.decode("utf-8"))
                    plugin_id = manifest_data.get("id")
                    plugin_name: str = manifest_data.get("name", plugin_id)
                except Exception as e:
                    raise ValueError(f"解析 plugin.json 失败:\n{e}") from e

                if not plugin_id or not re.match(r"^[a-z0-9_-]+$", plugin_id):
                    raise ValueError("插件ID无效或格式不正确！")

                manifest = PluginManifest.from_dict(manifest_data)
                manifest_error = validate_manifest(manifest)
                if manifest_error:
                    raise ValueError(manifest_error)

                total_size = 0
                file_count = 0
                for member in zf.infolist():
                    if not member.is_dir():
                        if member.flag_bits & 0x1:
                            raise ValueError("plugin archive contains encrypted files, which are not supported")
                        file_count += 1
                        total_size += max(0, int(member.file_size))
                        if total_size > 50 * 1024 * 1024:
                            raise ValueError(
                                f"plugin archive uncompressed size exceeds limit ({total_size / 1024 / 1024:.1f} MB)"
                            )
                if file_count == 0:
                    raise ValueError("压缩包为空，没有可安装的文件")
                if file_count > 500:
                    raise ValueError(f"插件文件过多 ({file_count} 个)，最大值限制为 500 个")
                if total_size > 50 * 1024 * 1024:
                    raise ValueError(f"插件总大小 ({total_size / 1024 / 1024:.1f} MB) 超过限制 (50 MB)")

                target_dir = resolve_under(plugins_dir, plugins_dir / plugin_id)
                if target_dir.exists():
                    if target_dir.is_symlink():
                        raise ValueError(f"插件目标目录不安全: {target_dir}")
                    if on_overwrite is None:
                        raise ValueError(f'插件 "{plugin_name}" 已存在，且未提供覆盖确认回调')
                    if not on_overwrite(plugin_name):
                        return None

                os.makedirs(staging_dir, exist_ok=True)
                seen_paths: set[str] = set()
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    filename = member.filename
                    if has_root:
                        rel_path = filename
                    else:
                        normalized_member = _safe_relative_plugin_path(filename)
                        if normalized_member is None:
                            raise ValueError(f"检测到路径穿越攻击，安装已终止: {filename}")
                        if not archive_root or not normalized_member.startswith(f"{archive_root}/"):
                            raise ValueError(f"plugin archive contains files outside its root folder: {filename}")
                        rel_path = normalized_member.split("/", 1)[1]
                    if not rel_path:
                        continue
                    safe_rel_path = _safe_relative_plugin_path(rel_path)
                    if safe_rel_path is None:
                        raise ValueError(f"检测到路径穿越攻击，安装已终止: {filename}")
                    lower_rel_path = safe_rel_path.lower()
                    if lower_rel_path in seen_paths:
                        raise ValueError(f"插件压缩包包含重复路径，安装已终止: {filename}")
                    seen_paths.add(lower_rel_path)
                    try:
                        dst = resolve_under(staging_dir, staging_dir / safe_rel_path)
                    except UnsafePathError:
                        raise ValueError(f"检测到路径穿越攻击，安装已终止: {filename}") from None
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dst, "wb") as fd:
                        shutil.copyfileobj(src, fd)

                if not (staging_dir / "plugin.json").is_file():
                    raise ValueError("解压后的插件包缺少 plugin.json 文件")

                if target_dir.exists():
                    backup_base = resolve_under(plugins_dir, plugins_dir / ".backup")
                    backup_dir = resolve_under(backup_base, backup_base / plugin_id)
                    if backup_dir.exists():
                        safe_rmtree_child(backup_base, backup_dir)
                    backup_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(target_dir, backup_dir)

                if target_dir.exists():
                    safe_rmtree_child(plugins_dir, target_dir)
                shutil.move(str(staging_dir), str(target_dir))
                staging_dir = None

            if backup_dir and backup_dir.exists():
                safe_rmtree_child(backup_dir.parent, backup_dir)
                backup_dir = None

            return plugin_id

        except Exception:
            _exc_info = sys.exc_info()
            if backup_dir and backup_dir.exists() and plugin_id:
                try:
                    tgt = resolve_under(plugins_dir, plugins_dir / plugin_id)
                    if tgt.exists():
                        safe_rmtree_child(plugins_dir, tgt)
                    shutil.copytree(backup_dir, tgt)
                    safe_rmtree_child(backup_dir.parent, backup_dir)
                except Exception as rollback_err:
                    logger.error("回滚插件安装失败: %s", rollback_err)
            raise _exc_info[1].with_traceback(_exc_info[2]) from _exc_info[1]
        finally:
            if staging_dir and staging_dir.exists():
                try:
                    safe_rmtree_child(staging_base, staging_dir)
                except Exception:
                    logger.debug("failed to remove plugin staging dir: %s", staging_dir, exc_info=True)
            if staging_base.exists():
                try:
                    if not any(staging_base.iterdir()):
                        staging_base.rmdir()
                except OSError:
                    logger.debug("删除插件暂存目录失败", exc_info=True)

    # ---- queries ----

    def get_plugin(self, plugin_id: str) -> PluginInfo | None:
        return self._plugins.get(plugin_id)

    def list_plugins(self) -> list[PluginInfo]:
        return list(self._plugins.values())

    def list_enabled(self) -> list[PluginInfo]:
        return [p for p in self._plugins.values() if p.status == "enabled"]

    def remove_plugin_record(self, plugin_id: str) -> None:
        """Remove a plugin from internal tracking (e.g. after deleting its directory)."""
        self._plugins.pop(plugin_id, None)
        self._loaded_modules.pop(plugin_id, None)
        self._active_apis.pop(plugin_id, None)

    def delete_plugin_files(self, plugin_id: str) -> None:
        """Delete a managed plugin directory after validating its boundary."""
        info = self._plugins.get(plugin_id)
        if info is None:
            raise ValueError(f"plugin not found: {plugin_id}")
        plugins_dir = Path(self._plugins_dir).resolve(strict=False)
        target = resolve_under(plugins_dir, info.directory)
        if target.name != plugin_id:
            raise UnsafePathError(f"plugin directory name mismatch: {target.name} != {plugin_id}")
        if target.is_symlink():
            raise UnsafePathError(f"refusing to delete symlinked plugin directory: {target}")
        if info.status == "enabled":
            self.disable_plugin(plugin_id)
        safe_rmtree_child(plugins_dir, target)
        self.remove_plugin_record(plugin_id)

    @property
    def plugins_dir(self) -> str:
        return self._plugins_dir
