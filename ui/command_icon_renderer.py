"""Theme-aware vector-style icons for selected built-in commands."""

from __future__ import annotations

from core.command_icon_catalog import BUILTIN_COMMAND_ICON_IDS, builtin_command_id_from_icon_path
from qt_compat import QColor, QPainter, QPainterPath, QPen, QPixmap, QPointF, QRectF, QtCompat

_ICON_CACHE: dict[tuple[str, int, str], QPixmap] = {}

_ACCENT_COLORS = {
    "base64": "#3478F6",
    "clip": "#00A69C",
    "color": "#AF52DE",
    "config": "#3478F6",
    "copy-path": "#5856D6",
    "dns": "#34A853",
    "env": "#3478F6",
    "git": "#E94F37",
    "hash": "#5856D6",
    "help": "#8E5BD9",
    "ip": "#2684FF",
    "json": "#D88700",
    "jwt": "#8E5BD9",
    "netdiag": "#19A974",
    "port": "#F08030",
    "process": "#E55353",
    "qr": "#30343B",
    "restart": "#3478F6",
    "selected": "#00A6D6",
    "sysreport": "#2D9C6B",
    "timestamp": "#E68A00",
    "topmost": "#F08030",
    "urlencode": "#007FAD",
    "uuid": "#7A5AF8",
    "wifi": "#168AAD",
}


def render_builtin_command_icon(command_id: str, size: int, theme: str = "dark") -> QPixmap | None:
    """Render a selected command icon without loading user-editable image files."""
    command_id = str(command_id or "").strip().lower()
    if command_id not in BUILTIN_COMMAND_ICON_IDS:
        return None

    size = max(16, int(size or 0))
    normalized_theme = "dark" if str(theme or "").lower() == "dark" else "light"
    cache_key = (command_id, size, normalized_theme)
    cached = _ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached

    pixmap = QPixmap(size, size)
    pixmap.fill(QtCompat.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QtCompat.Antialiasing)
    painter.setRenderHint(QtCompat.TextAntialiasing)
    painter.scale(size / 100.0, size / 100.0)

    accent = QColor(_ACCENT_COLORS[command_id])
    if normalized_theme == "dark":
        background = QColor(accent)
        background.setAlpha(210)
        foreground = QColor("#FFFFFF")
    else:
        background = accent.lighter(178)
        background.setAlpha(235)
        foreground = accent.darker(165)

    painter.setPen(QtCompat.NoPen)
    painter.setBrush(background)
    painter.drawRoundedRect(QRectF(5, 5, 90, 90), 22, 22)

    pen = QPen(foreground, 6)
    pen.setCapStyle(QtCompat.RoundCap)
    pen.setJoinStyle(QtCompat.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QtCompat.NoBrush)
    _draw_glyph(painter, command_id, foreground)
    painter.end()

    _ICON_CACHE[cache_key] = pixmap
    return pixmap


def render_builtin_command_icon_path(icon_path: str, size: int, theme: str = "dark") -> QPixmap | None:
    command_id = builtin_command_id_from_icon_path(icon_path)
    if not command_id:
        return None
    return render_builtin_command_icon(command_id, size, theme)


def _draw_glyph(painter: QPainter, command_id: str, color: QColor) -> None:
    draw = {
        "base64": _draw_base64,
        "clip": _draw_clipboard,
        "color": _draw_palette,
        "config": _draw_gear,
        "copy-path": _draw_copy_path,
        "dns": _draw_dns,
        "env": _draw_sliders,
        "git": _draw_git,
        "hash": _draw_hash,
        "help": _draw_help,
        "ip": _draw_globe,
        "json": _draw_json,
        "jwt": _draw_jwt,
        "netdiag": _draw_netdiag,
        "port": _draw_port,
        "process": _draw_process,
        "qr": _draw_qr,
        "restart": _draw_restart,
        "selected": _draw_selected,
        "sysreport": _draw_sysreport,
        "timestamp": _draw_clock,
        "topmost": _draw_pin,
        "urlencode": _draw_urlencode,
        "uuid": _draw_uuid,
        "wifi": _draw_wifi,
    }[command_id]
    draw(painter, color)


def _draw_gear(p: QPainter, _color: QColor) -> None:
    p.drawEllipse(QRectF(31, 31, 38, 38))
    p.drawEllipse(QRectF(43, 43, 14, 14))
    for x1, y1, x2, y2 in (
        (50, 20, 50, 30),
        (50, 70, 50, 80),
        (20, 50, 30, 50),
        (70, 50, 80, 50),
        (29, 29, 36, 36),
        (64, 64, 71, 71),
        (29, 71, 36, 64),
        (64, 36, 71, 29),
    ):
        p.drawLine(x1, y1, x2, y2)


def _draw_help(p: QPainter, color: QColor) -> None:
    p.drawEllipse(QRectF(22, 22, 56, 56))
    p.drawArc(QRectF(38, 31, 25, 24), 20 * 16, 220 * 16)
    p.drawLine(50, 53, 50, 60)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    p.drawEllipse(QRectF(46, 67, 8, 8))


def _draw_restart(p: QPainter, _color: QColor) -> None:
    p.drawArc(QRectF(23, 23, 54, 54), 35 * 16, 285 * 16)
    p.drawLine(68, 25, 77, 26)
    p.drawLine(77, 26, 74, 36)


def _draw_pin(p: QPainter, _color: QColor) -> None:
    path = QPainterPath()
    path.moveTo(38, 23)
    path.lineTo(69, 23)
    path.lineTo(61, 38)
    path.lineTo(68, 52)
    path.lineTo(55, 58)
    path.lineTo(50, 79)
    path.lineTo(45, 58)
    path.lineTo(32, 52)
    path.lineTo(39, 38)
    path.closeSubpath()
    p.drawPath(path)


def _draw_clipboard(p: QPainter, _color: QColor) -> None:
    p.drawRoundedRect(QRectF(28, 27, 44, 53), 6, 6)
    p.drawRoundedRect(QRectF(39, 20, 22, 15), 5, 5)
    p.drawLine(38, 49, 62, 49)
    p.drawLine(38, 61, 58, 61)


def _draw_selected(p: QPainter, _color: QColor) -> None:
    for x1, y1, x2, y2 in (
        (25, 38, 25, 25),
        (25, 25, 38, 25),
        (62, 25, 75, 25),
        (75, 25, 75, 38),
        (25, 62, 25, 75),
        (25, 75, 38, 75),
        (62, 75, 75, 75),
        (75, 62, 75, 75),
        (36, 44, 64, 44),
        (36, 56, 57, 56),
    ):
        p.drawLine(x1, y1, x2, y2)


def _draw_copy_path(p: QPainter, _color: QColor) -> None:
    p.drawRoundedRect(QRectF(25, 31, 36, 43), 5, 5)
    p.drawRoundedRect(QRectF(39, 23, 36, 43), 5, 5)
    p.drawLine(48, 39, 66, 39)
    p.drawLine(48, 50, 63, 50)


def _draw_uuid(p: QPainter, _color: QColor) -> None:
    for x, y in ((31, 31), (57, 31), (31, 57), (57, 57)):
        p.drawRoundedRect(QRectF(x, y, 12, 12), 3, 3)
    p.drawLine(43, 37, 57, 37)
    p.drawLine(37, 43, 37, 57)
    p.drawLine(63, 43, 63, 57)
    p.drawLine(43, 63, 57, 63)


def _draw_clock(p: QPainter, _color: QColor) -> None:
    p.drawEllipse(QRectF(22, 22, 56, 56))
    p.drawLine(50, 34, 50, 52)
    p.drawLine(50, 52, 64, 60)


def _draw_base64(p: QPainter, color: QColor) -> None:
    p.drawLine(26, 31, 26, 69)
    p.drawLine(26, 31, 43, 31)
    p.drawLine(26, 49, 43, 49)
    p.drawLine(26, 69, 43, 69)
    p.drawLine(43, 49, 43, 69)
    p.drawLine(58, 31, 58, 50)
    p.drawLine(58, 50, 75, 50)
    p.drawLine(75, 31, 75, 69)


def _draw_urlencode(p: QPainter, color: QColor) -> None:
    p.drawEllipse(QRectF(27, 27, 16, 16))
    p.drawEllipse(QRectF(57, 57, 16, 16))
    p.drawLine(31, 70, 69, 30)


def _draw_palette(p: QPainter, color: QColor) -> None:
    p.drawEllipse(QRectF(22, 24, 56, 52))
    p.setBrush(QColor(color))
    p.setPen(QtCompat.NoPen)
    for x, y in ((36, 39), (52, 33), (65, 45)):
        p.drawEllipse(QRectF(x - 4, y - 4, 8, 8))
    p.setBrush(QtCompat.NoBrush)
    pen = QPen(color, 6)
    pen.setCapStyle(QtCompat.RoundCap)
    p.setPen(pen)
    p.drawArc(QRectF(46, 51, 25, 20), 190 * 16, 155 * 16)


def _draw_hash(p: QPainter, _color: QColor) -> None:
    p.drawLine(38, 24, 33, 76)
    p.drawLine(63, 24, 58, 76)
    p.drawLine(25, 41, 72, 41)
    p.drawLine(23, 60, 70, 60)


def _draw_qr(p: QPainter, color: QColor) -> None:
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    for x, y in ((24, 24), (58, 24), (24, 58)):
        p.drawRect(QRectF(x, y, 18, 18))
        p.setBrush(QtCompat.NoBrush)
        p.setPen(QPen(color, 5))
        p.drawRect(QRectF(x + 4, y + 4, 10, 10))
        p.setPen(QtCompat.NoPen)
        p.setBrush(color)
    for x, y in ((57, 57), (70, 57), (57, 70), (70, 70), (64, 64)):
        p.drawRect(QRectF(x, y, 7, 7))


def _draw_json(p: QPainter, color: QColor) -> None:
    left = QPainterPath(QPointF(42, 25))
    left.cubicTo(34, 25, 34, 31, 34, 38)
    left.lineTo(34, 44)
    left.cubicTo(34, 49, 30, 50, 27, 50)
    left.cubicTo(30, 50, 34, 52, 34, 57)
    left.lineTo(34, 63)
    left.cubicTo(34, 70, 34, 75, 42, 75)
    p.drawPath(left)

    right = QPainterPath(QPointF(58, 25))
    right.cubicTo(66, 25, 66, 31, 66, 38)
    right.lineTo(66, 44)
    right.cubicTo(66, 49, 70, 50, 73, 50)
    right.cubicTo(70, 50, 66, 52, 66, 57)
    right.lineTo(66, 63)
    right.cubicTo(66, 70, 66, 75, 58, 75)
    p.drawPath(right)


def _draw_jwt(p: QPainter, color: QColor) -> None:
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    for x, y in ((28, 50), (50, 38), (72, 50), (50, 65)):
        p.drawEllipse(QRectF(x - 5, y - 5, 10, 10))
    p.setPen(QPen(color, 5))
    p.drawLine(33, 47, 45, 41)
    p.drawLine(55, 41, 67, 47)
    p.drawLine(68, 55, 55, 63)
    p.drawLine(45, 63, 32, 55)


def _draw_globe(p: QPainter, _color: QColor) -> None:
    p.drawEllipse(QRectF(22, 22, 56, 56))
    p.drawEllipse(QRectF(37, 22, 26, 56))
    p.drawLine(23, 50, 77, 50)
    p.drawArc(QRectF(25, 33, 50, 34), 0, 180 * 16)
    p.drawArc(QRectF(25, 33, 50, 34), 180 * 16, 180 * 16)


def _draw_netdiag(p: QPainter, color: QColor) -> None:
    p.drawEllipse(QRectF(22, 43, 12, 12))
    p.drawEllipse(QRectF(66, 43, 12, 12))
    path = QPainterPath(QPointF(34, 49))
    path.lineTo(42, 49)
    path.lineTo(47, 34)
    path.lineTo(55, 65)
    path.lineTo(60, 49)
    path.lineTo(66, 49)
    p.drawPath(path)


def _draw_wifi(p: QPainter, color: QColor) -> None:
    p.drawArc(QRectF(20, 24, 60, 52), 35 * 16, 110 * 16)
    p.drawArc(QRectF(31, 37, 38, 34), 35 * 16, 110 * 16)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    p.drawEllipse(QRectF(45, 65, 10, 10))


def _draw_port(p: QPainter, _color: QColor) -> None:
    p.drawRoundedRect(QRectF(27, 31, 46, 38), 8, 8)
    p.drawLine(38, 31, 38, 22)
    p.drawLine(62, 31, 62, 22)
    p.drawLine(38, 69, 38, 78)
    p.drawLine(62, 69, 62, 78)
    p.drawLine(40, 50, 60, 50)


def _draw_dns(p: QPainter, color: QColor) -> None:
    p.drawArc(QRectF(25, 25, 50, 50), 25 * 16, 130 * 16)
    p.drawArc(QRectF(25, 25, 50, 50), 205 * 16, 130 * 16)
    p.drawLine(68, 27, 75, 37)
    p.drawLine(68, 27, 58, 31)
    p.drawLine(32, 73, 25, 63)
    p.drawLine(32, 73, 42, 69)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    p.drawEllipse(QRectF(45, 45, 10, 10))


def _draw_process(p: QPainter, _color: QColor) -> None:
    p.drawRoundedRect(QRectF(22, 24, 56, 52), 7, 7)
    p.drawLine(22, 37, 78, 37)
    for y in (49, 61):
        p.drawLine(34, y, 66, y)
    p.drawEllipse(QRectF(28, 29, 3, 3))
    p.drawEllipse(QRectF(36, 29, 3, 3))


def _draw_sysreport(p: QPainter, color: QColor) -> None:
    p.drawRoundedRect(QRectF(22, 24, 56, 43), 6, 6)
    p.drawLine(40, 76, 60, 76)
    p.drawLine(50, 67, 50, 76)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    for x, y, h in ((33, 48, 12), (47, 41, 19), (61, 34, 26)):
        p.drawRoundedRect(QRectF(x, y, 7, h), 2, 2)


def _draw_sliders(p: QPainter, color: QColor) -> None:
    for y, knob_x in ((32, 62), (50, 39), (68, 56)):
        p.drawLine(25, y, 75, y)
        p.setPen(QtCompat.NoPen)
        p.setBrush(color)
        p.drawEllipse(QRectF(knob_x - 6, y - 6, 12, 12))
        pen = QPen(color, 6)
        pen.setCapStyle(QtCompat.RoundCap)
        p.setPen(pen)
        p.setBrush(QtCompat.NoBrush)


def _draw_git(p: QPainter, color: QColor) -> None:
    p.drawLine(36, 30, 36, 68)
    p.drawLine(36, 43, 62, 56)
    p.drawLine(62, 56, 62, 68)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    for x, y in ((36, 27), (36, 72), (62, 72)):
        p.drawEllipse(QRectF(x - 6, y - 6, 12, 12))
