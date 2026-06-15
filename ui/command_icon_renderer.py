"""Theme-aware vector-style icons for built-in slash commands."""

from __future__ import annotations

from core.command_icon_catalog import BUILTIN_COMMAND_ICON_IDS, builtin_command_id_from_icon_path
from qt_compat import QColor, QPainter, QPainterPath, QPen, QPixmap, QPointF, QRectF, QtCompat

_ICON_CACHE: dict[tuple[str, int, str], QPixmap] = {}

_ACCENT_COLORS = {
    "about": "#7A5AF8",
    "auto-backups": "#2D9C6B",
    "base64": "#3478F6",
    "cidr": "#168AAD",
    "clean-cache": "#00A69C",
    "clean-icons": "#00A69C",
    "clip": "#00A69C",
    "color": "#AF52DE",
    "config": "#3478F6",
    "config-file": "#3478F6",
    "config-history": "#3478F6",
    "config-repair": "#3478F6",
    "conflict": "#E55353",
    "copy-path": "#5856D6",
    "data-dir": "#3478F6",
    "diagnostics": "#19A974",
    "dns": "#34A853",
    "env": "#3478F6",
    "error-log": "#E55353",
    "explorer": "#2684FF",
    "git": "#E94F37",
    "god": "#D88700",
    "hash": "#5856D6",
    "help": "#8E5BD9",
    "history-dir": "#7A5AF8",
    "hosts": "#E55353",
    "icons-dir": "#AF52DE",
    "ip": "#2684FF",
    "install-dir": "#3478F6",
    "json": "#D88700",
    "jwt": "#8E5BD9",
    "log": "#64748B",
    "netdiag": "#19A974",
    "path-audit": "#D88700",
    "pin_off": "#64748B",
    "pin_on": "#F08030",
    "plugin-list": "#7A5AF8",
    "plugin-new": "#7A5AF8",
    "plugin-reload": "#7A5AF8",
    "port": "#F08030",
    "process": "#E55353",
    "qr": "#30343B",
    "quit": "#E55353",
    "reload-hooks": "#64748B",
    "restart": "#3478F6",
    "selected": "#00A6D6",
    "shortcut-health": "#19A974",
    "sysreport": "#2D9C6B",
    "timestamp": "#E68A00",
    "tls": "#2D9C6B",
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
        "about": _draw_info,
        "auto-backups": _draw_backup,
        "base64": _draw_base64,
        "cidr": _draw_cidr,
        "clean-cache": _draw_broom,
        "clean-icons": _draw_broom,
        "clip": _draw_clipboard,
        "color": _draw_palette,
        "config": _draw_gear,
        "config-file": _draw_config_file,
        "config-history": _draw_config_history,
        "config-repair": _draw_repair,
        "conflict": _draw_conflict,
        "copy-path": _draw_copy_path,
        "data-dir": _draw_data_folder,
        "diagnostics": _draw_diagnostics,
        "dns": _draw_dns,
        "env": _draw_sliders,
        "error-log": _draw_error_log,
        "explorer": _draw_explorer,
        "git": _draw_git,
        "god": _draw_crown,
        "hash": _draw_hash,
        "help": _draw_help,
        "history-dir": _draw_history_folder,
        "hosts": _draw_hosts,
        "icons-dir": _draw_icons_folder,
        "ip": _draw_globe,
        "install-dir": _draw_install_folder,
        "json": _draw_json,
        "jwt": _draw_jwt,
        "log": _draw_log,
        "netdiag": _draw_netdiag,
        "path-audit": _draw_path_audit,
        "pin_off": _draw_pin_off,
        "pin_on": _draw_pin_on,
        "plugin-list": _draw_plugin_list,
        "plugin-new": _draw_plugin_new,
        "plugin-reload": _draw_plugin_reload,
        "port": _draw_port,
        "process": _draw_process,
        "qr": _draw_qr,
        "quit": _draw_power,
        "reload-hooks": _draw_hook,
        "restart": _draw_restart,
        "selected": _draw_selected,
        "shortcut-health": _draw_shortcut_health,
        "sysreport": _draw_sysreport,
        "timestamp": _draw_clock,
        "tls": _draw_tls,
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


def _restore_stroke(p: QPainter, color: QColor, width: int = 6) -> None:
    pen = QPen(color, width)
    pen.setCapStyle(QtCompat.RoundCap)
    pen.setJoinStyle(QtCompat.RoundJoin)
    p.setPen(pen)
    p.setBrush(QtCompat.NoBrush)


def _draw_document(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(30, 20)
    path.lineTo(59, 20)
    path.lineTo(72, 33)
    path.lineTo(72, 80)
    path.lineTo(30, 80)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(59, 20, 59, 33)
    p.drawLine(59, 33, 72, 33)


def _draw_folder(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(20, 33)
    path.lineTo(43, 33)
    path.lineTo(50, 41)
    path.lineTo(80, 41)
    path.lineTo(80, 75)
    path.lineTo(20, 75)
    path.closeSubpath()
    p.drawPath(path)


def _draw_plugin(p: QPainter, color: QColor) -> None:
    path = QPainterPath()
    path.moveTo(29, 29)
    path.lineTo(43, 29)
    path.cubicTo(41, 19, 59, 19, 57, 29)
    path.lineTo(71, 29)
    path.lineTo(71, 43)
    path.cubicTo(81, 41, 81, 59, 71, 57)
    path.lineTo(71, 71)
    path.lineTo(57, 71)
    path.cubicTo(59, 81, 41, 81, 43, 71)
    path.lineTo(29, 71)
    path.lineTo(29, 57)
    path.cubicTo(19, 59, 19, 41, 29, 43)
    path.closeSubpath()
    p.drawPath(path)
    _restore_stroke(p, color)


def _draw_info(p: QPainter, color: QColor) -> None:
    p.drawEllipse(QRectF(23, 23, 54, 54))
    p.drawLine(50, 45, 50, 66)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    p.drawEllipse(QRectF(46, 33, 8, 8))


def _draw_backup(p: QPainter, _color: QColor) -> None:
    _draw_folder(p)
    p.drawArc(QRectF(38, 43, 31, 27), 35 * 16, 275 * 16)
    p.drawLine(64, 43, 72, 45)
    p.drawLine(72, 45, 68, 53)


def _draw_cidr(p: QPainter, color: QColor) -> None:
    p.drawLine(31, 50, 50, 32)
    p.drawLine(50, 32, 69, 50)
    p.drawLine(31, 50, 50, 68)
    p.drawLine(50, 68, 69, 50)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    for x, y in ((31, 50), (50, 32), (69, 50), (50, 68)):
        p.drawEllipse(QRectF(x - 6, y - 6, 12, 12))


def _draw_broom(p: QPainter, _color: QColor) -> None:
    p.drawLine(62, 24, 43, 51)
    path = QPainterPath()
    path.moveTo(36, 48)
    path.lineTo(51, 59)
    path.lineTo(40, 76)
    path.lineTo(21, 62)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(32, 57, 42, 65)


def _draw_config_file(p: QPainter, color: QColor) -> None:
    _draw_document(p)
    for y, knob_x in ((47, 43), (62, 57)):
        p.drawLine(38, y, 64, y)
        p.setPen(QtCompat.NoPen)
        p.setBrush(color)
        p.drawEllipse(QRectF(knob_x - 4, y - 4, 8, 8))
        _restore_stroke(p, color, 5)


def _draw_config_history(p: QPainter, color: QColor) -> None:
    _draw_document(p)
    p.drawEllipse(QRectF(40, 42, 25, 25))
    p.drawLine(52, 47, 52, 55)
    p.drawLine(52, 55, 59, 59)
    _restore_stroke(p, color)


def _draw_repair(p: QPainter, color: QColor) -> None:
    _draw_gear(p, color)
    p.drawLine(29, 72, 45, 56)
    p.drawLine(25, 76, 30, 71)
    p.drawArc(QRectF(18, 66, 17, 17), 35 * 16, 230 * 16)


def _draw_conflict(p: QPainter, color: QColor) -> None:
    p.drawLine(27, 31, 71, 69)
    p.drawLine(71, 31, 27, 69)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    p.drawEllipse(QRectF(22, 26, 10, 10))
    p.drawEllipse(QRectF(66, 64, 10, 10))
    p.drawEllipse(QRectF(66, 26, 10, 10))
    p.drawEllipse(QRectF(22, 64, 10, 10))


def _draw_data_folder(p: QPainter, color: QColor) -> None:
    _draw_folder(p)
    p.drawEllipse(QRectF(37, 47, 27, 9))
    p.drawArc(QRectF(37, 51, 27, 12), 180 * 16, 180 * 16)
    p.drawArc(QRectF(37, 58, 27, 12), 180 * 16, 180 * 16)
    _restore_stroke(p, color, 5)


def _draw_diagnostics(p: QPainter, color: QColor) -> None:
    p.drawEllipse(QRectF(22, 22, 56, 56))
    path = QPainterPath(QPointF(31, 52))
    path.lineTo(40, 52)
    path.lineTo(46, 39)
    path.lineTo(55, 63)
    path.lineTo(61, 52)
    path.lineTo(70, 52)
    p.drawPath(path)
    _restore_stroke(p, color)


def _draw_error_log(p: QPainter, color: QColor) -> None:
    _draw_document(p)
    p.drawLine(50, 42, 50, 59)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    p.drawEllipse(QRectF(46, 65, 8, 8))


def _draw_explorer(p: QPainter, _color: QColor) -> None:
    _draw_folder(p)
    p.drawArc(QRectF(42, 46, 28, 23), 35 * 16, 260 * 16)
    p.drawLine(65, 46, 72, 48)
    p.drawLine(72, 48, 68, 55)


def _draw_crown(p: QPainter, _color: QColor) -> None:
    path = QPainterPath()
    path.moveTo(24, 37)
    path.lineTo(39, 51)
    path.lineTo(50, 29)
    path.lineTo(61, 51)
    path.lineTo(76, 37)
    path.lineTo(69, 70)
    path.lineTo(31, 70)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(31, 61, 69, 61)


def _draw_history_folder(p: QPainter, color: QColor) -> None:
    _draw_folder(p)
    p.drawEllipse(QRectF(41, 47, 25, 25))
    p.drawLine(53, 52, 53, 59)
    p.drawLine(53, 59, 60, 63)
    _restore_stroke(p, color, 5)


def _draw_hosts(p: QPainter, color: QColor) -> None:
    _draw_document(p)
    p.drawLine(39, 49, 61, 49)
    p.drawLine(39, 62, 61, 62)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    for x, y in ((35, 49), (35, 62)):
        p.drawEllipse(QRectF(x - 3, y - 3, 6, 6))


def _draw_icons_folder(p: QPainter, color: QColor) -> None:
    _draw_folder(p)
    p.drawRoundedRect(QRectF(35, 48, 31, 21), 3, 3)
    p.drawLine(39, 65, 48, 56)
    p.drawLine(48, 56, 55, 62)
    p.drawLine(55, 62, 62, 54)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    p.drawEllipse(QRectF(55, 51, 5, 5))


def _draw_install_folder(p: QPainter, _color: QColor) -> None:
    _draw_folder(p)
    p.drawLine(50, 47, 50, 64)
    p.drawLine(42, 57, 50, 65)
    p.drawLine(58, 57, 50, 65)


def _draw_log(p: QPainter, color: QColor) -> None:
    _draw_document(p)
    for y in (43, 54, 65):
        p.drawLine(40, y, 63, y)
    _restore_stroke(p, color, 5)


def _draw_path_audit(p: QPainter, color: QColor) -> None:
    path = QPainterPath(QPointF(27, 68))
    path.cubicTo(36, 32, 47, 66, 59, 39)
    p.drawPath(path)
    p.drawEllipse(QRectF(54, 26, 22, 22))
    p.drawLine(70, 43, 79, 52)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    p.drawEllipse(QRectF(22, 63, 10, 10))


def _draw_pin_on(p: QPainter, color: QColor) -> None:
    _draw_pin(p, color)
    p.setPen(QtCompat.NoPen)
    p.setBrush(color)
    p.drawEllipse(QRectF(68, 22, 10, 10))


def _draw_pin_off(p: QPainter, color: QColor) -> None:
    _draw_pin(p, color)
    _restore_stroke(p, color, 7)
    p.drawLine(25, 25, 76, 76)


def _draw_plugin_list(p: QPainter, color: QColor) -> None:
    _draw_plugin(p, color)
    p.drawLine(42, 44, 60, 44)
    p.drawLine(42, 55, 60, 55)


def _draw_plugin_new(p: QPainter, color: QColor) -> None:
    _draw_plugin(p, color)
    p.drawLine(50, 40, 50, 60)
    p.drawLine(40, 50, 60, 50)


def _draw_plugin_reload(p: QPainter, color: QColor) -> None:
    _draw_plugin(p, color)
    p.drawArc(QRectF(39, 39, 24, 24), 35 * 16, 275 * 16)
    p.drawLine(58, 39, 65, 41)
    p.drawLine(65, 41, 62, 48)


def _draw_power(p: QPainter, _color: QColor) -> None:
    p.drawArc(QRectF(24, 25, 52, 52), 45 * 16, 270 * 16)
    p.drawLine(50, 20, 50, 50)


def _draw_hook(p: QPainter, color: QColor) -> None:
    p.drawLine(50, 21, 50, 60)
    p.drawArc(QRectF(28, 46, 44, 31), 180 * 16, 180 * 16)
    p.drawLine(50, 22, 62, 34)
    p.drawLine(50, 22, 38, 34)
    _restore_stroke(p, color)


def _draw_shortcut_health(p: QPainter, color: QColor) -> None:
    p.drawRoundedRect(QRectF(23, 23, 54, 54), 10, 10)
    p.drawLine(33, 52, 42, 61)
    p.drawLine(42, 61, 65, 38)
    _restore_stroke(p, color)


def _draw_tls(p: QPainter, color: QColor) -> None:
    shield = QPainterPath()
    shield.moveTo(50, 20)
    shield.lineTo(72, 29)
    shield.lineTo(69, 58)
    shield.cubicTo(66, 69, 58, 76, 50, 80)
    shield.cubicTo(42, 76, 34, 69, 31, 58)
    shield.lineTo(28, 29)
    shield.closeSubpath()
    p.drawPath(shield)
    p.drawRoundedRect(QRectF(39, 48, 22, 17), 4, 4)
    p.drawArc(QRectF(42, 36, 16, 20), 0, 180 * 16)
    _restore_stroke(p, color, 5)
