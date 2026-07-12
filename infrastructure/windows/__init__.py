"""W7 stage A — Windows platform adapter factories.

This module exists so the application layer can request the four platform
ports (:class:`application.ports.platform.WindowPort`,
:class:`application.ports.platform.AutoStartPort`,
:class:`application.ports.platform.IconProvider`,
:class:`application.ports.platform.GlobalHotkeyPort`) without importing
from :mod:`core` or :mod:`hooks`.  The four ``get_*_port`` functions are
the only public surface; the underlying adapter implementations live in
:mod:`infrastructure.windows.adapters` and its companion modules.

W7 directory migration (``platform/windows/``) is tracked as a P2
follow-up in :doc:`../architecture-decisions/w7-evaluation`.  Until that
move happens, the adapter factories live in :mod:`infrastructure.windows`
so the W3 layer can pull them through the application ports without
depending on the eventual ``platform.windows`` path.
"""

from __future__ import annotations

from typing import Any

from infrastructure.windows.adapters import (
    HooksGlobalHotkeyAdapter as _HooksGlobalHotkeyAdapter,
)
from infrastructure.windows.adapters import (
    WindowsAutoStartAdapter,
    WindowsWindowAdapter,
)
from infrastructure.windows.adapters import (
    get_auto_start_port as _get_auto_start_port,
)
from infrastructure.windows.adapters import (
    get_global_hotkey_port as _get_global_hotkey_port,
)
from infrastructure.windows.adapters import (
    get_icon_provider as _get_icon_provider,
)
from infrastructure.windows.adapters import (
    get_window_port as _get_window_port,
)
from infrastructure.windows.global_hotkey_adapter import HooksGlobalHotkeyAdapter
from infrastructure.windows.icon_provider_adapter import CoreIconProviderAdapter

# Re-export the concrete adapter classes so legacy import sites
# (e.g. ``from infrastructure.windows import WindowsWindowAdapter``)
# keep working.  These re-exports are part of the W7 P0 surface and
# stay until ``platform/windows/`` replaces the package entirely.


def window_port() -> Any:
    """Return the process-wide :class:`WindowPort` adapter."""
    return _get_window_port()


def auto_start_port() -> Any:
    """Return the process-wide :class:`AutoStartPort` adapter."""
    return _get_auto_start_port()


def icon_provider() -> Any:
    """Return the process-wide :class:`IconProvider` adapter."""
    return _get_icon_provider()


def global_hotkey_port() -> Any:
    """Return the process-wide :class:`GlobalHotkeyPort` adapter."""
    return _get_global_hotkey_port()


__all__ = [
    "_HooksGlobalHotkeyAdapter",
    "CoreIconProviderAdapter",
    "HooksGlobalHotkeyAdapter",
    "WindowsAutoStartAdapter",
    "WindowsWindowAdapter",
    "auto_start_port",
    "global_hotkey_port",
    "icon_provider",
    "window_port",
]
