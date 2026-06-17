"""Rounded window container widget.

Extracted from :mod:`ui.config_window.main_window` as part of the
P1-06 file-split pass.  :class:`RoundedWindow` is a frameless
`QWidget` that paints itself with an optional acrylic tint and
rounded corners — the building block used by `ConfigWindow` for the
chrome around the configuration panes.
"""

from __future__ import annotations

import logging

from qt_compat import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QtCompat,
    QWidget,
)
from ui.utils.window_effect import (
    paint_win10_rounded_surface,
)

logger = logging.getLogger(__name__)


class RoundedWindow(QWidget):
    """圆角窗口容器 - 支持磨砂玻璃效果"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.corner_radius = 8
        self.bg_color = QColor(43, 43, 43, 200)  # 默认半透明
        self.border_color = QColor(85, 85, 85, 150)
        self.use_acrylic = True  # 是否使用磨砂玻璃模式

    def set_colors(self, bg_color: str, border_color: str):
        """设置背景和边框颜色，支持 rgba() 格式"""
        self.bg_color = self._parse_color(bg_color)
        self.border_color = self._parse_color(border_color)
        self.update()

    def set_acrylic_mode(self, enabled: bool):
        """设置是否使用磨砂玻璃模式"""
        self.use_acrylic = enabled
        self.update()

    def _parse_color(self, color_str: str) -> QColor:
        """解析颜色字符串，支持 rgba() 格式"""
        color_str = color_str.strip()
        if color_str.startswith("rgba(") and color_str.endswith(")"):
            try:
                # 提取 rgba(r, g, b, a) 中的值
                values = color_str[5:-1].split(",")
                r = int(values[0].strip())
                g = int(values[1].strip())
                b = int(values[2].strip())
                a = int(values[3].strip())
                color = QColor(r, g, b, a)
                return color
            except (ValueError, IndexError):
                logger.debug("解析rgba颜色值失败", exc_info=True)
        # 回退到标准 QColor 解析
        return QColor(color_str)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            # Win10 特殊优化：使用更高质量的抗锯齿渲染
            try:
                from ui.utils.window_effect import is_win10

                if is_win10():
                    paint_win10_rounded_surface(painter, self, self.bg_color, self.border_color, self.corner_radius)
                    return
            except (AttributeError, ImportError, RuntimeError, TypeError) as exc:
                logger.debug("设置渲染提示失败: %s", exc, exc_info=True)

            try:
                from ui.utils.window_effect import is_win10

                inset = 1.0 if is_win10() else 0.5
            except (AttributeError, ImportError, RuntimeError, TypeError) as exc:
                logger.debug("获取窗口边距失败: %s", exc, exc_info=True)
                inset = 0.5

            path = QPainterPath()
            path.addRoundedRect(
                inset,
                inset,
                self.width() - inset * 2,
                self.height() - inset * 2,
                self.corner_radius,
                self.corner_radius,
            )

            if self.use_acrylic:
                tint_color = QColor(self.bg_color)
                try:
                    from ui.utils.window_effect import is_win10

                    if is_win10():
                        tint_color.setAlpha(min(tint_color.alpha(), 220))
                    else:
                        tint_color.setAlpha(min(tint_color.alpha(), 100))
                except (AttributeError, ImportError, RuntimeError, TypeError) as exc:
                    logger.debug("设置色调透明度失败: %s", exc, exc_info=True)
                    tint_color.setAlpha(min(tint_color.alpha(), 100))
                painter.fillPath(path, tint_color)
            else:
                painter.fillPath(path, self.bg_color)

            pen_color = QColor(self.border_color)
            pen_color.setAlpha(min(pen_color.alpha(), 120))
            pen = QPen(pen_color, 1)
            pen.setJoinStyle(QtCompat.RoundJoin)
            pen.setCapStyle(QtCompat.RoundCap)
            painter.setPen(pen)
            painter.drawPath(path)

            try:
                from ui.utils.window_effect import is_win10

                if is_win10():
                    soften_color_inner = QColor(self.bg_color)
                    soften_color_inner.setAlpha(int(soften_color_inner.alpha() * 0.6))
                    pen_inner = QPen(soften_color_inner, 0.5)
                    pen_inner.setJoinStyle(QtCompat.RoundJoin)
                    pen_inner.setCapStyle(QtCompat.RoundCap)
                    pen_inner.setCosmetic(True)
                    painter.setPen(pen_inner)
                    inner_path = QPainterPath()
                    inner_path.addRoundedRect(
                        0.75, 0.75, self.width() - 1.5, self.height() - 1.5, self.corner_radius, self.corner_radius
                    )
                    painter.drawPath(inner_path)

                    soften_color_outer = QColor(self.bg_color)
                    soften_color_outer.setAlpha(int(soften_color_outer.alpha() * 0.3))
                    pen_outer = QPen(soften_color_outer, 0.5)
                    pen_outer.setJoinStyle(QtCompat.RoundJoin)
                    pen_outer.setCapStyle(QtCompat.RoundCap)
                    pen_outer.setCosmetic(True)
                    painter.setPen(pen_outer)
                    outer_path = QPainterPath()
                    outer_path.addRoundedRect(
                        0.25,
                        0.25,
                        self.width() - 0.5,
                        self.height() - 0.5,
                        self.corner_radius + 0.5,
                        self.corner_radius + 0.5,
                    )
                    painter.drawPath(outer_path)
            except (AttributeError, RuntimeError, TypeError) as exc:
                logger.debug("绘制边框柔化失败: %s", exc, exc_info=True)
        finally:
            painter.end()
