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
TOKEN_ELEVATION_TYPE_CLASS = 18
TOKEN_INTEGRITY_LEVEL_CLASS = 25

TOKEN_ELEVATION_TYPE_NAMES = {
    1: "Default",
    2: "Full",
    3: "Limited",
}

if os.name == "nt":
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32

    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
    advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    advapi32.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)

    shell32.IsUserAnAdmin.argtypes = []
    shell32.IsUserAnAdmin.restype = wintypes.BOOL
else:
    user32 = None
    shell32 = None
    advapi32 = None
    kernel32 = None


class TOKEN_ELEVATION(ctypes.Structure):
    _fields_ = [("TokenIsElevated", wintypes.DWORD)]


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Sid", ctypes.c_void_p),
        ("Attributes", wintypes.DWORD),
    ]


class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", SID_AND_ATTRIBUTES)]


def _query_token_information(token, info_class: int):
    needed = wintypes.DWORD()
    advapi32.GetTokenInformation(token, info_class, None, 0, ctypes.byref(needed))
    if needed.value <= 0:
        return None

    buffer = ctypes.create_string_buffer(needed.value)
    if not advapi32.GetTokenInformation(
        token,
        info_class,
        buffer,
        needed,
        ctypes.byref(needed),
    ):
        return None
    return buffer


def _integrity_name(rid: int | None) -> str:
    if rid is None:
        return "Unknown"
    if rid >= 0x4000:
        return "System"
    if rid >= 0x3000:
        return "High"
    if rid >= 0x2000:
        return "Medium"
    if rid >= 0x1000:
        return "Low"
    return "Untrusted"


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
            except Exception as exc:
                logger.debug("关闭令牌句柄失败: %s", exc, exc_info=True)


def get_process_elevation_status() -> dict:
    """Return detailed elevation information for startup diagnostics."""
    status = {
        "available": False,
        "elevated": False,
        "elevation_type": "Unknown",
        "integrity_level": "Unknown",
        "integrity_rid": None,
        "is_user_an_admin": False,
    }
    if os.name != "nt":
        return status

    token = wintypes.HANDLE()
    try:
        status["is_user_an_admin"] = bool(shell32.IsUserAnAdmin())
    except Exception as exc:
        logger.debug("检查用户管理员状态失败: %s", exc, exc_info=True)

    try:
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
            return status

        elevation_buf = _query_token_information(token, TOKEN_ELEVATION_CLASS)
        if elevation_buf is not None:
            elevation = ctypes.cast(elevation_buf, ctypes.POINTER(TOKEN_ELEVATION)).contents
            status["elevated"] = bool(elevation.TokenIsElevated)

        elevation_type_buf = _query_token_information(token, TOKEN_ELEVATION_TYPE_CLASS)
        if elevation_type_buf is not None:
            elevation_type = ctypes.cast(elevation_type_buf, ctypes.POINTER(wintypes.DWORD)).contents.value
            status["elevation_type"] = TOKEN_ELEVATION_TYPE_NAMES.get(elevation_type, str(elevation_type))

        integrity_buf = _query_token_information(token, TOKEN_INTEGRITY_LEVEL_CLASS)
        if integrity_buf is not None:
            label = ctypes.cast(integrity_buf, ctypes.POINTER(TOKEN_MANDATORY_LABEL)).contents
            count_ptr = advapi32.GetSidSubAuthorityCount(label.Label.Sid)
            if count_ptr:
                count = ctypes.cast(count_ptr, ctypes.POINTER(ctypes.c_ubyte)).contents.value
                if count:
                    rid_ptr = advapi32.GetSidSubAuthority(label.Label.Sid, count - 1)
                    if rid_ptr:
                        rid = ctypes.cast(rid_ptr, ctypes.POINTER(wintypes.DWORD)).contents.value
                        status["integrity_rid"] = rid
                        status["integrity_level"] = _integrity_name(rid)

        status["available"] = True
        return status
    except Exception as exc:
        logger.debug("Failed to query elevation status: %s", exc)
        return status
    finally:
        if token:
            try:
                kernel32.CloseHandle(token)
            except Exception as exc:
                logger.debug("关闭令牌句柄失败: %s", exc, exc_info=True)


def format_process_elevation_status() -> str:
    status = get_process_elevation_status()
    integrity_rid = status.get("integrity_rid")
    integrity_rid_text = f"0x{integrity_rid:x}" if isinstance(integrity_rid, int) else "unknown"
    return (
        f"available={int(bool(status.get('available')))}, "
        f"elevated={int(bool(status.get('elevated')))}, "
        f"elevation_type={status.get('elevation_type')}, "
        f"integrity={status.get('integrity_level')}, "
        f"integrity_rid={integrity_rid_text}, "
        f"is_user_an_admin={int(bool(status.get('is_user_an_admin')))}"
    )


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
