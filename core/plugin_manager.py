"""Plugin system v1 — local plugin scanning, loading, and lifecycle management."""

from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
import logging
import os
import sys
import threading
import time
import traceback
import types
import zipfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from runtime_paths import app_root

from .command_registry import (
    CommandRegistry,
    remove_search_source,
)
from .path_security import UnsafePathError, resolve_under, safe_rmtree_child
from .plugin.constants import (
    HIGH_RISK_PERMISSIONS,
    OFFICIAL_PLUGIN_PACKAGE_SHA256,
    PERMISSIONS_KNOWN,
    PLUGIN_BLOCKED_IMPORT_ROOTS,
    PLUGIN_ERROR_LOG_BACKUPS,
    PLUGIN_ERROR_LOG_MAX_BYTES,
    PLUGIN_FAILURE_THRESHOLD,
    PLUGIN_FAILURE_WINDOW_SECONDS,
    PLUGIN_OS_BLOCKED_ATTRS,
    PLUGIN_PACKAGE_EXTENSION,
    PLUGIN_STATE_SCHEMA,
)
from .plugin.host_api import PluginAPI
from .plugin.installer import install_zip_archive
from .plugin.models import PluginInfo, PluginManifest
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
# PluginAPI lives in core.plugin.host_api; imported above for compatibility.
# ---------------------------------------------------------------------------


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
        plugins_dir = Path(app_root()) / ".plugins"
        expected = plugins_dir / f"{plugin_id}{PLUGIN_PACKAGE_EXTENSION}"
        if package != expected.resolve(strict=False):
            return False
        expected_hash = OFFICIAL_PLUGIN_PACKAGE_SHA256.get(plugin_id)
        if not expected_hash or not package.is_file():
            return False
        digest = hashlib.sha256()
        with package.open("rb") as package_file:
            for chunk in iter(lambda: package_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == expected_hash
    except (OSError, ValueError, TypeError):
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
        from core.plugin.isolated_runtime import IsolatedPluginRuntime

        self._isolated_runtime = IsolatedPluginRuntime()
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
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.debug("load plugin state failed: %s", exc)
            return {"schema": PLUGIN_STATE_SCHEMA, "plugins": {}}

    def _save_plugin_state(self) -> None:
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(self._plugin_state, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, ValueError, TypeError) as exc:
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
        except (ImportError, AttributeError, RuntimeError) as exc:
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
        except (ImportError, AttributeError, OSError) as exc:
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
        except (OSError, ValueError) as exc:
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
        except OSError as exc:
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
        return str(app_root() / "plugins")

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
        except (ImportError, OSError, AttributeError, ValueError, RuntimeError) as e:
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

        api = PluginAPI(
            plugin_id=m.id,
            plugin_dir=info.directory,
            permissions=m.permissions,
            registry=self._registry,
            manifest=m,
            failure_callback=self._record_plugin_failure,
            active_executors=self._plugin_active_executors,
        )
        if m.trust_level != "builtin":
            self._isolated_runtime.load(info, api)
            self._active_apis[m.id] = api
            return

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
                confirmed = self._confirm_high_risk_callback(info.manifest.name)  # type: ignore[arg-type]
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

        try:
            from .command_registry import cancel_search_tasks_for_plugin

            cancel_search_tasks_for_plugin(plugin_id)
        except (ImportError, AttributeError, RuntimeError) as exc:
            logger.debug("取消插件搜索任务失败 %s: %s", plugin_id, exc, exc_info=True)

        self._isolated_runtime.unload(plugin_id)
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
                    except (OSError, AttributeError, RuntimeError) as e:
                        logger.warning("执行插件 %s 的清理钩子 %s 失败: %s", plugin_id, hook_name, e)
        if api is not None:
            api.close()
        _drain_plugin_executors(self._plugin_active_executors, plugin_id)

        # Remove registered commands via owner index for consistency
        owner_id = f"plugin:{plugin_id}"
        registered_command_ids = list(info.registered_commands)
        self._registry.remove_by_owner(owner_id)
        for command_id in registered_command_ids:
            self._registry.remove(command_id)
        info.registered_commands.clear()
        for module_id, manifest_path in dict(getattr(info, "registered_modules", {}) or {}).items():
            try:
                from core.module_registry import get_module_registry

                get_module_registry().unregister_external_manifest(module_id, manifest_path)
            except (ImportError, AttributeError):
                logger.debug("插件模块反注册失败: %s", module_id, exc_info=True)
        info.registered_modules.clear()
        try:
            from core.chain_processors import unregister_external_processors

            unregister_external_processors(plugin_id)
        except (ImportError, AttributeError):
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

    def shutdown(self) -> None:
        """Disable all active plugins and release their owned workers."""
        for plugin_id in list(self._active_apis):
            try:
                self.disable_plugin(plugin_id, persist=False)
            except (OSError, RuntimeError, AttributeError):
                logger.debug("关闭插件失败: %s", plugin_id, exc_info=True)
        self._isolated_runtime.close()

    def worker_snapshot(self) -> dict[str, dict[str, Any]]:
        """Return process-isolated plugin worker state for diagnostics."""
        return self._isolated_runtime.snapshot()

    # ---- installation ----

    def install_from_package(
        self,
        package_path: str,
        *,
        on_overwrite: Callable[[str], bool] | None = None,
        before_overwrite: Callable[[str], None] | None = None,
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

            def _finalize_trust(installed_id: str, target_dir: Path) -> None:
                self._apply_install_source_trust(
                    installed_id,
                    target_dir,
                    builtin=_is_builtin_plugin_package(package_path, installed_id),
                )

            plugin_id = install_zip_archive(
                package_path,
                self._plugins_dir,
                manifest_from_dict=PluginManifest.from_dict,
                validate_manifest=validate_manifest,  # type: ignore[arg-type]
                on_overwrite=on_overwrite,
                before_overwrite=before_overwrite,
                post_install=_finalize_trust,
            )
            return plugin_id
        except zipfile.BadZipFile as e:
            raise ValueError(f"无效的 {PLUGIN_PACKAGE_EXTENSION} 插件包:\n{e}") from e

    def _apply_install_source_trust(self, plugin_id: str, target_dir: Path, *, builtin: bool) -> None:
        manifest_path = target_dir / "plugin.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("插件信任元数据格式无效")
        if builtin:
            data["trust_level"] = "builtin"
            data["install_source"] = "builtin"
        else:
            data["trust_level"] = "community-unverified"
            data["install_source"] = "third_party"
        temp_path = manifest_path.with_suffix(".json.tmp")
        try:
            temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp_path, manifest_path)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logger.debug("清理插件信任元数据临时文件失败: %s", temp_path, exc_info=True)

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
        if source != "builtin":
            logger.warning(
                "插件 %s 声明 trust_level=builtin 但 install_source=%s，降级为 community-unverified",
                m.id,
                source or "<missing>",
            )
            info.manifest.trust_level = "community-unverified"

    def install_from_zip(
        self,
        zip_path: str,
        *,
        on_overwrite: Callable[[str], bool] | None = None,
        before_overwrite: Callable[[str], None] | None = None,
    ) -> str | None:
        """Compatibility wrapper for plugin package installation."""
        return self.install_from_package(
            zip_path,
            on_overwrite=on_overwrite,
            before_overwrite=before_overwrite,
        )

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
