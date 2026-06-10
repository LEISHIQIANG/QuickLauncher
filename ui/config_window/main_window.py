"""
主配置窗口 - 无标题栏版本（圆角优化）
"""

import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

from core import APP_VERSION, DataManager, ShortcutItem, ShortcutType
from core.i18n import tr
from core.windows_uipi import allow_drag_drop_for_widget
from qt_compat import (
    QColor,
    QFrame,
    QHBoxLayout,
    QIcon,
    QLabel,
    QMainWindow,
    QPainter,
    QPainterPath,
    QPen,
    QPoint,
    QPushButton,
    QSize,
    QStackedWidget,
    QStatusBar,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from ui.styles.style import Glassmorphism
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.styles.window_chrome import apply_custom_window_chrome
from ui.utils.interruptible_animation import set_precise_timer, stop_named_animations
from ui.utils.ui_scale import scale_qss, sp
from ui.utils.window_effect import (
    enable_acrylic_for_config_window,
    get_window_effect,
    is_win11,
    paint_win10_rounded_surface,
)

from .theme_helper import get_radio_stylesheet, get_switch_stylesheet
from .window_lifecycle import WindowLifecycleController


class DotWidget(QWidget):
    def __init__(self, color: str, tooltip: str, parent=None):
        super().__init__(parent)
        self.setFixedWidth(sp(14))
        self._color = QColor(color)
        self.setToolTip(tooltip)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QtCompat.Antialiasing)
        p.setRenderHint(QtCompat.HighQualityAntialiasing)
        p.setPen(QtCompat.NoPen)
        p.setBrush(self._color)
        cy = self.height() // 2 + 1
        p.drawEllipse(sp(3), cy - sp(4), sp(8), sp(8))
        p.end()


class TitleBar(QWidget):
    """自定义标题栏"""

    back_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    update_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self._drag_pos = None
        self._in_settings_mode = False
        self._app_icon_path = None

        self.setFixedHeight(sp(36))
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(sp(8), 0, sp(1), 0)
        layout.setSpacing(sp(4))

        # 返回按钮 (默认隐藏)
        self.back_btn = QPushButton("‹")
        self.back_btn.setFixedSize(sp(32), sp(32))
        self.back_btn.setCursor(QtCompat.PointingHandCursor)
        self.back_btn.clicked.connect(self._on_back)
        self.back_btn.setVisible(False)
        self.back_btn.setStyleSheet(scale_qss("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 6px;
                font-size: 24px;
                font-weight: normal;
                color: #8e8e93;
                padding-bottom: 8px;
                margin-top: 2px;
            }
            QPushButton:hover {
                background-color: rgba(128, 128, 128, 0.1);
                color: #007aff;
            }
            QPushButton:pressed {
                background-color: rgba(128, 128, 128, 0.18);
                color: #006fd6;
            }
        """))
        layout.addWidget(self.back_btn)

        # 图标 (默认显示)
        icon_size = sp(25)
        # 兼容打包环境
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(icon_size, icon_size)
        self.icon_label.setCursor(QtCompat.PointingHandCursor)
        self.icon_label.mousePressEvent = self._on_update_click
        self.icon_label.setStyleSheet("background: transparent;")

        try:
            # 优先查找 assets 目录
            icon_path = os.path.join(base_dir, "assets", "app.ico")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(base_dir, "app.ico")

            if os.path.exists(icon_path):
                self._app_icon_path = icon_path
                if self.parent_window:
                    self.parent_window.setWindowIcon(QIcon(icon_path))

                pixmap = QIcon(icon_path).pixmap(icon_size, icon_size)
                if pixmap and not pixmap.isNull():
                    self.icon_label.setPixmap(
                        pixmap.scaled(icon_size, icon_size, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
                    )
        except Exception as exc:
            logger.debug("加载窗口图标失败: %s", exc, exc_info=True)
        layout.addWidget(self.icon_label, alignment=QtCompat.AlignVCenter)
        layout.addSpacing(sp(6))

        # 标题
        self.title_label = QLabel(f"QuickLauncher {APP_VERSION}")
        self.title_label.setCursor(QtCompat.PointingHandCursor)
        self.title_label.mousePressEvent = self._on_update_click
        self.title_label.setStyleSheet(scale_qss("font-size: 13px; font-weight: 400; background: transparent;"))
        self.title_label.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.title_label)

        layout.addStretch()

        # 设置按钮
        self.settings_btn = QPushButton()
        self.settings_btn.setFixedSize(sp(32), sp(32))
        self._settings_icon_path = None

        # 尝试加载设置图标
        try:
            setting_icon_path = os.path.join(base_dir, "assets", "setting.ico")
            if not os.path.exists(setting_icon_path):
                setting_icon_path = os.path.join(base_dir, "setting.ico")

            if os.path.exists(setting_icon_path):
                self._settings_icon_path = setting_icon_path
                self.settings_btn.setIcon(QIcon(setting_icon_path))
                self.settings_btn.setIconSize(QSize(sp(20), sp(20)))
            else:
                self.settings_btn.setText("⚙")
        except Exception as exc:
            logger.debug("加载设置图标失败: %s", exc, exc_info=True)
            self.settings_btn.setText("⚙")

        self.settings_btn.setCursor(QtCompat.PointingHandCursor)
        self.settings_btn.clicked.connect(self._on_settings)

        self.settings_btn.setStyleSheet(scale_qss("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                color: #aaaaaa;
            }
            QPushButton:hover {
                background-color: rgba(128, 128, 128, 0.1);
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: rgba(128, 128, 128, 0.18);
                color: #ffffff;
            }
        """))
        layout.addWidget(self.settings_btn)

        # 关闭按钮
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(sp(32), sp(32))
        self.close_btn.setCursor(QtCompat.PointingHandCursor)
        self.close_btn.clicked.connect(self._on_close)
        self.close_btn.setStyleSheet(scale_qss("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 6px;
                font-size: 18px;
                color: #aaaaaa;
            }
            QPushButton:hover {
                background-color: #e81123;
                color: white;
            }
            QPushButton:pressed {
                background-color: #c50f1f;
                color: white;
            }
        """))
        layout.addWidget(self.close_btn)

    def set_theme(self, theme: str):
        """根据主题设置文字和按钮颜色"""
        self._theme = theme
        if theme == "dark":
            text_color = "#ffffff"
            subtext_color = "#aaaaaa"
            btn_hover_bg = "rgba(255, 255, 255, 0.1)"
        else:
            text_color = "#1c1c1e"
            subtext_color = "#555555"
            btn_hover_bg = "rgba(0, 0, 0, 0.05)"

        self.title_label.setStyleSheet(
            scale_qss(f"font-size: 13px; font-weight: 400; background: transparent; color: {text_color};")
        )

        # 更新按钮样式
        btn_base_style = scale_qss(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
                color: {subtext_color};
                padding: 0px;
                margin: 0px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover_bg};
                color: {text_color};
            }}
            QPushButton:pressed {{
                background-color: rgba(128, 128, 128, 0.18);
                color: {text_color};
            }}
        """)

        self.back_btn.setStyleSheet(btn_base_style + scale_qss("QPushButton { font-size: 24px; padding-bottom: 8px; }"))
        self.settings_btn.setStyleSheet(btn_base_style + scale_qss("QPushButton { font-size: 18px; }"))

        # 关闭按钮特殊处理 hover 颜色
        self.close_btn.setStyleSheet(scale_qss(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
                font-size: 18px;
                color: {subtext_color};
                padding: 0px;
                margin: 0px;
            }}
            QPushButton:hover {{
                background-color: #e81123;
                color: white;
            }}
            QPushButton:pressed {{
                background-color: #c50f1f;
                color: white;
            }}
        """))

        if not self._settings_icon_path:
            return

        try:
            from qt_compat import QPixmap

            # 如果是暗主题，反色图标
            if theme == "dark":
                # 加载原始图标
                pixmap = QPixmap(self._settings_icon_path)
                if pixmap.isNull():
                    return

                # 缩放到需要的大小
                pixmap = pixmap.scaled(sp(20), sp(20), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)

                # 转换为 QImage 进行像素操作
                image = pixmap.toImage()

                # 反色处理 - 保持透明度，只反转RGB
                for y in range(image.height()):
                    for x in range(image.width()):
                        pixel = image.pixelColor(x, y)
                        # 保持 alpha，反转 RGB
                        inverted = QColor(255 - pixel.red(), 255 - pixel.green(), 255 - pixel.blue(), pixel.alpha())
                        image.setPixelColor(x, y, inverted)

                # 转回 QPixmap
                inverted_pixmap = QPixmap.fromImage(image)
                self.settings_btn.setIcon(QIcon(inverted_pixmap))
            else:
                # 亮主题使用原始图标
                self.settings_btn.setIcon(QIcon(self._settings_icon_path))

            self.settings_btn.setIconSize(QSize(sp(20), sp(20)))
        except Exception as exc:
            logger.debug("应用主题到设置图标失败: %s", exc, exc_info=True)

    def set_mode(self, is_settings):
        if self._in_settings_mode == is_settings:
            return
        self._in_settings_mode = is_settings
        self.back_btn.setVisible(is_settings)
        self.icon_label.setVisible(not is_settings)
        self.settings_btn.setVisible(not is_settings)
        self.retranslate_ui()

    def rescale_ui(self):
        self.setFixedHeight(sp(36))
        layout = self.layout()
        if layout is not None:
            layout.setContentsMargins(sp(8), 0, sp(1), 0)
            layout.setSpacing(sp(4))

        self.back_btn.setFixedSize(sp(32), sp(32))
        self.icon_label.setFixedSize(sp(25), sp(25))
        if self._app_icon_path and os.path.exists(self._app_icon_path):
            pixmap = QIcon(self._app_icon_path).pixmap(sp(25), sp(25))
            if pixmap and not pixmap.isNull():
                self.icon_label.setPixmap(
                    pixmap.scaled(sp(25), sp(25), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
                )

        self.settings_btn.setFixedSize(sp(32), sp(32))
        self.settings_btn.setIconSize(QSize(sp(20), sp(20)))
        self.close_btn.setFixedSize(sp(32), sp(32))
        self.set_theme(getattr(self, "_theme", "dark"))
        self.retranslate_ui()

    def retranslate_ui(self):
        if not self._in_settings_mode:
            self.title_label.setText(f"QuickLauncher {APP_VERSION}")
            self.title_label.setAlignment(QtCompat.AlignLeft | QtCompat.AlignVCenter)
            self.title_label.setContentsMargins(0, 0, 0, 0)
            return

        self.title_label.setText(tr("设置"))
        self.title_label.setAlignment(QtCompat.AlignLeft | QtCompat.AlignVCenter)
        self.title_label.setContentsMargins(0, 0, 0, 0)

    def _on_back(self):
        self.back_requested.emit()

    def _on_settings(self):
        self.settings_requested.emit()

    def _on_update_click(self, event):
        if self._in_settings_mode:
            return
        if event.button() == QtCompat.LeftButton:
            self.update_requested.emit()

    def _on_close(self):
        if self.parent_window:
            self.parent_window.close()

    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            if hasattr(event, "globalPosition"):
                self._drag_pos = event.globalPosition().toPoint()
            else:
                self._drag_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & QtCompat.LeftButton:
            if hasattr(event, "globalPosition"):
                new_pos = event.globalPosition().toPoint()
            else:
                new_pos = event.globalPos()

            if self.parent_window:
                diff = new_pos - self._drag_pos
                target_pos = self.parent_window.pos() + diff
                # 约束窗口在屏幕可见区域内（标题栏至少保留 40px 可见）
                target_pos = self._clamp_to_screen(target_pos)
                self.parent_window.move(target_pos)
            self._drag_pos = new_pos

    def _clamp_to_screen(self, pos):
        """将窗口位置约束到所有屏幕的合并可用区域内"""
        from PyQt5.QtCore import QRect
        from PyQt5.QtWidgets import QApplication

        screens = QApplication.screens()
        if not screens:
            return pos

        # 合并所有屏幕的可用几何区域
        combined = screens[0].availableGeometry()
        for screen in screens[1:]:
            combined = combined.united(screen.availableGeometry())

        win = self.parent_window
        win_rect = QRect(pos, win.size())

        min_visible = 40  # 标题栏至少可见的像素数
        # 水平约束
        if win_rect.right() < combined.left() + min_visible:
            pos.setX(combined.left() + min_visible - win.width())
        elif win_rect.left() > combined.right() - min_visible:
            pos.setX(combined.right() - min_visible)
        # 垂直约束
        if win_rect.bottom() < combined.top() + min_visible:
            pos.setY(combined.top() + min_visible - win.height())
        elif win_rect.top() > combined.bottom() - min_visible:
            pos.setY(combined.bottom() - min_visible)

        return pos

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


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
                    paint_win10_rounded_surface(
                        painter, self, self.bg_color, self.border_color, self.corner_radius
                    )
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


class ConfigWindow(QMainWindow):
    """主配置窗口"""

    # 信号定义
    settings_changed = pyqtSignal()

    # 布局常量
    FOLDER_PANEL_WIDTH = 160  # base value, scaled at usage
    # SETTINGS_PANEL_WIDTH = 220  # Removed
    ICON_WIDGET_SIZE = 65  # 调整为 65，对应 IconWidget 的正方形尺寸
    ICON_COLS = 6
    ICON_GRID_PADDING = 16  # 调整边距 (微调)
    ICON_GRID_SPACING = 8

    def __init__(self, data_manager: DataManager, tray_app=None):
        super().__init__()
        self.data_manager = data_manager
        self.tray_app = tray_app
        self._drag_drop_compat_applied = False
        self._shortcut_edit_active = False
        self._shortcut_action_last_trigger_at = {}
        self._shortcut_action_debounce_ms = 250
        self._shortcut_dialog_release_delay_ms = 250
        self._settings_panel_preload_scheduled = False
        self._lifecycle = WindowLifecycleController(self, ("_anim_timer", "_hide_anim_timer"))
        self._window_shadow_state = None
        self._resize_region_pending_state = None
        self._resize_region_last_state = None
        self._window_animation_generation = 0
        self._interrupted_show_target_pos = None
        self._pending_show_target_pos = None

        # 对话框实例引用（防止多实例冲突）
        self._active_file_dialog = None
        self._active_hotkey_dialog = None
        self._active_url_dialog = None
        self._active_command_dialog = None
        self._active_chain_dialog = None
        # 对话框历史强引用，防止因 Python 垃圾回收机制过早销毁窗口包装对象导致的 C++ 崩溃
        self._dialog_history = []

        # 无边框 + 透明背景
        apply_custom_window_chrome(self, kind="window", translucent=True)
        self.setWindowOpacity(0)  # 初始透明度为 0

        # 计算固定窗口大小 - 增加宽度使左右边距一致
        total_width, total_height = self._calculate_window_size()
        self.setFixedSize(total_width, total_height)

        self._setup_ui()
        self._apply_theme()

        # 延迟应用窗口阴影效果（需要在窗口显示后）
        self._shadow_applied = False

        self._lifecycle.defer(0, self._load_initial_folder)

        # 新手引导标记
        self._guide_shown = False

    def _calculate_window_size(self) -> tuple[int, int]:
        icon_grid_width = (
            sp(self.ICON_GRID_PADDING) * 2
            + self.ICON_COLS * sp(self.ICON_WIDGET_SIZE)
            + (self.ICON_COLS - 1) * sp(self.ICON_GRID_SPACING)
        )
        total_width = sp(self.FOLDER_PANEL_WIDTH) + icon_grid_width
        return total_width, sp(560)

    def _show_welcome_guide(self):
        """显示新手引导"""
        if not self._guide_shown:
            self._guide_shown = True
            try:
                from .welcome_integration import show_welcome_if_first_run

                show_welcome_if_first_run(self, self.data_manager)
            except (AttributeError, ImportError, RuntimeError, TypeError):
                logger.exception("新手引导加载失败")

    def showEvent(self, event):
        """窗口显示事件 - 首次运行显示引导、应用阴影效果"""
        generation = self._lifecycle.open_generation()
        centered_show = bool(getattr(self, "_centered_show_animation", False))
        # 预先将窗口移动到偏移起点并设置为全透明，避免任何初始抖动
        pos = QPoint(self.pos())
        interrupted_target = getattr(self, "_interrupted_show_target_pos", None)
        target_pos = QPoint(interrupted_target) if interrupted_target is not None and not centered_show else pos
        self._interrupted_show_target_pos = None
        self._pending_show_target_pos = QPoint(target_pos)
        self.setWindowOpacity(0.0)
        if not centered_show:
            self.move(target_pos.x(), target_pos.y() + sp(16))

        # 每次重新打开时重置高级模式复选框（纯 UI 状态，不持久化）
        panel = getattr(self, "settings_panel", None)
        if panel and hasattr(panel, "advanced_mode_cb"):
            panel.advanced_mode_cb.setChecked(False)

        super().showEvent(event)
        if not self._drag_drop_compat_applied:
            self._drag_drop_compat_applied = True
            self._lifecycle.defer(0, allow_drag_drop_for_widget, self, generation=generation)
        # 立即应用阴影和亚克力效果（去掉延迟，确保窗口零延迟渲染）
        self._apply_window_shadow()
        self._start_show_animation()
        self._schedule_settings_panel_preload(generation)

    def _next_window_animation_generation(self) -> int:
        self._window_animation_generation = int(getattr(self, "_window_animation_generation", 0) or 0) + 1
        return self._window_animation_generation

    def _is_window_animation_current(self, generation: int) -> bool:
        return generation == int(getattr(self, "_window_animation_generation", -1) or -1)

    def _stop_window_animation_timer(self, name: str) -> None:
        timer = getattr(self, name, None)
        if timer is None:
            return
        try:
            if timer.isActive():
                timer.stop()
        except Exception as exc:
            logger.debug("停止窗口动画定时器失败: %s", exc, exc_info=True)

    def hide(self):
        """Hide immediately while preserving a half-finished show target."""
        timer = getattr(self, "_anim_timer", None)
        try:
            show_anim_active = bool(timer is not None and timer.isActive())
        except Exception as exc:
            logger.debug("检查显示动画定时器失败: %s", exc, exc_info=True)
            show_anim_active = False
        if show_anim_active:
            target = getattr(self, "_anim_target_pos", None)
            if target is not None:
                self._interrupted_show_target_pos = QPoint(target)
            self._next_window_animation_generation()
            self._stop_window_animation_timer("_anim_timer")
        self._stop_window_animation_timer("_hide_anim_timer")
        super().hide()

    def _setup_ui(self):
        """设置UI"""
        # 圆角容器
        self.rounded_container = RoundedWindow(self)
        self.setCentralWidget(self.rounded_container)

        main_layout = QVBoxLayout(self.rounded_container)
        main_layout.setContentsMargins(sp(1), sp(1), sp(1), sp(1))
        main_layout.setSpacing(0)

        # 自定义标题栏
        self.title_bar = TitleBar(self)
        self.title_bar.settings_requested.connect(self._show_settings)
        self.title_bar.back_requested.connect(self._show_launcher)
        self.title_bar.update_requested.connect(self._check_update_now)
        main_layout.addWidget(self.title_bar)

        self.top_separator = QFrame()
        self.top_separator.setFixedHeight(0)

        # 内容区域堆栈
        self.stack = QStackedWidget()

        # 1. 启动器视图 (Folder + Icons)
        launcher_widget = QWidget()
        launcher_layout = QHBoxLayout(launcher_widget)
        launcher_layout.setContentsMargins(0, 0, 0, 0)
        launcher_layout.setSpacing(0)

        # 左侧：文件夹面板
        from .folder_panel import FolderPanel

        self.folder_panel = FolderPanel(self.data_manager)
        self.folder_panel.setFixedWidth(sp(self.FOLDER_PANEL_WIDTH))
        self.folder_panel.folder_selected.connect(self._on_folder_selected)
        launcher_layout.addWidget(self.folder_panel)

        # 中间：图标网格
        from .icon_grid import IconGrid

        self.icon_grid = IconGrid(self.data_manager)
        self.icon_grid.shortcut_edit_requested.connect(self._on_shortcut_edit)
        self.icon_grid.shortcut_delete_requested.connect(self._on_shortcut_delete)
        self.icon_grid.shortcut_added.connect(self.settings_changed.emit)  # 拖放添加后刷新弹窗
        self.icon_grid.add_file_requested.connect(self._on_add_file)
        self.icon_grid.add_hotkey_requested.connect(self._on_add_hotkey)
        self.icon_grid.add_url_requested.connect(self._on_add_url)
        self.icon_grid.add_command_requested.connect(self._on_add_command)
        self.icon_grid.add_chain_requested.connect(self._on_add_chain)
        launcher_layout.addWidget(self.icon_grid, 1)

        self.stack.addWidget(launcher_widget)

        # 2. 设置视图（延迟创建，SettingsPanel 是重量模块，仅在用户点击齿轮图标时才创建）
        self.settings_panel = None
        self._settings_placeholder = QWidget()  # 占位符
        self.stack.addWidget(self._settings_placeholder)

        main_layout.addWidget(self.stack, 1)

        # 状态栏
        self.status_bar = QStatusBar()
        self.status_bar.setFixedHeight(sp(22))
        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.setStyleSheet(scale_qss("font-size: 11px; background: transparent; QStatusBar::item { border: none; }"))
        self.status_bar.setContentsMargins(sp(self.FOLDER_PANEL_WIDTH) + sp(4), 0, 0, 0)

        # 右侧版本信息 - 纯文本QLabel
        import platform

        # 判断 Windows 版本
        if platform.system() == "Windows":
            build = int(platform.version().split(".")[-1])
            system_version = f"Win{'11' if build >= 22000 else '10'}"
        else:
            system_version = platform.system()

        # 管理员指示灯：紫色=代码运行，绿色=非管理员，红色=管理员
        import ctypes

        is_compiled = (
            getattr(sys, "frozen", False) or "__compiled__" in dir(__builtins__) or globals().get("__compiled__", False)
        )
        if is_compiled:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            dot_color = "#ff6b6b" if is_admin else "#6bcb77"
            dot_tip = "管理员运行" if is_admin else "普通用户运行"
        else:
            dot_color = "#b39ddb"
            dot_tip = "代码版本运行"
        self.admin_dot = DotWidget(dot_color, dot_tip)
        self.status_bar.addPermanentWidget(self.admin_dot)

        self.version_label = QLabel(f"{system_version} | Vers {APP_VERSION}")
        self.version_label.setFrameStyle(0)
        self.status_bar.addPermanentWidget(self.version_label)

        main_layout.addWidget(self.status_bar)
        self.status_bar.showMessage(tr("就绪"))

    def rescale_ui(self):
        """Re-apply geometry that depends on the current global UI scale."""
        total_width, total_height = self._calculate_window_size()
        self.setFixedSize(total_width, total_height)

        main_layout = self.rounded_container.layout()
        if main_layout is not None:
            main_layout.setContentsMargins(sp(1), sp(1), sp(1), sp(1))
            main_layout.setSpacing(0)

        if hasattr(self, "title_bar"):
            self.title_bar.rescale_ui()
        if hasattr(self, "folder_panel"):
            self.folder_panel.setFixedWidth(sp(self.FOLDER_PANEL_WIDTH))
            if hasattr(self.folder_panel, "rescale_ui"):
                self.folder_panel.rescale_ui()
        if hasattr(self, "status_bar"):
            self.status_bar.setFixedHeight(sp(22))
            self.status_bar.setContentsMargins(sp(self.FOLDER_PANEL_WIDTH) + sp(4), 0, 0, 0)
        if hasattr(self, "icon_grid") and hasattr(self.icon_grid, "rescale_ui"):
            self.icon_grid.rescale_ui()
        if hasattr(self, "settings_panel") and self.settings_panel is not None:
            if hasattr(self.settings_panel, "rescale_ui"):
                self.settings_panel.rescale_ui()

        self._apply_theme()
        self.updateGeometry()
        self.update()

    def _ensure_settings_panel(self):
        """确保设置面板已创建（延迟初始化）"""
        if self.settings_panel is not None:
            return
        try:
            import logging

            logger = logging.getLogger(__name__)
            logger.info("开始创建设置面板...")

            from .settings_panel import SettingsPanel

            self.settings_panel = SettingsPanel(self.data_manager, self.tray_app)
            self.settings_panel.settings_changed.connect(self._on_settings_panel_changed)
            self.settings_panel.color_filter_changed.connect(self._apply_color_filter)
            self.settings_panel.command_settings_changed.connect(self.settings_changed.emit)
            self.settings_panel.import_completed.connect(self._on_import_completed)
            # 连接触发配置变更信号
            if self.tray_app and hasattr(self.tray_app, '_apply_mouse_hook_settings'):
                self.settings_panel.trigger_config_changed.connect(self.tray_app._apply_mouse_hook_settings)

            # 替换占位符
            idx = self.stack.indexOf(self._settings_placeholder)
            self.stack.removeWidget(self._settings_placeholder)
            self._settings_placeholder.deleteLater()
            self._settings_placeholder = None
            self.stack.insertWidget(idx, self.settings_panel)

            # 应用当前主题
            theme = self.data_manager.get_settings().theme
            panel_theme = getattr(self.settings_panel, "current_theme", None)
            if panel_theme != theme and hasattr(self.settings_panel, "apply_theme"):
                self.settings_panel.apply_theme(theme)

            logger.info("设置面板创建成功")
        except Exception as e:
            logger.exception("创建设置面板失败")

            try:
                from ui.styles.themed_messagebox import ThemedMessageBox

                ThemedMessageBox.critical(self, tr("错误"), tr("无法加载设置面板:\n{error}", error=e))
            except Exception as exc:
                logger.debug("显示错误对话框失败: %s", exc, exc_info=True)
            raise

    def _schedule_settings_panel_preload(self, generation: int | None = None):
        """Pre-create the heavy settings panel while the window is idle."""
        if self.settings_panel is not None or self._settings_panel_preload_scheduled:
            return
        self._settings_panel_preload_scheduled = True
        lifecycle = getattr(self, "_lifecycle", None)
        if lifecycle is not None:
            lifecycle.defer(450, self._preload_settings_panel, generation=generation)
        else:
            QTimer.singleShot(450, self._preload_settings_panel)

    def _preload_settings_panel(self):
        self._settings_panel_preload_scheduled = False
        if self.settings_panel is not None or not self.isVisible():
            return
        try:
            self._ensure_settings_panel()
        except Exception:
            logger.debug("预加载设置面板失败", exc_info=True)

    def _show_settings(self):
        try:
            self._ensure_settings_panel()
            self._set_main_page(1, is_settings=True, direction="left")
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"显示设置面板失败: {e}")

    def _check_update_now(self):
        try:
            if self.tray_app and hasattr(self.tray_app, "_check_update_now"):
                self.tray_app._check_update_now(parent=self)
                return

            from services.update.checker import UpdateChecker
            from services.update.ui import UpdateNotification

            checker = UpdateChecker()
            info = checker.check_now()
            if info and not info.has_update:
                UpdateNotification.show_up_to_date(parent=self)
        except Exception as e:
            ThemedMessageBox.warning(self, tr("检查更新失败"), tr("无法检查更新:\n{error}", error=e))

    def _show_launcher(self):
        self._set_main_page(0, is_settings=False, direction="right")

    def _set_main_page(self, index: int, *, is_settings: bool, direction: str = "left"):
        current_index = self.stack.currentIndex()
        current_mode = getattr(self.title_bar, "_in_settings_mode", False)
        status_visible = self.status_bar.isVisible()
        if current_index == index and current_mode == is_settings and status_visible == (not is_settings):
            return

        self.setUpdatesEnabled(False)
        try:
            self._slide_to_page(index, direction=direction)
            self.title_bar.set_mode(is_settings)
            self.status_bar.setVisible(not is_settings)
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def _slide_to_page(self, index, direction="left"):
        """切换页面"""
        if self.stack.currentIndex() == index:
            return
        self.stack.setCurrentIndex(index)

    def capture_view_state(self) -> dict:
        state = {"stack_index": 0}
        try:
            state["stack_index"] = int(self.stack.currentIndex())
        except (AttributeError, RuntimeError, TypeError) as exc:
            logger.debug("捕获配置窗口页面状态失败: %s", exc, exc_info=True)
        settings_panel = getattr(self, "settings_panel", None)
        if settings_panel is not None and hasattr(settings_panel, "capture_view_state"):
            try:
                state.update(settings_panel.capture_view_state())
            except (AttributeError, RuntimeError, TypeError) as exc:
                logger.debug("捕获设置页面状态失败: %s", exc, exc_info=True)
        try:
            state["folder_id"] = getattr(self.icon_grid, "current_folder_id", None)
        except (AttributeError, RuntimeError, TypeError) as exc:
            logger.debug("捕获当前文件夹状态失败: %s", exc, exc_info=True)
        return state

    def restore_view_state(self, state: dict | None):
        if not isinstance(state, dict):
            return
        try:
            stack_index = int(state.get("stack_index", 0) or 0)
        except (TypeError, ValueError):
            stack_index = 0

        if stack_index == 1:
            self._ensure_settings_panel()
            if self.settings_panel is not None and hasattr(self.settings_panel, "restore_view_state"):
                self.settings_panel.restore_view_state(state)
            self._set_main_page(1, is_settings=True)
            return

        self._set_main_page(0, is_settings=False)
        folder_id = state.get("folder_id")
        if folder_id:
            QTimer.singleShot(0, lambda fid=folder_id: self._on_folder_selected(fid))

    def _load_initial_folder(self):
        """加载初始文件夹"""
        folder_id = None

        # 首先尝试从当前选中项获取
        current_item = self.folder_panel.folder_list.currentItem()
        if current_item:
            folder_id = current_item.data(QtCompat.UserRole)

        # 如果没有选中项，查找"常用"文件夹并选中它
        if not folder_id:
            for i in range(self.folder_panel.folder_list.count()):
                item = self.folder_panel.folder_list.item(i)
                fid = item.data(QtCompat.UserRole)
                folder = self.data_manager.data.get_folder_by_id(fid)
                if folder and not folder.is_dock:
                    # 选中这个文件夹
                    self.folder_panel.folder_list.setCurrentItem(item)
                    folder_id = fid
                    break

        # 如果仍然没有找到，尝试使用"default" id
        if not folder_id:
            folder = self.data_manager.data.get_folder_by_id("default")
            if folder:
                folder_id = folder.id

        # 加载文件夹
        if folder_id:
            self._on_folder_selected(folder_id)

    def _get_menu_stylesheet(self) -> str:
        """获取右键菜单样式 — 半透明背景配合模糊效果"""
        theme = self.data_manager.get_settings().theme

        if theme == "dark":
            return scale_qss("""
                QMenu {
                    background-color: rgba(30, 30, 30, 120);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 12px;
                    padding: 6px;
                }
                QMenu::item {
                    background-color: transparent;
                    color: #ffffff;
                    padding: 8px 22px;
                    border-radius: 8px;
                    margin: 2px 4px;
                }
                QMenu::item:selected {
                    background-color: rgba(10, 132, 255, 0.30);
                    color: rgba(255, 255, 255, 0.95);
                }
                QMenu::separator {
                    height: 1px;
                    background-color: rgba(255, 255, 255, 0.12);
                    margin: 6px 10px;
                }
            """)
        else:
            return scale_qss("""
                QMenu {
                    background-color: rgba(255, 255, 255, 120);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 12px;
                    padding: 6px;
                }
                QMenu::item {
                    background-color: transparent;
                    color: #1c1c1e;
                    padding: 8px 22px;
                    border-radius: 8px;
                    margin: 2px 4px;
                }
                QMenu::item:selected {
                    background-color: rgba(0, 122, 255, 0.14);
                    color: rgba(28, 28, 30, 0.96);
                }
                QMenu::separator {
                    height: 1px;
                    background-color: #e5e5ea;
                    margin: 6px 10px;
                }
            """)

    def get_menu_stylesheet(self) -> str:
        """公开方法供子组件调用"""
        return self._get_menu_stylesheet()

    def get_theme(self) -> str:
        """获取当前主题"""
        return self.data_manager.get_settings().theme

    def _apply_theme(self):
        """应用主题 - 磨砂玻璃拟态风格"""
        theme = self.data_manager.get_settings().theme
        self._theme = theme
        toggle_style = get_switch_stylesheet(theme) + get_radio_stylesheet(theme)

        # 使用新的磨砂玻璃拟态样式
        glassmorphism_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)

        if theme == "dark":
            # 深色主题：适度半透明深色背景
            self.rounded_container.set_colors("rgba(28, 28, 30, 180)", "rgba(190, 190, 197, 60)")
        else:
            # 浅色主题：适度半透明浅色背景
            self.rounded_container.set_colors("rgba(242, 242, 247, 160)", "rgba(229, 229, 234, 150)")

        # 应用完整样式表
        self.setStyleSheet(glassmorphism_style + toggle_style)

        self.title_bar.setStyleSheet("background: transparent;")

        # 处理分隔线颜色
        sep_color = "transparent"
        self.top_separator.setStyleSheet(f"background-color: {sep_color};")

        # 设置状态栏颜色
        status_color = "rgba(255, 255, 255, 0.5)" if theme == "dark" else "rgba(0, 0, 0, 0.5)"
        self.status_bar.setStyleSheet(
            scale_qss(f"font-size: 11px; background: transparent; color: {status_color}; QStatusBar::item {{ border: none; }}")
        )
        self.version_label.setStyleSheet(scale_qss(f"font-size: 11px; color: {status_color}; padding: 0; margin-right: 10px;"))

        # 设置标题栏和设置面板主题
        self.title_bar.set_theme(theme)
        if hasattr(self.title_bar, "retranslate_ui"):
            self.title_bar.retranslate_ui()
        if hasattr(self, "_refresh_status_bar"):
            self._refresh_status_bar()
        if hasattr(self, "settings_panel") and hasattr(self.settings_panel, "apply_theme"):
            self.settings_panel.apply_theme(theme)

        if hasattr(self, "icon_grid") and hasattr(self.icon_grid, "apply_theme"):
            try:
                self.icon_grid.apply_theme(theme)
            except Exception as exc:
                logger.debug("应用图标网格主题失败: %s", exc, exc_info=True)

        if hasattr(self.folder_panel, "apply_theme"):
            try:
                self.folder_panel.apply_theme(theme)
            except Exception as exc:
                logger.debug("应用文件夹面板主题失败: %s", exc, exc_info=True)

        # QSS设置font-family/font-size会重建QFont对象，丢失渲染优化属性
        # 递归给所有子控件重新设置 hinting 和抗锯齿
        from ui.utils.font_manager import tune_font_rendering

        tune_font_rendering(self, recursive=True)

        # 切换主题时立即刷新 acrylic/DWM 磨砂玻璃底色，避免新旧主题颜色混合
        self._apply_window_shadow()

        # 刷新颜色滤镜
        self._apply_color_filter()

    def _on_folder_selected(self, folder_id: str):
        """选中文件夹"""
        self.icon_grid.load_folder(folder_id)
        self._refresh_status_bar(folder_id)

    def _refresh_status_bar(self, folder_id: str | None = None):
        if folder_id is None:
            folder_id = getattr(self.icon_grid, "current_folder_id", None)
        if not folder_id:
            self.status_bar.showMessage(tr("就绪"))
            return
        folder = self.data_manager.data.get_folder_by_id(folder_id)
        if folder:
            # 计算所有文件夹的总项数
            total_items = sum(len(f.items) for f in self.data_manager.data.folders)
            self.status_bar.showMessage(
                tr(
                    "当前: {folder} {count}项  共计: {total} 项",
                    folder=folder.name,
                    count=len(folder.items),
                    total=total_items,
                )
            )

    def _begin_shortcut_dialog_action(self, action_key: str | None = None) -> bool:
        if action_key:
            now = time.monotonic()
            last = float(getattr(self, "_shortcut_action_last_trigger_at", {}).get(action_key, 0.0))
            debounce_s = max(0.0, float(getattr(self, "_shortcut_action_debounce_ms", 250)) / 1000.0)
            if last > 0.0 and now - last < debounce_s:
                return False
            self._shortcut_action_last_trigger_at[action_key] = now
        if self._shortcut_edit_active:
            return False
        self._shortcut_edit_active = True
        self._set_shortcut_action_buttons_enabled(False)
        return True

    def _end_shortcut_dialog_action(self):
        # 立即释放，不使用延迟定时器（避免访问已删除的Qt对象）
        self._release_shortcut_dialog_action()

    def _release_shortcut_dialog_action(self):
        self._shortcut_edit_active = False
        self._set_shortcut_action_buttons_enabled(True)

    def _set_shortcut_action_buttons_enabled(self, enabled: bool):
        icon_grid = getattr(self, "icon_grid", None)
        if icon_grid is None:
            return
        for name in ("add_file_btn", "add_hotkey_btn", "add_url_btn", "add_command_btn"):
            btn = getattr(icon_grid, name, None)
            if btn is not None:
                try:
                    btn.setEnabled(enabled)
                except RuntimeError:
                    logger.debug("设置按钮启用状态失败", exc_info=True)

    def _clear_active_dialog_if_current(self, attr_name: str, dialog) -> None:
        if getattr(self, attr_name, None) is dialog:
            setattr(self, attr_name, None)

    def _activate_existing_dialog(self, attr_name: str) -> bool:
        dialog = getattr(self, attr_name, None)
        if dialog is None:
            return False
        try:
            if not dialog.isVisible():
                setattr(self, attr_name, None)
                return False
            dialog.activateWindow()
            dialog.raise_()
            return True
        except RuntimeError:
            setattr(self, attr_name, None)
            return False

    def _run_shortcut_dialog(self, dialog, on_accept, active_attr_name: str | None = None):
        # 记录到对话框历史中保持强引用，防止因局部垃圾回收触发闪退
        if hasattr(self, "_dialog_history"):
            self._dialog_history.append(dialog)
        try:
            if dialog.exec_():
                on_accept(dialog.get_shortcut())
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"对话框执行失败: {e}", exc_info=True)
        finally:
            if hasattr(self, "_dialog_history"):
                self._dialog_history = [item for item in self._dialog_history if item is not dialog]
            if active_attr_name:
                self._clear_active_dialog_if_current(active_attr_name, dialog)
            self._end_shortcut_dialog_action()

    def _on_shortcut_edit(self, shortcut: ShortcutItem):
        """编辑快捷方式"""
        if getattr(shortcut, "_icon_repo_source", "") == "system":
            return
        if not self._begin_shortcut_dialog_action():
            return
        folder_id = self.icon_grid.current_folder_id
        if not shortcut or not folder_id:
            self._end_shortcut_dialog_action()
            return

        folder = self.data_manager.data.get_folder_by_id(folder_id)
        if folder:
            shortcut = next((item for item in folder.items if item.id == shortcut.id), shortcut)

        if shortcut.type == ShortcutType.HOTKEY:
            from .hotkey_dialog import HotkeyDialog

            dialog = HotkeyDialog(self, shortcut)
        elif shortcut.type == ShortcutType.URL:
            from .url_dialog import UrlDialog

            dialog = UrlDialog(self, shortcut)
        elif shortcut.type == ShortcutType.COMMAND:
            from .command_dialog import CommandDialog

            dialog = CommandDialog(self, shortcut)
        elif shortcut.type == ShortcutType.BATCH_LAUNCH:
            from .batch_launch_dialog import BatchLaunchDialog

            dialog = BatchLaunchDialog(self.data_manager, folder_id, self, shortcut)
        elif shortcut.type == ShortcutType.CHAIN:
            from .chain_dialog import ChainDialog

            dialog = ChainDialog(self, shortcut)
        else:
            from .shortcut_dialog import ShortcutDialog

            dialog = ShortcutDialog(self, shortcut)

        old_icon = (shortcut.icon_path if shortcut else "") or ""

        def _apply_update(updated):
            self.data_manager.update_shortcut(folder_id, updated)
            # 图标路径发生变化且新路径有效时，批量重定向同目录下缺失的图标
            if updated.icon_path and updated.icon_path != old_icon:
                redirected = self.data_manager.redirect_missing_icon_paths(updated.icon_path)
                if redirected:
                    import logging

                    logging.getLogger(__name__).info(f"批量重定向图标路径: {redirected} 个")
            self.icon_grid.load_folder(folder_id)
            self.settings_changed.emit()  # 通知弹窗刷新数据

        self._run_shortcut_dialog(dialog, _apply_update)

    def _on_shortcut_delete(self, shortcut: ShortcutItem):
        """删除快捷方式 - 使用自定义主题对话框"""
        if getattr(shortcut, "_icon_repo_source", "") == "system":
            return
        theme = self.data_manager.get_settings().theme

        confirmed = ThemedMessageBox.question(
            self, tr("确认删除"), tr("确定要删除 '{name}' 吗?", name=shortcut.name), theme
        )

        if confirmed:
            folder_id = self.icon_grid.current_folder_id
            self.data_manager.delete_shortcut(folder_id, shortcut.id)
            self.icon_grid.load_folder(folder_id)
            self.settings_changed.emit()  # 通知弹窗刷新数据

    def _on_add_file(self):
        """添加文件快捷方式"""
        # 检查是否已有实例
        if self._activate_existing_dialog("_active_file_dialog"):
            return

        if not self._begin_shortcut_dialog_action("file"):
            return
        folder_id = self.icon_grid.current_folder_id
        if not folder_id:
            self._end_shortcut_dialog_action()
            return

        try:
            from .shortcut_dialog import ShortcutDialog

            dialog = ShortcutDialog(self)
            self._active_file_dialog = dialog
            dialog.finished.connect(lambda dialog=dialog: self._clear_active_dialog_if_current("_active_file_dialog", dialog))

            def _apply_add(shortcut):
                self.data_manager.add_shortcut(folder_id, shortcut)
                self.icon_grid.load_folder(folder_id)
                self.settings_changed.emit()

            self._run_shortcut_dialog(dialog, _apply_add, "_active_file_dialog")
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"创建文件对话框失败: {e}")
            self._clear_active_dialog_if_current("_active_file_dialog", locals().get("dialog"))
            self._end_shortcut_dialog_action()

    def _on_add_hotkey(self):
        """添加快捷键"""
        # 检查是否已有实例
        if self._activate_existing_dialog("_active_hotkey_dialog"):
            return

        if not self._begin_shortcut_dialog_action("hotkey"):
            return
        folder_id = self.icon_grid.current_folder_id
        if not folder_id:
            self._end_shortcut_dialog_action()
            return

        try:
            from .hotkey_dialog import HotkeyDialog

            dialog = HotkeyDialog(self)
            self._active_hotkey_dialog = dialog
            dialog.finished.connect(lambda dialog=dialog: self._clear_active_dialog_if_current("_active_hotkey_dialog", dialog))

            def _apply_add(shortcut):
                self.data_manager.add_shortcut(folder_id, shortcut)
                self.icon_grid.load_folder(folder_id)
                self.settings_changed.emit()

            self._run_shortcut_dialog(dialog, _apply_add, "_active_hotkey_dialog")
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"创建快捷键对话框失败: {e}")
            self._clear_active_dialog_if_current("_active_hotkey_dialog", locals().get("dialog"))
            self._end_shortcut_dialog_action()

    def _on_add_url(self):
        """添加URL"""
        # 检查是否已有实例
        if self._activate_existing_dialog("_active_url_dialog"):
            return

        if not self._begin_shortcut_dialog_action("url"):
            return
        folder_id = self.icon_grid.current_folder_id
        if not folder_id:
            self._end_shortcut_dialog_action()
            return

        try:
            from .url_dialog import UrlDialog

            dialog = UrlDialog(self)
            self._active_url_dialog = dialog
            dialog.finished.connect(lambda dialog=dialog: self._clear_active_dialog_if_current("_active_url_dialog", dialog))

            def _apply_add(shortcut):
                self.data_manager.add_shortcut(folder_id, shortcut)
                self.icon_grid.load_folder(folder_id)
                self.settings_changed.emit()

            self._run_shortcut_dialog(dialog, _apply_add, "_active_url_dialog")
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"创建URL对话框失败: {e}")
            self._clear_active_dialog_if_current("_active_url_dialog", locals().get("dialog"))
            self._end_shortcut_dialog_action()

    def _on_add_command(self):
        """添加命令"""
        # 检查是否已有实例
        if self._activate_existing_dialog("_active_command_dialog"):
            return

        if not self._begin_shortcut_dialog_action("command"):
            return
        folder_id = self.icon_grid.current_folder_id
        if not folder_id:
            self._end_shortcut_dialog_action()
            return

        try:
            from .command_dialog import CommandDialog

            dialog = CommandDialog(self)
            self._active_command_dialog = dialog
            dialog.finished.connect(lambda dialog=dialog: self._clear_active_dialog_if_current("_active_command_dialog", dialog))

            def _apply_add(shortcut):
                self.data_manager.add_shortcut(folder_id, shortcut)
                self.icon_grid.load_folder(folder_id)
                self.settings_changed.emit()

            self._run_shortcut_dialog(dialog, _apply_add, "_active_command_dialog")
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"创建命令对话框失败: {e}")
            self._clear_active_dialog_if_current("_active_command_dialog", locals().get("dialog"))
            self._end_shortcut_dialog_action()

    def _on_add_chain(self):
        """Create an action chain."""
        if self._activate_existing_dialog("_active_chain_dialog"):
            return

        if not self._begin_shortcut_dialog_action("chain"):
            return
        folder_id = self.icon_grid.current_folder_id
        if not folder_id:
            self._end_shortcut_dialog_action()
            return

        try:
            from .chain_dialog import ChainDialog

            dialog = ChainDialog(self)
            self._active_chain_dialog = dialog
            dialog.finished.connect(lambda dialog=dialog: self._clear_active_dialog_if_current("_active_chain_dialog", dialog))

            def _apply_add(shortcut):
                self.data_manager.add_shortcut(folder_id, shortcut)
                self.icon_grid.load_folder(folder_id)
                self.settings_changed.emit()

            self._run_shortcut_dialog(dialog, _apply_add, "_active_chain_dialog")
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Create chain dialog failed: {e}", exc_info=True)
            self._clear_active_dialog_if_current("_active_chain_dialog", locals().get("dialog"))
            self._end_shortcut_dialog_action()

    def _on_settings_panel_changed(self):
        """设置面板变更"""
        # 保存当前选中的文件夹
        current_folder_id = self.icon_grid.current_folder_id

        # 重新加载数据
        self.data_manager.reload()

        self.rescale_ui()

        # 刷新文件夹列表（不触发选中事件）
        if hasattr(self.folder_panel, "_load_folders"):
            # 临时断开信号
            try:
                self.folder_panel.folder_selected.disconnect()
            except Exception as exc:
                logger.debug("断开文件夹选择信号失败: %s", exc, exc_info=True)

            self.folder_panel._load_folders()

            # 恢复选中状态
            if current_folder_id:
                for i in range(self.folder_panel.folder_list.count()):
                    item = self.folder_panel.folder_list.item(i)
                    if item.data(QtCompat.UserRole) == current_folder_id:
                        self.folder_panel.folder_list.setCurrentRow(i)
                        break

            # 重新连接信号
            self.folder_panel.folder_selected.connect(self._on_folder_selected)

        # 重新加载图标网格以刷新图标
        if current_folder_id:
            self.icon_grid.load_folder(current_folder_id)

        self.settings_changed.emit()

        # 更新颜色滤镜
        self._apply_color_filter()

    def _on_import_completed(self, count: int):
        """导入完成处理"""
        # 刷新UI
        folder_id = self.icon_grid.current_folder_id
        if folder_id:
            self.icon_grid.load_folder(folder_id)

        # 刷新文件夹列表（因为可能新建了文件夹）
        if hasattr(self.folder_panel, "_load_folders"):
            self.folder_panel._load_folders()

        self.settings_changed.emit()

    def closeEvent(self, event):
        """窗口关闭时确保数据已保存"""
        lifecycle = getattr(self, "_lifecycle", None)
        if lifecycle is not None:
            lifecycle.close_generation()
            lifecycle.stop_timers()
        self._settings_panel_preload_scheduled = False
        resize_region_timer = getattr(self, "_resize_region_timer", None)
        if resize_region_timer is not None:
            try:
                resize_region_timer.stop()
            except Exception as exc:
                logger.debug("停止窗口区域更新定时器失败: %s", exc, exc_info=True)
        settings_panel = getattr(self, "settings_panel", None)
        if settings_panel is not None and hasattr(settings_panel, "stop_background_timers"):
            try:
                settings_panel.stop_background_timers()
            except Exception as exc:
                logger.debug("停止后台定时器失败: %s", exc, exc_info=True)
        icon_grid = getattr(self, "icon_grid", None)
        if icon_grid is not None and hasattr(icon_grid, "_stop_icon_thread"):
            try:
                icon_grid._stop_icon_thread()
            except Exception as exc:
                logger.debug("停止图标加载线程失败: %s", exc, exc_info=True)
        if icon_grid is not None and hasattr(icon_grid, "_stop_favicon_fetch_thread"):
            try:
                icon_grid._stop_favicon_fetch_thread()
            except Exception as exc:
                logger.debug("停止批量 favicon 线程失败: %s", exc, exc_info=True)
        try:
            # 强制保存所有待保存的数据
            self.data_manager.flush_pending_save()
        except Exception as exc:
            logger.debug("保存数据失败: %s", exc, exc_info=True)
        super().closeEvent(event)

    def _start_show_animation(self):
        """苹果风格的高质感弹性滑入动画 - 100% 兼容编译及免崩溃设计"""
        generation = self._next_window_animation_generation()
        self._stop_window_animation_timer("_anim_timer")
        self._stop_window_animation_timer("_hide_anim_timer")
        start_pos = QPoint(self.pos())
        offset_px = 0 if bool(getattr(self, "_centered_show_animation", False)) else sp(16)
        target_pos = getattr(self, "_pending_show_target_pos", None)
        if target_pos is None:
            target_pos = QPoint(start_pos.x(), start_pos.y() - offset_px)
        else:
            target_pos = QPoint(target_pos)
        self._pending_show_target_pos = None
        self._anim_start_pos = start_pos
        self._anim_target_pos = target_pos
        self._anim_start_opacity = max(0.0, min(1.0, float(self.windowOpacity())))

        # 动画参数
        self._anim_step = 0
        self._anim_duration_ms = 240  # 240ms 流畅的主窗口动效
        self._anim_interval_ms = 16  # 16ms (60 FPS) 完美同步显示器刷新率，防止 DWM 阻塞
        self._anim_total_steps = max(1, self._anim_duration_ms // self._anim_interval_ms)

        # 创建并启动定时器
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(self._anim_interval_ms)
        set_precise_timer(self._anim_timer, owner="ConfigWindow._anim_timer")
        self._anim_timer.timeout.connect(lambda generation=generation: self._on_main_animation_tick(generation))
        self._anim_timer.start()

    def _on_main_animation_tick(self, generation: int | None = None):
        if generation is not None and not self._is_window_animation_current(generation):
            return
        self._anim_step += 1
        progress = self._anim_step / self._anim_total_steps

        if progress >= 1.0:
            progress = 1.0
            if hasattr(self, "_anim_timer"):
                self._anim_timer.stop()

        # Easing curve: EaseOutCubic (平滑指数级物理减速，无回弹，滑入极度丝滑且收尾无顿感)
        t = progress - 1.0
        eased = t * t * t + 1.0

        # 加速透明度淡入：在 67% 的进度时透明度就达到 1.0，从而提前关闭 DWM 混合层以消除卡顿
        start_opacity = float(getattr(self, "_anim_start_opacity", 0.0))
        self.setWindowOpacity(min(1.0, start_opacity + (1.0 - start_opacity) * progress * 1.5))

        start_pos = getattr(self, "_anim_start_pos", self.pos())
        target_pos = self._anim_target_pos
        current_x = int(start_pos.x() + (target_pos.x() - start_pos.x()) * eased)
        current_y = int(start_pos.y() + (target_pos.y() - start_pos.y()) * eased)
        self.move(current_x, current_y)
        if progress >= 1.0:
            self._centered_show_animation = False

    def animate_close_then(self, callback=None, *, callback_delay_ms: int | None = None):
        """Play a short disappearance animation and optionally overlap the callback."""
        generation = self._next_window_animation_generation()
        for timer_name in ("_anim_timer", "_hide_anim_timer"):
            self._stop_window_animation_timer(timer_name)
        stop_named_animations(self, "anim_group", "hide_anim_group")

        if callback and callback_delay_ms is not None:
            QTimer.singleShot(
                max(0, int(callback_delay_ms)),
                lambda generation=generation, callback=callback: self._run_window_animation_callback(
                    generation, callback
                ),
            )
            callback = None

        start_pos = self.pos()
        self._hide_anim_callback = callback
        self._hide_anim_start_pos = start_pos
        self._hide_anim_target_pos = QPoint(start_pos.x(), start_pos.y())
        self._hide_anim_start_opacity = float(self.windowOpacity())
        self._hide_anim_step = 0
        self._hide_anim_duration_ms = 180
        self._hide_anim_interval_ms = 16
        self._hide_anim_total_steps = max(1, self._hide_anim_duration_ms // self._hide_anim_interval_ms)

        self._hide_anim_timer = QTimer(self)
        self._hide_anim_timer.setInterval(self._hide_anim_interval_ms)
        set_precise_timer(self._hide_anim_timer, owner="ConfigWindow._hide_anim_timer")
        self._hide_anim_timer.timeout.connect(lambda generation=generation: self._on_hide_animation_tick(generation))
        self._hide_anim_timer.start()

    def _run_window_animation_callback(self, generation: int, callback) -> None:
        if not self._is_window_animation_current(generation):
            return
        try:
            callback()
        except Exception as exc:
            logger.debug("窗口动画回调执行失败: %s", exc, exc_info=True)

    def _on_hide_animation_tick(self, generation: int | None = None):
        if generation is not None and not self._is_window_animation_current(generation):
            return
        self._hide_anim_step += 1
        progress = min(1.0, self._hide_anim_step / self._hide_anim_total_steps)
        eased = 1.0 - (1.0 - progress) * (1.0 - progress) * (1.0 - progress)

        start = self._hide_anim_start_pos
        target = self._hide_anim_target_pos
        current_y = int(start.y() + (target.y() - start.y()) * eased)
        self.move(start.x(), current_y)
        start_opacity = float(getattr(self, "_hide_anim_start_opacity", 1.0))
        self.setWindowOpacity(max(0.0, start_opacity * (1.0 - progress)))

        if progress < 1.0:
            return

        try:
            self._hide_anim_timer.stop()
        except Exception as exc:
            logger.debug("停止隐藏动画失败: %s", exc, exc_info=True)

        callback = getattr(self, "_hide_anim_callback", None)
        self.close()
        if callback:
            QTimer.singleShot(
                0,
                lambda generation=generation, callback=callback: self._run_window_animation_callback(
                    generation, callback
                ),
            )

    def _apply_color_filter(self):
        """读取设置并通过修改 Acrylic 底色参数来应用颜色滤镜 (仅 Win11)"""
        if not is_win11():
            return
        try:
            from ui.styles.color_filter_overlay import compute_graded_tint

            settings = self.data_manager.get_settings()
            theme = settings.theme or "dark"

            bp = getattr(settings, f"{theme}_black_point", 50)
            wp = getattr(settings, f"{theme}_white_point", 50)
            mg = getattr(settings, f"{theme}_mid_gamma", 50)
            tp = getattr(settings, f"{theme}_temperature", 50)
            acrylic_val = getattr(settings, f"{theme}_acrylic", 30)
            bg_alpha_val = getattr(settings, f"{theme}_bg_alpha_filter", 100)

            r, g, b = compute_graded_tint(theme, bp, wp, mg, tp)

            # Acrylic 滑块 (1-255): 控制磨砂强度
            # 底色α 滑块 (1-255): 作为整体透明度的缩放系数
            base_alpha = max(5, min(int(acrylic_val), 250))
            scale = max(0.05, min(int(bg_alpha_val) / 100.0, 2.55))
            gradient_alpha = max(5, min(int(base_alpha * scale), 250))
            gradient_color = f"{gradient_alpha:02x}{r:02x}{g:02x}{b:02x}"

            hwnd = int(self.winId())
            if hwnd:
                effect = get_window_effect()
                effect.apply_unified_blur_effect(hwnd, gradient_color, enable=True)
        except Exception as exc:
            logger.debug("应用颜色滤镜失败: %s", exc, exc_info=True)

    def _apply_window_shadow(self):
        """应用窗口圆角和平台相关视觉效果"""
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return

            effect = get_window_effect()
            radius = 8
            theme = self.data_manager.get_settings().theme
            is_win11_platform = is_win11()
            state = (theme, is_win11_platform, self.width(), self.height(), radius)
            if state == getattr(self, "_window_shadow_state", None):
                return

            # 强制刷新效果状态
            # self._shadow_applied = True # Removed this flag check logic

            # Win11 使用 DWM 原生圆角 + 阴影 + Acrylic 效果
            if is_win11_platform:
                effect.set_round_corners(hwnd, enable=True)
                effect.enable_window_shadow(hwnd, radius)
                # 启用磨砂玻璃效果 - 使用更低的 alpha (10) 获得极度透明的模糊
                enable_acrylic_for_config_window(self, theme, blur_amount=10)
            else:
                # Win10: 只做区域裁剪，背景由 Qt 自绘，避免 DWM/Acrylic 黑色遮罩。
                enable_acrylic_for_config_window(self, theme, blur_amount=8, radius=radius)
            self._window_shadow_state = state
        except Exception as exc:
            logger.debug("应用窗口阴影失败: %s", exc, exc_info=True)

    def _schedule_resize_region_update(self):
        if is_win11():
            return
        state = (self.width(), self.height(), 12)
        if state == getattr(self, "_resize_region_last_state", None):
            return
        self._resize_region_pending_state = state
        timer = getattr(self, "_resize_region_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._apply_pending_resize_region)
            self._resize_region_timer = timer
        if not timer.isActive():
            timer.start(50)

    def _apply_pending_resize_region(self):
        """合并 Win10 resize 期间的 region/DWM 调用。"""
        state = getattr(self, "_resize_region_pending_state", None)
        if state is None or state == getattr(self, "_resize_region_last_state", None):
            return
        w, h, radius = state
        if w <= 0 or h <= 0:
            return
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return
            effect = get_window_effect()
            effect.set_window_region(hwnd, w, h, radius)
            effect.set_dwm_blur_behind(hwnd, 0, 0, 0, enable=False)
            self._resize_region_last_state = state
        except Exception as exc:
            logger.debug("调整窗口大小时更新圆角失败: %s", exc, exc_info=True)

    def resizeEvent(self, event):
        """窗口大小变化时更新圆角区域（仅 Win10 需要）"""
        super().resizeEvent(event)
        try:
            self._schedule_resize_region_update()
        except Exception as exc:
            logger.debug("调整窗口大小时更新圆角失败: %s", exc, exc_info=True)
