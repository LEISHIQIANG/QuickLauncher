"""Pixel-snap helpers for high-DPI rendering.

In QuickLauncher every paint event that draws hairline borders, focus
rings or one-pixel separators must use :class:`QPen` configured with
``setCosmetic(True)``; otherwise the line width is multiplied by the
device pixel ratio and the border looks fat on 200% DPI displays.

The helpers here wrap the common patterns:

* :func:`snap_rect` – return a :class:`QRectF` whose edges sit on whole
  pixel coordinates (0.5 offset for thin strokes).
* :func:`make_cosmetic_pen` – build a 1-px cosmetic :class:`QPen`.
* :func:`stroke_path` – convenience that strokes a :class:`QPainterPath`
  with a cosmetic pen.
* :func:`create_pixmap` – build a :class:`QPixmap` that honours the
  current device pixel ratio, so icons and thumbnails stay crisp on
  150% / 200% / 250% DPI displays.
* :func:`build_rounded_mask` – build a :class:`QBitmap` matching a
  rounded-rectangle shape, suitable for ``QWidget.setMask()``. This is
  used by :class:`ui.themed_tool_window.ThemedToolWindow` and
  :class:`LauncherPopup` to defeat per-pixel alpha hit testing in
  ``WA_TranslucentBackground`` mode and stop mouse events from passing
  through transparent corners.

Example
-------
::

    from ui.utils.pixel_snap import snap_rect, make_cosmetic_pen

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = snap_rect(self.rect())
        p.setPen(make_cosmetic_pen(QColor(0, 0, 0, 80)))
        p.drawRoundedRect(rect, 6, 6)
"""

from __future__ import annotations

import logging
import time

from qt_compat import (
    QBitmap,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRect,
    QRectF,
    QRegion,
    QSize,
    Qt,
    QWidget,
)
from ui.utils.ui_scale import MDT_EFFECTIVE_DPI

__all__ = [
    "snap_rect",
    "make_cosmetic_pen",
    "stroke_path",
    "create_pixmap",
    "device_pixel_ratio",
    "build_rounded_mask",
]

logger = logging.getLogger(__name__)


def _is_pixel_snap_enabled() -> bool:
    """Return ``True`` so cosmetic pens stay 1 physical pixel wide on all DPIs.

    When cosmetic painting is disabled, 1-px hairline strokes are
    multiplied by the device pixel ratio and appear fat / blurry on
    high-DPI displays.

    If cosmetic pens introduce rendering artifacts in extreme edge cases
    (e.g. >300% scaling), the feature can be gated via an environment
    variable ``QL_PIXEL_SNAP`` set to ``0``.

    Result is cached to avoid repeated ``os.environ`` lookups on every
    paint event.
    """
    global _PIXEL_SNAP_CACHED, _PIXEL_SNAP_ENABLED
    if not _PIXEL_SNAP_CACHED:
        import os

        _PIXEL_SNAP_ENABLED = os.environ.get("QL_PIXEL_SNAP", "1") != "0"
        _PIXEL_SNAP_CACHED = True
    return _PIXEL_SNAP_ENABLED


_PIXEL_SNAP_CACHED = False
_PIXEL_SNAP_ENABLED = True


def _to_rectf(rect: QRect | QRectF) -> QRectF:
    if isinstance(rect, QRectF):
        return rect
    return QRectF(rect)


def snap_rect(rect: QRect | QRectF, *, inset: float = 0.5) -> QRectF:
    """Return ``rect`` with edges snapped to whole pixels.

    A positive ``inset`` shrinks the rectangle by the given amount on each
    side – useful when stroking a 1-px cosmetic pen so the stroke fits
    entirely inside the widget bounds.
    """

    rf = _to_rectf(rect)
    if inset:
        rf = rf.adjusted(inset, inset, -inset, -inset)
    if not _is_pixel_snap_enabled():
        return rf
    x = round(rf.left())
    y = round(rf.top())
    w = round(rf.right()) - x
    h = round(rf.bottom()) - y
    return QRectF(float(x), float(y), float(w), float(h))


def make_cosmetic_pen(color: QColor, width: float | int = 1, style: object | None = None) -> QPen:
    """Return a cosmetic :class:`QPen` with the given colour and width.

    ``style`` is an optional ``Qt.PenStyle`` value (e.g. ``Qt.SolidLine``).
    """

    from qt_compat import QPen as _QPen
    from qt_compat import Qt as _Qt

    pen = _QPen(QColor(color))
    pen.setWidth(max(1, round(float(width))))
    if _is_pixel_snap_enabled():
        pen.setCosmetic(True)
    else:
        pen.setCosmetic(False)
    pen.setJoinStyle(_Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(_Qt.PenCapStyle.RoundCap)
    if style is not None:
        pen.setStyle(style)  # type: ignore[arg-type]
    return pen


def stroke_path(
    painter: QPainter,
    path: QPainterPath,
    color: QColor,
    width: int = 1,
) -> None:
    """Stroke ``path`` on ``painter`` with a cosmetic pen."""

    if not isinstance(path, QPainterPath):
        return
    from qt_compat import QtCompat

    painter.save()
    painter.setPen(make_cosmetic_pen(color, width=width))
    painter.setBrush(QtCompat.NoBrush)
    painter.drawPath(path)
    painter.restore()


def _win32_device_pixel_ratio(hwnd: int | None = None) -> float | None:
    """Read the true hardware DPR via ``GetDpiForMonitor`` (Win32).

    Returns ``None`` when the Win32 API is unavailable or the call fails.

    Results are cached per monitor handle for 5 seconds to avoid
    redundant Win32 syscalls during rapid paint events.
    """
    try:
        import ctypes
        from ctypes import wintypes

        if hwnd:
            hmon = ctypes.windll.user32.MonitorFromWindow(
                wintypes.HWND(hwnd),
                2,  # MONITOR_DEFAULTTONEAREST
            )
        else:
            hmon = ctypes.windll.user32.MonitorFromPoint(
                wintypes.POINT(0, 0),
                1,  # MONITOR_DEFAULTTOPRIMARY
            )
        if not hmon:
            return None

        # --- per-monitor cache with 5-second TTL ---
        _now = time.monotonic()
        if hmon in _DPI_CACHE and _now - _DPI_CACHE[hmon][0] < 5.0:
            return _DPI_CACHE[hmon][1]

        dpi_x = ctypes.c_uint()
        dpi_y = ctypes.c_uint()
        hr = ctypes.windll.shcore.GetDpiForMonitor(
            hmon,
            MDT_EFFECTIVE_DPI,
            ctypes.byref(dpi_x),
            ctypes.byref(dpi_y),
        )
        if hr == 0 and dpi_x.value > 0:
            result = float(dpi_x.value) / 96.0
            _DPI_CACHE[hmon] = (_now, result)
            # Limit cache size to avoid leaking stale entries
            if len(_DPI_CACHE) > 16:
                _DPI_CACHE.pop(next(iter(_DPI_CACHE)), None)
            return result
    except Exception:
        logger.debug("Win32 DPI detection failed in device_pixel_ratio", exc_info=True)
    return None


# Per-monitor DPR cache: {hmon: (timestamp, ratio)}
_DPI_CACHE: dict[int, tuple[float, float]] = {}


def device_pixel_ratio(widget: object | None = None) -> float:
    """Return the device pixel ratio for the given widget (or app default).

    Since ``QT_AUTO_SCREEN_SCALE_FACTOR=0`` pins Qt's DPR to 1.0,
    this function falls back to ``GetDpiForMonitor`` (Win32) to obtain
    the true hardware pixel ratio.  This ensures pixmaps, icons and
    thumbnails are rendered at the correct resolution on 150% / 200% /
    250% DPI displays.

    Falls back to ``1.0`` when neither Qt nor Win32 can provide a DPR
    (e.g. in headless tests before QApplication is created).
    """

    # --- Qt DPR query (pinned to 1.0 due to QT_AUTO_SCREEN_SCALE_FACTOR=0) ---
    qt_dpr: float | None = None
    if widget is not None and isinstance(widget, QWidget):
        try:
            qt_dpr = float(widget.devicePixelRatio())
        except (AttributeError, RuntimeError, TypeError):
            logger.debug("widget device pixel ratio unavailable", exc_info=True)
    if qt_dpr is None or qt_dpr == 1.0:
        try:
            from typing import Any, cast

            from qt_compat import QApplication

            app = QApplication.instance()
            if app is not None:
                try:
                    qt_dpr = float(cast(Any, app).devicePixelRatio())
                except (AttributeError, RuntimeError, TypeError):
                    logger.debug("app devicePixelRatio unavailable", exc_info=True)
        except (ImportError, AttributeError, RuntimeError, TypeError):
            logger.debug("application device pixel ratio unavailable", exc_info=True)

    # --- If Qt DPR is 1.0, fall back to Win32 hardware DPR ---
    if qt_dpr is not None and qt_dpr != 1.0:
        return qt_dpr

    hwnd = 0
    if widget is not None and isinstance(widget, QWidget):
        try:
            hwnd = int(widget.winId() or 0)
        except Exception:
            hwnd = 0

    win32_dpr = _win32_device_pixel_ratio(hwnd)
    if win32_dpr is not None:
        return win32_dpr

    return 1.0


def create_pixmap(
    width: int,
    height: int,
    widget: QWidget | None = None,
    *,
    fill_color: QColor | None = None,
) -> QPixmap:
    """Build a :class:`QPixmap` honouring the current device pixel ratio.

    On 200% DPI displays a 16x16 icon needs a 32x32 backing pixmap or
    Qt will downscale a low-resolution pixmap and the icon will look
    blurry. This helper allocates the right backing size and configures
    the pixmap's ``devicePixelRatio`` so Qt knows how to scale on draw.
    """

    dpr = device_pixel_ratio(widget)
    backing_w = max(1, int(round(width * dpr)))
    backing_h = max(1, int(round(height * dpr)))
    pix = QPixmap(backing_w, backing_h)
    try:
        pix.setDevicePixelRatio(dpr)
    except AttributeError:
        logger.debug("pixmap device pixel ratio API unavailable", exc_info=True)
    if fill_color is not None and not pix.isNull():
        pix.fill(QColor(fill_color))
    return pix


def build_rounded_mask(
    width: int,
    height: int,
    radius: int,
) -> QRegion:
    """Build a :class:`QRegion` matching a rounded-rectangle shape.

    The result is suitable for ``QWidget.setMask()`` on a window that
    uses ``WA_TranslucentBackground``. The mask is built via a
    per-pixel :class:`QBitmap` so the rounded corners stay smooth on
    any DPI (using ``QPainterPath.toFillPolygon().toPolygon()`` would
    collapse to zero-area triangles at the corners on integer
    rounding and create tiny "holes" that allow mouse events to
    pass through the painted body).

    Parameters
    ----------
    width, height:
        Window size in logical pixels. The returned region covers the
        full window; the four corners outside the rounded rectangle
        become click-through.
    radius:
        Corner radius in logical pixels.
    """

    if width <= 0 or height <= 0:
        return QRegion()
    w = int(width)
    h = int(height)
    r = max(0, int(radius))
    if r <= 0:
        return QRegion(0, 0, w, h)

    bitmap = QBitmap(QSize(w, h))
    bitmap.fill(Qt.GlobalColor.color0)  # transparent
    painter = QPainter(bitmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.color1)  # opaque
        painter.drawRoundedRect(0, 0, w, h, r, r)
    finally:
        painter.end()
    return QRegion(bitmap)
