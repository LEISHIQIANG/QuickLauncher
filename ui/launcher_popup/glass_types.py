"""Glass background types — extracted from glass_background.py for S7 split."""

from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes

from qt_compat import QImage

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

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
