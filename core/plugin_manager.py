"""Plugin system v1 — local plugin scanning, loading, and lifecycle management."""

from __future__ import annotations

import builtins
import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import types
import webbrowser
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .background_tasks import start_background_thread
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
from .network_security import ResponseTooLargeError, safe_urlopen, sanitize_headers, validate_public_http_url
from .path_security import UnsafePathError, resolve_under, safe_rmtree_child
from .plugin.constants import (
    HIGH_RISK_PERMISSIONS,
    PERMISSIONS_KNOWN,
    PLUGIN_API_HTTP_METHODS,
    PLUGIN_API_HTTP_TIMEOUT_SECONDS,
    PLUGIN_API_MAX_HTTP_HEADER_CHARS,
    PLUGIN_API_MAX_HTTP_HEADERS,
    PLUGIN_API_MAX_HTTP_REQUEST_BYTES,
    PLUGIN_API_MAX_HTTP_RESPONSE_BYTES,
    PLUGIN_API_MAX_TEXT_FILE_BYTES,
    PLUGIN_BLOCKED_IMPORT_ROOTS,
    PLUGIN_COMMAND_SOFT_TIMEOUT_SECONDS,
    PLUGIN_ERROR_LOG_BACKUPS,
    PLUGIN_ERROR_LOG_MAX_BYTES,
    PLUGIN_FAILURE_THRESHOLD,
    PLUGIN_FAILURE_WINDOW_SECONDS,
    PLUGIN_OS_BLOCKED_ATTRS,
    PLUGIN_PACKAGE_EXTENSION,
    PLUGIN_STATE_SCHEMA,
    PLUGIN_TRUST_LEVELS,
)
from .plugin.installer import install_zip_archive
from .plugin.paths import is_plugin_package_path
from .plugin.paths import safe_relative_plugin_path as _safe_relative_plugin_path

logger = logging.getLogger(__name__)
_PLUGIN_EXECUTOR_REGISTRY_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# ── Plugin executor tracking ──────────────────────────────────────────────
# ---------------------------------------------------------------------------


def _track_executor(
    registry: dict[str, list[threading.Thread]],
    plugin_id: str,
    executor: threading.Thread,
) -> None:
    """Register a plugin command worker thread."""
    with _PLUGIN_EXECUTOR_REGISTRY_LOCK:
        executors = registry.setdefault(plugin_id, [])
        executors.append(executor)


def _untrack_executor(
    registry: dict[str, list[threading.Thread]],
    plugin_id: str,
    executor: threading.Thread,
) -> None:
    """Remove a finished command worker from the tracking registry."""
    with _PLUGIN_EXECUTOR_REGISTRY_LOCK:
        executors = registry.get(plugin_id)
        if executors is not None:
            try:
                executors.remove(executor)
            except ValueError as exc:
                logger.debug("plugin executor already untracked: %s", exc, exc_info=True)
            if not executors:
                registry.pop(plugin_id, None)


def _drain_plugin_executors(
    registry: dict[str, list[threading.Thread]],
    plugin_id: str,
    timeout: float = 5.0,
) -> None:
    """Wait briefly for tracked plugin command workers during quarantine."""
    with _PLUGIN_EXECUTOR_REGISTRY_LOCK:
        workers = registry.pop(plugin_id, [])
    if not workers:
        return
    deadline = time.monotonic() + max(0.0, float(timeout or 0.0))
    for worker in workers:
        remaining = max(0.0, deadline - time.monotonic())
        if remaining <= 0:
            break
        worker.join(timeout=remaining)
    still_alive = [worker for worker in workers if worker.is_alive()]
    if still_alive:
        logger.warning("插件 %s 隔离时仍有 %d 个命令工作线程在运行", plugin_id, len(still_alive))


# ---------------------------------------------------------------------------
# ── Data models ───────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class _RestrictedPluginModule(types.ModuleType):
    def __init__(self, original: types.ModuleType, blocked_attrs: frozenset[str], plugin_id: str):
        super().__init__(original.__name__)
        self._original = original
        self._blocked_attrs = blocked_attrs
        self._plugin_id = plugin_id

    def __getattr__(self, name: str):
        if name in self._blocked_attrs:
            raise PermissionError(f"插件 {self._plugin_id} 不能直接调用 os.{name}; 请使用 PluginAPI")
        return getattr(self._original, name)


def _make_plugin_builtins(plugin_id: str, permissions: list[str], *, restricted: bool) -> dict[str, Any]:
    if not restricted:
        return vars(builtins)

    allowed = set(permissions or [])
    safe_builtins = dict(vars(builtins))
    original_import = builtins.__import__
    original_open = builtins.open

    def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = str(name or "").split(".", 1)[0]
        if level == 0 and root in PLUGIN_BLOCKED_IMPORT_ROOTS:
            raise PermissionError(f"插件 {plugin_id} 不能直接导入 {root}; 请使用 PluginAPI")
        module = original_import(name, globals, locals, fromlist, level)
        if level == 0 and root == "os":
            return _RestrictedPluginModule(module, PLUGIN_OS_BLOCKED_ATTRS, plugin_id)
        return module

    def restricted_open(file, mode="r", *args, **kwargs):
        normalized_mode = str(mode or "r")
        writes = any(flag in normalized_mode for flag in ("w", "a", "x", "+"))
        if writes and "file.write" not in allowed:
            raise PermissionError(f"插件 {plugin_id} 缺少权限: file.write")
        if not writes and "file.read" not in allowed:
            raise PermissionError(f"插件 {plugin_id} 缺少权限: file.read")
        return original_open(file, mode, *args, **kwargs)

    safe_builtins["__import__"] = restricted_import
    safe_builtins["open"] = restricted_open
    safe_builtins["eval"] = None
    safe_builtins["exec"] = None
    return safe_builtins


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
    trust_level: str = "community-unverified"
    install_source: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> PluginManifest:
        trust = data.get("trust_level", "").lower().replace(" ", "-")
        if trust not in PLUGIN_TRUST_LEVELS:
            trust = "community-unverified"
        install_source = str(data.get("install_source", "") or "").strip()
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
            install_source=install_source,
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
# ── Plugin lifecycle state machine ─────────────────────────────────────
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "loaded": frozenset({"enabled", "error", "disabled"}),
    "enabled": frozenset({"disabled", "error", "quarantined"}),
    "disabled": frozenset({"enabled", "error", "quarantined"}),
    "error": frozenset({"enabled", "disabled", "quarantined"}),
    "quarantined": frozenset({"disabled"}),
}


def _validate_state_transition(info: PluginInfo, target_status: str) -> bool:
    """Check whether *target_status* is reachable from the current status.

    Returns ``True`` if the transition is valid.  Logs a warning and returns
    ``False`` otherwise.  The ``quarantined`` target is always allowed from
    any state except itself to ensure quarantine is never silently blocked.
    """
    if target_status == "quarantined" and info.status == "quarantined":
        return False
    if target_status == "quarantined":
        return True
    allowed = _VALID_TRANSITIONS.get(info.status, frozenset())
    if target_status not in allowed:
        logger.warning(
            "Invalid plugin state transition: %s -> %s (plugin=%s)",
            info.status,
            target_status,
            info.manifest.id,
        )
        return False
    return True


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
        active_executors: dict[str, list[threading.Thread]] | None = None,
    ):
        self._plugin_id = plugin_id
        self._plugin_dir = Path(plugin_dir)
        self._permissions = set(permissions)
        self._registry = registry
        self._manifest = manifest
        self._failure_callback = failure_callback
        self._plugin_active_executors = active_executors if active_executors is not None else {}
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

            ok = register_external_processor(definition, handler, owner=self._plugin_id, permissions=frozenset(self._permissions))
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
            if not isinstance(result, CommandResult):
                return CommandResult(success=False, message="插件返回类型错误", error="类型错误")
            result.actions = _normalize_actions(result.actions)
            return limit_command_result_actions(result)

        def _safe(context: CommandContext) -> CommandResult:
            done_event = threading.Event()
            result_holder: dict[str, Any] = {}
            worker: threading.Thread | None = None

            def _run_handler() -> None:
                try:
                    result_holder["result"] = handler(context)
                except Exception as exc:
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
            return cb.text() or ""
        except Exception:
            logger.debug("read_clipboard failed", exc_info=True)
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
        except Exception as exc:
            logger.debug("插件 API 获取选中文件失败: %s", exc, exc_info=True)
            return []

    def get_theme(self) -> str:
        """Return the current host theme without exposing the DataManager object."""
        try:
            from core import get_data_manager

            theme = getattr(get_data_manager().get_settings(), "theme", "dark")
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
            return bool(webbrowser.open(parsed.geturl())), ""
        except Exception as exc:
            return False, str(exc)

    def open_file(self, path: str | Path) -> tuple[bool, str]:
        """Open an existing file through Windows file association."""
        self._check_permission("open.file")
        target = Path(path).expanduser().resolve(strict=False)
        if not target.is_file():
            return False, f"file not found: {target}"
        try:
            os.startfile(str(target))
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def open_folder(self, path: str | Path) -> tuple[bool, str]:
        """Open an existing folder through Windows file association."""
        self._check_permission("open.file")
        target = Path(path).expanduser().resolve(strict=False)
        if not target.is_dir():
            return False, f"folder not found: {target}"
        try:
            os.startfile(str(target))
            return True, ""
        except Exception as exc:
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
                from .network_security import read_limited_response

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

        from .shortcut_executor import ShortcutExecutor

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
                return False, str(exc)
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
        if not show_window and not run_as_admin:
            from .shortcut_executor import ShortcutExecutor

            try:
                ShortcutExecutor._popen_silent(
                    [comspec, "/d", "/s", cmd_flag, command],
                    cwd=cwd or None,
                    env=ShortcutExecutor._sanitized_child_env(),
                    shell=False,
                )
                return True, ""
            except Exception as exc:
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


def _is_builtin_plugin_package(package_path: str, plugin_id: str) -> bool:
    try:
        package = Path(package_path).resolve(strict=False)
        plugins_dir = Path(__file__).resolve(strict=False).parents[1] / ".plugins"
        expected = plugins_dir / f"{plugin_id}{PLUGIN_PACKAGE_EXTENSION}"
        return package == expected.resolve(strict=False)
    except Exception:
        logger.debug("判断官方插件包来源失败: %s", package_path, exc_info=True)
        return False


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
        self._plugin_active_executors: dict[str, list[threading.Thread]] = {}
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
        if not _validate_state_transition(info, "quarantined"):
            logger.debug("插件 %s 状态转换到 quarantined 被拒绝 (当前 %s)", plugin_id, info.status)
            return
        if info.status == "enabled":
            self.disable_plugin(plugin_id, persist=True)
        info = self._plugins.get(plugin_id)
        if info is None:
            return
        try:
            from .command_registry import cancel_search_tasks_for_plugin

            active_searches = cancel_search_tasks_for_plugin(plugin_id)
            if active_searches:
                logger.warning("插件 %s 隔离时仍有 %d 个搜索任务处于活动或排队状态", plugin_id, active_searches)
        except Exception as exc:
            logger.debug("取消插件搜索任务失败 %s: %s", plugin_id, exc, exc_info=True)
        _drain_plugin_executors(self._plugin_active_executors, plugin_id)
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
        if not _validate_state_transition(info, "disabled"):
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
        self._validate_install_source_trust(info)
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
                loader.__dict__["__builtins__"] = _make_plugin_builtins(
                    m.id,
                    m.permissions,
                    restricted=m.trust_level != "builtin",
                )
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
            active_executors=self._plugin_active_executors,
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
        registered_command_ids = list(info.registered_commands)
        self._registry.remove_by_owner(owner_id)
        for command_id in registered_command_ids:
            self._registry.remove(command_id)
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

        # 先尝试重新解析 manifest，如果失败则不触碰当前运行状态
        module_name = f"_plugin_{plugin_id}"
        manifest_path = Path(info.directory) / "plugin.json"
        new_info = self._load_manifest(info.directory, manifest_path)
        if new_info and new_info.status == "error":
            # manifest 解析失败，保留旧插件不动
            self._plugins[plugin_id] = new_info
            self._save_enabled()
            return False

        # 先禁用旧版本（必须在替换 info 之前执行，否则 disable_plugin 看不到旧的 registered_commands）
        if was_enabled or was_error:
            self.disable_plugin(plugin_id)

        # 清理 sys.modules 中该插件的所有模块（包括子模块），确保重新加载时代码是最新的
        prefix = f"{module_name}."
        keys_to_remove = [k for k in sys.modules if k == module_name or k.startswith(prefix)]
        for k in keys_to_remove:
            sys.modules.pop(k, None)

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
        if not is_plugin_package_path(package_path):
            raise ValueError(f"插件安装包必须使用 {PLUGIN_PACKAGE_EXTENSION} 扩展名")

        try:
            plugin_id = install_zip_archive(
                package_path,
                self._plugins_dir,
                manifest_from_dict=PluginManifest.from_dict,
                validate_manifest=validate_manifest,
                on_overwrite=on_overwrite,
            )
            if plugin_id:
                self._apply_install_source_trust(plugin_id, package_path)
            return plugin_id
        except zipfile.BadZipFile as e:
            raise ValueError(f"无效的 {PLUGIN_PACKAGE_EXTENSION} 插件包:\n{e}") from e

    def _apply_install_source_trust(self, plugin_id: str, package_path: str) -> None:
        manifest_path = Path(self._plugins_dir) / plugin_id / "plugin.json"
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            if _is_builtin_plugin_package(package_path, plugin_id):
                data["trust_level"] = "builtin"
                data["install_source"] = "builtin"
            else:
                data["trust_level"] = "community-unverified"
                data["install_source"] = "third_party"
            manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("写入插件安装来源信任元数据失败 %s: %s", plugin_id, exc, exc_info=True)

    def _validate_install_source_trust(self, info: PluginInfo) -> None:
        """Validate trust_level consistency with install_source at load time.

        If a plugin claims ``builtin`` trust but was not installed from an
        official source, demote it to ``community-unverified`` and log a
        warning.
        """
        m = info.manifest
        if m.trust_level != "builtin":
            return
        source = m.install_source
        if source and source != "builtin":
            logger.warning(
                "插件 %s 声明 trust_level=builtin 但 install_source=%s，降级为 community-unverified",
                m.id,
                source,
            )
            info.manifest.trust_level = "community-unverified"

    def install_from_zip(
        self,
        zip_path: str,
        *,
        on_overwrite: Callable[[str], bool] | None = None,
    ) -> str | None:
        """Compatibility wrapper for plugin package installation."""
        return self.install_from_package(zip_path, on_overwrite=on_overwrite)

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
