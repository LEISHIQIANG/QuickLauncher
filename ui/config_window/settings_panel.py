"""
设置面板 - 分类导航版本
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core import DataManager
from core.i18n import tr
from qt_compat import (
    QBrush,
    QColor,
    QDialog,
    QEasingCurve,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPoint,
    QPropertyAnimation,
    QPushButton,
    QRectF,
    QSize,
    QStackedWidget,
    Qt,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
    pyqtProperty,
    pyqtSignal,
)
from ui.styles.style import StyleSheet
from ui.utils.font_manager import get_font_css_with_size, get_qfont, tune_font_rendering
from ui.utils.window_effect import get_window_effect, paint_win10_rounded_surface

from .settings_about_page import SettingsAboutPageMixin
from .settings_appearance_page import SettingsAppearancePageMixin
from .settings_commands_page import SettingsCommandsPageMixin
from .settings_data_actions import SettingsDataActionsMixin
from .settings_data_page import SettingsDataPageMixin
from .settings_page_helpers import SettingsPageHelpersMixin
from .settings_plugins_page import SettingsPluginsPageMixin
from .settings_popup_page import SettingsPopupPageMixin
from .settings_support_page import SettingsSupportPageMixin
from .settings_system_page import SettingsSystemPageMixin

logger = logging.getLogger(__name__)


class CompactProgressDialog(QDialog):
    """紧凑型进度/状态对话框 - 模糊半透明背景"""

    def __init__(self, parent, title, theme="dark"):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(240)
        self.setMaximumWidth(400)
        self.setMinimumHeight(90)
        self.setWindowFlags(QtCompat.FramelessWindowHint | QtCompat.Dialog)
        self.setAttribute(QtCompat.WA_TranslucentBackground, True)
        self.setWindowOpacity(0)

        from ui.utils.window_effect import is_win11

        self.corner_radius = 8 if is_win11() else 8
        self._acrylic_applied = False
        self._dialog_finished = False
        self._detect_theme()
        self._setup_ui()

    def _detect_theme(self):
        if self.theme == "dark":
            self.bg_color = QColor(28, 28, 30, 180)
            self.border_color = QColor(190, 190, 197, 60)
            self.text_color = "#dddddd"
        else:
            self.bg_color = QColor(242, 242, 247, 160)
            self.border_color = QColor(229, 229, 234, 150)
            self.text_color = "#333333"

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # 标题栏（图标 + 标题）
        self.title_layout = QHBoxLayout()
        self.title_layout.setSpacing(8)
        self.title_layout.setContentsMargins(0, 0, 0, 0)

        # 图标
        self.icon_label = QLabel()
        self.icon_label.setStyleSheet("font-size: 20px; margin-top: -3px;")
        self.icon_label.setFixedSize(24, 24)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setVisible(False)
        self.title_layout.addWidget(self.icon_label)

        # 标题
        self.title_label = QLabel()
        self.title_label.setFont(get_qfont(13, 400))
        self.title_label.setStyleSheet("font-size: 13px; font-weight: 400;")
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_layout.addWidget(self.title_label, 1)

        main_layout.addLayout(self.title_layout)

        # 消息内容
        self.msg_label = QLabel(tr("正在处理..."))
        self.msg_label.setWordWrap(True)
        self.msg_label.setAlignment(QtCompat.AlignLeft | QtCompat.AlignTop)
        self.msg_label.setStyleSheet(
            f"font-family: 'Segoe UI', 'Microsoft YaHei UI', sans-serif; "
            f"font-size: 11px; line-height: 1.4; "
            f"background: transparent; color: {self.text_color};"
        )
        main_layout.addWidget(self.msg_label)

        # 按钮
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(6)
        self.btn_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_layout.addStretch()
        self.ok_btn = QPushButton(tr("确定"))
        self.ok_btn.setDefault(True)
        self.ok_btn.setFixedHeight(22)
        self.ok_btn.setMinimumWidth(52)
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setVisible(False)
        self.btn_layout.addWidget(self.ok_btn)
        main_layout.addLayout(self.btn_layout)

        from ui.styles.style import get_dialog_stylesheet

        self.setStyleSheet(get_dialog_stylesheet(self.theme))
        tune_font_rendering(self, recursive=True)
        self.title_label.setFont(get_qfont(13, 400))

    def paintEvent(self, event):
        """背景绘制 - 完全按照ThemedMessageBox的逻辑"""
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)

        from ui.utils.window_effect import is_win10

        if is_win10():
            paint_win10_rounded_surface(painter, self, self.bg_color, self.border_color, self.corner_radius)
            return

        inset = 1.0 if is_win10() else 0.5

        path = QPainterPath()
        path.addRoundedRect(
            inset, inset, self.width() - inset * 2, self.height() - inset * 2, self.corner_radius, self.corner_radius
        )

        # 磨砂玻璃模式：与ThemedMessageBox完全一致
        tint_color = QColor(self.bg_color)
        if is_win10():
            tint_color.setAlpha(min(tint_color.alpha(), 220))
        else:
            tint_color.setAlpha(min(tint_color.alpha(), 100))
        painter.fillPath(path, tint_color)

        # 边框
        pen_color = QColor(self.border_color)
        pen_color.setAlpha(min(pen_color.alpha(), 120))
        painter.setPen(QPen(pen_color, 1))
        painter.drawPath(path)

    def showEvent(self, event):
        """显示时居中并应用模糊效果"""
        super().showEvent(event)
        self._dialog_finished = False
        self.adjustSize()
        from ui.utils.dialog_helper import center_dialog_on_main_window

        center_dialog_on_main_window(self)
        if not self._acrylic_applied:
            self._acrylic_applied = True
            QTimer.singleShot(10, self._apply_acrylic)
        self._start_show_animation()

    def _start_show_animation(self):
        """窗口出现动画 (0.2s)"""
        self.opacity_anim = QtCompat.QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(200)
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        self.opacity_anim.setEasingCurve(QtCompat.OutCubic)

        pos = self.pos()
        self.pos_anim = QtCompat.QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(200)
        self.pos_anim.setStartValue(QPoint(pos.x(), pos.y() + 20))
        self.pos_anim.setEndValue(pos)
        self.pos_anim.setEasingCurve(QtCompat.OutCubic)

        self.anim_group = QtCompat.QParallelAnimationGroup()
        self.anim_group.addAnimation(self.opacity_anim)
        self.anim_group.addAnimation(self.pos_anim)
        self.anim_group.start()

    def _apply_acrylic(self):
        """应用模糊效果 - 与主配置窗口一致"""
        try:
            if self._dialog_finished or not self.isVisible():
                return
            from ui.utils.window_effect import enable_acrylic_for_config_window, is_win11

            hwnd = int(self.winId())
            if not hwnd:
                return
            effect = get_window_effect()

            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
                effect.enable_window_shadow(hwnd, self.corner_radius)
            else:
                w, h = self.width(), self.height()
                if w > 0 and h > 0:
                    effect.set_window_region(hwnd, w, h, self.corner_radius)

            enable_acrylic_for_config_window(self, self.theme, blur_amount=30, radius=self.corner_radius)
        except Exception as exc:
            logger.debug("应用窗口特效失败: %s", exc, exc_info=True)

    def done(self, result):
        self._dialog_finished = True
        for attr in ("anim_group", "opacity_anim", "pos_anim"):
            anim = getattr(self, attr, None)
            if anim is not None:
                try:
                    anim.stop()
                except Exception as exc:
                    logger.debug("停止动画失败: %s", exc, exc_info=True)
        super().done(result)

    def show_success(self, msg, title=""):
        """显示成功消息"""
        self.icon_label.setText("✓")
        self.icon_label.setVisible(True)
        self.title_label.setText(title if title else self.windowTitle())
        self.msg_label.setText(msg)
        self.ok_btn.setVisible(True)
        self.adjustSize()

    def show_failure(self, msg, title=""):
        """显示失败消息"""
        self.icon_label.setText("✗")
        self.icon_label.setVisible(True)
        self.title_label.setText(title if title else self.windowTitle())
        self.msg_label.setText(msg)
        self.ok_btn.setVisible(True)
        self.adjustSize()


from ui.utils.smooth_scroll import SmoothScrollArea


class NavigationItem(QListWidgetItem):
    def __init__(self, text, icon_name=None, theme="dark"):
        super().__init__(text)
        self.icon_name = icon_name or ""
        self.setTextAlignment(QtCompat.AlignLeft | QtCompat.AlignVCenter)
        self.setSizeHint(QSize(0, 40))


class NavigationItemWidget(QWidget):
    """Custom navigation item widget with theme-aware styling."""

    def __init__(self, text, icon, theme="dark", parent=None):
        super().__init__(parent)
        self.text = text
        self.icon = icon
        self.theme = theme
        self.item = None  # Reference to QListWidgetItem
        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        h = max(19, fm.height()) + 22  # 22px padding total (11px top/bottom), scales perfectly with high-DPI
        return QSize(100, h)

    def update_icon(self, new_icon):
        self.icon = new_icon
        self.update()

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Determine selection and hover states
        is_selected = False
        if self.item is not None:
            is_selected = self.item.isSelected()
        is_hovered = self.underMouse()

        # Draw hover background
        if is_hovered and not is_selected:
            if self.theme == "dark":
                hover_bg = QColor(255, 255, 255, 12)  # rgba(255, 255, 255, 0.05)
            else:
                hover_bg = QColor(0, 0, 0, 8)  # rgba(0, 0, 0, 0.03)
            painter.setBrush(hover_bg)
            painter.setPen(QtCompat.NoPen)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(8, 2, -8, -2), 6, 6)

        # Draw icon
        if self.icon:
            pixmap = self.icon.pixmap(19, 19)
            y = (self.height() - pixmap.height()) // 2
            painter.drawPixmap(14, y, pixmap)

        # Draw text
        if self.theme == "dark":
            text_color = (
                QColor(255, 255, 255, 242)
                if is_selected
                else (QColor(255, 255, 255, 217) if is_hovered else QColor(255, 255, 255, 150))
            )
        else:
            text_color = (
                QColor(0, 0, 0, 242) if is_selected else (QColor(0, 0, 0, 200) if is_hovered else QColor(0, 0, 0, 150))
            )

        painter.setPen(text_color)
        from ui.utils.font_manager import get_qfont

        painter.setFont(get_qfont(12))

        text_rect = QRectF(38, 0, self.width() - 48, self.height())
        painter.drawText(text_rect, QtCompat.AlignLeft | QtCompat.AlignVCenter, self.text)

        painter.end()


class NavigationWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(140)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.setSpacing(4)
        self.setIconSize(QSize(19, 19))
        from ui.utils.font_manager import get_qfont

        self.setFont(get_qfont(13))

        self.theme = "dark"
        self._pill_rect = QRectF()
        self._pill_opacity = 0.0
        self._pill_rect_anim = None
        self._pill_opacity_anim = None

        self.selectionModel().selectionChanged.connect(self._on_selection_changed)

    @pyqtProperty(QRectF)
    def pill_rect(self) -> QRectF:
        return self._pill_rect

    @pill_rect.setter
    def pill_rect(self, rect: QRectF):
        self._pill_rect = rect
        self.viewport().update()

    @pyqtProperty(float)
    def pill_opacity(self) -> float:
        return self._pill_opacity

    @pill_opacity.setter
    def pill_opacity(self, opacity: float):
        self._pill_opacity = opacity
        self.viewport().update()

    def _on_selection_changed(self, selected, deselected):
        curr_indexes = self.selectedIndexes()
        if curr_indexes:
            index = curr_indexes[0]
            visual_rect = self.visualRect(index)
            target_rect = QRectF(visual_rect).adjusted(8, 2, -8, -2)

            if self._pill_rect_anim is not None:
                self._pill_rect_anim.stop()

            if self._pill_rect.isEmpty() or self._pill_opacity < 0.1:
                self._pill_rect = target_rect
            else:
                self._pill_rect_anim = QPropertyAnimation(self, b"pill_rect")
                self._pill_rect_anim.setDuration(220)
                self._pill_rect_anim.setStartValue(self._pill_rect)
                self._pill_rect_anim.setEndValue(target_rect)
                self._pill_rect_anim.setEasingCurve(QEasingCurve.OutCubic)
                self._pill_rect_anim.start()

            if self._pill_opacity_anim is not None:
                self._pill_opacity_anim.stop()
            self._pill_opacity_anim = QPropertyAnimation(self, b"pill_opacity")
            self._pill_opacity_anim.setDuration(180)
            self._pill_opacity_anim.setStartValue(self._pill_opacity)
            self._pill_opacity_anim.setEndValue(1.0)
            self._pill_opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._pill_opacity_anim.start()
        else:
            if self._pill_opacity_anim is not None:
                self._pill_opacity_anim.stop()
            self._pill_opacity_anim = QPropertyAnimation(self, b"pill_opacity")
            self._pill_opacity_anim.setDuration(180)
            self._pill_opacity_anim.setStartValue(self._pill_opacity)
            self._pill_opacity_anim.setEndValue(0.0)
            self._pill_opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._pill_opacity_anim.start()

    def apply_theme(self, theme):
        self.theme = theme
        self._apply_nav_icons(theme)

        self.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                outline: none;
                padding-top: 10px;
            }
            QListWidget::item {
                background-color: transparent;
                border: none;
                padding: 0px;
                margin: 2px 8px;
            }
            QListWidget::item:selected {
                background-color: transparent;
                border: none;
            }
            QListWidget::item:hover {
                background-color: transparent;
                border: none;
            }
        """)

    def _apply_nav_icons(self, theme: str):
        from .action_button_icons import create_action_button_icon

        for row in range(self.count()):
            item = self.item(row)
            widget = self.itemWidget(item)
            if isinstance(widget, NavigationItemWidget):
                widget.theme = theme
                icon_name = getattr(item, "icon_name", "")
                if icon_name:
                    new_icon = create_action_button_icon(icon_name, theme, 19)
                    widget.update_icon(new_icon)
                widget.update()

    def paintEvent(self, event):
        if self._pill_opacity > 0 and not self._pill_rect.isEmpty():
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.Antialiasing)

            if self.theme == "dark":
                pill_color = QColor(255, 255, 255, int(self._pill_opacity * 38))  # rgba(255, 255, 255, 0.15)
            else:
                pill_color = QColor(0, 0, 0, int(self._pill_opacity * 20))  # rgba(0, 0, 0, 0.08)

            painter.setBrush(QBrush(pill_color))
            painter.setPen(QtCompat.NoPen)
            painter.drawRoundedRect(self._pill_rect, 6, 6)
            painter.end()

        super().paintEvent(event)


class BaseSettingPage(SmoothScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCompat.ScrollBarAsNeeded)
        # 让 ScrollArea 透明
        self.setStyleSheet("QScrollArea, QWidget#Content { background: transparent; border: none; }")

        self.content_widget = QWidget()
        self.content_widget.setObjectName("Content")
        self.setWidget(self.content_widget)

        self.layout = QVBoxLayout(self.content_widget)
        self.layout.setContentsMargins(10, 5, 10, 5)
        self.layout.setSpacing(10)

    def add_group(self, title):
        from ui.utils.font_manager import get_qfont

        group = QGroupBox(tr(title))
        group.setFont(get_qfont(14))
        group.setProperty("settingsGroupTitle", title)

        group.setStyleSheet("""
            QGroupBox {
                border: none;
                padding-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 0px;
                top: -4px;
                padding-left: 18px;
                color: white;
            }
        """)

        icon_label = QLabel()
        icon_label.setObjectName("SettingsGroupIcon")
        icon_label.setProperty("settingsGroupIconTitle", title)
        icon_label.setParent(group)
        icon_label.setFixedSize(14, 14)
        icon_label.setAlignment(QtCompat.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")
        icon_label.setPixmap(self._create_group_icon(title, "dark", 14))
        icon_label.raise_()

        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
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
        if "危险" in title:
            return QColor(255, 99, 99)
        if "插件" in title:
            return QColor(44, 190, 155)
        if "收藏命令" in title:
            return QColor(255, 184, 77)
        if "命令" in title:
            return QColor(82, 145, 255)
        if "支持一下" in title:
            return QColor(255, 122, 86)
        if "日志" in title or "配置" in title or "管理" in title:
            return QColor(54, 176, 116)
        if "主题" in title or "背景" in title or "外观" in title or "视觉" in title:
            return QColor(112, 101, 242)
        if "语言" in title:
            return QColor(28, 150, 130)
        if "弹窗" in title or "位置" in title or "触发" in title or "交互" in title:
            return QColor(45, 126, 235)
        if "关于" in title or "简介" in title or "作者" in title:
            return QColor(28, 150, 130)
        return QColor(45, 126, 235) if theme == "light" else QColor(96, 166, 255)

    def _create_group_icon(self, title: str, theme: str, size: int = 14) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform)
        painter.scale(size / 22.0, size / 22.0)

        accent = self._group_icon_accent(title, theme)
        accent.setAlpha(145 if theme == "light" else 165)
        ink = QColor(38, 49, 64, 150) if theme == "light" else QColor(235, 241, 250, 165)
        bg = QColor(accent)
        bg.setAlpha(12 if theme == "light" else 18)
        border = QColor(accent)
        border.setAlpha(55 if theme == "light" else 70)

        painter.setPen(QPen(border, 1.2))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(QRectF(1.0, 1.0, 20.0, 20.0), 6.0, 6.0)

        pen = QPen(ink, 1.8)
        pen.setCapStyle(QtCompat.RoundCap)
        pen.setJoinStyle(QtCompat.RoundJoin)
        accent_pen = QPen(accent, 2.0)
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
            painter.setPen(QPen(accent, 1.7))
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
            painter.setPen(QPen(accent, 1.8))
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
        self.setStyleSheet("QScrollArea, QWidget#Content { background: transparent; border: none; }" + scrollbar_style)
        try:
            self.verticalScrollBar().setStyleSheet(scrollbar_style)
            self.horizontalScrollBar().setStyleSheet(scrollbar_style)
        except Exception as exc:
            logger.debug("设置滚动条样式失败: %s", exc, exc_info=True)

        style = f"""
            QGroupBox {{
                border: none;
                padding-top: 5px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 0px;
                top: -4px;
                padding-left: 18px;
                color: {title_color};
                font-weight: 400;
            }}
        """

        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(style)

        for label in self.findChildren(QLabel, "SettingsGroupIcon"):
            title = label.property("settingsGroupIconTitle") or ""
            label.setPixmap(self._create_group_icon(str(title), theme, 14))
            parent = label.parent()
            if parent:
                self._position_group_icon(parent)

        # 应用按钮样式 — 与主窗口底部按钮一致
        from ui.styles.style import Glassmorphism

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


class SettingsPanel(
    SettingsPageHelpersMixin,
    SettingsSystemPageMixin,
    SettingsAppearancePageMixin,
    SettingsPopupPageMixin,
    SettingsDataPageMixin,
    SettingsAboutPageMixin,
    SettingsDataActionsMixin,
    SettingsPluginsPageMixin,
    SettingsCommandsPageMixin,
    SettingsSupportPageMixin,
    QWidget,
):
    settings_changed = pyqtSignal()
    command_settings_changed = pyqtSignal()
    import_completed = pyqtSignal(int)
    back_requested = pyqtSignal()
    hotkey_recording_changed = pyqtSignal(bool)
    special_apps_changed = pyqtSignal()
    trigger_config_changed = pyqtSignal()

    def __init__(self, data_manager: DataManager, tray_app=None):
        super().__init__()
        self.data_manager = data_manager
        self.tray_app = tray_app
        self._updating = False
        self.current_theme = "dark"

        self.export_thread = None
        self.import_thread = None

        # 滑杆防抖动定时器 - 滑动结束后才触发设置变更
        self._slider_debounce_timer = QTimer(self)
        self._slider_debounce_timer.setSingleShot(True)
        self._slider_debounce_timer.setInterval(150)  # 150ms 防抖动
        self._slider_debounce_timer.timeout.connect(self._emit_slider_settings_changed)
        self._pending_slider_change = False

        self._setup_ui()
        self._load_settings()

    def _get_desc_color(self):
        """获取描述文字颜色"""
        return "#b0b0b5" if self.current_theme == "dark" else "#666666"

    def apply_theme(self, theme: str):
        """应用主题样式"""
        self.current_theme = theme

        # 导航栏样式
        self.nav_widget.apply_theme(theme)

        # 分栏容器圆角矩形样式
        if theme == "dark":
            container_style = """
                QWidget#NavContainer, QWidget#ContentContainer {
                    background-color: rgba(255, 255, 255, 0.06);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 10px;
                }
            """
        else:
            container_style = """
                QWidget#NavContainer, QWidget#ContentContainer {
                    background-color: rgba(255, 255, 255, 0.20);
                    border: 1px solid rgba(0, 0, 0, 0.06);
                    border-radius: 10px;
                }
            """
        self.nav_container.setStyleSheet(container_style)
        self.content_container.setStyleSheet(container_style)

        # 内容区域统一使用 Glassmorphism 样式
        try:
            from ui.styles.style import Glassmorphism

            from .settings_helpers import SwitchButton
            from .theme_helper import get_radio_stylesheet, get_switch_stylesheet

            # 综合样式表
            full_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
            full_style += get_switch_stylesheet(theme)
            full_style += get_radio_stylesheet(theme)

            # 设置主样式
            self.setStyleSheet(full_style)

            # 为 QLabel 标题等设置特定样式 (如果需要)
            text_color = "rgba(255, 255, 255, 0.9)" if theme == "dark" else "rgba(28, 28, 30, 0.9)"
            self.setStyleSheet(self.styleSheet() + f"\nQLabel {{ color: {text_color}; }}")

            # 更新自定义开关按钮的主题背景与文字颜色
            for btn in self.findChildren(SwitchButton):
                btn.set_theme(theme)

        except Exception as e:
            logger.debug("Failed to apply SettingsPanel theme: %s", e, exc_info=True)

        # Apply theme to all pages (for updating group box titles)
        pages = [
            self.page_system,
            self.page_appearance,
            self.page_popup,
            self.page_data,
            self.page_plugins,
            self.page_commands,
            self.page_about,
            self.page_support,
        ]
        for page in pages:
            if hasattr(page, "apply_theme"):
                page.apply_theme(theme)

        # 更新描述文字颜色
        desc_color = self._get_desc_color()
        for obj_name in [
            "data_desc_1",
            "data_desc_2",
            "data_desc_3",
            "context_menu_desc",
            "plugins_desc",
            "fav_desc",
            "disable_desc",
        ]:
            label = self.findChild(QLabel, obj_name)
            if label:
                style = label.styleSheet()
                import re

                new_style = re.sub(r"color:\s*#[0-9a-fA-F]{6};", f"color: {desc_color};", style)
                label.setStyleSheet(new_style)

        # 更新右键菜单卡片描述
        if hasattr(self, "context_menu_cards"):
            for menu_id, card in self.context_menu_cards.items():
                desc_label = card.findChild(QLabel, f"desc_{menu_id}")
                if desc_label:
                    desc_label.setStyleSheet(
                        f"{get_font_css_with_size(11, 400)} color: {desc_color}; background: transparent; border: none;"
                    )

        # 触发插件与命令列表的主题重绘刷新
        if 4 in self._initialized_pages:
            self._rebuild_plugin_list(preserve_scroll=True)
        if 5 in self._initialized_pages:
            self._command_refresh_apply_theme = False
            try:
                self._refresh_command_settings()
            finally:
                self._command_refresh_apply_theme = True

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 1. 左侧导航栏圆角容器
        self.nav_container = QWidget()
        self.nav_container.setObjectName("NavContainer")
        nav_container_layout = QVBoxLayout(self.nav_container)
        nav_container_layout.setContentsMargins(0, 0, 0, 0)
        nav_container_layout.setSpacing(0)

        self.nav_widget = NavigationWidget()
        self.nav_widget.itemSelectionChanged.connect(self._on_nav_changed)
        nav_container_layout.addWidget(self.nav_widget)
        main_layout.addWidget(self.nav_container)

        # 2. 右侧内容区圆角容器
        self.content_container = QWidget()
        self.content_container.setObjectName("ContentContainer")
        content_container_layout = QVBoxLayout(self.content_container)
        content_container_layout.setContentsMargins(0, 0, 0, 0)
        content_container_layout.setSpacing(0)

        self.content_stack = QStackedWidget()
        content_container_layout.addWidget(self.content_stack)
        main_layout.addWidget(self.content_container, 1)

        # 分隔线（保留属性引用，但不再添加到布局）
        self.separator = QFrame()

        # === 添加页面 ===
        self._init_pages()
        self._init_nav_items()

    def _init_pages(self):
        # 页面构建函数映射（索引 -> 构建方法）
        self._page_builders = {
            0: self._setup_system_page,
            1: self._setup_appearance_page,
            2: self._setup_popup_page,
            3: self._setup_data_page,
            4: self._setup_plugins_page,
            5: self._setup_commands_page,
            6: self._setup_about_page,
            7: self._setup_support_page,
        }
        # 需要底部 stretch 的页面
        self._pages_need_stretch = {0, 1, 3, 6, 7}
        # 已初始化的页面索引集合
        self._initialized_pages = set()
        # 页面引用（索引 -> BaseSettingPage）
        self._pages = {}

        # 为所有页面创建空的 BaseSettingPage 占位
        page_attrs = [
            "page_system",
            "page_appearance",
            "page_popup",
            "page_data",
            "page_plugins",
            "page_commands",
            "page_about",
            "page_support",
        ]
        for i in range(8):
            page = BaseSettingPage()
            setattr(self, page_attrs[i], page)
            self._pages[i] = page
            self.content_stack.addWidget(page)

        # 只立即构建第一个页面（系统设置），其余延迟
        self._ensure_page_built(0)

    def _ensure_page_built(self, index):
        """延迟构建页面，首次访问时才初始化"""
        if index in self._initialized_pages:
            return
        builder = self._page_builders.get(index)
        if not builder:
            return
        page = self._pages[index]
        builder(page)
        if index in self._pages_need_stretch:
            page.layout.addStretch()
        self._initialized_pages.add(index)
        # 加载该页面的设置数据
        self._load_settings_for_page(index)
        # 应用当前主题
        try:
            theme = self.data_manager.get_settings().theme
            if hasattr(page, "apply_theme"):
                page.apply_theme(theme)
        except Exception as exc:
            logger.debug("应用页面主题失败: %s", exc, exc_info=True)

    def _init_nav_items(self):
        items = [
            ("系统设置", 0, "system"),
            ("弹窗外观", 1, "appearance"),
            ("弹窗交互", 2, "interaction"),
            ("配置管理", 3, "settings_data"),
            ("插件管理", 4, "plugin"),
            ("命令管理", 5, "command"),
            ("支持一下", 7, "support"),
            ("关于软件", 6, "about"),
        ]

        for text, index, icon_name in items:
            item = NavigationItem(tr(text), icon_name)
            item.setData(QtCompat.UserRole, index)
            self.nav_widget.addItem(item)

            # Create Custom NavigationItemWidget
            from .action_button_icons import create_action_button_icon

            icon = create_action_button_icon(icon_name, self.current_theme, 19)

            widget = NavigationItemWidget(tr(text), icon, self.current_theme, self.nav_widget)
            widget.item = item

            # Clear QListWidgetItem text to prevent default text rendering (eliminates ghosting/overlapping)
            item.setText("")

            item.setSizeHint(widget.sizeHint())

            self.nav_widget.setItemWidget(item, widget)

        self.nav_widget.setCurrentRow(0)

    def _current_page_scroll_value(self, index: int) -> int:
        page = self._pages.get(index)
        if page is None or not hasattr(page, "verticalScrollBar"):
            return 0
        try:
            return page.verticalScrollBar().value()
        except Exception:
            return 0

    def _restore_page_scroll_value(self, index: int, value: int):
        page = self._pages.get(index)
        if page is None or not hasattr(page, "verticalScrollBar"):
            return
        try:
            page.verticalScrollBar().setValue(value)
        except Exception as exc:
            logger.debug("恢复页面滚动位置失败: %s", exc, exc_info=True)

    def _on_nav_changed(self):
        items = self.nav_widget.selectedItems()
        if items:
            index = items[0].data(QtCompat.UserRole)
            self._ensure_page_built(index)
            self.content_stack.setCurrentIndex(index)

    def _load_settings(self):
        self._updating = True
        settings = self.data_manager.get_settings()

        # 只加载已构建页面的设置
        for idx in self._initialized_pages:
            self._load_settings_for_page(idx, settings)

        self._updating = False

        # Apply theme to this panel
        self.apply_theme(settings.theme)

    def _load_settings_for_page(self, index, settings=None):
        """加载指定页面的设置数据"""
        if settings is None:
            settings = self.data_manager.get_settings()
        old_updating = self._updating
        self._updating = True
        try:
            if index == 0:
                self._load_system_settings(settings)
            elif index == 1:
                self._load_appearance_settings(settings)
            elif index == 2:
                self._load_popup_settings(settings)
            elif index == 3:
                pass  # data page has no settings to load
            elif index == 4:
                pass  # plugins page
            elif index == 5:
                pass  # commands page
            elif index == 6:
                pass  # about page is static
            elif index == 7:
                pass  # support page is dynamic
        finally:
            self._updating = old_updating

    # === Slider Debounce ===

    def _emit_slider_settings_changed(self):
        """防抖动定时器触发时发送设置变更信号"""
        if self._pending_slider_change:
            self._pending_slider_change = False
            self.settings_changed.emit()

    def _schedule_slider_settings_changed(self):
        """使用防抖动延迟发送设置变更信号（用于滑杆）"""
        self._pending_slider_change = True
        # 重置定时器（如果正在滑动，会一直重置，直到停止）
        if self._slider_debounce_timer.isActive():
            self._slider_debounce_timer.stop()
        self._slider_debounce_timer.start()

    def stop_background_timers(self):
        """Stop debounced settings timers before the owning window closes."""
        for timer_name in ("_slider_debounce_timer",):
            timer = getattr(self, timer_name, None)
            if timer is None:
                continue
            try:
                timer.stop()
            except Exception as exc:
                logger.debug("停止防抖定时器失败: %s", exc, exc_info=True)
        stop_command_timers = getattr(self, "_stop_command_page_timers", None)
        if callable(stop_command_timers):
            stop_command_timers()

    # Import/Export
