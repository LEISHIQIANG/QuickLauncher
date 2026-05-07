"""Windows privilege and drag-drop compatibility helpers."""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes

logger = logging.getLogger(__name__)

WM_COPYDATA = 0x004A
WM_COPYGLOBALDATA = 0x0049
WM_DROPFILES = 0x0233
MSGFLT_ALLOW = 1
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION_CLASS = 20

if os.name == "nt":
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32
else:
    user32 = None
    shell32 = None
    advapi32 = None
    kernel32 = None


class TOKEN_ELEVATION(ctypes.Structure):
    _fields_ = [("TokenIsElevated", wintypes.DWORD)]


def is_process_elevated() -> bool:
    """Return whether the current process is running elevated."""
    if os.name != "nt":
        return False

    token = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
            return False

        elevation = TOKEN_ELEVATION()
        size = wintypes.DWORD()
        if not advapi32.GetTokenInformation(
            token,
            TOKEN_ELEVATION_CLASS,
            ctypes.byref(elevation),
            ctypes.sizeof(elevation),
            ctypes.byref(size),
        ):
            return False
        return bool(elevation.TokenIsElevated)
    except Exception as exc:
        logger.debug("Failed to detect elevation: %s", exc)
        return False
    finally:
        if token:
            try:
                kernel32.CloseHandle(token)
            except Exception:
                pass


def allow_drag_drop_for_window(hwnd: int) -> bool:
    """Allow Explorer drag-drop into an elevated window."""
    if os.name != "nt" or not hwnd or not is_process_elevated():
        return False

    applied = False

    for message in (WM_DROPFILES, WM_COPYDATA, WM_COPYGLOBALDATA):
        try:
            if user32.ChangeWindowMessageFilterEx(hwnd, message, MSGFLT_ALLOW, None):
                applied = True
        except Exception as exc:
            logger.debug("ChangeWindowMessageFilterEx failed for %s: %s", message, exc)

    try:
        shell32.DragAcceptFiles(hwnd, True)
        applied = True
    except Exception as exc:
        logger.debug("DragAcceptFiles failed: %s", exc)

    return applied


def allow_drag_drop_for_widget(widget) -> bool:
    """Qt wrapper around allow_drag_drop_for_window()."""
    try:
        return allow_drag_drop_for_window(int(widget.winId()))
    except Exception:
        return False
