"""Restricted module loader extracted from plugin_manager.py."""

from __future__ import annotations

import builtins
import types
from typing import Any

from core.plugin.constants import PLUGIN_BLOCKED_IMPORT_ROOTS, PLUGIN_OS_BLOCKED_ATTRS


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
