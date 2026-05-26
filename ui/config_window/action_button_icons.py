"""Small unified icons for config action buttons."""

from qt_compat import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QRectF, QtCompat


def create_action_button_icon(kind: str, theme: str, size: int = 18) -> QIcon:
    """Create a muted line icon for footer action buttons."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QtCompat.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QtCompat.Antialiasing)
    painter.setRenderHint(QtCompat.SmoothPixmapTransform)
    painter.scale(size / 18.0, size / 18.0)

    if theme == "dark":
        ink = QColor(224, 232, 242, 178)
        soft = QColor(146, 165, 190, 135)
        accent = QColor(122, 166, 222, 165)
    else:
        ink = QColor(38, 49, 64, 170)
        soft = QColor(96, 112, 132, 125)
        accent = QColor(57, 109, 178, 150)

    pen = QPen(ink, 1.25)
    pen.setCapStyle(QtCompat.RoundCap)
    pen.setJoinStyle(QtCompat.RoundJoin)
    soft_pen = QPen(soft, 1.1)
    soft_pen.setCapStyle(QtCompat.RoundCap)
    soft_pen.setJoinStyle(QtCompat.RoundJoin)
    accent_pen = QPen(accent, 1.3)
    accent_pen.setCapStyle(QtCompat.RoundCap)
    accent_pen.setJoinStyle(QtCompat.RoundJoin)

    def line(x1, y1, x2, y2, color_pen=pen):
        painter.setPen(color_pen)
        painter.drawLine(int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2)))

    def rounded_rect(x, y, w, h, color_pen=pen, radius=2.0):
        painter.setPen(color_pen)
        painter.setBrush(QtCompat.NoBrush)
        painter.drawRoundedRect(QRectF(x, y, w, h), radius, radius)

    def ellipse(x, y, w, h, color_pen=pen):
        painter.setPen(color_pen)
        painter.setBrush(QtCompat.NoBrush)
        painter.drawEllipse(QRectF(x, y, w, h))

    if kind == "plugin":
        rounded_rect(3.3, 4.8, 10.0, 9.8)
        line(6.1, 4.8, 6.1, 3.6, soft_pen)
        line(10.5, 4.8, 10.5, 3.6, soft_pen)
        line(6.1, 14.6, 6.1, 15.7, soft_pen)
        line(10.5, 14.6, 10.5, 15.7, soft_pen)
        line(2.2, 7.6, 3.3, 7.6, soft_pen)
        line(2.2, 11.8, 3.3, 11.8, soft_pen)
        line(13.3, 7.6, 15.0, 7.6, soft_pen)
        line(13.3, 11.8, 15.0, 11.8, soft_pen)
        painter.setPen(QtCompat.NoPen)
        painter.setBrush(QBrush(accent))
        painter.drawRoundedRect(QRectF(6.0, 7.3, 4.6, 4.6), 1.1, 1.1)
    elif kind == "folder":
        path = QPainterPath()
        path.moveTo(2.8, 6.5)
        path.lineTo(6.5, 6.5)
        path.lineTo(7.8, 4.9)
        path.lineTo(15.2, 4.9)
        path.lineTo(15.2, 14.2)
        path.lineTo(2.8, 14.2)
        path.closeSubpath()
        painter.setPen(pen)
        painter.setBrush(QtCompat.NoBrush)
        painter.drawPath(path)
        line(10.8, 8.7, 10.8, 12.3, accent_pen)
        line(9.0, 10.5, 12.6, 10.5, accent_pen)
    elif kind == "file":
        rounded_rect(4.2, 2.9, 9.6, 12.3)
        line(10.2, 2.9, 13.8, 6.5, soft_pen)
        line(10.2, 2.9, 10.2, 6.5, soft_pen)
        line(10.2, 6.5, 13.8, 6.5, soft_pen)
        line(6.3, 8.6, 11.7, 8.6, accent_pen)
        line(6.3, 11.2, 11.0, 11.2, soft_pen)
    elif kind == "hotkey":
        rounded_rect(2.7, 4.3, 12.6, 9.7)
        painter.setPen(QtCompat.NoPen)
        painter.setBrush(QBrush(accent))
        for x in (4.9, 8.1, 11.3):
            painter.drawRoundedRect(QRectF(x, 6.8, 1.5, 1.5), 0.7, 0.7)
        painter.setBrush(QBrush(soft))
        for x in (4.9, 8.1, 11.3):
            painter.drawRoundedRect(QRectF(x, 9.8, 1.5, 1.5), 0.7, 0.7)
        painter.drawRoundedRect(QRectF(5.1, 12.2, 7.9, 1.2), 0.6, 0.6)
    elif kind == "url":
        ellipse(3.2, 3.2, 11.6, 11.6)
        painter.setPen(soft_pen)
        painter.drawArc(QRectF(5.0, 3.2, 8.0, 11.6), 90 * 16, 180 * 16)
        painter.drawArc(QRectF(5.0, 3.2, 8.0, 11.6), -90 * 16, 180 * 16)
        line(3.9, 9.0, 14.1, 9.0, accent_pen)
    elif kind == "command":
        rounded_rect(2.8, 3.9, 12.4, 10.4)
        line(2.8, 6.6, 15.2, 6.6, soft_pen)
        painter.setPen(QtCompat.NoPen)
        painter.setBrush(QBrush(accent))
        painter.drawEllipse(QRectF(5.0, 5.0, 1.2, 1.2))
        painter.drawEllipse(QRectF(7.3, 5.0, 1.2, 1.2))
        line(5.3, 8.6, 7.3, 10.2, accent_pen)
        line(7.3, 10.2, 5.3, 11.8, accent_pen)
        line(9.3, 11.7, 12.3, 11.7, soft_pen)
    elif kind == "system":
        painter.setPen(pen)
        painter.drawEllipse(QRectF(5.0, 5.0, 8.0, 8.0))
        for x1, y1, x2, y2 in (
            (9, 2.9, 9, 4.4),
            (9, 13.6, 9, 15.1),
            (2.9, 9, 4.4, 9),
            (13.6, 9, 15.1, 9),
            (4.7, 4.7, 5.8, 5.8),
            (12.2, 12.2, 13.3, 13.3),
            (13.3, 4.7, 12.2, 5.8),
            (5.8, 12.2, 4.7, 13.3),
        ):
            line(x1, y1, x2, y2, soft_pen)
        painter.setPen(accent_pen)
        painter.drawEllipse(QRectF(7.2, 7.2, 3.6, 3.6))
    elif kind == "appearance":
        ellipse(3.4, 3.4, 11.2, 11.2)
        painter.setPen(QtCompat.NoPen)
        painter.setBrush(QBrush(accent))
        painter.drawEllipse(QRectF(6.4, 5.7, 1.5, 1.5))
        painter.drawEllipse(QRectF(10.1, 6.3, 1.5, 1.5))
        painter.drawEllipse(QRectF(6.9, 10.1, 1.5, 1.5))
        painter.setPen(soft_pen)
        painter.setBrush(QtCompat.NoBrush)
        painter.drawArc(QRectF(8.0, 9.0, 5.8, 4.7), 185 * 16, 130 * 16)
    elif kind == "interaction":
        line(5.0, 4.6, 5.0, 11.2)
        line(7.8, 3.8, 7.8, 11.4)
        line(10.6, 5.2, 10.6, 11.6)
        line(13.2, 7.4, 13.2, 11.9)
        painter.setPen(accent_pen)
        painter.drawArc(QRectF(4.8, 9.6, 9.2, 5.6), 200 * 16, 145 * 16)
    elif kind == "settings_data":
        rounded_rect(3.6, 4.6, 10.8, 9.2)
        line(5.0, 7.0, 13.0, 7.0, accent_pen)
        line(7.0, 10.0, 11.0, 10.0, soft_pen)
    elif kind == "about":
        ellipse(3.6, 3.6, 10.8, 10.8, accent_pen)
        painter.setPen(QtCompat.NoPen)
        painter.setBrush(QBrush(ink))
        painter.drawEllipse(QRectF(8.2, 6.0, 1.6, 1.6))
        painter.drawRoundedRect(QRectF(8.2, 8.7, 1.6, 4.3), 0.8, 0.8)
    elif kind in ("support", "star"):
        painter.setPen(accent_pen)
        painter.drawEllipse(QRectF(3.4, 3.4, 11.2, 11.2))
        heart = QPainterPath()
        heart.moveTo(9.0, 12.5)
        heart.cubicTo(5.7, 10.4, 5.0, 8.6, 5.0, 7.2)
        heart.cubicTo(5.0, 5.7, 6.2, 4.8, 7.5, 4.8)
        heart.cubicTo(8.2, 4.8, 8.7, 5.1, 9.0, 5.7)
        heart.cubicTo(9.3, 5.1, 9.8, 4.8, 10.5, 4.8)
        heart.cubicTo(11.8, 4.8, 13.0, 5.7, 13.0, 7.2)
        heart.cubicTo(13.0, 8.6, 12.3, 10.4, 9.0, 12.5)
        painter.setPen(QtCompat.NoPen)
        painter.setBrush(QBrush(accent))
        painter.drawPath(heart)
    else:
        painter.setPen(QtCompat.NoPen)
        painter.setBrush(QBrush(accent))
        painter.drawEllipse(QRectF(6.5, 6.5, 5.0, 5.0))

    painter.end()
    return QIcon(pixmap)
