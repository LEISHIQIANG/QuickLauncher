"""Pure-Python glass-background renderer for :class:`LauncherPopup`.

The renderer captures the physical desktop behind the popup, applies the same
visual pipeline as the legacy Direct2D-based ``glass_background.dll`` (Gaussian
blur, saturation boost, radial highlight, tint overlay, dark border, and inner
linear highlight) using only Pillow + Qt, and publishes the latest premultiplied
BGRA frame through a Python triple buffer so the Qt paint thread can drop stale
frames.

SetWindowDisplayAffinity(..., WDA_EXCLUDEFROMCAPTURE) is still used so the
launcher popup does not appear in its own captured background (the trick the
native build relied on).  Without that flag the popup would freeze inside the
glass, so we keep the call here.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes

from PIL import Image as PILImage
from PIL import ImageFilter

from qt_compat import QColor, QImage, QPainter, QRect, QTimer
from qt_compat import Qt as _QtCompat
from ui.utils.ui_scale import sp

logger = logging.getLogger(__name__)

GLASS_ABI_VERSION = 1
# 20 FPS is the fastest rate at which the pure-Python pipeline (PIL blur +
# in-Python saturation + alpha composite) can keep up on a 276x581 popup
# without dropping the first frame.  The legacy C++ renderer targeted 120
# FPS via Direct2D hardware effects; the Python version cannot match that
# cadence, so we drop the target by 6x and pace everything else off it.
TARGET_FPS = 20
TARGET_FRAME_INTERVAL_MS = 1000 // TARGET_FPS
# The repaint timer polls at 60 Hz so a freshly produced frame is on screen
# within ~16 ms.  The worker produces at ``TARGET_FPS`` independently; the
# timer only triggers a paint when a newer frame is actually available.
_REPAINT_INTERVAL_MS = 16
BUFFER_COUNT = 3
WDA_EXCLUDEFROMCAPTURE = 0x00000011
# PIL's ``GaussianBlur(radius=...)`` uses sigma == radius / 2; Direct2D's
# ``D2D1GaussianBlur`` standard deviation is the same sigma we feed it.  The
# legacy renderer received ``blur_radius`` and passed it straight into
# ``D2D1_GAUSSIANBLUR_PROP_STANDARD_DEVIATION``, so we mirror that 1:1 here.
# The Python renderer also downscales the frame before blurring to keep the
# cost roughly constant in the popup size; the legacy build skipped the
# downscale because Direct2D was hardware-accelerated.
_BACKEND_BLUR_DOWNSAMPLE = 0.25


class GlassBackgroundError(RuntimeError):
    """Raised when the glass renderer cannot produce a frame."""


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _Rect),
        ("rcWork", _Rect),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class _FrameBuffer:
    __slots__ = (
        "image",
        "width",
        "height",
        "stride",
        "generation",
        "readers",
    )

    def __init__(self) -> None:
        self.image: QImage | None = None
        self.width = 0
        self.height = 0
        self.stride = 0
        self.generation = 0
        self.readers = 0


class _DisplayAffinity:
    """Tiny RAII wrapper around ``SetWindowDisplayAffinity``.

    The native renderer owned this responsibility; we keep it here so callers
    (``LauncherPopup``) don't have to special-case the glass background.
    """

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
            wintypes.HDC,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_void_p),
            wintypes.HANDLE,
            ctypes.c_uint,
        ]
        self._gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        self._gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self._gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self._gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self._gdi32.DeleteObject.restype = wintypes.BOOL
        self._gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self._gdi32.DeleteDC.restype = wintypes.BOOL
        # ``BitBlt`` defaults its arguments to ``c_int`` when no ``argtypes`` are
        # set; on 64-bit Windows the HDC handles are 64-bit values, so the
        # default conversion overflows and the worker thread dies with
        # "argument 1: OverflowError".  Pin every parameter to the matching
        # Win32 type here.
        self._gdi32.BitBlt.argtypes = [
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.DWORD,
        ]
        self._gdi32.BitBlt.restype = wintypes.BOOL
        # ``GetDIBits`` is not currently used, but if a future change pulls
        # it in, the same default-conversion trap exists.  Pin it preemptively.
        self._gdi32.GetDIBits.argtypes = [
            wintypes.HDC,
            wintypes.HBITMAP,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint,
        ]
        self._gdi32.GetDIBits.restype = ctypes.c_int
        # PerMonitorV2-aware screen capture: with the manifest embedded by
        # build_win11_setup.bat the packaged process is PerMonitorV2-aware, so
        # the legacy "DISPLAY" DC returned by GDI is the *primary* monitor's
        # DC, scaled by the primary monitor's DPI.  When the popup lives on
        # another DPI monitor, BitBlt then returns either an empty/black
        # frame or content stretched by the wrong DPI ratio.  Pin the
        # ``MonitorFromPoint`` / ``GetMonitorInfoW`` argtypes so we can ask
        # for a per-monitor DC and have GDI honor the popup's monitor.
        self._user32.MonitorFromPoint.argtypes = [
            ctypes.POINTER(_POINT),
            wintypes.DWORD,
        ]
        self._user32.MonitorFromPoint.restype = ctypes.c_void_p
        self._user32.GetMonitorInfoW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_MONITORINFOEXW),
        ]
        self._user32.GetMonitorInfoW.restype = wintypes.BOOL

    def set_exclude_from_capture(self, hwnd: int) -> tuple[bool, int]:
        previous = wintypes.DWORD(0)
        if self._user32.GetWindowDisplayAffinity(wintypes.HWND(int(hwnd)), ctypes.byref(previous)):
            ok = bool(
                self._user32.SetWindowDisplayAffinity(wintypes.HWND(int(hwnd)), wintypes.DWORD(WDA_EXCLUDEFROMCAPTURE))
            )
            return ok, int(previous.value)
        ok = bool(
            self._user32.SetWindowDisplayAffinity(wintypes.HWND(int(hwnd)), wintypes.DWORD(WDA_EXCLUDEFROMCAPTURE))
        )
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

        # Lock onto the monitor that actually contains the popup.  Under
        # PerMonitorV2 DPI awareness the legacy "DISPLAY" DC behaves as if
        # the *primary* monitor owned it; BitBlt against it would re-scale
        # the captured pixels by the primary monitor's DPI and, when the
        # popup lives on a different monitor, the result is either an empty
        # black frame or content stretched by the wrong DPI ratio.
        center_x = int(rect.left) + width // 2
        center_y = int(rect.top) + height // 2
        pt = _POINT(x=center_x, y=center_y)
        MONITOR_DEFAULTTONEAREST = 0x00000002
        hmonitor = self._user32.MonitorFromPoint(ctypes.byref(pt), MONITOR_DEFAULTTONEAREST)
        device_name: str | None = None
        # ``GetMonitorInfoW``'s ``rcMonitor`` is in *virtual screen*
        # coordinates, but the per-monitor DC returned by ``CreateDCW`` is in
        # *that monitor's local* coordinate space (origin = monitor's
        # top-left).  ``GetWindowRect``'s ``rect.left/top`` are in the
        # virtual screen coordinate space, so we have to translate by
        # ``rcMonitor.left/top`` to point BitBlt at the correct physical
        # pixels on secondary monitors.  Without this, a popup on a
        # secondary monitor would sample the wrong region (offset by the
        # monitor's origin in the virtual desktop), producing leftover
        # "right-angle" strips on the secondary screen even after the
        # corner-radius DPI was fixed.
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
                        ("biSize", ctypes.c_uint32),
                        ("biWidth", ctypes.c_int32),
                        ("biHeight", ctypes.c_int32),
                        ("biPlanes", ctypes.c_uint16),
                        ("biBitCount", ctypes.c_uint16),
                        ("biCompression", ctypes.c_uint32),
                        ("biSizeImage", ctypes.c_uint32),
                        ("biXPelsPerMeter", ctypes.c_int32),
                        ("biYPelsPerMeter", ctypes.c_int32),
                        ("biClrUsed", ctypes.c_uint32),
                        ("biClrImportant", ctypes.c_uint32),
                    ]

                class BITMAPINFO(ctypes.Structure):
                    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]

                info = BITMAPINFO()
                info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                info.bmiHeader.biWidth = width
                info.bmiHeader.biHeight = -height
                info.bmiHeader.biPlanes = 1
                info.bmiHeader.biBitCount = 32
                info.bmiHeader.biCompression = 0  # BI_RGB
                bits = ctypes.c_void_p()
                bitmap = self._gdi32.CreateDIBSection(screen, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
                if not bitmap or not bits.value:
                    if bitmap:
                        self._gdi32.DeleteObject(bitmap)
                    return None
                try:
                    self._gdi32.SelectObject(memory, bitmap)
                    SRCCOPY = 0x00CC0020
                    CAPTUREBLT = 0x40000000
                    if not self._gdi32.BitBlt(
                        memory,
                        0,
                        0,
                        width,
                        height,
                        screen,
                        int(rect.left) - monitor_offset_x,
                        int(rect.top) - monitor_offset_y,
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


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _apply_saturation(pixels: bytearray, factor: float, *, channels: int = 4) -> None:
    """In-place saturation boost using the Rec. 601 luma weights.

    Matches the perceptual effect of Direct2D's ``D2D1Saturation`` which
    amplifies each channel's deviation from the perceived luma by ``factor``.
    """
    if abs(factor - 1.0) < 1e-3:
        return
    if channels == 4:
        # BGRA order (legacy Direct2D compatibility)
        for index in range(0, len(pixels), 4):
            b = pixels[index]
            g = pixels[index + 1]
            r = pixels[index + 2]
            luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            nr = max(0, min(255, int(round(luma + (r - luma) * factor))))
            ng = max(0, min(255, int(round(luma + (g - luma) * factor))))
            nb = max(0, min(255, int(round(luma + (b - luma) * factor))))
            pixels[index] = nb
            pixels[index + 1] = ng
            pixels[index + 2] = nr
    else:
        # RGB order (pure Python convert("RGB") fallback)
        for index in range(0, len(pixels), 3):
            r = pixels[index]
            g = pixels[index + 1]
            b = pixels[index + 2]
            luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            nr = max(0, min(255, int(round(luma + (r - luma) * factor))))
            ng = max(0, min(255, int(round(luma + (g - luma) * factor))))
            nb = max(0, min(255, int(round(luma + (b - luma) * factor))))
            pixels[index] = nr
            pixels[index + 1] = ng
            pixels[index + 2] = nb


def _build_radial_highlight(width: int, height: int, strength: float) -> PILImage.Image | None:
    """Pre-render the radial highlight used for the bright top-left lobe.

    The legacy Direct2D version painted a radial gradient on the GPU; we
    compute the same alpha field with numpy so the cost is one vectorised
    pass over the image instead of a per-pixel Python loop (the latter
    dominated the per-frame budget on a 276x581 popup).
    """
    if strength <= 0.0:
        return None
    radius_w = max(1, int(round(width * 0.85)))
    radius_h = max(1, int(round(height * 0.85)))
    cx = int(round(width * 0.10))
    cy = int(round(height * 0.10))
    max_alpha = int(round(strength * 0.25 * 255))
    if max_alpha <= 0:
        return None
    w = max(1, width)
    h = max(1, height)
    try:
        import numpy as np

        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        dx = (xs - cx) / max(1, radius_w)
        dy = (ys - cy) / max(1, radius_h)
        d2 = dx * dx + dy * dy
        t = np.clip(1.0 - d2, 0.0, 1.0)
        alpha = np.clip((max_alpha * t * t).astype(np.int32), 0, 255).astype(np.uint8)
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[..., 0:3] = 255
        rgba[..., 3] = alpha
        return PILImage.fromarray(rgba, "RGBA")
    except Exception:
        pixels = bytearray(w * h * 4)
        for y in range(h):
            dy = (y - cy) / max(1, radius_h)
            for x in range(w):
                dx = (x - cx) / max(1, radius_w)
                d2 = dx * dx + dy * dy
                if d2 >= 1.0:
                    continue
                t = 1.0 - d2
                alpha = int(round(max_alpha * t * t))
                if alpha <= 0:
                    continue
                offset = (y * w + x) * 4
                cur = pixels[offset + 3]
                new = cur + alpha
                if new > 255:
                    new = 255
                pixels[offset + 3] = new
                pixels[offset] = max(pixels[offset], 255)
                pixels[offset + 1] = max(pixels[offset + 1], 255)
                pixels[offset + 2] = max(pixels[offset + 2], 255)
        return PILImage.frombuffer("RGBA", (w, h), bytes(pixels), "raw", "RGBA", 0, 1)


def _build_inner_highlight(width: int, height: int, strength: float) -> PILImage.Image | None:
    if strength <= 0.0:
        return None
    w = max(1, width)
    h = max(1, height)
    if w <= 3 or h <= 3:
        return None
    inner_max = int(round(strength * 0.75 * 255))
    inner_min = int(round(0.02 * 255))
    if inner_max <= 0 and inner_min <= 0:
        return None
    try:
        import numpy as np

        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        # The C++ version paints a linear gradient from (1.5, 1.5) to
        # (right - 1.5, bottom - 1.5) and uses ``max(tx, ty)`` so the
        # gradient is darkest in the bottom-right.
        tx = np.clip((xs - 1.5) / max(1, w - 3), 0.0, 1.0)
        ty = np.clip((ys - 1.5) / max(1, h - 3), 0.0, 1.0)
        t = np.clip(1.0 - np.maximum(tx, ty), 0.0, 1.0)
        alpha_f = inner_max * t + inner_min * (1.0 - t)
        alpha = np.clip(alpha_f, 0, 255).astype(np.uint8)
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[..., 0:3] = 255
        rgba[..., 3] = alpha
        return PILImage.fromarray(rgba, "RGBA")
    except Exception:
        pixels = bytearray(w * h * 4)
        denom_x = max(1, w - 3)
        denom_y = max(1, h - 3)
        for y in range(1, h - 2):
            ty = (y - 1.5) / denom_y
            for x in range(1, w - 2):
                tx = (x - 1.5) / denom_x
                t = max(0.0, 1.0 - max(tx, ty))
                alpha = int(round(inner_max * t + inner_min * (1.0 - t)))
                if alpha <= 0:
                    continue
                offset = (y * w + x) * 4
                cur = pixels[offset + 3]
                new = cur + alpha
                if new > 255:
                    new = 255
                pixels[offset + 3] = new
                pixels[offset] = max(pixels[offset], 255)
                pixels[offset + 1] = max(pixels[offset + 1], 255)
                pixels[offset + 2] = max(pixels[offset + 2], 255)
        return PILImage.frombuffer("RGBA", (w, h), bytes(pixels), "raw", "RGBA", 0, 1)


def _build_dark_border(width: int, height: int, strength: int) -> PILImage.Image | None:
    if strength <= 0 or width <= 1 or height <= 1:
        return None
    w = max(1, width)
    h = max(1, height)
    try:
        import numpy as np

        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[..., 0] = 15
        rgba[..., 1] = 23
        rgba[..., 2] = 42
        rgba[0, :, 3] = strength
        rgba[h - 1, :, 3] = strength
        rgba[:, 0, 3] = strength
        rgba[:, w - 1, 3] = strength
        return PILImage.fromarray(rgba, "RGBA")
    except Exception:
        pixels = bytearray(w * h * 4)
        for x in range(w):
            offset_top = x * 4
            offset_bottom = (h - 1) * w * 4 + x * 4
            for channel in range(3):
                pixels[offset_top + channel] = 15
                pixels[offset_bottom + channel] = 15
            pixels[offset_top + 3] = strength
            pixels[offset_bottom + 3] = strength
            pixels[offset_top + 1] = max(pixels[offset_top + 1], 23)
            pixels[offset_top + 2] = max(pixels[offset_top + 2], 42)
            pixels[offset_bottom + 1] = max(pixels[offset_bottom + 1], 23)
            pixels[offset_bottom + 2] = max(pixels[offset_bottom + 2], 42)
        for y in range(h):
            offset_left = y * w * 4
            offset_right = y * w * 4 + (w - 1) * 4
            for channel in range(3):
                pixels[offset_left + channel] = 15
                pixels[offset_right + channel] = 15
            pixels[offset_left + 3] = strength
            pixels[offset_right + 3] = strength
            pixels[offset_left + 1] = max(pixels[offset_left + 1], 23)
            pixels[offset_left + 2] = max(pixels[offset_left + 2], 42)
            pixels[offset_right + 1] = max(pixels[offset_right + 1], 23)
            pixels[offset_right + 2] = max(pixels[offset_right + 2], 42)
        return PILImage.frombuffer("RGBA", (w, h), bytes(pixels), "raw", "RGBA", 0, 1)


def _render_frame(
    captured_bgra: bytes,
    width: int,
    height: int,
    stride: int,
    *,
    blur_radius: float,
    saturation: float,
    highlight: float,
    brightness: float,
    opacity: float,
    precomputed_layers: dict | None = None,
) -> bytes:
    """Replicate the Direct2D layer order on top of a captured BGRA frame.

    ``precomputed_layers`` is an optional cache of the size/parameter-driven
    overlay layers (radial highlight, dark border, inner highlight).  When
    provided, those layers are reused instead of being rebuilt for every
    frame, which is the difference between 60 FPS and 120 FPS for the
    Python renderer.
    """
    if width <= 0 or height <= 0:
        return b""
    src = PILImage.frombuffer("RGBA", (width, height), captured_bgra, "raw", "BGRA", stride, 1)

    if blur_radius > 0.0:
        downscale = max(1, int(round(width * _BACKEND_BLUR_DOWNSAMPLE)))
        downscale_h = max(1, int(round(height * _BACKEND_BLUR_DOWNSAMPLE)))
        if downscale < width or downscale_h < height:
            small = src.resize((downscale, downscale_h), PILImage.Resampling.BILINEAR)
            blurred_small = small.filter(ImageFilter.GaussianBlur(radius=blur_radius / 2.0))
            blurred = blurred_small.resize((width, height), PILImage.Resampling.BILINEAR)
        else:
            blurred = src.filter(ImageFilter.GaussianBlur(radius=blur_radius / 2.0))
    else:
        blurred = src

    # Saturation + tint go through numpy vectorised ops.  The previous
    # implementation walked every RGBA pixel in a Python for-loop, which on a
    # 276x581 popup is ~640k Python iterations *per frame*; that's the main
    # reason a 20 FPS target still felt choppy.
    rgb = blurred.convert("RGB")
    if abs(saturation - 1.0) > 1e-3:
        try:
            import numpy as np

            arr = np.asarray(rgb, dtype=np.float32)
            luma = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
            luma = luma[..., None]
            arr = luma + (arr - luma) * saturation
            np.clip(arr, 0.0, 255.0, out=arr)
            rgb = PILImage.fromarray(arr.astype(np.uint8), "RGB")
        except Exception:
            pixels = bytearray(rgb.tobytes())
            _apply_saturation(pixels, saturation, channels=3)
            rgb = PILImage.frombytes("RGB", (width, height), bytes(pixels))

    tint_alpha = _clamp(opacity, 0.0, 1.0)
    if tint_alpha > 0.0:
        base_r = int(round(20.0 + _clamp(brightness, 0.0, 1.0) * 235.0))
        base_g = int(round(20.0 + _clamp(brightness, 0.0, 1.0) * 235.0))
        base_b = int(round(25.0 + _clamp(brightness, 0.0, 1.0) * 230.0))
        try:
            import numpy as np

            arr = np.asarray(rgb, dtype=np.float32)
            arr[..., 0] = arr[..., 0] * (1.0 - tint_alpha) + base_r * tint_alpha
            arr[..., 1] = arr[..., 1] * (1.0 - tint_alpha) + base_g * tint_alpha
            arr[..., 2] = arr[..., 2] * (1.0 - tint_alpha) + base_b * tint_alpha
            np.clip(arr, 0.0, 255.0, out=arr)
            rgb = PILImage.fromarray(arr.astype(np.uint8), "RGB")
        except Exception:
            pixels = bytearray(rgb.tobytes())
            for index in range(0, len(pixels), 3):
                r = pixels[index]
                g = pixels[index + 1]
                b = pixels[index + 2]
                pixels[index] = int(round(r * (1.0 - tint_alpha) + base_r * tint_alpha))
                pixels[index + 1] = int(round(g * (1.0 - tint_alpha) + base_g * tint_alpha))
                pixels[index + 2] = int(round(b * (1.0 - tint_alpha) + base_b * tint_alpha))
            rgb = PILImage.frombytes("RGB", (width, height), bytes(pixels))

    composited = rgb.convert("RGBA")
    if precomputed_layers is not None:
        radial = precomputed_layers.get("radial")
        if radial is not None:
            composited = PILImage.alpha_composite(composited, radial)
        if highlight > 0.0:
            border = precomputed_layers.get("dark_border")
            if border is not None:
                composited = PILImage.alpha_composite(composited, border)
            inner = precomputed_layers.get("inner")
            if inner is not None:
                composited = PILImage.alpha_composite(composited, inner)
    else:
        radial = _build_radial_highlight(width, height, _clamp(highlight, 0.0, 1.0))
        if radial is not None:
            composited = PILImage.alpha_composite(composited, radial)
        if highlight > 0.0:
            dark_alpha = max(0, min(255, int(round(0.14 * (1.0 - _clamp(brightness, 0.0, 1.0) * 0.4) * 255))))
            if dark_alpha > 0:
                border = _build_dark_border(width, height, dark_alpha)
                if border is not None:
                    composited = PILImage.alpha_composite(composited, border)
            inner = _build_inner_highlight(width, height, _clamp(highlight, 0.0, 1.0))
            if inner is not None:
                composited = PILImage.alpha_composite(composited, inner)

    return composited.tobytes()


def _make_highlight_layers(width: int, height: int, highlight: float, brightness: float) -> dict:
    """Build the size/parameter-dependent highlight layers used by ``_render_frame``.

    These layers only depend on the popup size, the ``highlight`` strength, and
    the ``brightness`` value — never on the captured frame — so callers can
    cache the result and reuse it across the same popup session.
    """
    highlight_clamped = _clamp(highlight, 0.0, 1.0)
    layers: dict = {
        "radial": _build_radial_highlight(width, height, highlight_clamped),
    }
    if highlight > 0.0:
        dark_alpha = max(0, min(255, int(round(0.14 * (1.0 - _clamp(brightness, 0.0, 1.0) * 0.4) * 255))))
        layers["dark_border"] = _build_dark_border(width, height, dark_alpha) if dark_alpha > 0 else None
        layers["inner"] = _build_inner_highlight(width, height, highlight_clamped)
    else:
        layers["dark_border"] = None
        layers["inner"] = None
    return layers


def _build_rounded_mask(width: int, height: int, corner_radius: float) -> PILImage.Image | None:
    """Return an alpha mask where the rounded rect is opaque and the rest is 0.

    The C++ renderer uses a Direct2D layer clipped to a rounded rectangle; we
    mimic that with a single-channel alpha mask composited over the rendered
    frame.  The mask is rasterised with ``QPainter.drawRoundedRect`` (a true
    circular arc with anti-aliasing) rather than PIL's ``ImageDraw.rounded_rectangle``
    because the latter uses a polygon approximation — its corners show a visible
    "staircase" that becomes obvious as soon as ``QPainter.drawImage`` scales
    the physical-pixel mask down to the content area's logical-pixel size.
    Using the same primitive as the rest of the popup's chrome keeps the
    glass and the rounded rect ``path`` perfectly aligned.
    """
    if width <= 0 or height <= 0 or corner_radius <= 0.0:
        return None
    radius = min(corner_radius, min(width, height) / 2.0)
    if radius <= 0.0:
        return None

    qimage = QImage(width, height, QImage.Format_Grayscale8)
    if qimage.isNull():
        return None
    qimage.fill(0)
    painter = QPainter(qimage)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.HighQualityAntialiasing, True)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.setPen(_QtCompat.NoPen)
        painter.setBrush(QColor(255, 255, 255))
        # ``drawRoundedRect``'s bounding box is the full rect; the radius is
        # the corner radius.  Match the popup's ``path.addRoundedRect`` (which
        # uses the same primitive) so the mask and the clip path describe the
        # same shape to the pixel.
        painter.drawRoundedRect(0, 0, width, height, radius, radius)
    finally:
        painter.end()

    stride = qimage.bytesPerLine()
    ptr = qimage.bits()
    ptr.setsize(stride * height)
    return PILImage.frombuffer("L", (width, height), bytes(ptr), "raw", "L", stride, 1)


def _apply_rounded_mask(rgba_bytes: bytes, width: int, height: int, corner_radius: float) -> bytes:
    """Erase the alpha channel outside the rounded content rectangle."""
    mask = _build_rounded_mask(width, height, corner_radius)
    if mask is None:
        return rgba_bytes
    image = PILImage.frombuffer("RGBA", (width, height), rgba_bytes, "raw", "RGBA", 0, 1)
    image.putalpha(mask)
    return image.tobytes()


def _build_config(
    popup,
    *,
    margin: float,
    top_inset: float,
    scale: float,
) -> dict:
    settings = popup.settings
    # ``settings.corner_radius`` / ``settings.glass_blur_radius`` are *design*
    # values.  The popup's chrome (``_get_paint_corner_radius``) scales them
    # through ``sp()`` (UI scale) before handing the value to ``addRoundedRect``
    # or any other size-aware call.  The mask is rasterised at the popup's
    # physical pixel resolution, so we have to apply the *same* ``sp()`` first
    # and then multiply by the device pixel ratio.  Skipping ``sp()`` would
    # make the glass's corners smaller than the popup's corners whenever the
    # UI scale is anything other than 100%, exposing a strip of raw background
    # along the popup's rounded corners — the "right-angle residue" the user
    # was seeing.
    corner_radius_setting = max(0, int(getattr(settings, "corner_radius", 8) or 0))
    blur_radius_setting = max(0, int(getattr(settings, "glass_blur_radius", 20) or 0))
    return {
        "opacity": max(0.0, min(1.0, float(getattr(settings, "glass_bg_alpha", 30)) / 100.0)),
        "brightness": 0.90,
        "highlight": max(0.0, min(1.0, float(getattr(settings, "glass_edge_opacity", 0.9)))),
        "blur_radius": float(sp(blur_radius_setting) * scale),
        "saturation": 2.5,
        "corner_radius": float(sp(corner_radius_setting) * scale),
        "inset_left": margin,
        "inset_top": margin + top_inset,
        "inset_right": margin,
        "inset_bottom": margin,
    }


class GlassBackgroundRenderer:
    """Own a Python renderer context for one popup HWND."""

    def __init__(self, popup) -> None:
        self.popup = popup
        self._affinity = _DisplayAffinity()
        # Bind ``GetDpiForMonitor`` once so ``_dpi_scale`` can ask the OS for
        # the *real* monitor DPI instead of relying on ``devicePixelRatioF``.
        # The project pins ``QT_AUTO_SCREEN_SCALE_FACTOR=0`` in ``qt_compat``,
        # which forces Qt's DPR to ``1.0`` on every monitor — fine for layout,
        # wrong for the glass renderer: Win32's ``GetWindowRect`` /
        # ``BitBlt`` still return coordinates in the *monitor's* actual
        # physical pixels, so on a 150% DPI secondary monitor the captured
        # frame is 1.5× larger than Qt's logical size.  Multiplying the mask
        # corner radius by Qt's ``1.0`` left the mask's corners inside the
        # popup's corners by ~4 logical px on the 150% screen, which is
        # exactly the "right-angle residue" the user reported.
        self._user32_dpi: ctypes.WinDLL | None = None
        self._shcore: ctypes.WinDLL | None = None
        try:
            self._user32_dpi = ctypes.WinDLL("user32", use_last_error=True)
            self._user32_dpi.MonitorFromWindow.argtypes = [
                wintypes.HWND,
                wintypes.DWORD,
            ]
            self._user32_dpi.MonitorFromWindow.restype = ctypes.c_void_p
            self._shcore = ctypes.WinDLL("shcore", use_last_error=True)
            self._shcore.GetDpiForMonitor.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_uint32),
                ctypes.POINTER(ctypes.c_uint32),
            ]
            self._shcore.GetDpiForMonitor.restype = ctypes.HRESULT
        except Exception as exc:
            self._user32_dpi = None
            self._shcore = None
            logger.debug("GetDpiForMonitor not available: %s", exc, exc_info=True)
        self._buffers: list[_FrameBuffer] = [_FrameBuffer() for _ in range(BUFFER_COUNT)]
        self._frame_lock = threading.Lock()
        self._latest_index = -1
        self._next_generation = 1

        self._config_lock = threading.Lock()
        self._config: dict = {}
        self._geometry_set = False
        self._geometry: tuple[int, int, int, int] = (0, 0, 0, 0)

        self._running = False
        self._stop_requested = False
        self._first_frame_ready = False
        self._first_frame_event = threading.Event()
        self._affinity_changed = False
        self._previous_affinity = 0
        self._affinity_hwnd = 0
        self._last_error: str | None = None
        self._last_error_code = 0
        self._worker: threading.Thread | None = None
        self._fatal_reported = False

        # Cache for size-dependent static layers.  The rounded mask, radial
        # highlight, dark border, and inner highlight only depend on
        # (width, height, corner_radius, highlight, brightness) — values that
        # don't change every frame — so we rebuild them on demand and reuse
        # the same buffers across frames.
        self._static_layer_cache: dict[tuple, object] = {}

        # Geometry generation counter.  Bumped every time ``sync_geometry``
        # actually changes the captured window rectangle; the worker checks
        # this against the last generation it used so it can skip its sleep
        # and immediately produce a frame at the new position whenever the
        # user drags the popup around.
        self._geometry_generation = 0
        self._geometry_event = threading.Event()

        # Set by ``_publish_frame`` whenever a new QImage is available; the
        # main-thread repaint timer polls this to decide whether to call
        # ``popup.update()`` so the latest frame is on screen within one
        # repaint tick (~16 ms) instead of having to wait for the worker's
        # next 50 ms production tick.
        self._new_frame_event = threading.Event()
        self._last_drawn_generation = 0

        self._repaint_timer = QTimer(popup)
        # Repaint at 60 Hz so a freshly produced frame is shown to the user
        # within ~16 ms.  The worker's production rate is independent (capped
        # by ``TARGET_FPS``); the timer just polls whether a newer frame is
        # available and only triggers a paint when one is.
        self._repaint_timer.setInterval(_REPAINT_INTERVAL_MS)
        try:
            from ui.utils.interruptible_animation import set_precise_timer

            set_precise_timer(self._repaint_timer, owner="LauncherPopup._glass_repaint_timer")
        except Exception:
            logger.debug("set_precise_timer for glass renderer failed", exc_info=True)
        self._repaint_timer.timeout.connect(self._on_repaint_tick)

    @property
    def active(self) -> bool:
        return bool(self._running and self._worker is not None and self._worker.is_alive())

    def _native_error(self, prefix: str) -> GlassBackgroundError:
        code = self._last_error_code
        detail = self._last_error or "unknown glass renderer error"
        return GlassBackgroundError(f"{prefix} (code={code}): {detail}")

    def _set_error(self, code: int, message: str) -> None:
        self._last_error_code = int(code)
        self._last_error = str(message)

    def _dpi_scale(self) -> float:
        # Prefer ``GetDpiForMonitor`` so we get the *real* monitor DPI on
        # multi-monitor setups where each monitor can have its own scaling.
        # Qt's ``devicePixelRatioF()`` is pinned to ``1.0`` because the
        # project forces ``QT_AUTO_SCREEN_SCALE_FACTOR=0``; on a 150% DPI
        # secondary monitor that would under-size the mask corner radius by
        # ~33% and leave a sliver of raw background along all four corners
        # of the popup.
        if self._user32_dpi is not None and self._shcore is not None:
            try:
                hwnd = int(self.popup.winId() or 0)
                if hwnd:
                    MONITOR_DEFAULTTONEAREST = 0x00000002
                    MDT_EFFECTIVE_DPI = 0x00000000
                    hmonitor = self._user32_dpi.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
                    if hmonitor:
                        dpi_x = ctypes.c_uint32(0)
                        dpi_y = ctypes.c_uint32(0)
                        hr = self._shcore.GetDpiForMonitor(
                            hmonitor,
                            MDT_EFFECTIVE_DPI,
                            ctypes.byref(dpi_x),
                            ctypes.byref(dpi_y),
                        )
                        if hr == 0 and dpi_x.value:
                            return max(0.5, min(4.0, float(dpi_x.value) / 96.0))
            except Exception as exc:
                logger.debug("GetDpiForMonitor lookup failed: %s", exc, exc_info=True)
        try:
            return max(0.5, min(4.0, float(self.popup.devicePixelRatioF())))
        except Exception:
            return 1.0

    def sync_geometry(self) -> bool:
        hwnd = int(self.popup.winId() or 0)
        if not hwnd:
            return False
        rect = self._affinity.get_window_rect(hwnd)
        if rect is None:
            return False
        new_geometry = (int(rect.left), int(rect.top), int(rect.right - rect.left), int(rect.bottom - rect.top))
        if new_geometry[2] <= 0 or new_geometry[3] <= 0:
            return False
        with self._config_lock:
            geometry_changed = (
                not self._geometry_set
                or self._geometry[0] != new_geometry[0]
                or self._geometry[1] != new_geometry[1]
                or self._geometry[2] != new_geometry[2]
                or self._geometry[3] != new_geometry[3]
            )
            self._geometry = new_geometry
            self._geometry_set = True
            if geometry_changed:
                self._geometry_generation += 1
        if geometry_changed:
            # Wake the worker out of its inter-frame sleep so the new
            # geometry is captured on the very next iteration instead of
            # after up to ``TARGET_FRAME_INTERVAL_MS`` of stale sleep.  This
            # is what makes the glass blur "follow" the popup during drags.
            self._geometry_event.set()
        return True

    def configure(self) -> bool:
        scale = self._dpi_scale()
        margin = float(max(0, int(getattr(self.popup, "shadow_margin", 0) or 0))) * scale
        top_inset = 0.0
        try:
            top_inset = float(max(0, int(self.popup._background_top_inset()))) * scale
        except Exception:
            top_inset = 0.0
        with self._config_lock:
            self._config = _build_config(self.popup, margin=margin, top_inset=top_inset, scale=scale)
        return True

    def prepare(self, timeout_ms: int = 3000) -> None:
        if self.active:
            if not self.configure() or not self.sync_geometry():
                raise self._native_error("failed to update the active glass renderer")
            self._ensure_timer()
            return
        self.stop(destroy=True)
        # Log at INFO so the first-line diagnosis is visible without having
        # to flip ``enable_debug_log`` on.  The four numbers tell us which
        # of the three common failure paths we landed on:
        #   is_glass_renderer_available() = PIL + ctypes.WinDLL
        #   active below = whether WDA_EXCLUDEFROMCAPTURE was accepted
        logger.info(
            "Glass renderer prepare: hwnd=%s w=%s h=%s dpr=%.2f blur=%.1f",
            int(self.popup.winId() or 0),
            self.popup.width(),
            self.popup.height(),
            self._dpi_scale(),
            getattr(self.popup.settings, "glass_blur_radius", 20),
        )
        hwnd = int(self.popup.winId() or 0)
        if not hwnd:
            raise GlassBackgroundError("failed to create the glass renderer context: missing HWND")
        ok, previous = self._affinity.set_exclude_from_capture(hwnd)
        if not ok:
            raise GlassBackgroundError("failed to set WDA_EXCLUDEFROMCAPTURE on the popup HWND")
        self._affinity_changed = True
        self._previous_affinity = int(previous)
        self._affinity_hwnd = hwnd
        self._stop_requested = False
        self._first_frame_ready = False
        self._first_frame_event.clear()
        self._last_error_code = 0
        self._last_error = None
        self._geometry_generation = 0
        self._geometry_event.clear()
        self._new_frame_event.clear()
        self._last_drawn_generation = 0
        if not self.configure() or not self.sync_geometry():
            self._restore_affinity()
            raise self._native_error("failed to configure the glass renderer")
        try:
            worker = threading.Thread(
                target=self._worker_main,
                name="GlassBackgroundWorker",
                daemon=True,
            )
            self._worker = worker
            self._running = True
            worker.start()
        except Exception as exc:
            self._running = False
            self._worker = None
            self._restore_affinity()
            logger.debug("Unable to start glass renderer thread: %s", exc, exc_info=True)
            raise GlassBackgroundError(f"failed to start the glass renderer thread: {exc}") from exc
        if not self._first_frame_event.wait(timeout=max(0.0, float(timeout_ms) / 1000.0)):
            self.stop(destroy=True)
            raise self._native_error("failed to render the first glass frame")
        self._ensure_timer()

    def _restore_affinity(self) -> None:
        if not self._affinity_changed or not self._affinity_hwnd:
            return
        self._affinity.restore(self._affinity_hwnd, self._previous_affinity)
        self._affinity_changed = False

    def _ensure_timer(self) -> None:
        if not self._repaint_timer.isActive():
            self._repaint_timer.start()

    def _on_repaint_tick(self) -> None:
        if not self.active:
            if not self._fatal_reported:
                self._fatal_reported = True
                try:
                    self.popup._handle_glass_background_failure(str(self._native_error("glass rendering stopped")))
                except Exception:
                    logger.debug("Failed to report glass renderer stop", exc_info=True)
            self._repaint_timer.stop()
            return
        # The worker may still be alive (``self.active`` True) yet every
        # frame it produces fails inside ``_process_frame`` and never gets
        # published.  Detect that via ``_last_error`` so the user gets a
        # tray icon message + log entry instead of a silent "icons only"
        # popup.
        if self._last_error and not self._fatal_reported:
            self._fatal_reported = True
            try:
                self.popup._handle_glass_background_failure(
                    str(self._native_error("glass renderer reported a per-frame error"))
                )
            except Exception:
                logger.debug("Failed to report glass renderer error", exc_info=True)
            self._repaint_timer.stop()
            return
        # Poll for a new frame.  The worker sets ``_new_frame_event`` from
        # ``_publish_frame``; we only call ``popup.update()`` when the
        # generation has advanced past the last one we drew, so the popup
        # repaints exactly once per produced frame (not 60 times a second).
        if not self._new_frame_event.is_set():
            return
        with self._frame_lock:
            current_index = self._latest_index
            if current_index < 0 or current_index >= BUFFER_COUNT:
                return
            current_generation = self._buffers[current_index].generation
            if current_generation == self._last_drawn_generation:
                return
            self._last_drawn_generation = current_generation
        if self.popup.isVisible():
            self.popup.update()

    def _snapshot(self) -> tuple[dict | None, tuple[int, int, int, int] | None]:
        with self._config_lock:
            config = dict(self._config)
            geometry = self._geometry if self._geometry_set else None
        return config, geometry

    def _worker_main(self) -> None:
        try:
            interval = 1.0 / max(1, TARGET_FPS)
            next_frame = time.perf_counter()
            last_geometry_generation = -1
            while not self._stop_requested:
                # Honor a geometry-change wake-up immediately so the worker
                # doesn't sit on its sleep while the user is dragging the
                # popup around; otherwise the new position would not be
                # captured until the next ``interval`` boundary.
                self._geometry_event.wait(timeout=0.0)
                self._geometry_event.clear()
                config, geometry = self._snapshot()
                if config is None or geometry is None:
                    if not self.sync_geometry():
                        self._set_error(1, "glass target window has no geometry")
                        break
                    config, geometry = self._snapshot()
                    if config is None or geometry is None:
                        self._set_error(1, "glass target window has no geometry")
                        break
                geometry_generation = self._geometry_generation
                x, y, width, height = geometry
                rect = _Rect(left=int(x), top=int(y), right=int(x + width), bottom=int(y + height))
                captured = self._affinity.capture_desktop(rect)
                if not captured:
                    self._set_error(3, "unable to capture the desktop behind the popup")
                    break
                self._process_frame(captured, width, height, config)
                if not self._first_frame_ready:
                    self._first_frame_ready = True
                    self._first_frame_event.set()
                    logger.info(
                        "Glass first frame published: %sx%s (screen rect=%s,%s %sx%s)",
                        width,
                        height,
                        int(geometry[0]),
                        int(geometry[1]),
                        int(geometry[2]),
                        int(geometry[3]),
                    )
                last_geometry_generation = geometry_generation
                # If the geometry changed since the last frame (or since we
                # started this loop), skip the inter-frame sleep and grab
                # the next frame immediately.  This is what keeps the blur
                # following the cursor while the user drags the popup.
                if self._geometry_generation != last_geometry_generation:
                    next_frame = time.perf_counter()
                    continue
                next_frame += interval
                now = time.perf_counter()
                if next_frame > now:
                    time.sleep(min(0.05, next_frame - now))
                else:
                    next_frame = now
        except Exception as exc:
            # Log at ERROR so a crashing worker is visible without flipping
            # ``enable_debug_log`` on — see the same reasoning in
            # ``_process_frame`` below.
            logger.error("Glass worker crashed: %s", exc, exc_info=True)
            self._set_error(8, f"glass worker crashed: {exc}")
        finally:
            self._running = False

    def _process_frame(self, captured: bytes, width: int, height: int, config: dict) -> None:
        try:
            left = _clamp(float(config.get("inset_left", 0.0)), 0.0, float(width))
            top = _clamp(float(config.get("inset_top", 0.0)), 0.0, float(height))
            right = max(left, float(width) - max(0.0, float(config.get("inset_right", 0.0))))
            bottom = max(top, float(height) - max(0.0, float(config.get("inset_bottom", 0.0))))
            content_w = max(1, int(round(right - left)))
            content_h = max(1, int(round(bottom - top)))
            if left >= 1.0 or top >= 1.0 or right < width - 1.0 or bottom < height - 1.0:
                src_image = PILImage.frombuffer("RGBA", (width, height), captured, "raw", "BGRA", width * 4, 1)
                cropped = src_image.crop((int(left), int(top), int(right), int(bottom)))
            else:
                cropped = PILImage.frombuffer("RGBA", (width, height), captured, "raw", "BGRA", width * 4, 1)
            cropped = cropped.copy()
            if cropped.size != (content_w, content_h):
                cropped = cropped.resize((content_w, content_h), PILImage.Resampling.BILINEAR)
            content_bytes = cropped.tobytes()
            blur_radius = float(config.get("blur_radius", 0.0))
            highlight = float(config.get("highlight", 0.0))
            brightness = float(config.get("brightness", 0.9))
            # The highlight/border overlays only depend on (size, highlight,
            # brightness); rebuild them only when one of those changes.
            layer_cache_key = (content_w, content_h, round(highlight, 3), round(brightness, 3))
            layers_obj = self._static_layer_cache.get(layer_cache_key)
            if layers_obj is None:
                layers_obj = _make_highlight_layers(content_w, content_h, highlight, brightness)
                self._static_layer_cache[layer_cache_key] = layers_obj
            layers: dict | None = layers_obj  # type: ignore[assignment]
            rendered = _render_frame(
                content_bytes,
                content_w,
                content_h,
                content_w * 4,
                blur_radius=blur_radius,
                saturation=float(config.get("saturation", 2.5)),
                highlight=highlight,
                brightness=brightness,
                opacity=float(config.get("opacity", 0.3)),
                precomputed_layers=layers,
            )
            if not rendered:
                return
            corner_radius = float(config.get("corner_radius", 0.0))
            # The rounded mask only depends on (size, corner_radius); cache it
            # so we don't rebuild it 20+ times a second.  The C++ renderer
            # didn't have this cost because Direct2D layers clip at composite
            # time; the Python version does the clip in software.
            mask_cache_key = (content_w, content_h, round(corner_radius, 2))
            cached_mask = self._static_layer_cache.get(mask_cache_key)
            if cached_mask is None:
                cached_mask = _build_rounded_mask(content_w, content_h, corner_radius)
                if cached_mask is not None:
                    self._static_layer_cache[mask_cache_key] = cached_mask
            cached_mask_image: PILImage.Image | None = cached_mask  # type: ignore[assignment]
            if cached_mask_image is not None:
                image = PILImage.frombuffer("RGBA", (content_w, content_h), rendered, "raw", "RGBA", 0, 1)
                image.putalpha(cached_mask_image)
                masked = image.tobytes()
            else:
                masked = _apply_rounded_mask(rendered, content_w, content_h, corner_radius)
            qimage = QImage(
                masked,
                content_w,
                content_h,
                content_w * 4,
                QImage.Format_ARGB32_Premultiplied,
            ).copy()
            self._publish_frame(qimage, content_w, content_h)
        except Exception as exc:
            # Log at ERROR (not DEBUG) so a broken per-frame pipeline is
            # visible in ``config/error.log`` even when ``enable_debug_log``
            # is false — otherwise the popup just shows the icons with no
            # background and we have no breadcrumb to find out why.
            logger.error("Glass frame processing failed: %s", exc, exc_info=True)
            self._set_error(8, f"frame processing failed: {exc}")

    def _publish_frame(self, image: QImage, width: int, height: int) -> None:
        published = False
        with self._frame_lock:
            for offset in range(1, BUFFER_COUNT + 1):
                candidate = (self._latest_index + offset) % BUFFER_COUNT
                if self._buffers[candidate].readers == 0:
                    buffer = self._buffers[candidate]
                    buffer.image = image
                    buffer.width = width
                    buffer.height = height
                    buffer.stride = width * 4
                    buffer.generation = self._next_generation
                    self._next_generation += 1
                    self._latest_index = candidate
                    published = True
                    break
        if published:
            # Wake the repaint timer so the new frame is on screen within
            # one repaint interval (~16 ms) instead of having to wait for
            # the worker's next production tick.
            self._new_frame_event.set()

    def draw(self, painter) -> bool:
        if not self.active and not self._first_frame_ready:
            return False
        with self._frame_lock:
            index = self._latest_index
            if index < 0 or index >= BUFFER_COUNT:
                return False
            buffer = self._buffers[index]
            if buffer.image is None or buffer.image.isNull():
                return False
            buffer.readers += 1
            image = buffer.image
        try:
            target_rect = self.popup.rect()
            scale = self._dpi_scale()
            with self._config_lock:
                config = dict(self._config)
            # ``_process_frame`` already cropped the captured frame down to the
            # content rect (popup rect minus ``shadow_margin`` / top inset),
            # so the QImage we hand back is *only* the content area in
            # physical pixels.  Earlier revisions drew it at logical (0, 0)
            # stretched to the full popup rect, which shifted the glass
            # up-and-left by ``shadow_margin`` and stretched the inner
            # content across the shadow ring — the result looked like the
            # blur was sourced from a different place than the window.
            inset_left = float(config.get("inset_left", 0.0)) / scale
            inset_top = float(config.get("inset_top", 0.0)) / scale
            inset_right = float(config.get("inset_right", 0.0)) / scale
            inset_bottom = float(config.get("inset_bottom", 0.0)) / scale
            content_x = int(round(inset_left))
            content_y = int(round(inset_top))
            content_w = max(1, int(round(target_rect.width() - inset_left - inset_right)))
            content_h = max(1, int(round(target_rect.height() - inset_top - inset_bottom)))
            painter.drawImage(
                QRect(content_x, content_y, content_w, content_h),
                image,
            )
            return True
        finally:
            with self._frame_lock:
                if self._buffers[index].readers > 0:
                    self._buffers[index].readers -= 1

    def stop(self, *, destroy: bool = False) -> None:
        self._stop_requested = True
        # Stop the repaint timer before joining the worker so a pending
        # ``_on_repaint_tick`` can't observe the worker mid-shutdown and
        # report a normal stop as a glass failure.
        try:
            self._repaint_timer.stop()
        except Exception:
            logger.debug("Stopping glass repaint timer failed", exc_info=True)
        # Unblock the worker if it is currently sitting on the geometry
        # wait, otherwise the join below can stall for the full timeout.
        self._geometry_event.set()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=1.0)
        self._worker = None
        self._running = False
        self._first_frame_event.set()
        self._first_frame_ready = False
        self._new_frame_event.clear()
        if self._affinity_changed:
            self._restore_affinity()
        if destroy:
            with self._frame_lock:
                self._latest_index = -1
                for buffer in self._buffers:
                    buffer.image = None
                    buffer.width = 0
                    buffer.height = 0
                    buffer.stride = 0
                    buffer.generation = 0
            # Drop the static-layer cache so the next prepare() rebuilds it
            # at the new geometry; otherwise we'd keep stale masks around if
            # the popup is resized.
            self._static_layer_cache.clear()
            self._geometry_generation = 0
            self._geometry_event.clear()
            self._last_drawn_generation = 0
            self._fatal_reported = False

    def close(self) -> None:
        self.stop(destroy=True)


def is_glass_renderer_available() -> bool:
    """Return True when the Python glass renderer can run on this host."""
    try:
        from PIL import Image, ImageFilter  # noqa: F401
    except Exception:
        return False
    if not hasattr(ctypes, "WinDLL"):
        return False
    return True
