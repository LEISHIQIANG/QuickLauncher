"""Plugin system v1 — local plugin scanning, loading, and lifecycle management."""

from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .command_registry import (
    COMMAND_INTERACTION_PANEL,
    CommandContext,
    CommandDefinition,
    CommandRegistry,
    CommandResult,
    _search_sources,
    limit_command_result_actions,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ── Data models ───────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

PERMISSIONS_KNOWN = frozenset({
    "clipboard.read",
    "clipboard.write",
    "file.read",
    "file.write",
    "open.url",
    "open.file",
    "process.run",
    "network.request",
    "admin.required",
})

HIGH_RISK_PERMISSIONS = frozenset({
    "process.run",
    "file.write",
    "admin.required",
})


PLUGIN_TRUST_LEVELS = ("builtin", "local-trusted", "community-unverified")
PLUGIN_PACKAGE_EXTENSION = ".qlzip"


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
    def from_dict(cls, data: dict) -> "PluginManifest":
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
    status: str = "loaded"  # loaded | enabled | disabled | error
    error: str = ""
    registered_commands: list[str] = field(default_factory=list)
    registered_search_sources: list[str] = field(default_factory=list)
    enabled_at: float = 0.0
    last_error_at: float = 0.0
    last_run_at: float = 0.0


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
    ):
        self._plugin_id = plugin_id
        self._plugin_dir = Path(plugin_dir)
        self._permissions = set(permissions)
        self._registry = registry
        self._manifest = manifest
        self._registered_ids: list[str] = []
        self._staged_commands: list[CommandDefinition] = []
        self._staged_search_sources: list[str] = []
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
        p = Path(path).resolve()
        data = self.data_dir.resolve()
        if p != data and data not in p.parents:
            raise PermissionError(f"路径 {p} 不在插件数据目录 {data} 内")
        return p

    def register_search_source(
        self,
        id: str,
        handler: Callable[[str], list[dict]] | None = None,
    ) -> None:
        self.logger.info("search source staged: %s", id)
        # Defer write to _search_sources until commit_staged is called.
        # This ensures rollback can clean up completely if registration fails.
        self._staged_search_sources.append(id)

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
        cmd = CommandDefinition(
            id=id,
            title=title,
            aliases=aliases or [],
            description=description,
            category=category,
            handler=self._wrap_handler(handler),
            icon_path=resolved_icon,
            source=f"plugin:{self._plugin_id}",
            interaction_mode=interaction_mode,
            search_terms=plugin_terms + list(search_terms or []),
        )
        self._staged_commands.append(cmd)
        return True

    def commit_staged(self) -> bool:
        """Atomically register all staged commands and search sources. Rollback on any failure."""
        if self._committed:
            return True
        # Write staged search sources to global dict
        written_sources: list[str] = []
        for sid in self._staged_search_sources:
            _search_sources[sid] = {
                "handler": None,
                "plugin_id": self._plugin_id,
            }
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
                    _search_sources.pop(sid, None)
                available_ids = [c.id for c in self._staged_commands]
                logger.error(
                    "插件 %s 命令注册失败，已回滚 %d 个已注册命令和 %d 个搜索源。"
                    "失败命令: %s, 所有尝试: %s",
                    self._plugin_id, len(committed_ids), len(written_sources),
                    cmd.id, available_ids,
                )
                self._staged_commands.clear()
                self._staged_search_sources.clear()
                self._registered_ids.clear()
                return False
        self._registered_ids = committed_ids[:]
        self._staged_commands.clear()
        self._staged_search_sources.clear()
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
            terms.extend([
                manifest.name,
                manifest.description,
                manifest.author,
                *list(manifest.keywords or []),
            ])
        return [t for t in terms if t]

    def _wrap_handler(
        self,
        handler: Callable[[CommandContext], CommandResult],
    ) -> Callable[[CommandContext], CommandResult]:
        def _validate(result: Any) -> CommandResult:
            if result is None:
                return CommandResult(success=False, message="插件未返回结果", error="返回值无效")
            if isinstance(result, dict):
                valid_keys = {"success", "message", "display_type", "payload",
                              "actions", "error", "is_async", "progress", "cancellable"}
                extra = set(result.keys()) - valid_keys
                if extra:
                    return CommandResult(
                        success=False,
                        message="插件返回数据无效",
                        error=f"未知字段: {', '.join(sorted(extra))}",
                    )
                return limit_command_result_actions(CommandResult(**result))
            if not isinstance(result, CommandResult):
                return CommandResult(success=False, message="插件返回类型错误", error="类型错误")
            return limit_command_result_actions(result)

        def _safe(context: CommandContext) -> CommandResult:
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(handler, context)
                    result = future.result()
                return _validate(result)
            except Exception as e:
                self.logger.error("插件命令 %s 执行异常: %s", handler.__name__ if hasattr(handler, "__name__") else "?", e)
                return CommandResult(success=False, message=f"插件执行失败: {e}", error=str(e))
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
        except Exception:
            pass

    def get_selected_files(self) -> list[str]:
        self._check_permission("file.read")
        try:
            from ui.launcher_popup.file_selection import get_selected_files_for_process
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
        return f"plugin.entry 鍖呭惈涓嶅畨鍏ㄨ矾寰? {m.entry}"
    if m.icon and _safe_relative_plugin_path(m.icon) is None:
        return f"plugin.icon 鍖呭惈涓嶅畨鍏ㄨ矾寰? {m.icon}"
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
    def __init__(self, registry: CommandRegistry, plugins_dir: str = "",
                 save_callback: Callable[[list[str]], None] | None = None):
        self._registry = registry
        self._plugins_dir = plugins_dir or self._default_plugins_dir()
        self._plugins: dict[str, PluginInfo] = {}
        self._loaded_modules: dict[str, object] = {}
        self._active_apis: dict[str, PluginAPI] = {}
        self._save_callback = save_callback
        self._confirm_high_risk_callback: Callable[[PluginInfo], bool] | None = None

    def set_save_callback(self, callback: Callable[[list[str]], None] | None) -> None:
        self._save_callback = callback

    def set_confirm_high_risk_callback(self, callback: Callable[[PluginInfo], bool] | None) -> None:
        self._confirm_high_risk_callback = callback

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
        for plugin_id in [p.manifest.id for p in self._plugins.values() if p.status == "enabled"]:
            self.disable_plugin(plugin_id, persist=False)
        self._plugins.clear()
        base = Path(self._plugins_dir)
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
            with open(manifest_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            m = PluginManifest.from_dict(raw)
            err = validate_manifest(m)
            if err:
                return PluginInfo(
                    manifest=m, directory=directory,
                    status="error", error=err,
                )
            plugin_root = Path(directory).resolve()
            safe_entry = _safe_relative_plugin_path(m.entry)
            if safe_entry is None:
                return PluginInfo(
                    manifest=m,
                    directory=directory,
                    status="error",
                    error=f"plugin.entry 鍖呭惈涓嶅畨鍏ㄨ矾寰? {m.entry}",
                )
            entry_path = (plugin_root / safe_entry).resolve()
            if entry_path != plugin_root and plugin_root not in entry_path.parents:
                return PluginInfo(
                    manifest=m,
                    directory=directory,
                    status="error",
                    error=f"plugin.entry 鍖呭惈涓嶅畨鍏ㄨ矾寰? {m.entry}",
                )
            if not entry_path.is_file():
                return PluginInfo(
                    manifest=m,
                    directory=directory,
                    status="error",
                    error=f"插件入口文件不存在: {entry_path}",
                )
            return PluginInfo(manifest=m, directory=directory, status="loaded")
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
            logger.error("插件加载失败 %s: %s", plugin_id, e)
            return False

    def _do_load(self, info: PluginInfo) -> None:
        m = info.manifest
        safe_entry = _safe_relative_plugin_path(m.entry)
        if safe_entry is None:
            raise ValueError(f"plugin.entry unsafe path: {m.entry}")
        plugin_root = Path(info.directory).resolve()
        entry_path = (plugin_root / safe_entry).resolve()
        if entry_path != plugin_root and plugin_root not in entry_path.parents:
            raise ValueError(f"plugin.entry unsafe path: {m.entry}")
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
            spec.loader.exec_module(loader)

        if not hasattr(loader, "register"):
            raise AttributeError(f"插件 {m.id} 缺少 register(api) 函数")

        api = PluginAPI(
            plugin_id=m.id,
            plugin_dir=info.directory,
            permissions=m.permissions,
            registry=self._registry,
            manifest=m,
        )
        loader.register(api)
        # Transactional commit — rollback on any registration failure.
        # Save pending info BEFORE commit because commit clears staging lists.
        pending_search_sources = list(api._staged_search_sources)
        if not api.commit_staged():
            raise RuntimeError(
                f"插件 {m.id} 命令注册事务失败，已回滚所有已注册命令和搜索源"
            )
        info.registered_commands = list(api._registered_ids)
        info.registered_search_sources = pending_search_sources
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
                confirmed = self._confirm_high_risk_callback(info.manifest.name)  # type: ignore[misc]
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
        # Clean up search sources
        for sid in info.registered_search_sources:
            _search_sources.pop(sid, None)
        info.registered_search_sources.clear()
        info.status = "disabled"
        if persist:
            self._save_enabled()
        return True

    def reload_plugin(self, plugin_id: str) -> bool:
        info = self._plugins.get(plugin_id)
        if info is None:
            return False
        # Snapshot old state for rollback on failure
        old_info = PluginInfo(
            manifest=info.manifest,
            directory=info.directory,
            status=info.status,
            error=info.error,
            registered_commands=list(info.registered_commands),
            registered_search_sources=list(info.registered_search_sources),
            enabled_at=info.enabled_at,
            last_error_at=info.last_error_at,
            last_run_at=info.last_run_at,
        )
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
            # Rollback: restore old state so the plugin remains available
            self._plugins[plugin_id] = old_info
            self._save_enabled()
            logger.info("重载插件 %s 失败，已回滚到先前状态", plugin_id)
        return ok

    # ---- persistence ----

    def auto_enable(self, enabled_ids: list[str]) -> int:
        """Auto-enable plugins from a saved list (e.g. from AppSettings)."""
        count = 0
        failed: list[str] = []
        for pid in enabled_ids:
            info = self._plugins.get(pid)
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

        plugins_dir = Path(self._plugins_dir).resolve()
        staging_base = plugins_dir / ".staging"
        staging_base.mkdir(parents=True, exist_ok=True)

        staging_dir = staging_base / f"install-{uuid.uuid4().hex[:12]}"
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
                    raise ValueError(f"解析 plugin.json 失败:\n{e}")

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
                        file_count += 1
                        total_size += member.file_size
                if file_count == 0:
                    raise ValueError("压缩包为空，没有可安装的文件")
                if file_count > 500:
                    raise ValueError(f"插件文件过多 ({file_count} 个)，最大值限制为 500 个")
                if total_size > 50 * 1024 * 1024:
                    raise ValueError(
                        f"插件总大小 ({total_size / 1024 / 1024:.1f} MB) 超过限制 (50 MB)"
                    )

                target_dir = (plugins_dir / plugin_id).resolve()
                if target_dir.exists():
                    if on_overwrite is None:
                        raise ValueError(
                            f"插件 \"{plugin_name}\" 已存在，且未提供覆盖确认回调"
                        )
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
                    dst = (staging_dir / safe_rel_path).resolve()
                    if not dst.is_relative_to(staging_dir):
                        raise ValueError(f"检测到路径穿越攻击，安装已终止: {filename}")
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dst, "wb") as fd:
                        shutil.copyfileobj(src, fd)

                if not (staging_dir / "plugin.json").is_file():
                    raise ValueError("解压后的插件包缺少 plugin.json 文件")

                if target_dir.exists():
                    backup_dir = plugins_dir / ".backup" / plugin_id
                    if backup_dir.exists():
                        shutil.rmtree(backup_dir)
                    backup_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(target_dir, backup_dir)

                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.move(str(staging_dir), str(target_dir))
                staging_dir = None

            if backup_dir and backup_dir.exists():
                shutil.rmtree(backup_dir)
                backup_dir = None

            return plugin_id

        except Exception:
            _exc_info = sys.exc_info()
            if backup_dir and backup_dir.exists() and plugin_id:
                try:
                    tgt = (plugins_dir / plugin_id).resolve()
                    if tgt.exists():
                        shutil.rmtree(tgt)
                    shutil.copytree(backup_dir, tgt)
                    shutil.rmtree(backup_dir)
                except Exception as rollback_err:
                    logger.error("回滚插件安装失败: %s", rollback_err)
            raise _exc_info[1].with_traceback(_exc_info[2])
        finally:
            if staging_dir and staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            if staging_base.exists():
                try:
                    if not any(staging_base.iterdir()):
                        staging_base.rmdir()
                except OSError:
                    pass

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

    @property
    def plugins_dir(self) -> str:
        return self._plugins_dir
