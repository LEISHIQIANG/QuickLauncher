"""Unified native DLL loader for QuickLauncher acceleration modules.

All native DLLs (qlcrypto, qlsearch, ...) are loaded through this module.
DLLs are hard dependencies: missing or corrupt DLLs raise ``RuntimeError``
(fail-fast) instead of silently degrading to a Python fallback.

The loader mirrors the proven pattern from ``hooks/hooks_wrapper.py``:
ctypes.CDLL load + required-export validation + singleton caching.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from collections.abc import Callable

from runtime_paths import native_dir

logger = logging.getLogger(__name__)


class NativeDLL:
    """Wraps a loaded native DLL with export validation."""

    def __init__(self, name: str, dll: ctypes.CDLL, required_exports: tuple[str, ...]):
        self.name = name
        self.dll = dll
        self.required_exports = required_exports
        self.missing_exports: list[str] = [sym for sym in required_exports if not hasattr(dll, sym)]
        if self.missing_exports:
            raise RuntimeError(f"{name}.dll missing required exports: {', '.join(self.missing_exports)}")

    def __getattr__(self, attr: str):
        return getattr(self.dll, attr)


class _NativeLoader:
    """Singleton registry that lazily loads native DLLs on first access."""

    _instance: _NativeLoader | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._cache: dict[str, NativeDLL] = {}
        self._cache_lock = threading.Lock()

    @classmethod
    def get(cls) -> _NativeLoader:
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def load(
        self,
        name: str,
        required_exports: tuple[str, ...],
        *,
        path_factory: Callable[[], str] | None = None,
    ) -> NativeDLL:
        """Load *name*.dll (e.g. ``"qlcrypto"``) and validate exports.

        Raises ``RuntimeError`` if the DLL cannot be found or is missing
        required symbols.
        """
        if name in self._cache:
            return self._cache[name]

        with self._cache_lock:
            if name in self._cache:
                return self._cache[name]

            dll_path = path_factory() if path_factory else self._find_dll(name)
            try:
                dll = ctypes.CDLL(dll_path)
            except OSError as exc:
                raise RuntimeError(
                    f"无法加载原生加速 DLL: {name}.dll (路径: {dll_path})。" f"请确认程序安装完整。错误: {exc}"
                ) from exc

            wrapper = NativeDLL(name, dll, required_exports)
            self._cache[name] = wrapper
            logger.info("已加载原生 DLL: %s.dll", name)
            return wrapper

    @staticmethod
    def _find_dll(name: str) -> str:
        """Probe candidate paths: <native>/{name}.dll then <native>/{name}/{name}.dll."""
        base = native_dir()
        candidates = [
            base / f"{name}.dll",
            base / name / f"{name}.dll",
        ]
        for p in candidates:
            if p.is_file():
                return str(p)
        return str(candidates[0])


def load_native(name: str, required_exports: tuple[str, ...]) -> NativeDLL:
    """Convenience helper to load a native DLL by name."""
    return _NativeLoader.get().load(name, required_exports)


_QLCRYPTO_EXPORTS = (
    "QLcrypto_hashFile",
    "QLcrypto_version",
    "QLcrypto_lastError",
)

_QLSEARCH_EXPORTS = (
    "QLsearch_version",
    "QLsearch_lastError",
    "QLsearch_init",
    "QLsearch_release",
    "QLsearch_loadAll",
    "QLsearch_search",
    "QLsearch_setHistoryBonuses",
)

_QLWINDOW_EXPORTS = (
    "QLwindow_version",
    "QLwindow_lastError",
    "QLwindow_Activate",
    "QLwindow_GetWindowsForPids",
    "QLwindow_GetProcessWindows",
    "QLwindow_ActivateHwnd",
    "QLwindow_IsMinimized",
)


def QLcrypto() -> NativeDLL:
    """Return the loaded QLcrypto.dll wrapper (singleton)."""
    return load_native("QLCrypto", _QLCRYPTO_EXPORTS)


def QLsearch() -> NativeDLL:
    """Return the loaded QLsearch.dll wrapper (singleton)."""
    return load_native("QLsearch", _QLSEARCH_EXPORTS)


def QLwindow() -> NativeDLL:
    """Return the loaded QLwindow.dll wrapper (singleton)."""
    return load_native("QLwindow", _QLWINDOW_EXPORTS)


_QLVALIDATE_EXPORTS = (
    "QLvalidate_version",
    "QLvalidate_lastError",
    "QLvalidate_IsPublicIpv4",
    "QLvalidate_IsPublicIpv6",
    "QLvalidate_IsPublicIpString",
    "QLvalidate_ResolveHost",
    "QLvalidate_NormalizeUrl",
    "QLvalidate_PublicUrl",
    "QLvalidate_IsLoopbackIpv4",
    "QLvalidate_IsPrivateIpv4",
    "QLvalidate_IsLinkLocalIpv4",
    "QLvalidate_IsMulticastIpv4",
)


def QLvalidate() -> NativeDLL:
    """Return the loaded QLvalidate.dll wrapper (singleton)."""
    return load_native("QLvalidate", _QLVALIDATE_EXPORTS)


_QLWATCH_EXPORTS = (
    "QLwatch_version",
    "QLwatch_lastError",
    "QLwatch_Init",
    "QLwatch_Release",
    "QLwatch_Start",
    "QLwatch_Stop",
    "QLwatch_StopAll",
)


def QLwatch() -> NativeDLL:
    """Return the loaded QLwatch.dll wrapper (singleton)."""
    return load_native("QLwatch", _QLWATCH_EXPORTS)


_QLAUTOSTART_EXPORTS = (
    "QLautostart_version",
    "QLautostart_lastError",
    "QLautostart_Enable",
    "QLautostart_Disable",
    "QLautostart_IsEnabled",
    "QLautostart_GetMethod",
    "QLautostart_GetStatus",
    "QLautostart_RunHelper",
    "QLautostart_RunLauncher",
    "QLautostart_IsAllowedTarget",
    "QLautostart_CleanupLegacyTasks",
)


def QLautostart() -> NativeDLL:
    """Return the loaded QLautostart.dll wrapper (singleton)."""
    return load_native("QLautostart", _QLAUTOSTART_EXPORTS)


_QLUPDATE_EXPORTS = (
    "QLupdate_version",
    "QLupdate_lastError",
    "QLupdate_Check",
    "QLupdate_Download",
    "QLupdate_CancelDownload",
    "QLupdate_Install",
    "QLupdate_GetLatestSession",
    "QLupdate_ConfirmFirstStart",
    "QLupdate_ValidateDownloadUrl",
    "QLupdate_CheckConnectivity",
)


def QLupdate() -> NativeDLL:
    """Return the loaded QLupdate.dll wrapper (singleton)."""
    return load_native("QLupdate", _QLUPDATE_EXPORTS)


_QLCLIPBOARD_EXPORTS = (
    "QLclipboard_version",
    "QLclipboard_lastError",
    "QLclipboard_EnsureComInit",
    "QLclipboard_ReadText",
    "QLclipboard_WriteText",
    "QLclipboard_CreateSnapshot",
    "QLclipboard_GetSnapshotEntry",
    "QLclipboard_GetSnapshotEntryName",
    "QLclipboard_RestoreSnapshot",
    "QLclipboard_FreeSnapshot",
    "QLclipboard_EnumFormats",
    "QLclipboard_GetSequenceNumber",
    "QLclipboard_BuildHtmlFormat",
)


def QLclipboard() -> NativeDLL:
    """Return the loaded QLclipboard.dll wrapper (singleton)."""
    return load_native("QLclipboard", _QLCLIPBOARD_EXPORTS)


_QLICON_EXPORTS = (
    "QLicon_version",
    "QLicon_lastError",
    "QLicon_ExtractFromFile",
    "QLicon_ExtractFromResource",
    "QLicon_LoadImageFile",
    "QLicon_IsEmpty",
    "QLicon_GetFileTypeName",
)


def QLicon() -> NativeDLL:
    """Return the loaded QLicon.dll wrapper (singleton)."""
    return load_native("QLicon", _QLICON_EXPORTS)


_QLSHELL_EXPORTS = (
    "QLshell_version",
    "QLshell_lastError",
    "QLshell_OpenPath",
    "QLshell_Relaunch",
    "QLshell_RunDetached",
    "QLshell_LaunchWithFile",
)


def QLshell() -> NativeDLL:
    """Return the loaded QLshell.dll wrapper (singleton)."""
    return load_native("QLshell", _QLSHELL_EXPORTS)
