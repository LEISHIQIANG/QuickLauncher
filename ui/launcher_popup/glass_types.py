"""Glass background types — extracted from glass_background.py for S7 split."""

from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes

from qt_compat import QImage

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

BUFFER_COUNT = 4
WDA_EXCLUDEFROMCAPTURE = 0x00000011
_BACKEND_BLUR_DOWNSAMPLE = 0.25
_HIGH_RES_BLUR_DOWNSAMPLE = 0.20
_HIGH_RES_PIXEL_THRESHOLD = 2_500_000

# ── Error ──────────────────────────────────────────────────────────────


class GlassBackgroundError(RuntimeError):
    """Raised when the glass renderer cannot produce a frame."""


# ── ctypes structures ──────────────────────────────────────────────────


class _Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _Rect),
        ("rcWork", _Rect),
        ("dwFlags", ctypes.c_ulong),
        ("szDevice", ctypes.c_wchar * 32),
    ]


# ── DisplayAffinity ────────────────────────────────────────────────────


_WDA_EXCLUDEFROMCAPTURE = 0x00000011


class _DisplayAffinity:
    """RAII wrapper around SetWindowDisplayAffinity + desktop capture."""

    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
        self._user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
        self._user32.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self._user32.GetWindowDisplayAffinity.restype = wintypes.BOOL
        self._user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_Rect)]
        self._user32.GetWindowRect.restype = wintypes.BOOL
        self._gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self._gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self._gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self._gdi32.CreateDCW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]
        self._gdi32.CreateDCW.restype = wintypes.HDC
        self._gdi32.CreateDIBSection.argtypes = [
            wintypes.HDC, ctypes.c_void_p, ctypes.c_uint,
            ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, ctypes.c_uint,
        ]
        self._gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        self._gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self._gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self._gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self._gdi32.DeleteObject.restype = wintypes.BOOL
        self._gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self._gdi32.DeleteDC.restype = wintypes.BOOL
        self._gdi32.BitBlt.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
        ]
        self._gdi32.BitBlt.restype = wintypes.BOOL
        self._gdi32.GetDIBits.argtypes = [
            wintypes.HDC, wintypes.HBITMAP, ctypes.c_uint, ctypes.c_uint,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
        ]
        self._gdi32.GetDIBits.restype = ctypes.c_int
        self._user32.MonitorFromPoint.argtypes = [ctypes.POINTER(_POINT), wintypes.DWORD]
        self._user32.MonitorFromPoint.restype = ctypes.c_void_p
        self._user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONITORINFOEXW)]
        self._user32.GetMonitorInfoW.restype = wintypes.BOOL

    def set_exclude_from_capture(self, hwnd: int) -> tuple[bool, int]:
        previous = wintypes.DWORD(0)
        if self._user32.GetWindowDisplayAffinity(wintypes.HWND(int(hwnd)), ctypes.byref(previous)):
            ok = bool(self._user32.SetWindowDisplayAffinity(
                wintypes.HWND(int(hwnd)), wintypes.DWORD(WDA_EXCLUDEFROMCAPTURE)))
            return ok, int(previous.value)
        ok = bool(self._user32.SetWindowDisplayAffinity(
            wintypes.HWND(int(hwnd)), wintypes.DWORD(WDA_EXCLUDEFROMCAPTURE)))
        return ok, 0

    def restore(self, hwnd: int, previous: int) -> None:
        try:
            self._user32.SetWindowDisplayAffinity(wintypes.HWND(int(hwnd)), wintypes.DWORD(int(previous)))
        except OSError as exc:
            logger.debug("SetWindowDisplayAffinity restore failed: %s", exc, exc_info=True)

    def get_window_rect(self, hwnd: int) -> _Rect | None:
        rect = _Rect()
        if not self._user32.GetWindowRect(wintypes.HWND(int(hwnd)), ctypes.byref(rect)):
            return None
        return rect

    def capture_desktop(self, rect: _Rect) -> bytes | None:
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            return None
        center_x = int(rect.left) + width // 2
        center_y = int(rect.top) + height // 2
        pt = _POINT(x=center_x, y=center_y)
        MONITOR_DEFAULTTONEAREST = 0x00000002
        hmonitor = self._user32.MonitorFromPoint(ctypes.byref(pt), MONITOR_DEFAULTTONEAREST)
        device_name: str | None = None
        monitor_offset_x = 0
        monitor_offset_y = 0
        if hmonitor:
            info = _MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
            if self._user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
                device_name = info.szDevice or None
                monitor_offset_x = int(info.rcMonitor.left)
                monitor_offset_y = int(info.rcMonitor.top)
        if device_name:
            screen = self._gdi32.CreateDCW("DISPLAY", device_name, None, None)
        else:
            screen = self._gdi32.CreateDCW("DISPLAY", None, None, None)
        if not screen:
            return None
        try:
            memory = self._gdi32.CreateCompatibleDC(screen)
            if not memory:
                return None
            try:
                class BITMAPINFOHEADER(ctypes.Structure):
                    _fields_ = [
                        ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                        ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                        ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                        ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                        ("biClrImportant", ctypes.c_uint32),
                    ]
                class BITMAPINFO(ctypes.Structure):
                    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]
                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = width
                bmi.bmiHeader.biHeight = -height
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                bmi.bmiHeader.biCompression = 0
                bits = ctypes.c_void_p()
                bitmap = self._gdi32.CreateDIBSection(screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
                if not bitmap or not bits.value:
                    if bitmap:
                        self._gdi32.DeleteObject(bitmap)
                    return None
                try:
                    self._gdi32.SelectObject(memory, bitmap)
                    SRCCOPY = 0x00CC0020
                    CAPTUREBLT = 0x40000000
                    if not self._gdi32.BitBlt(
                        memory, 0, 0, width, height, screen,
                        int(rect.left) - monitor_offset_x, int(rect.top) - monitor_offset_y,
                        SRCCOPY | CAPTUREBLT,
                    ):
                        return None
                    size = width * height * 4
                    buffer = (ctypes.c_uint8 * size).from_address(bits.value)
                    return bytes(buffer)
                finally:
                    self._gdi32.DeleteObject(bitmap)
            finally:
                self._gdi32.DeleteDC(memory)
        finally:
            self._gdi32.DeleteDC(screen)


# ── Frame buffer ───────────────────────────────────────────────────────


class _FrameBuffer:
    """Triple-buffer slot for a single premultiplied BGRA frame."""

    __slots__ = ("_lock", "_generation", "_image", "_width", "_height")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0
        self._image: QImage | None = None
        self._width = 0
        self._height = 0


# ── Helpers ────────────────────────────────────────────────────────────


def _blur_downsample(width: int, height: int) -> tuple[int, int]:
    factor = _HIGH_RES_BLUR_DOWNSAMPLE if width * height >= _HIGH_RES_PIXEL_THRESHOLD else _BACKEND_BLUR_DOWNSAMPLE
    return max(1, int(round(width * factor))), max(1, int(round(height * factor)))
