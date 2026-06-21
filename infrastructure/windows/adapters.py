"""Concrete Windows capability adapters."""

from __future__ import annotations

from pathlib import Path

from infrastructure.process import runtime as process_runtime
from infrastructure.windows.global_hotkey_adapter import HooksGlobalHotkeyAdapter
from infrastructure.windows.icon_provider_adapter import CoreIconProviderAdapter


class WindowsWindowAdapter:
    def open_path(self, path: str | Path) -> None:
        process_runtime.startfile(path)

    def focus(self, native_handle: int) -> bool:
        if not native_handle:
            return False
        import win32con
        import win32gui

        try:
            win32gui.ShowWindow(int(native_handle), win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(int(native_handle))
            return True
        except (OSError, RuntimeError):
            return False


class WindowsAutoStartAdapter:
    def status(self) -> tuple[bool, str]:
        from core.auto_start_manager import get_auto_start_method, is_auto_start_enabled

        return bool(is_auto_start_enabled()), str(get_auto_start_method())

    def enable(self) -> tuple[bool, str]:
        from core.auto_start_manager import enable_auto_start

        return enable_auto_start()

    def disable(self) -> tuple[bool, str]:
        from core.auto_start_manager import disable_auto_start

        return disable_auto_start()


# Module-level singletons so the application port can hand out stable
# adapters through :func:`infrastructure.windows.adapters.get_*_port`
# factories.  Each factory is cheap to call but the underlying adapter
# is process-wide so the icon and hotkey caches stay warm.
_default_window: WindowsWindowAdapter | None = None
_default_auto_start: WindowsAutoStartAdapter | None = None
_default_icon: CoreIconProviderAdapter | None = None
_default_hotkey: HooksGlobalHotkeyAdapter | None = None


def get_window_port() -> WindowsWindowAdapter:
    global _default_window
    if _default_window is None:
        _default_window = WindowsWindowAdapter()
    return _default_window


def get_auto_start_port() -> WindowsAutoStartAdapter:
    global _default_auto_start
    if _default_auto_start is None:
        _default_auto_start = WindowsAutoStartAdapter()
    return _default_auto_start


def get_icon_provider() -> CoreIconProviderAdapter:
    global _default_icon
    if _default_icon is None:
        _default_icon = CoreIconProviderAdapter()
    return _default_icon


def get_global_hotkey_port() -> HooksGlobalHotkeyAdapter:
    global _default_hotkey
    if _default_hotkey is None:
        _default_hotkey = HooksGlobalHotkeyAdapter()
    return _default_hotkey
