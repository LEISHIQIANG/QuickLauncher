"""Windows-specific platform modules.

Modules in this package encapsulate native Windows APIs (Win32, COM, shell)
behind clean abstractions. No Qt or UI dependencies allowed.

Migration targets (from core/):
- ``core/window_detection.py`` — native window HWND detection
- ``core/global_hotkey_manager.py`` — Windows global hotkey registration
- ``core/auto_start_manager.py`` — registry-based auto-start
- ``core/file_association.py`` — Windows file extension association
- ``core/shell_namespace.py`` — Windows shell namespace access
- ``core/win_event.py`` — low-level win32 event handling
- ``core/folder_watcher.py`` — ReadDirectoryChangesW
- ``core/com_power_monitor.py`` — Windows power events via COM
- ``core/gdi_monitor.py`` — GDI-based hook (if not visual-only)
- ``core/tray_controller.py`` — Windows system tray interaction
- ``core/window_utilities.py`` — Windows window management
"""

from __future__ import annotations
