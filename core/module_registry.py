"""Small module registry for built-in and future plugin modules."""

from __future__ import annotations

import importlib
import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.action_chain_host import DefaultActionChainHostAPI
from core.version import APP_VERSION
from runtime_paths import resource_path

logger = logging.getLogger(__name__)

MODULE_AVAILABLE = "available"
MODULE_DISABLED = "disabled"
MODULE_UNLICENSED = "unlicensed"
MODULE_MISSING = "missing"
MODULE_INCOMPATIBLE = "incompatible"
MODULE_BROKEN = "broken"
MODULE_STATUSES = {
    MODULE_AVAILABLE,
    MODULE_DISABLED,
    MODULE_UNLICENSED,
    MODULE_MISSING,
    MODULE_INCOMPATIBLE,
    MODULE_BROKEN,
}

ACTION_CHAIN_MODULE_ID = "quicklauncher.action_chain"
ACTION_CHAIN_MANIFEST = resource_path("modules", "action_chain", "module.json")


@dataclass
class ModuleRecord:
    module_id: str
    status: str
    manifest: dict[str, Any]
    api: Any = None
    error: str = ""
    manifest_path: str = ""
    provider: str = "builtin"

    def is_available(self) -> bool:
        available = self.status == MODULE_AVAILABLE
        if available and self.api is not None:
            try:
                return bool(self.api.is_available())
            except Exception:
                logger.debug("module availability check failed: %s", self.module_id, exc_info=True)
                return False
        return available


class ModuleRegistry:
    def __init__(self):
        self._records: dict[str, ModuleRecord] = {}
        self._disabled: set[str] = set()
        self._external_manifests: dict[str, Path] = {}
        self._action_chain_editor: Callable[..., Any] | None = None
        self._shortcut_executor: Callable[..., Any] | None = None

    def set_action_chain_editor(self, editor: Callable[..., Any] | None) -> None:
        self._action_chain_editor = editor
        self._records.pop(ACTION_CHAIN_MODULE_ID, None)

    def set_shortcut_executor(self, executor: Callable[..., Any] | None) -> None:
        self._shortcut_executor = executor
        self._records.pop(ACTION_CHAIN_MODULE_ID, None)

    def _host_api(self, data_manager: Any) -> DefaultActionChainHostAPI:
        return DefaultActionChainHostAPI(
            data_manager,
            editor=self._action_chain_editor,
            shortcut_executor=self._shortcut_executor,
        )

    def set_disabled(self, module_id: str, disabled: bool = True) -> None:
        module_id = str(module_id or "")
        if disabled:
            self._disabled.add(module_id)
        else:
            self._disabled.discard(module_id)
        self._records.pop(module_id, None)

    def get(self, module_id: str, *, data_manager: Any = None) -> ModuleRecord:
        module_id = str(module_id or "")
        if module_id == ACTION_CHAIN_MODULE_ID:
            return self.load_action_chain(data_manager=data_manager)
        # 查询已注册的外部 manifest
        if module_id in self._external_manifests:
            cached = self._records.get(module_id)
            if cached is not None:
                return cached
            record = self._load_generic_module(module_id, data_manager=data_manager)
            self._records[module_id] = record
            return record
        return ModuleRecord(module_id, MODULE_MISSING, {}, None, "module_not_registered")

    def _load_generic_module(self, module_id: str, *, data_manager: Any = None) -> ModuleRecord:
        """通用模块加载：从 external_manifests 读取 manifest 并加载模块。"""
        if module_id in self._disabled:
            return ModuleRecord(module_id, MODULE_DISABLED, {}, None, "module_disabled")
        manifest_path = self._external_manifests.get(module_id)
        if manifest_path is None:
            return ModuleRecord(module_id, MODULE_MISSING, {}, None, "no_manifest_registered")
        try:
            if not manifest_path.exists():
                return ModuleRecord(module_id, MODULE_MISSING, {}, None, "manifest_missing", str(manifest_path))
            with manifest_path.open("r", encoding="utf-8") as fh:
                manifest = json.load(fh)
            actual_id = str(manifest.get("id") or "")
            if actual_id != module_id:
                return ModuleRecord(
                    module_id, MODULE_BROKEN, manifest, None, "manifest_id_mismatch", str(manifest_path)
                )
            if not _host_version_compatible(APP_VERSION, manifest):
                return ModuleRecord(
                    module_id, MODULE_INCOMPATIBLE, manifest, None, "host_version_incompatible", str(manifest_path)
                )
            entry = str(manifest.get("entry") or "")
            module_name, class_name = entry.split(":", 1)
            module = _import_module_from_manifest(module_name, manifest_path)
            module_cls = getattr(module, class_name)
            api = module_cls(self._host_api(data_manager), manifest)
            return ModuleRecord(module_id, MODULE_AVAILABLE, manifest, api, "", str(manifest_path), "plugin")
        except Exception as exc:
            logger.exception("failed to load module %s", module_id)
            return ModuleRecord(module_id, MODULE_BROKEN, {}, None, str(exc), str(manifest_path))

    def register_external_manifest(self, module_id: str, manifest_path: str | Path) -> bool:
        """Register a module manifest supplied by a plugin package.

        External manifests are intentionally explicit: the host still loads the
        module through the same API contract, but the manifest can live outside
        the built-in ``modules/`` directory.
        """

        module_id = str(module_id or "").strip()
        path = Path(manifest_path).resolve(strict=False)
        if not module_id or not path.is_file():
            return False
        try:
            with path.open("r", encoding="utf-8") as fh:
                manifest = json.load(fh)
        except Exception:
            return False
        if str(manifest.get("id") or "") != module_id:
            return False
        self._external_manifests[module_id] = path
        self._records.pop(module_id, None)
        return True

    def unregister_external_manifest(self, module_id: str, manifest_path: str | Path | None = None) -> None:
        module_id = str(module_id or "").strip()
        existing = self._external_manifests.get(module_id)
        if existing is None:
            return
        if manifest_path is not None and existing != Path(manifest_path).resolve(strict=False):
            return
        self._external_manifests.pop(module_id, None)
        self._records.pop(module_id, None)

    def load_action_chain(self, *, data_manager: Any = None) -> ModuleRecord:
        cached = self._records.get(ACTION_CHAIN_MODULE_ID)
        if cached is not None and data_manager is None:
            return cached
        record = self._load_action_chain(data_manager=data_manager)
        if data_manager is None:
            self._records[ACTION_CHAIN_MODULE_ID] = record
        return record

    def _load_action_chain(self, *, data_manager: Any = None) -> ModuleRecord:
        if ACTION_CHAIN_MODULE_ID in self._disabled:
            return ModuleRecord(ACTION_CHAIN_MODULE_ID, MODULE_DISABLED, {}, None, "module_disabled")
        manifest_path = self._external_manifests.get(ACTION_CHAIN_MODULE_ID, ACTION_CHAIN_MANIFEST)
        provider = "plugin" if manifest_path != ACTION_CHAIN_MANIFEST else "builtin"
        try:
            if not manifest_path.exists():
                return ModuleRecord(
                    ACTION_CHAIN_MODULE_ID,
                    MODULE_MISSING,
                    {},
                    None,
                    "manifest_missing",
                    str(manifest_path),
                    provider,
                )
            with manifest_path.open("r", encoding="utf-8") as fh:
                manifest = json.load(fh)
            module_id = str(manifest.get("id") or "")
            if module_id != ACTION_CHAIN_MODULE_ID:
                return ModuleRecord(
                    ACTION_CHAIN_MODULE_ID,
                    MODULE_BROKEN,
                    manifest,
                    None,
                    "manifest_id_mismatch",
                    str(manifest_path),
                    provider,
                )
            if not _host_version_compatible(APP_VERSION, manifest):
                return ModuleRecord(
                    module_id,
                    MODULE_INCOMPATIBLE,
                    manifest,
                    None,
                    "host_version_incompatible",
                    str(manifest_path),
                    provider,
                )
            entry = str(manifest.get("entry") or "")
            module_name, class_name = entry.split(":", 1)
            module = _import_module_from_manifest(module_name, manifest_path)
            module_cls = getattr(module, class_name)
            api = module_cls(self._host_api(data_manager), manifest)
            return ModuleRecord(module_id, MODULE_AVAILABLE, manifest, api, "", str(manifest_path), provider)
        except Exception as exc:
            logger.exception("failed to load action-chain module")
            return ModuleRecord(ACTION_CHAIN_MODULE_ID, MODULE_BROKEN, {}, None, str(exc), str(manifest_path), provider)


def _host_version_compatible(host_version: str, manifest: dict[str, Any]) -> bool:
    min_version = str(manifest.get("min_host_version") or "").strip()
    max_version = str(manifest.get("max_host_version") or "").strip()
    if min_version and _version_tuple(host_version) < _version_tuple(min_version):
        return False
    if max_version and _version_tuple(host_version) > _version_tuple(max_version):
        return False
    return True


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for part in str(value or "").split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts or [0])


def _import_module_from_manifest(module_name: str, manifest_path: Path):
    module_dir = str(Path(manifest_path).resolve(strict=False).parent)
    if module_dir in sys.path:
        return importlib.import_module(module_name)
    sys.path.insert(0, module_dir)
    try:
        return importlib.import_module(module_name)
    finally:
        try:
            sys.path.remove(module_dir)
        except ValueError as exc:
            logger.debug("临时模块路径已不存在: %s", exc, exc_info=True)


_module_registry: ModuleRegistry | None = None


def get_module_registry() -> ModuleRegistry:
    global _module_registry
    if _module_registry is None:
        _module_registry = ModuleRegistry()
    return _module_registry
