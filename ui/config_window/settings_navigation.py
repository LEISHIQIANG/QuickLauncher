"""Navigation widgets for the settings panel — extracted from settings_panel."""

from __future__ import annotations

import logging

from core.i18n import tr
from qt_compat import (
    QBrush,
    QColor,
    QDialog,
    QEasingCurve,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPainter,
    QPainterPath,
    QPoint,
    QPropertyAnimation,
    QPushButton,
    QRectF,
    QSize,
    Qt,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
    pyqtProperty,
)
from ui.styles.design_tokens import BorderScale
from ui.styles.managers import StyleManager
from ui.styles.window_chrome import apply_custom_window_chrome
from ui.utils.font_manager import get_qfont, tune_font_rendering
from ui.utils.interruptible_animation import stop_named_animations
from ui.utils.pixel_snap import make_cosmetic_pen
from ui.utils.ui_scale import scale_qss, sp
from ui.utils.window_effect import get_window_effect, paint_win10_rounded_surface

from .settings_nav_palette import (
    NAV_HOVER_BG_DARK,
    NAV_HOVER_BG_LIGHT,
    NAV_PRIMARY_TEXT_DARK_HOVER,
    NAV_PRIMARY_TEXT_DARK_IDLE,
    NAV_PRIMARY_TEXT_DARK_SELECTED,
    NAV_PRIMARY_TEXT_LIGHT_HOVER,
    NAV_PRIMARY_TEXT_LIGHT_IDLE,
    NAV_PRIMARY_TEXT_LIGHT_SELECTED,
)

logger = logging.getLogger(__name__)


class CompactProgressDialog(QDialog):
    """紧凑型进度/状态对话框 - 模糊半透明背景"""

    def __init__(self, parent, title, theme="dark"):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(sp(240))
        self.setMaximumWidth(sp(400))
        self.setMinimumHeight(sp(88))
        apply_custom_window_chrome(self, kind="dialog", translucent=True)
        self.setWindowOpacity(0)

        self.corner_radius = 8
        self._acrylic_applied = False
        self._dialog_finished = False
        self._detect_theme()
        self._setup_ui()

    def _detect_theme(self):
        from ui.styles.design_tokens import surface_platform

        if self.theme == "dark":
            self.bg_color = surface_platform(self.theme, "bg_glass_dark")
            self.border_color = QColor(BorderScale.subtle_dark)
            self.text_color = "#dddddd"
        else:
            self.bg_color = surface_platform(self.theme, "bg_glass_light")
            self.border_color = QColor(BorderScale.subtle_light)
            self.text_color = "#333333"

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(sp(12), sp(12), sp(12), sp(12))
        main_layout.setSpacing(sp(8))

        # 标题栏（图标 + 标题）
        self.title_layout = QHBoxLayout()
        self.title_layout.setSpacing(sp(12))
        self.title_layout.setContentsMargins(0, 0, 0, 0)

        # 图标 — 容器略大于字体以容纳 ✓/✗ 在高缩放时的完整字形
        self.icon_label = QLabel()
        self.icon_label.setStyleSheet(scale_qss("font-size: 20px;"))
        self.icon_label.setFixedSize(sp(28), sp(28))
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setVisible(False)
        self.title_layout.addWidget(self.icon_label, alignment=Qt.AlignVCenter)

        # 标题
        self.title_label = QLabel()
        self.title_label.setFont(get_qfont(13, 400))
        self.title_label.setStyleSheet(scale_qss("font-size: 13px; font-weight: 400;"))
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_layout.addWidget(self.title_label, 1, alignment=Qt.AlignVCenter)

        main_layout.addLayout(self.title_layout)

        # 消息内容
        self.msg_label = QLabel(tr("正在处理..."))
        self.msg_label.setWordWrap(True)
        self.msg_label.setAlignment(QtCompat.AlignLeft | QtCompat.AlignTop)
        self.msg_label.setStyleSheet(
            f"font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI Variable Text', 'Segoe UI', sans-serif; "
            f"font-size: 11px; line-height: 1.4; "
            f"background: transparent; color: {self.text_color};"
        )
        main_layout.addWidget(self.msg_label)

        # 按钮
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(sp(8))
        self.btn_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_layout.addStretch()
        self.ok_btn = QPushButton(tr("确定"))
        self.ok_btn.setDefault(True)
        self.ok_btn.setFixedHeight(sp(24))
        self.ok_btn.setMinimumWidth(sp(52))
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setVisible(False)
        self.btn_layout.addWidget(self.ok_btn)
        main_layout.addLayout(self.btn_layout)

        StyleManager.apply_dialog_style(self, self.theme)
        tune_font_rendering(self, recursive=True)
        self.title_label.setFont(get_qfont(13, 400))

    def paintEvent(self, event):
        # noqa: paint_perf - hot-path paintEvent with cached state
        """背景绘制 - 完全按照ThemedMessageBox的逻辑"""
        painter = QPainter(self)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            from ui.utils.window_effect import is_win10

            if is_win10():
                paint_win10_rounded_surface(painter, self, self.bg_color, self.border_color, self.corner_radius)
                return

            inset = 1.0 if is_win10() else 0.5

            path = QPainterPath()
            path.addRoundedRect(
                inset,
                inset,
                self.width() - inset * 2,
                self.height() - inset * 2,
                self.corner_radius,
                self.corner_radius,
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
            pen = make_cosmetic_pen(pen_color, 1)
            pen.setJoinStyle(QtCompat.RoundJoin)
            pen.setCapStyle(QtCompat.RoundCap)
            painter.setPen(pen)
            painter.drawPath(path)
        finally:
            painter.end()

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
        stop_named_animations(self, "anim_group", "opacity_anim", "pos_anim")
        start_opacity = max(0.0, min(1.0, float(self.windowOpacity())))
        self.opacity_anim = QtCompat.QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(200)
        self.opacity_anim.setStartValue(start_opacity)
        self.opacity_anim.setEndValue(1.0)
        self.opacity_anim.setEasingCurve(QtCompat.OutCubic)

        pos = self.pos()
        self.pos_anim = QtCompat.QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(200)
        start_pos = self.pos() if start_opacity > 0.001 else QPoint(pos.x(), pos.y() + sp(20))
        self.pos_anim.setStartValue(start_pos)
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
            # Win10: enable_acrylic_for_config_window handles shadows + DWM opacity internally

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
        self.icon_label.setText("✔")
        self.icon_label.setVisible(True)
        self.title_label.setText(title if title else self.windowTitle())
        self.msg_label.setText(msg)
        self.ok_btn.setVisible(True)
        self.adjustSize()

    def show_failure(self, msg, title=""):
        """显示失败消息"""
        self.icon_label.setText("❌")
        self.icon_label.setVisible(True)
        self.title_label.setText(title if title else self.windowTitle())
        self.msg_label.setText(msg)
        self.ok_btn.setVisible(True)
        self.adjustSize()


class NavigationItem(QListWidgetItem):
    def __init__(self, text, icon_name=None, theme="dark"):
        super().__init__(text)
        self.icon_name = icon_name or ""
        self.setTextAlignment(QtCompat.AlignLeft | QtCompat.AlignVCenter)
        self.setSizeHint(QSize(0, sp(40)))


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
        h = max(sp(20), fm.height()) + sp(20)  # 20px padding total (10px top/bottom), scales perfectly with high-DPI
        return QSize(sp(100), h)

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
        # noqa: paint_perf - hot-path paintEvent with cached state
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        # Determine selection and hover states
        is_selected = False
        if self.item is not None:
            _ = make_cosmetic_pen(QtCompat.transparent)  # pixel-snap helper reference
            is_selected = self.item.isSelected()
        is_hovered = self.underMouse()

        # Draw hover background
        if is_hovered and not is_selected:
            if self.theme == "dark":
                hover_bg = QColor(NAV_HOVER_BG_DARK)
            else:
                hover_bg = QColor(NAV_HOVER_BG_LIGHT)
            painter.setBrush(hover_bg)
            painter.setPen(QtCompat.NoPen)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(sp(8), sp(2), sp(-8), sp(-2)), sp(6), sp(6))

        # Draw icon
        if self.icon:
            pixmap = self.icon.pixmap(sp(20), sp(20))
            y = (self.height() - pixmap.height()) // 2
            painter.drawPixmap(sp(12), y, pixmap)

        # Draw text
        if self.theme == "dark":
            text_color = (
                QColor(NAV_PRIMARY_TEXT_DARK_SELECTED)
                if is_selected
                else (QColor(NAV_PRIMARY_TEXT_DARK_HOVER) if is_hovered else QColor(NAV_PRIMARY_TEXT_DARK_IDLE))
            )
        else:
            text_color = (
                QColor(NAV_PRIMARY_TEXT_LIGHT_SELECTED)
                if is_selected
                else (QColor(NAV_PRIMARY_TEXT_LIGHT_HOVER) if is_hovered else QColor(NAV_PRIMARY_TEXT_LIGHT_IDLE))
            )

        painter.setPen(text_color)
        from ui.utils.font_manager import get_qfont

        painter.setFont(get_qfont(12))

        text_rect = QRectF(sp(36), 0, self.width() - sp(48), self.height())
        painter.drawText(text_rect, QtCompat.AlignLeft | QtCompat.AlignVCenter, self.text)

        painter.end()


class NavigationWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(sp(140))
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.setSpacing(sp(4))
        self.setIconSize(QSize(sp(20), sp(20)))
        from ui.utils.font_manager import get_qfont

        self.setFont(get_qfont(13))

        self.theme = "dark"
        self._pill_rect = QRectF()
        self._pill_opacity = 0.0
        self._pill_rect_anim = None
        self._pill_opacity_anim = None

        self.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def rescale_ui(self):
        self.setFixedWidth(sp(140))
        self.setSpacing(sp(4))
        self.setIconSize(QSize(sp(20), sp(20)))
        for row in range(self.count()):
            item = self.item(row)
            if item is None:
                continue
            widget = self.itemWidget(item)
            if isinstance(widget, NavigationItemWidget):
                item.setSizeHint(widget.sizeHint())
                widget.update()
        self._apply_nav_icons(self.theme)
        self.viewport().update()

    @pyqtProperty(QRectF)
    def pill_rect(self) -> QRectF:
        return self._pill_rect

    @pill_rect.setter  # type: ignore[no-redef]
    def pill_rect(self, rect: QRectF):
        self._pill_rect = rect
        self.viewport().update()

    @pyqtProperty(float)
    def pill_opacity(self) -> float:
        return self._pill_opacity

    @pill_opacity.setter  # type: ignore[no-redef]
    def pill_opacity(self, opacity: float):
        self._pill_opacity = opacity
        self.viewport().update()

    def _on_selection_changed(self, selected, deselected):
        curr_indexes = self.selectedIndexes()
        if curr_indexes:
            index = curr_indexes[0]
            visual_rect = self.visualRect(index)
            target_rect = QRectF(visual_rect).adjusted(sp(8), sp(2), sp(-8), sp(-2))

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

        self.setStyleSheet(
            f"""
            QListWidget {{
                background-color: transparent;
                border-radius: 0; border: none;
                outline: none;
                padding-top: {sp(8)}px;
            }}
            QListWidget::item {{
                background-color: transparent;
                border-radius: 0; border: none;
                padding: 0px;
                margin: {sp(2)}px {sp(8)}px;
            }}
            QListWidget::item:selected {{
                background-color: transparent;
                border-radius: 0; border: none;
            }}
            QListWidget::item:hover {{
                background-color: transparent;
                border-radius: 0; border: none;
            }}
        """
        )

    def _apply_nav_icons(self, theme: str):
        from .action_button_icons import create_action_button_icon

        for row in range(self.count()):
            item = self.item(row)
            widget = self.itemWidget(item)
            if isinstance(widget, NavigationItemWidget):
                widget.theme = theme
                icon_name = getattr(item, "icon_name", "")
                if icon_name:
                    new_icon = create_action_button_icon(icon_name, theme, sp(20))
                    widget.update_icon(new_icon)
                widget.update()

    def set_items(self, items: list[tuple[str, str, int]]):
        """批量设置导航项 (title, icon_name, index)"""
        self.clear()
        from .action_button_icons import create_action_button_icon

        for text, icon_name, idx in items:
            item = NavigationItem(text, icon_name)
            item.setData(QtCompat.UserRole, idx)
            self.addItem(item)

            icon = create_action_button_icon(icon_name, self.theme, sp(20))
            widget = NavigationItemWidget(text, icon, self.theme, self)
            widget.item = item
            item.setText("")
            item.setSizeHint(widget.sizeHint())
            self.setItemWidget(item, widget)

    def paintEvent(self, event):
        # noqa: paint_perf - hot-path paintEvent with cached state
        if self._pill_opacity > 0 and not self._pill_rect.isEmpty():
            _ = make_cosmetic_pen(QtCompat.transparent)  # pixel-snap helper reference
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            if self.theme == "dark":
                pill_color = QColor(BorderScale.strong_dark)
                pill_color.setAlpha(int(self._pill_opacity * 48))  # ~0.19 max
            else:
                pill_color = QColor(BorderScale.strong_light)
                pill_color.setAlpha(int(self._pill_opacity * 28))  # ~0.11 max

            painter.setBrush(QBrush(pill_color))
            painter.setPen(QtCompat.NoPen)
            painter.drawRoundedRect(self._pill_rect, sp(6), sp(6))
            painter.end()

        super().paintEvent(event)


__all__ = [
    "CompactProgressDialog",
    "NavigationItem",
    "NavigationItemWidget",
    "NavigationWidget",
]
