"""Adapter that implements :class:`application.ports.platform.GlobalHotkeyPort`.

The port returns an opaque handle that the application later passes back
to ``unregister``.  QuickLauncher's :class:`hooks.hotkey_manager.HotkeyManager`
keeps its own handle table; the adapter returns the host hotkey-id so
the application does not need to know about the underlying Qt machinery.
"""

from __future__ import annotations

from collections.abc import Callable


class HooksGlobalHotkeyAdapter:
    """Adapter backed by :class:`hooks.hotkey_manager.HotkeyManager`."""

    def __init__(self) -> None:
        self._handle_seq = 0
        self._handles: dict[int, int] = {}  # port handle -> host hotkey id

    def _next_handle(self) -> int:
        self._handle_seq += 1
        return self._handle_seq

    def register(self, hotkey: str, callback: Callable[[], None]) -> object:
        from hooks.hotkey_manager import HotkeyManager

        host = HotkeyManager.instance()  # type: ignore[attr-defined]
        host_id = host.register(hotkey, callback)
        port_handle = self._next_handle()
        self._handles[port_handle] = int(host_id)
        return port_handle

    def unregister(self, handle: object) -> None:
        from hooks.hotkey_manager import HotkeyManager

        port_handle = int(handle) if isinstance(handle, int | str) else 0
        host_id = self._handles.pop(port_handle, None)
        if host_id is None:
            return
        HotkeyManager.instance().unregister(host_id)  # type: ignore[attr-defined]

    def close(self) -> None:
        from hooks.hotkey_manager import HotkeyManager

        for host_id in list(self._handles.values()):
            HotkeyManager.instance().unregister(host_id)  # type: ignore[attr-defined]
        self._handles.clear()
