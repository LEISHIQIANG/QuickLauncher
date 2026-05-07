"""
设置面板 - 分类导航版本
"""

import os
import sys
import shutil
import time
import winreg
import logging
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ui.tooltip_helper import install_tooltip
from qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QFormLayout, QSlider, QSpinBox, QRadioButton,
    QButtonGroup, QLabel, QFrame, QCheckBox,
    QLineEdit, QPushButton, QPlainTextEdit, QListWidget, QListWidgetItem, QFileDialog, QScrollArea, QMessageBox,
    QPainter, QPixmap, QColor, QPen, QBrush, QRect, QRectF, QDialog, QTimer, QIcon, QStackedWidget,
    Qt, QtCompat, pyqtSignal, PYQT_VERSION, QThread, QStyledItemDelegate, QSize, QKeySequence, QMenu, QAction, QComboBox,
    QPainterPath, exec_dialog, QPoint, QApplication
)

from core import APP_VERSION, DataManager, DEFAULT_SPECIAL_APPS, ShortcutItem, ShortcutType
from core.app_scanner import AppScanner
from .theme_helper import apply_theme_to_dialog, get_radio_stylesheet, get_switch_stylesheet
from .settings_helpers import NumberedListDelegate, ProgressDialog, ExportThread, ImportThread
from .folder_panel import PopupMenu
from ui.styles.style import StyleSheet
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.utils.font_manager import get_font_family, get_font_css_with_size
from ui.utils.window_effect import get_window_effect
from .settings_page_helpers import SettingsPageHelpersMixin
from .settings_system_page import SettingsSystemPageMixin
from .settings_appearance_page import SettingsAppearancePageMixin
from .settings_popup_page import SettingsPopupPageMixin
from .settings_data_page import SettingsDataPageMixin
from .settings_about_page import SettingsAboutPageMixin
from .settings_data_actions import SettingsDataActionsMixin

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
        self.corner_radius = 8 if is_win11() else 12
        self._acrylic_applied = False
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
        self.title_label.setStyleSheet("font-size: 13px; font-weight: 500;")
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_layout.addWidget(self.title_label, 1)

        main_layout.addLayout(self.title_layout)

        # 消息内容
        self.msg_label = QLabel("正在处理...")
        self.msg_label.setWordWrap(True)
        self.msg_label.setAlignment(QtCompat.AlignLeft | QtCompat.AlignTop)
        self.msg_label.setStyleSheet(
            f"font-family: 'Segoe UI', 'Microsoft YaHei UI', sans-serif; "
            f"font-size: 11px; line-height: 1.4; padding-left: 32px; "
            f"background: transparent; color: {self.text_color};"
        )
        main_layout.addWidget(self.msg_label)

        # 按钮
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(6)
        self.btn_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_layout.addStretch()
        self.ok_btn = QPushButton("确定")
        self.ok_btn.setDefault(True)
        self.ok_btn.setFixedHeight(22)
        self.ok_btn.setMinimumWidth(52)
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setVisible(False)
        self.btn_layout.addWidget(self.ok_btn)
        main_layout.addLayout(self.btn_layout)

        from ui.styles.style import get_dialog_stylesheet
        self.setStyleSheet(get_dialog_stylesheet(self.theme))

    def paintEvent(self, event):
        """背景绘制 - 完全按照ThemedMessageBox的逻辑"""
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)

        from ui.utils.window_effect import is_win10
        if is_win10():
            painter.setRenderHint(QtCompat.HighQualityAntialiasing, True)
            painter.setRenderHint(QtCompat.SmoothPixmapTransform, True)

        inset = 1.0 if is_win10() else 0.5

        path = QPainterPath()
        path.addRoundedRect(
            inset, inset,
            self.width() - inset * 2, self.height() - inset * 2,
            self.corner_radius, self.corner_radius
        )

        # 磨砂玻璃模式：与ThemedMessageBox完全一致
        tint_color = QColor(self.bg_color)
        if is_win10():
            tint_color.setAlpha(min(tint_color.alpha(), 150))
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
        except Exception:
            pass

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

class NavigationItem(QListWidgetItem):
    def __init__(self, text, icon_name=None, theme="dark"):
        super().__init__(text)
        self.setTextAlignment(QtCompat.AlignLeft | QtCompat.AlignVCenter)
        self.setSizeHint(QSize(0, 40))
        # 字体通过样式表和全局字体设置，不在这里单独设置

class NavigationWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(140)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.setSpacing(4)
        # 通过 QFont 对象设置 PreferNoHinting，避免中文字被压扁
        from ui.utils.font_manager import get_qfont
        self.setFont(get_qfont(13))
        
    def apply_theme(self, theme):
        if theme == "dark":
            self.setStyleSheet("""
                QListWidget {
                    background-color: transparent;
                    border: none;
                    outline: none;
                    padding-top: 10px;
                }
                QListWidget::item {
                    background-color: transparent;
                    color: rgba(255, 255, 255, 0.6);
                    border-radius: 6px;
                    padding-left: 12px;
                    margin: 2px 8px;
                }
                QListWidget::item:selected {
                    background-color: rgba(255, 255, 255, 0.15);
                    color: #ffffff;
                }
                QListWidget::item:hover:!selected {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: rgba(255, 255, 255, 0.9);
                }
            """)
        else:
            self.setStyleSheet("""
                QListWidget {
                    background-color: transparent;
                    border: none;
                    outline: none;
                    padding-top: 10px;
                }
                QListWidget::item {
                    background-color: transparent;
                    color: rgba(0, 0, 0, 0.6);
                    border-radius: 6px;
                    padding-left: 12px;
                    margin: 2px 8px;
                }
                QListWidget::item:selected {
                    background-color: rgba(0, 0, 0, 0.08);
                    color: #000000;
                }
                QListWidget::item:hover:!selected {
                    background-color: rgba(0, 0, 0, 0.04);
                    color: rgba(0, 0, 0, 0.8);
                }
            """)

class BaseSettingPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        # 隐藏垂直滚动条，但仍可通过鼠标滚轮滚动
        self.setVerticalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
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
        group = QGroupBox(title)
        group.setFont(get_qfont(14))

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
                padding-left: 0px;
                color: white;
            }
        """)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self.layout.addWidget(group)
        return layout, group

    def apply_theme(self, theme):
        """应用主题到所有分组标题和按钮"""
        title_color = "rgba(28,28,30,0.9)" if theme == "light" else "rgba(255,255,255,0.9)"

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
                padding-left: 0px;
                color: {title_color};
                font-weight: 500;
            }}
        """

        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(style)
            
        # 应用按钮样式 — 与主窗口底部按钮一致
        if theme == "dark":
            btn_bg = "rgba(255,255,255,0.18)"
            btn_border = "rgba(255,255,255,0.22)"
            btn_hover = "rgba(255,255,255,0.28)"
            btn_hover_text = "rgba(255,255,255,0.95)"
            text_color = "rgba(255,255,255,0.85)"
        else:
            btn_bg = "rgba(255,255,255,0.75)"
            btn_border = "rgba(255,255,255,0.35)"
            btn_hover = "rgba(255,255,255,0.95)"
            btn_hover_text = "rgba(28,28,30,0.9)"
            text_color = "rgba(28,28,30,0.75)"

        btn_style = f"""
            QPushButton {{
                font-size: 11px;
                padding: 5px 12px;
                background: {btn_bg};
                border: 1px solid {btn_border};
                border-radius: 8px;
                color: {text_color};
                font-weight: 400;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
                color: {btn_hover_text};
            }}
            QPushButton:pressed {{ opacity: 0.7; }}
            QPushButton:disabled {{
                color: rgba(128,128,128,0.4);
                background: rgba(128,128,128,0.08);
                border: 1px solid rgba(128,128,128,0.15);
            }}
            QPushButton:checked {{
                background-color: rgba(10,132,255,0.85);
                color: white;
                border: 1px solid rgba(10,132,255,0.9);
            }}
        """

        for btn in self.findChildren(QPushButton):
            if "清除所有配置" in btn.text():
                continue
            btn.setStyleSheet(btn_style)

class SettingsPanel(SettingsPageHelpersMixin, SettingsSystemPageMixin, SettingsAppearancePageMixin, SettingsPopupPageMixin, SettingsDataPageMixin, SettingsAboutPageMixin, SettingsDataActionsMixin, QWidget):
    settings_changed = pyqtSignal()
    import_completed = pyqtSignal(int)
    back_requested = pyqtSignal()
    hotkey_recording_changed = pyqtSignal(bool)
    special_apps_changed = pyqtSignal()
    
    def __init__(self, data_manager: DataManager):
        super().__init__()
        self.data_manager = data_manager
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
            from .theme_helper import get_switch_stylesheet, get_radio_stylesheet
            
            # 综合样式表
            full_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
            full_style += get_switch_stylesheet(theme)
            full_style += get_radio_stylesheet(theme)
            
            # 设置主样式
            self.setStyleSheet(full_style)
            
            # 为 QLabel 标题等设置特定样式 (如果需要)
            text_color = "rgba(255, 255, 255, 0.9)" if theme == "dark" else "rgba(28, 28, 30, 0.9)"
            self.setStyleSheet(self.styleSheet() + f"\nQLabel {{ color: {text_color}; }}")
            
        except Exception as e:
            logger.debug("Failed to apply SettingsPanel theme: %s", e, exc_info=True)

        # Apply theme to all pages (for updating group box titles)
        pages = [
            self.page_system, self.page_appearance, self.page_popup,
            self.page_data, self.page_about
        ]
        for page in pages:
            if hasattr(page, 'apply_theme'):
                page.apply_theme(theme)

        # 更新描述文字颜色
        desc_color = self._get_desc_color()
        for obj_name in ["data_desc_1", "data_desc_2", "data_desc_3", "context_menu_desc"]:
            label = self.findChild(QLabel, obj_name)
            if label:
                style = label.styleSheet()
                import re
                new_style = re.sub(r'color:\s*#[0-9a-fA-F]{6};', f'color: {desc_color};', style)
                label.setStyleSheet(new_style)

        # 更新右键菜单卡片描述
        if hasattr(self, 'context_menu_cards'):
            for menu_id, card in self.context_menu_cards.items():
                desc_label = card.findChild(QLabel, f"desc_{menu_id}")
                if desc_label:
                    desc_label.setStyleSheet(f"{get_font_css_with_size(11, 400)} color: {desc_color}; background: transparent; border: none;")
        

        
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
            4: self._setup_about_page,
        }
        # 需要底部 stretch 的页面
        self._pages_need_stretch = {0, 1, 3, 4}
        # 已初始化的页面索引集合
        self._initialized_pages = set()
        # 页面引用（索引 -> BaseSettingPage）
        self._pages = {}

        # 为所有页面创建空的 BaseSettingPage 占位
        page_attrs = [
            'page_system', 'page_appearance', 'page_popup',
            'page_data', 'page_about'
        ]
        for i in range(5):
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
            if hasattr(page, 'apply_theme'):
                page.apply_theme(theme)
        except Exception:
            pass

    def _init_nav_items(self):
        items = [
            ("系统设置", 0),
            ("弹窗外观", 1),
            ("弹窗交互", 2),
            ("配置管理", 3),
            ("关于软件", 4)
        ]
        
        for text, index in items:
            item = NavigationItem(text)
            item.setData(QtCompat.UserRole, index)
            self.nav_widget.addItem(item)
            
        self.nav_widget.setCurrentRow(0)










    def _update_ui_state_for_mode(self, mode):
        # 1. Visual Effects Group Visibility
        # 跟随主题模式和亚克力模式都隐藏视觉特效调节
        # 亚克力模式采用和配置窗口一样的磨砂玻璃效果，不需要手动调节模糊度/高光
        if mode == "theme" or mode == "acrylic":
            self.visual_effect_group.setVisible(False)
        else:
            self.visual_effect_group.setVisible(True)
            
        # 2. Window Corner Radius - 所有模式下均可调节圆角
        # 亚克力模式使用 paintEvent 绘制完美圆角，不再依赖 DWM
        if not self.corner_spin.isEnabled() or self.corner_spin.value() == 0:
            settings = self.data_manager.get_settings()
            self.corner_spin.blockSignals(True)
            self.corner_spin.setValue(settings.corner_radius)
            self.corner_spin.blockSignals(False)
        self.corner_spin.setEnabled(True)

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
                pass  # about page is static
        finally:
            self._updating = old_updating

    def _load_system_settings(self, settings):
        try:
            from core.auto_start_manager import is_auto_start_enabled
            actual_enabled = is_auto_start_enabled()

            if settings.auto_start != actual_enabled:
                self.data_manager.update_settings(auto_start=actual_enabled)

            self.auto_start_cb.setChecked(actual_enabled)
        except Exception as e:
            logger.debug("Failed to load auto-start state: %s", e, exc_info=True)
            self.auto_start_cb.setChecked(False)
            self.data_manager.update_settings(auto_start=False)

        self.show_on_startup_cb.setChecked(settings.show_on_startup)
        self.hw_accel_cb.setChecked(settings.hardware_acceleration)
        self.hide_tray_cb.setChecked(settings.hide_tray_icon)
        self.disable_logging_cb.setChecked(getattr(settings, 'disable_logging', False))
        self.debug_log_cb.setChecked(getattr(settings, 'enable_debug_log', False))

        # 主题设置
        follow_system = getattr(settings, 'theme_follow_system', True)
        if follow_system:
            self.follow_system_radio.setChecked(True)
        elif settings.theme == "dark":
            self.dark_radio.setChecked(True)
        else:
            self.light_radio.setChecked(True)

    def _load_appearance_settings(self, settings):
        self.icon_size_spin.setValue(settings.icon_size)
        self.cell_size_spin.setValue(settings.cell_size)
        self.cols_spin.setValue(settings.cols)
        self.corner_spin.setValue(settings.corner_radius)

        if not settings.dock_enabled:
            self.dock_height_spin.setValue(0)
        else:
            self.dock_height_spin.setValue(settings.dock_height_mode)

        self.popup_max_rows_spin.setValue(getattr(settings, 'popup_max_rows', 3))

        self.bg_alpha_slider.setValue(settings.bg_alpha)
        self.bg_alpha_label.setText(f"{settings.bg_alpha}%")
        self.dock_bg_alpha_slider.setValue(settings.dock_bg_alpha)
        self.dock_bg_alpha_label.setText(f"{settings.dock_bg_alpha}%")
        self.icon_alpha_slider.setValue(int(settings.icon_alpha * 100))
        self.icon_alpha_label.setText(f"{int(settings.icon_alpha * 100)}%")

        self.bg_path_edit.setText(settings.custom_bg_path)

        self.blur_radius_slider.setValue(settings.bg_blur_radius)
        self.blur_radius_label.setText(str(settings.bg_blur_radius))

        self.edge_opacity_slider.setValue(int(settings.edge_highlight_opacity * 100))
        self.edge_opacity_label.setText(f"{int(settings.edge_highlight_opacity * 100)}%")

        current_alpha = settings.bg_alpha
        current_blur = settings.bg_blur_radius
        current_edge = settings.edge_highlight_opacity

        if settings.bg_mode == "theme":
            self.bg_theme_radio.setChecked(True)
            self.bg_image_widget.setVisible(False)
            current_alpha = getattr(settings, 'theme_bg_alpha', 90)
            current_blur = getattr(settings, 'theme_blur_radius', 0)
            current_edge = getattr(settings, 'theme_edge_opacity', 0.0)
        elif settings.bg_mode == "image":
            self.bg_image_radio.setChecked(True)
            self.bg_image_widget.setVisible(True)
            current_alpha = getattr(settings, 'image_bg_alpha', 90)
            current_blur = getattr(settings, 'image_blur_radius', 0)
            current_edge = getattr(settings, 'image_edge_opacity', 0.0)
        elif settings.bg_mode == "acrylic":
            self.bg_acrylic_radio.setChecked(True)
            self.bg_image_widget.setVisible(False)
            current_alpha = getattr(settings, 'acrylic_bg_alpha', 90)
            current_blur = getattr(settings, 'acrylic_blur_radius', 0)
            current_edge = getattr(settings, 'acrylic_edge_opacity', 0.0)

        self.bg_alpha_slider.blockSignals(True)
        self.bg_alpha_slider.setValue(current_alpha)
        self.bg_alpha_slider.blockSignals(False)
        self.bg_alpha_label.setText(f"{current_alpha}%")

        self.blur_radius_slider.blockSignals(True)
        self.blur_radius_slider.setValue(current_blur)
        self.blur_radius_slider.blockSignals(False)
        self.blur_radius_label.setText(str(current_blur))

        self.edge_opacity_slider.blockSignals(True)
        self.edge_opacity_slider.setValue(int(current_edge * 100))
        self.edge_opacity_slider.blockSignals(False)
        self.edge_opacity_label.setText(f"{int(current_edge * 100)}%")

        self._update_ui_state_for_mode(settings.bg_mode)

        self.bg_path_edit.setText(settings.custom_bg_path)

    def _load_popup_settings(self, settings):
        if settings.popup_align_mode == "mouse_top_left":
            self.pos_mouse_tl.setChecked(True)
        else:
            self.pos_mouse_center.setChecked(True)

        popup_auto_close = getattr(settings, 'popup_auto_close', True)
        if popup_auto_close:
            self.auto_close_yes.setChecked(True)
        else:
            self.auto_close_no.setChecked(True)
        self.delay_widget.setVisible(popup_auto_close)

        self.delay_slider.setValue(settings.hover_leave_delay)
        self.delay_label.setText(f"{settings.hover_leave_delay}ms")

        double_click_interval = getattr(settings, 'double_click_interval', 300)
        self.double_click_slider.setValue(double_click_interval)
        self.double_click_label.setText(f"{double_click_interval}ms")

        self.special_apps_list.clear()
        for app in settings.special_apps:
            item = QListWidgetItem(app)
            item.setFlags(item.flags() | QtCompat.ItemIsDragEnabled | QtCompat.ItemIsEditable)
            self.special_apps_list.addItem(item)


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

    # === Event Handlers ===
    
    def _on_auto_start_changed_legacy(self, state):
        if self._updating:
            return

        checked = state == 2
        import logging
        logger = logging.getLogger(__name__)

        if checked:
            self._updating = True

            from core.auto_start_manager import enable_auto_start
            success, method = enable_auto_start()
            logger.info(f"开机自启：启用结果 success={success}, method={method}")

            if success:
                self.data_manager.update_settings(auto_start=True)
                self._updating = False
                # 成功时静默完成，不弹窗
            else:
                self.data_manager.update_settings(auto_start=False)
                self._updating = False
                logger.error("开机自启：启用失败")
                ThemedMessageBox.critical(self, "启用失败",
                    "可能原因：\n"
                    "• 杀毒软件拦截\n"
                    "• 系统策略禁止修改启动项\n\n"
                    "建议：将程序添加到杀毒软件白名单后重试")
                QTimer.singleShot(0, lambda: self._reset_checkbox_state(False))
        else:
            self._updating = True
            logger.info("开机自启：开始禁用")
            from core.auto_start_manager import disable_auto_start
            disable_auto_start()
            # 清理旧服务（如果有）
            try:
                from core.service_manager import _cleanup_legacy_service
                _cleanup_legacy_service()
            except Exception as e:
                logger.debug("Legacy service cleanup failed while disabling auto-start: %s", e)
            self.data_manager.update_settings(auto_start=False)
            self._updating = False
            logger.info("开机自启：禁用完成")

    def _on_auto_start_changed(self, state):
        if self._updating:
            return

        checked = state == 2
        import logging
        logger = logging.getLogger(__name__)

        if checked:
            self._updating = True
            from core.auto_start_manager import enable_auto_start

            success, method = enable_auto_start()
            logger.info(f"开机自启：启用结果 success={success}, method={method}")

            if success:
                self.data_manager.update_settings(auto_start=True)
                self._updating = False
                return

            self.data_manager.update_settings(auto_start=False)
            self._updating = False
            logger.error("开机自启：启用失败")

            if method == "cancelled":
                ThemedMessageBox.warning(self, "已取消", "你取消了管理员授权，自启动未启用。")
            else:
                ThemedMessageBox.critical(
                    self,
                    "启用失败",
                    "helper 创建开机自启失败。\n\n请检查 UAC、任务计划程序服务和日志。"
                )
            QTimer.singleShot(0, lambda: self._reset_checkbox_state(False))
            return

        self._updating = True
        logger.info("开机自启：开始禁用")
        from core.auto_start_manager import disable_auto_start

        success, method = disable_auto_start()

        try:
            from core.service_manager import _cleanup_legacy_service
            _cleanup_legacy_service()
        except Exception:
            pass

        if success:
            self.data_manager.update_settings(auto_start=False)
            self._updating = False
            logger.info("开机自启：禁用完成")
            return

        self._updating = False
        if method == "cancelled":
            ThemedMessageBox.warning(self, "已取消", "你取消了管理员授权，自启动保持原状。")
        else:
            ThemedMessageBox.critical(self, "禁用失败", "helper 禁用开机自启失败，自启动保持原状。")
        QTimer.singleShot(0, lambda: self._reset_checkbox_state(True))

    def _reset_checkbox_state(self, checked):
        self._updating = True
        self.auto_start_cb.setChecked(checked)
        self._updating = False

    def _on_startup_show_changed(self, state):
        if self._updating: return
        self.data_manager.update_settings(show_on_startup=(state == 2))

    def _on_hw_accel_changed(self, state):
        if self._updating: return
        self.data_manager.update_settings(hardware_acceleration=(state == 2))

    def _on_hide_tray_changed(self, state):
        if self._updating: return
        checked = state == 2
        self.data_manager.update_settings(hide_tray_icon=checked)
        if checked:
            ThemedMessageBox.information(
                self,
                "提示",
                "托盘图标已隐藏。\n如需再次进入设置，请使用内置命令'配置窗口' (show_config_window)。"
            )

    def _on_disable_logging_changed(self, state):
        if self._updating: return
        checked = state == 2
        if checked:
            reply = ThemedMessageBox.question(
                self,
                "确认关闭日志",
                "关闭日志后将停止记录运行日志到 error.log 文件。\n\n"
                "这将减少硬盘写入，但可能影响问题排查。\n配置信息仍会正常保存。\n\n"
                "确定要关闭日志记录吗？"
            )
            if reply == ThemedMessageBox.Yes:
                self.data_manager.update_settings(disable_logging=True)
                # 动态移除文件日志处理器
                import logging
                root_logger = logging.getLogger()
                for handler in root_logger.handlers[:]:
                    if isinstance(handler, logging.FileHandler):
                        handler.close()
                        root_logger.removeHandler(handler)
            else:
                self.disable_logging_cb.setChecked(False)
        else:
            self.data_manager.update_settings(disable_logging=False)
            # 提示需要重启才能重新启用日志
            ThemedMessageBox.warning(
                self,
                "需要重启",
                "重新启用日志需要重启程序才能生效。"
            )

    def _on_debug_log_changed(self, state):
        if self._updating: return
        checked = state == 2

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"DEBUG日志开关变更: {checked}")

        # 直接设置属性
        self.data_manager.data.settings.enable_debug_log = checked
        logger.info(f"设置后的值: {self.data_manager.data.settings.enable_debug_log}")

        # 立即保存
        self.data_manager.save(immediate=True)
        logger.info("已调用 save(immediate=True)")

        if checked:
            reply = ThemedMessageBox.question(
                self,
                "需要重启",
                "DEBUG日志已开启，需要重启程序才能生效。\n\n是否立即重启？"
            )
            if reply == ThemedMessageBox.Yes:
                self._restart_app()

    def _restart_app(self):
        """重启应用"""
        import logging
        import subprocess
        import tempfile
        import sys
        import os

        logger = logging.getLogger(__name__)
        logger.info("用户请求重启应用...")

        try:
            exe = sys.executable
            is_frozen = getattr(sys, 'frozen', False)

            if not is_frozen and 'python' in os.path.basename(exe).lower():
                if sys.argv[0].lower().endswith('.exe'):
                    exe = os.path.abspath(sys.argv[0])
                    is_frozen = True

            if is_frozen:
                if not os.path.isabs(exe):
                    exe = os.path.abspath(exe)
                cwd = os.path.dirname(exe)

                vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WScript.Sleep 1000
WshShell.Run """{exe}""", 0, False
Set fso = CreateObject("Scripting.FileSystemObject")
fso.DeleteFile WScript.ScriptFullName
'''
                vbs_file = os.path.join(tempfile.gettempdir(), 'quicklauncher_restart.vbs')
                with open(vbs_file, 'w', encoding='utf-8') as f:
                    f.write(vbs_content)

                subprocess.Popen(['wscript.exe', vbs_file], cwd=cwd, creationflags=0x08000000, shell=False)
            else:
                cwd = os.path.dirname(os.path.abspath(__file__))
                while cwd and not os.path.exists(os.path.join(cwd, 'main.py')):
                    parent = os.path.dirname(cwd)
                    if parent == cwd:
                        break
                    cwd = parent

                main_py = os.path.join(cwd, 'main.py')

                vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WScript.Sleep 1000
WshShell.Run """{exe}"" ""{main_py}""", 0, False
Set fso = CreateObject("Scripting.FileSystemObject")
fso.DeleteFile WScript.ScriptFullName
'''
                vbs_file = os.path.join(tempfile.gettempdir(), 'quicklauncher_restart.vbs')
                with open(vbs_file, 'w', encoding='utf-8') as f:
                    f.write(vbs_content)

                subprocess.Popen(['wscript.exe', vbs_file], cwd=cwd, creationflags=0x08000000, shell=False)

            from qt_compat import QApplication, QTimer
            QTimer.singleShot(100, QApplication.quit)

        except Exception as e:
            logger.error(f"重启失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _on_theme_changed(self, button):
        if self._updating: return

        if button == self.follow_system_radio:
            system_theme = self._get_system_theme()
            new_theme = system_theme
            self.data_manager.update_settings(theme=system_theme, theme_follow_system=True)
        elif button == self.dark_radio:
            new_theme = "dark"
            self.data_manager.update_settings(theme="dark", theme_follow_system=False)
        else:
            new_theme = "light"
            self.data_manager.update_settings(theme="light", theme_follow_system=False)

        # 简单淡入淡出动画
        self.setUpdatesEnabled(False)
        self.apply_theme(new_theme)
        self.setUpdatesEnabled(True)
        self.update()

        self.settings_changed.emit()

    def _get_system_theme(self):
        """检测系统主题"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "light" if value == 1 else "dark"
        except Exception as e:
            logger.debug("Failed to detect system theme: %s", e)
            return "dark"

    def _on_size_changed(self):
        if self._updating: return

        updates = {
            "icon_size": self.icon_size_spin.value(),
            "cell_size": self.cell_size_spin.value(),
            "cols": self.cols_spin.value(),
            "popup_max_rows": self.popup_max_rows_spin.value()
        }

        # Only update corner_radius if the spinbox is enabled
        if self.corner_spin.isEnabled():
            updates["corner_radius"] = self.corner_spin.value()

        self.data_manager.update_settings(**updates)

    def _on_dock_size_changed(self):
        if self._updating: return

        height_val = self.dock_height_spin.value()
        enabled = height_val > 0
        mode = height_val if height_val > 0 else 1 # Default to 1 if disabled

        self.data_manager.update_settings(
            dock_enabled=enabled,
            dock_height_mode=mode
        )

    def _on_bg_alpha_changed(self, value):
        self.bg_alpha_label.setText(f"{value}%")
        if self._updating: return

        mode = self.data_manager.get_settings().bg_mode
        with self.data_manager.batch_update():
            # 更新当前生效的透明度
            self.data_manager.update_settings(bg_alpha=value)

            # 根据当前模式保存到对应参数
            if mode == "theme":
                 self.data_manager.update_settings(theme_bg_alpha=value)
            elif mode == "image":
                 self.data_manager.update_settings(image_bg_alpha=value)
            elif mode == "acrylic":
                 self.data_manager.update_settings(acrylic_bg_alpha=value)

    def _on_dock_bg_alpha_changed(self, value):
        self.dock_bg_alpha_label.setText(f"{value}%")
        if self._updating: return
        self.data_manager.update_settings(dock_bg_alpha=value)

    def _on_icon_alpha_changed(self, value):
        self.icon_alpha_label.setText(f"{value}%")
        if self._updating: return
        self.data_manager.update_settings(icon_alpha=value/100.0)

    def _on_bg_mode_changed(self, button):
        mode = "theme"
        if button == self.bg_image_radio: 
            mode = "image"
        elif button == self.bg_acrylic_radio:
            mode = "acrylic"
        
        self.bg_image_widget.setVisible(mode == "image")
        self._update_ui_state_for_mode(mode)
        
        # 切换模式时，加载该模式对应的参数
        settings = self.data_manager.get_settings()
        if mode == "theme":
            target_alpha = getattr(settings, 'theme_bg_alpha', 90)
            target_blur = getattr(settings, 'theme_blur_radius', 0)
            target_edge = getattr(settings, 'theme_edge_opacity', 0.0)
        elif mode == "image":
            target_alpha = getattr(settings, 'image_bg_alpha', 90)
            target_blur = getattr(settings, 'image_blur_radius', 0)
            target_edge = getattr(settings, 'image_edge_opacity', 0.0)
        else: # acrylic
            target_alpha = getattr(settings, 'acrylic_bg_alpha', 90)
            target_blur = getattr(settings, 'acrylic_blur_radius', 0)
            target_edge = getattr(settings, 'acrylic_edge_opacity', 0.0)
            
        # 更新 UI (Block signals to prevent writing back immediately)
        self.bg_alpha_slider.blockSignals(True)
        self.bg_alpha_slider.setValue(target_alpha)
        self.bg_alpha_slider.blockSignals(False)
        self.bg_alpha_label.setText(f"{target_alpha}%")
        
        self.blur_radius_slider.blockSignals(True)
        self.blur_radius_slider.setValue(target_blur)
        self.blur_radius_slider.blockSignals(False)
        self.blur_radius_label.setText(str(target_blur))
        
        self.edge_opacity_slider.blockSignals(True)
        self.edge_opacity_slider.setValue(int(target_edge * 100))
        self.edge_opacity_slider.blockSignals(False)
        self.edge_opacity_label.setText(f"{int(target_edge * 100)}%")
        
        if self._updating: return
        with self.data_manager.batch_update():
            self.data_manager.update_settings(bg_mode=mode)
            # 同时更新当前的 bg_alpha / bg_blur_radius / edge_opacity 以便立即生效
            self.data_manager.update_settings(bg_alpha=target_alpha)
            self.data_manager.update_settings(bg_blur_radius=target_blur)
            self.data_manager.update_settings(edge_highlight_opacity=target_edge)
        self.settings_changed.emit()

    def _browse_bg_image(self):
        # ... logic similar to old settings ...
        # Simplified for brevity, assume similar logic
        file_path, _ = QFileDialog.getOpenFileName(self, "选择背景图片", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            self.bg_path_edit.setText(file_path)
            self.data_manager.update_settings(custom_bg_path=file_path)
            self.settings_changed.emit()
            
    def _on_bg_blur_changed(self, value):
        self.bg_blur_label.setText(str(value))
        if self._updating: return
        self.data_manager.update_settings(bg_blur_radius=value)
        self._schedule_slider_settings_changed()
        
    def _on_blur_radius_changed(self, value):
        self.blur_radius_label.setText(str(value))
        if self._updating: return

        mode = self.data_manager.get_settings().bg_mode
        with self.data_manager.batch_update():
            # 更新当前生效的模糊度
            self.data_manager.update_settings(bg_blur_radius=value)

            # 根据当前模式保存到对应参数
            if mode == "theme":
                self.data_manager.update_settings(theme_blur_radius=value)
            elif mode == "image":
                 self.data_manager.update_settings(image_blur_radius=value)
            elif mode == "acrylic":
                 self.data_manager.update_settings(acrylic_blur_radius=value)

        self._schedule_slider_settings_changed()
        
    def _on_edge_opacity_changed(self, value):
        self.edge_opacity_label.setText(f"{value}%")
        if self._updating: return

        mode = self.data_manager.get_settings().bg_mode
        with self.data_manager.batch_update():
            # Update current effective value
            self.data_manager.update_settings(edge_highlight_opacity=value/100.0)

            # Save to specific mode
            if mode == "theme":
                self.data_manager.update_settings(theme_edge_opacity=value/100.0)
            elif mode == "image":
                 self.data_manager.update_settings(image_edge_opacity=value/100.0)
            elif mode == "acrylic":
                 self.data_manager.update_settings(acrylic_edge_opacity=value/100.0)

    def _on_popup_pos_changed(self, button):
        if self._updating: return
        pos = "mouse_center"
        if button == self.pos_mouse_tl: pos = "mouse_top_left"
        self.data_manager.update_settings(popup_align_mode=pos)

    def _on_delay_changed(self, value):
        self.delay_label.setText(f"{value}ms")
        if self._updating: return
        self.data_manager.update_settings(hover_leave_delay=value)

    def _on_double_click_interval_changed(self, value):
        self.double_click_label.setText(f"{value}ms")
        if self._updating: return
        self.data_manager.update_settings(double_click_interval=value)

    def _on_auto_close_changed(self, button):
        if self._updating: return
        auto_close = (button == self.auto_close_yes)
        self.delay_widget.setVisible(auto_close)
        self.data_manager.update_settings(popup_auto_close=auto_close)

    # Removed _on_mc_* handlers as they are deleted

    # Special Apps Logic (Simplified copy from old settings)
    def _add_special_app(self):
        item = QListWidgetItem("new_app")
        item.setFlags(item.flags() | QtCompat.ItemIsDragEnabled | QtCompat.ItemIsEditable)
        self.special_apps_list.addItem(item)
        self.special_apps_list.setCurrentItem(item)
        self.special_apps_list.editItem(item)

    def _remove_special_app(self):
        row = self.special_apps_list.currentRow()
        if row >= 0:
            self.special_apps_list.takeItem(row)

    def _edit_special_app_item(self, item):
        self.special_apps_list.editItem(item)

    def _reset_special_apps(self):
        self.special_apps_list.clear()
        for app in DEFAULT_SPECIAL_APPS:
            item = QListWidgetItem(app)
            item.setFlags(item.flags() | QtCompat.ItemIsDragEnabled | QtCompat.ItemIsEditable)
            self.special_apps_list.addItem(item)
        self._apply_special_apps()

    def _apply_special_apps(self):
        if self._updating: return
        apps = []
        for i in range(self.special_apps_list.count()):
            item = self.special_apps_list.item(i)
            text = item.text().strip().lower()
            if text:
                apps.append(text)
        self.data_manager.update_settings(special_apps=apps)
        self.special_apps_changed.emit()
            
    def _validate_hotkey(self, hotkey_str: str) -> tuple:
        """验证快捷键是否有效

        Returns:
            (is_valid: bool, error_msg: str)
        """
        # 允许空快捷键（不设置）
        if not hotkey_str or not hotkey_str.strip():
            return True, ""

        parts = [p.strip() for p in hotkey_str.split("+")]
        modifiers = []
        main_key = None

        for part in parts:
            part_lower = part.lower().replace("<", "").replace(">", "")
            if part_lower in ("ctrl", "alt", "shift", "cmd", "win"):
                modifiers.append(part_lower)
            else:
                main_key = part

        # 不允许使用 Alt 键
        if "alt" in modifiers:
            return False, "不允许使用 Alt 键\n请使用 Ctrl、Shift 或 Win"

        # 必须有主键
        if not main_key:
            return False, "必须包含一个主键（字母、数字或功能键）"

        # 必须有修饰键
        if not modifiers:
            return False, "必须包含至少一个修饰键（Ctrl、Shift、Win）"

        # 检查系统快捷键冲突
        try:
            from core.hotkey_conflict_checker import check_conflict
            is_conflict, conflict_desc = check_conflict(hotkey_str)
            if is_conflict:
                return False, f"快捷键冲突：{conflict_desc}"
        except Exception:
            pass

        return True, ""

    # Import/Export






    
