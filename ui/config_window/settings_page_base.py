"""Base settings page — extracted from settings_panel (per §4.7)."""

# NOTE: pixmap_dpi — QPixmap constructed locally; drawn via painter that
#       honours devicePixelRatio at the paint-time context.
from __future__ import annotations

import logging

from core.i18n import tr
from qt_compat import (
    QBrush,
    QColor,
    QFrame,
    QGroupBox,
    QLabel,
    QPainter,
    QPainterPath,
    QPixmap,
    QPushButton,
    QRectF,
    QtCompat,
    QVBoxLayout,
    QWidget,
)
from ui.styles.style import Glassmorphism, StyleSheet
from ui.utils.pixel_snap import create_pixmap, make_cosmetic_pen
from ui.utils.smooth_scroll import SmoothScrollArea
from ui.utils.ui_scale import scale_qss, sp

from .icon_grid_palette import LIGHTNING_BOLT  # noqa: F401 - used by mock tests
from .settings_group_icon_palette import group_icon_accent
from .settings_nav_palette import NAV_INK_DARK, NAV_INK_LIGHT

logger = logging.getLogger(__name__)


class BaseSettingPage(SmoothScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCompat.ScrollBarAsNeeded)
        # 让 ScrollArea 透明
        self.setStyleSheet("QScrollArea, QWidget#Content { background: transparent; border-radius: 0; border: none; }")

        self.content_widget = QWidget()
        self.content_widget.setObjectName("Content")
        self.setWidget(self.content_widget)

        self.layout = QVBoxLayout(self.content_widget)
        self.layout.setContentsMargins(sp(8), sp(5), sp(8), sp(5))
        self.layout.setSpacing(sp(8))

    def add_group(self, title):
        from ui.utils.font_manager import get_qfont

        group = QGroupBox(tr(title))
        group.setFont(get_qfont(14))
        group.setProperty("settingsGroupTitle", title)

        group.setStyleSheet(
            scale_qss(
                """
            QGroupBox {
                border-radius: 0; border: none;
                padding-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 0px;
                top: -2px;
                padding-left: 20px;
                color: white;
            }
        """
            )
        )

        icon_label = QLabel()
        icon_label.setObjectName("SettingsGroupIcon")
        icon_label.setProperty("settingsGroupIconTitle", title)
        icon_label.setParent(group)
        icon_label.setFixedSize(sp(12), sp(12))
        icon_label.setAlignment(QtCompat.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border-radius: 0; border: none;")
        icon_label.setPixmap(self._create_group_icon(title, "dark", sp(12)))
        icon_label.raise_()

        layout = QVBoxLayout(group)
        layout.setContentsMargins(sp(8), sp(8), sp(8), sp(8))
        layout.setSpacing(sp(8))
        self.layout.addWidget(group)
        self._position_group_icon(group)
        return layout, group

    def _position_group_icon(self, group):
        icon_label = group.findChild(QLabel, "SettingsGroupIcon")
        if not icon_label:
            return
        icon_label.move(0, 0)
        icon_label.raise_()

    def _group_icon_kind(self, title: str) -> str:
        if "插件" in title:
            return "plugin"
        if "收藏命令" in title:
            return "command_favorite"
        if "内置命令" in title or "命令" in title:
            return "command"
        if "支持一下" in title:
            return "support"
        if "启动" in title or "运行" in title:
            return "power"
        if "排序" in title:
            return "sort"
        if "主题" in title or "背景" in title or "外观" in title:
            return "palette"
        if "语言" in title:
            return "info"
        if "日志" in title:
            return "log"
        if "尺寸" in title or "布局" in title:
            return "layout"
        if "透明" in title:
            return "opacity"
        if "视觉" in title or "特效" in title:
            return "spark"
        if "位置" in title:
            return "target"
        if "触发" in title or "交互" in title:
            return "gesture"
        if "危险" in title:
            return "warning"
        if "配置" in title or "管理" in title:
            return "archive"
        if "关于" in title or "简介" in title or "作者" in title:
            return "info"
        if "添加" in title:
            return "plus"
        if "分类" in title or "同步" in title:
            return "folder"
        if "高级" in title:
            return "sliders"
        if "技巧" in title or "操作" in title:
            return "guide"
        return "dot"

    def _group_icon_accent(self, title: str, theme: str) -> QColor:
        return QColor(group_icon_accent(title, theme))

    def _create_group_icon(self, title: str, theme: str, size: int = 14) -> QPixmap:
        pixmap = create_pixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform)
        painter.scale(size / 22.0, size / 22.0)

        accent = self._group_icon_accent(title, theme)
        accent.setAlpha(145 if theme == "light" else 165)
        ink = QColor(NAV_INK_LIGHT) if theme == "light" else QColor(NAV_INK_DARK)
        bg = QColor(accent)
        bg.setAlpha(12 if theme == "light" else 18)
        border = QColor(accent)
        border.setAlpha(55 if theme == "light" else 70)

        painter.setPen(make_cosmetic_pen(border, 1.2, 1))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(QRectF(1.0, 1.0, 20.0, 20.0), 6.0, 6.0)

        pen = make_cosmetic_pen(ink, 1.8)
        pen.setCapStyle(QtCompat.RoundCap)
        pen.setJoinStyle(QtCompat.RoundJoin)
        accent_pen = make_cosmetic_pen(accent, 2.0)
        accent_pen.setCapStyle(QtCompat.RoundCap)
        accent_pen.setJoinStyle(QtCompat.RoundJoin)

        def line(x1, y1, x2, y2, color_pen=pen):
            painter.setPen(color_pen)
            painter.drawLine(int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2)))

        def ellipse(x, y, w, h, color_pen=pen, brush=None):
            painter.setPen(color_pen)
            painter.setBrush(brush if brush is not None else QtCompat.NoBrush)
            painter.drawEllipse(QRectF(x, y, w, h))

        def rect(x, y, w, h, color_pen=pen, brush=None, radius=2.5):
            painter.setPen(color_pen)
            painter.setBrush(brush if brush is not None else QtCompat.NoBrush)
            painter.drawRoundedRect(QRectF(x, y, w, h), radius, radius)

        def heart_path() -> QPainterPath:
            path = QPainterPath()
            path.moveTo(11, 16.2)
            path.cubicTo(6.5, 13.2, 5.0, 10.8, 5.0, 8.7)
            path.cubicTo(5.0, 6.7, 6.6, 5.3, 8.4, 5.3)
            path.cubicTo(9.6, 5.3, 10.5, 5.9, 11, 6.8)
            path.cubicTo(11.5, 5.9, 12.4, 5.3, 13.6, 5.3)
            path.cubicTo(15.4, 5.3, 17.0, 6.7, 17.0, 8.7)
            path.cubicTo(17.0, 10.8, 15.5, 13.2, 11, 16.2)
            return path

        def star_path(cx=11, cy=10.8, outer=6.2, inner=2.8) -> QPainterPath:
            points = [
                (cx, cy - outer),
                (cx + 1.0, cy - inner),
                (cx + outer, cy - inner),
                (cx + 1.8, cy + 0.8),
                (cx + 3.1, cy + outer),
                (cx, cy + 2.6),
                (cx - 3.1, cy + outer),
                (cx - 1.8, cy + 0.8),
                (cx - outer, cy - inner),
                (cx - 1.0, cy - inner),
            ]
            path = QPainterPath()
            path.moveTo(*points[0])
            for point in points[1:]:
                path.lineTo(*point)
            path.closeSubpath()
            return path

        kind = self._group_icon_kind(title)
        if kind == "power":
            painter.setPen(accent_pen)
            painter.drawArc(QRectF(6, 6, 10, 10), 35 * 16, 290 * 16)
            line(11, 4.7, 11, 10.5)
        elif kind == "sort":
            line(6, 7, 16, 7)
            line(6, 11, 14, 11)
            line(6, 15, 12, 15)
            line(16, 5, 18, 7)
            line(16, 9, 18, 7)
        elif kind == "palette":
            ellipse(5, 5, 12, 12)
            painter.setBrush(QBrush(accent))
            painter.setPen(QtCompat.NoPen)
            painter.drawEllipse(QRectF(8, 7, 2.4, 2.4))
            painter.drawEllipse(QRectF(12, 8, 2.4, 2.4))
            painter.drawEllipse(QRectF(8.8, 12, 2.4, 2.4))
            painter.setPen(pen)
            painter.setBrush(QtCompat.NoBrush)
            painter.drawArc(QRectF(10, 11, 6, 5), 180 * 16, 145 * 16)
        elif kind == "log":
            rect(6, 4.5, 10, 13)
            line(8.5, 8, 13.5, 8, accent_pen)
            line(8.5, 11, 13.5, 11)
            line(8.5, 14, 12.5, 14)
        elif kind == "layout":
            rect(5, 5, 12, 12)
            line(11, 5, 11, 17)
            line(5, 10.5, 17, 10.5, accent_pen)
        elif kind == "opacity":
            path = QPainterPath()
            path.moveTo(11, 4)
            path.cubicTo(16, 9, 17, 12, 17, 14)
            path.cubicTo(17, 17, 14.5, 18.5, 11, 18.5)
            path.cubicTo(7.5, 18.5, 5, 17, 5, 14)
            path.cubicTo(5, 12, 6, 9, 11, 4)
            painter.setPen(pen)
            painter.setBrush(QtCompat.NoBrush)
            painter.drawPath(path)
            line(6.8, 14.5, 15.2, 14.5, accent_pen)
        elif kind == "spark":
            line(11, 4.5, 11, 7.2, accent_pen)
            line(11, 14.8, 11, 17.5, accent_pen)
            line(4.5, 11, 7.2, 11, accent_pen)
            line(14.8, 11, 17.5, 11, accent_pen)
            line(7, 7, 8.7, 8.7)
            line(15, 7, 13.3, 8.7)
            line(7, 15, 8.7, 13.3)
            line(15, 15, 13.3, 13.3)
        elif kind == "target":
            ellipse(5, 5, 12, 12)
            ellipse(8.3, 8.3, 5.4, 5.4, accent_pen)
            line(11, 3.5, 11, 6)
            line(11, 16, 11, 18.5)
            line(3.5, 11, 6, 11)
            line(16, 11, 18.5, 11)
        elif kind == "gesture":
            line(7, 7, 7, 14)
            line(10, 5.5, 10, 14)
            line(13, 7, 13, 14)
            line(16, 9.5, 16, 14)
            painter.setPen(accent_pen)
            painter.drawArc(QRectF(6, 11, 11, 7), 200 * 16, 145 * 16)
        elif kind == "plugin":
            rect(5, 6, 12, 10.5)
            line(8, 6, 8, 4.5, pen)
            line(14, 6, 14, 4.5, pen)
            line(8, 16.5, 8, 18, pen)
            line(14, 16.5, 14, 18, pen)
            line(3.5, 9.5, 5, 9.5, pen)
            line(3.5, 13.2, 5, 13.2, pen)
            line(17, 9.5, 18.5, 9.5, pen)
            line(17, 13.2, 18.5, 13.2, pen)
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(accent))
            painter.drawRoundedRect(QRectF(8.5, 9, 5, 4.8), 1.2, 1.2)
        elif kind == "command":
            rect(5, 5, 12, 12)
            line(5, 8.3, 17, 8.3, pen)
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(accent))
            painter.drawEllipse(QRectF(7.0, 6.3, 1.4, 1.4))
            painter.drawEllipse(QRectF(9.4, 6.3, 1.4, 1.4))
            line(7.2, 10.9, 9.2, 12.5, accent_pen)
            line(9.2, 12.5, 7.2, 14.1, accent_pen)
            line(11.2, 14.1, 14.3, 14.1)
        elif kind == "command_favorite":
            pen_star = make_cosmetic_pen(accent, 1.7)
            pen_star.setJoinStyle(QtCompat.RoundJoin)
            pen_star.setCapStyle(QtCompat.RoundCap)
            painter.setPen(pen_star)
            painter.setBrush(QtCompat.NoBrush)
            painter.drawPath(star_path(10.7, 10.3, 5.6, 2.5))
            line(6.5, 16, 15.5, 16, pen)
            line(14.6, 5.6, 17.2, 5.6, pen)
            line(15.9, 4.3, 15.9, 6.9, pen)
        elif kind == "support":
            painter.setPen(accent_pen)
            painter.setBrush(QtCompat.NoBrush)
            painter.drawEllipse(QRectF(4.8, 4.8, 12.4, 12.4))
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(accent))
            painter.drawPath(heart_path())
        elif kind == "warning":
            path = QPainterPath()
            path.moveTo(11, 4.5)
            path.lineTo(18, 17)
            path.lineTo(4, 17)
            path.closeSubpath()
            pen_warn = make_cosmetic_pen(accent, 1.8)
            pen_warn.setJoinStyle(QtCompat.RoundJoin)
            pen_warn.setCapStyle(QtCompat.RoundCap)
            painter.setPen(pen_warn)
            painter.setBrush(QtCompat.NoBrush)
            painter.drawPath(path)
            line(11, 8.3, 11, 12.6)
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(ink))
            painter.drawEllipse(QRectF(10.1, 14.2, 1.8, 1.8))
        elif kind == "archive":
            rect(5, 6.5, 12, 10.5)
            line(6, 9, 16, 9, accent_pen)
            line(9, 12, 13, 12)
        elif kind == "info":
            ellipse(5, 5, 12, 12, accent_pen)
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(ink))
            painter.drawEllipse(QRectF(10, 7.2, 2, 2))
            painter.drawRoundedRect(QRectF(10, 10.4, 2, 5.5), 1, 1)
        elif kind == "plus":
            line(6, 11, 16, 11, accent_pen)
            line(11, 6, 11, 16, accent_pen)
        elif kind == "folder":
            painter.setPen(pen)
            painter.setBrush(QtCompat.NoBrush)
            path = QPainterPath()
            path.moveTo(4.8, 8)
            path.lineTo(8.8, 8)
            path.lineTo(10, 6.5)
            path.lineTo(17.2, 6.5)
            path.lineTo(17.2, 16.5)
            path.lineTo(4.8, 16.5)
            path.closeSubpath()
            painter.drawPath(path)
            line(7.5, 12, 14.5, 12, accent_pen)
        elif kind == "sliders":
            line(5.5, 7, 16.5, 7)
            line(5.5, 11, 16.5, 11)
            line(5.5, 15, 16.5, 15)
            ellipse(7, 5.6, 2.8, 2.8, accent_pen, QBrush(bg))
            ellipse(12.2, 9.6, 2.8, 2.8, accent_pen, QBrush(bg))
            ellipse(9.4, 13.6, 2.8, 2.8, accent_pen, QBrush(bg))
        elif kind == "guide":
            rect(6, 5, 10, 12)
            line(9, 8, 13, 8, accent_pen)
            line(9, 11, 13, 11)
            line(9, 14, 12, 14)
        else:
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(accent))
            painter.drawEllipse(QRectF(8, 8, 6, 6))

        painter.end()
        return pixmap

    def apply_theme(self, theme):
        """应用主题到所有分组标题和按钮"""
        title_color = "rgba(28,28,30,0.9)" if theme == "light" else "rgba(255,255,255,0.9)"
        scrollbar_style = StyleSheet.get_scrollbar_style(theme)
        self.setStyleSheet(
            "QScrollArea, QWidget#Content { background: transparent; border-radius: 0; border: none; }"
            + scrollbar_style
        )
        try:
            self.verticalScrollBar().setStyleSheet(scrollbar_style)
            self.horizontalScrollBar().setStyleSheet(scrollbar_style)
        except Exception as exc:
            logger.debug("设置滚动条样式失败: %s", exc, exc_info=True)

        style = scale_qss(
            f"""
            QGroupBox {{
                border-radius: 0; border: none;
                padding-top: 5px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 0px;
                top: -2px;
                padding-left: 20px;
                color: {title_color};
                font-weight: 400;
            }}
        """
        )

        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(style)

        for label in self.findChildren(QLabel, "SettingsGroupIcon"):
            title = label.property("settingsGroupIconTitle") or ""
            label.setPixmap(self._create_group_icon(str(title), theme, sp(12)))
            parent = label.parent()
            if parent:
                self._position_group_icon(parent)

        # 应用按钮样式
        btn_style = Glassmorphism.get_action_button_style(theme, is_compact=False, is_delete=False)
        compact_btn_style = Glassmorphism.get_action_button_style(theme, is_compact=True, is_delete=False)
        delete_btn_style = Glassmorphism.get_action_button_style(theme, is_compact=False, is_delete=True)

        for btn in self.findChildren(QPushButton):
            if "清除所有配置" in btn.text():
                continue
            if btn.property("is_compact_btn"):
                btn.setStyleSheet(compact_btn_style)
            elif btn.property("is_delete_btn"):
                btn.setStyleSheet(delete_btn_style)
            else:
                btn.setStyleSheet(btn_style)
