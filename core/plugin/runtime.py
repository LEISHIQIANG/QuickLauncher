"""Plugin module loading runtime, separate from lifecycle orchestration."""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.path_security import resolve_under

from .models import PluginInfo
from .paths import safe_relative_plugin_path


@dataclass(frozen=True)
class RuntimeLoadResult:
    module: Any
    api: Any
    registered_commands: tuple[str, ...]
    registered_search_sources: tuple[str, ...]
    registered_modules: dict[str, str]
    registered_chain_processors: tuple[str, ...]


class PluginRuntime:
    def __init__(
        self,
        *,
        api_factory: Callable[[PluginInfo], Any],
        builtins_factory: Callable[..., dict[str, Any]],
    ) -> None:
        self.api_factory = api_factory
        self.builtins_factory = builtins_factory

    def load(self, info: PluginInfo) -> RuntimeLoadResult:
        manifest = info.manifest
        safe_entry = safe_relative_plugin_path(manifest.entry)
        if safe_entry is None:
            raise ValueError(f"plugin.entry unsafe path: {manifest.entry}")
        plugin_root = Path(info.directory).resolve(strict=False)
        entry_path = resolve_under(plugin_root, plugin_root / safe_entry)
        if not os.path.isfile(entry_path):
            raise FileNotFoundError(f"插件入口文件不存在: {entry_path}")

        module_name = f"_plugin_{manifest.id}"
        module = sys.modules.get(module_name)
        if module is None:
            spec = importlib.util.spec_from_file_location(module_name, entry_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载插件模块: {entry_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                module.__dict__["__builtins__"] = self.builtins_factory(
                    manifest.id,
                    manifest.permissions,
                    restricted=manifest.trust_level != "builtin",
                )
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(module_name, None)
                raise
        register = getattr(module, "register", None)
        if not callable(register):
            raise AttributeError(f"插件 {manifest.id} 缺少 register(api) 函数")

        api = self.api_factory(info)
        register(api)
        pending_search_sources = tuple(api._staged_search_sources)
        if not api.commit_staged():
            raise RuntimeError(f"插件 {manifest.id} 命令注册事务失败，已回滚所有已注册命令和搜索源")
        return RuntimeLoadResult(
            module=module,
            api=api,
            registered_commands=tuple(api._registered_ids),
            registered_search_sources=pending_search_sources,
            registered_modules=dict(getattr(api, "_registered_modules", {}) or {}),
            registered_chain_processors=tuple(getattr(api, "_registered_chain_processors", []) or []),
        )

    @staticmethod
    def unload_modules(plugin_id: str) -> None:
        module_name = f"_plugin_{plugin_id}"
        prefix = f"{module_name}."
        for key in [name for name in sys.modules if name == module_name or name.startswith(prefix)]:
            sys.modules.pop(key, None)
