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
    return False


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


def device_pixel_ratio(widget: object | None = None) -> float:
    """Return the device pixel ratio for the given widget (or app default).

    Falls back to ``1.0`` if the QApplication instance is not available
    (e.g. in tests that build widgets before instantiating QApplication).
    """

    if widget is not None and isinstance(widget, QWidget):
        try:
            return float(widget.devicePixelRatio())
        except (AttributeError, RuntimeError, TypeError):
            logger.debug("widget device pixel ratio unavailable", exc_info=True)
    try:
        from typing import Any, cast

        from qt_compat import QApplication

        app = QApplication.instance()
        if app is not None:
            try:
                return float(cast(Any, app).devicePixelRatio())
            except (AttributeError, RuntimeError, TypeError):
                return 1.0
    except (ImportError, AttributeError, RuntimeError, TypeError):
        logger.debug("application device pixel ratio unavailable", exc_info=True)
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
