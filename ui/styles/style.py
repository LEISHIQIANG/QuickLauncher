"""
统一样式模块
提供统一的 UI 样式、颜色常量和组件

此模块整合了原本分散在 folder_panel.py 和 icon_grid.py 中的 PopupMenu 类，
以及统一的颜色方案和样式表生成器。
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from qt_compat import (
    QWidget, QVBoxLayout, QPushButton, QApplication,
    QPainter, QColor, QPen, QRectF, QPainterPath,
    QtCompat, Qt
)


class Colors:
    """
    设计规范颜色常量
    """
    
    # 系统蓝色
    BLUE = "#007AFF"
    BLUE_LIGHT = "#0A84FF"
    
    # 系统绿色
    # 系统绿色 (改为青色)
    GREEN = "#30B0C7"
    GREEN_LIGHT = "#40C8E0"
    
    # 系统红色
    RED = "#FF3B30"
    RED_LIGHT = "#FF453A"
    
    # 系统灰色
    GRAY = "#8E8E93"
    GRAY2 = "#636366"
    GRAY3 = "#48484A"
    GRAY4 = "#3A3A3C"
    GRAY5 = "#2C2C2E"
    GRAY6 = "#1C1C1E"
    
    # 深色主题背景
    DARK_BG_PRIMARY = "rgba(28, 28, 30, 0.85)"
    DARK_BG_SECONDARY = "rgba(44, 44, 46, 0.85)"
    DARK_BG_TERTIARY = "rgba(58, 58, 60, 0.85)"
    DARK_TEXT_PRIMARY = "#FFFFFF"
    DARK_TEXT_SECONDARY = "#8E8E93"
    DARK_BORDER = "rgba(255, 255, 255, 0.1)"
    DARK_SEPARATOR = "rgba(255, 255, 255, 0.16)"
    
    # 浅色主题背景
    LIGHT_BG_PRIMARY = "rgba(242, 242, 247, 0.8)"
    LIGHT_BG_SECONDARY = "rgba(255, 255, 255, 0.8)"
    LIGHT_BG_TERTIARY = "rgba(229, 229, 234, 0.8)"
    LIGHT_TEXT_PRIMARY = "#1C1C1E"
    LIGHT_TEXT_SECONDARY = "#8E8E93"
    LIGHT_BORDER = "rgba(0, 0, 0, 0.08)"
    LIGHT_SEPARATOR = "rgba(60, 60, 67, 0.18)"
    
    # 通用圆角
    RADIUS_SMALL = 8
    RADIUS_MEDIUM = 10
    RADIUS_LARGE = 12
    RADIUS_XLARGE = 16
    
    @classmethod
    def get_bg_primary(cls, theme: str) -> str:
        return cls.DARK_BG_PRIMARY if theme == "dark" else cls.LIGHT_BG_PRIMARY
    
    @classmethod
    def get_bg_secondary(cls, theme: str) -> str:
        return cls.DARK_BG_SECONDARY if theme == "dark" else cls.LIGHT_BG_SECONDARY
    
    @classmethod
    def get_text_primary(cls, theme: str) -> str:
        return cls.DARK_TEXT_PRIMARY if theme == "dark" else cls.LIGHT_TEXT_PRIMARY
    
    @classmethod
    def get_text_secondary(cls, theme: str) -> str:
        return cls.DARK_TEXT_SECONDARY if theme == "dark" else cls.LIGHT_TEXT_SECONDARY
    
    @classmethod
    def get_border(cls, theme: str) -> str:
        return cls.DARK_BORDER if theme == "dark" else cls.LIGHT_BORDER
    
    @classmethod
    def get_accent(cls, theme: str) -> str:
        return cls.BLUE_LIGHT if theme == "dark" else cls.BLUE


class PopupMenu(QWidget):
    """
    自定义风格右键弹出菜单

    特性:
    - 圆角边框（完美圆角，无直角残留）
    - 磨砂玻璃模糊背景（与主配置窗口一致）
    - 悬停高亮效果
    - 支持深色/浅色主题
    - 自动定位到屏幕内
    - 内联展开式子菜单
    """

    def __init__(self, theme: str = "dark", radius: int = 12, parent=None):
        super().__init__(parent, QtCompat.Popup | QtCompat.FramelessWindowHint | QtCompat.NoDropShadowWindowHint)
        self._theme = theme
        self._radius = radius
        self._blur_applied = False

        self.setAutoFillBackground(False)
        self.setAttribute(QtCompat.WA_TranslucentBackground, True)
        self.setAttribute(QtCompat.WA_NoSystemBackground, True)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(3)

        # 子菜单项容器列表，用于展开/收起
        self._sub_items_widgets = []
        self._submenu_expanded = False

        # 按钮样式
        self._btn_style_dark = (
            "QPushButton{background:transparent;border:none;padding:7px 16px;margin:0px;"
            "border-radius:8px;color:rgba(255,255,255,0.85);font-size:11px;text-align:left;"
            "font-family:'Segoe UI','Microsoft YaHei UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(255,255,255,0.10);color:rgba(255,255,255,0.95);}"
            "QPushButton:pressed{background:rgba(255,255,255,0.16);}"
            "QPushButton:disabled{color:rgba(255,255,255,110);}"
        )
        self._btn_style_light = (
            "QPushButton{background:transparent;border:none;padding:7px 16px;margin:0px;"
            "border-radius:8px;color:rgba(28,28,30,0.85);font-size:11px;text-align:left;"
            "font-family:'Segoe UI','Microsoft YaHei UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(0,0,0,0.06);color:rgba(28,28,30,0.95);}"
            "QPushButton:pressed{background:rgba(0,0,0,0.10);}"
            "QPushButton:disabled{color:rgba(60,60,67,120);}"
        )
        # 子菜单项缩进样式
        self._sub_btn_style_dark = (
            "QPushButton{background:transparent;border:none;padding:7px 16px 7px 28px;margin:0px;"
            "border-radius:8px;color:rgba(255,255,255,0.75);font-size:11px;text-align:left;"
            "font-family:'Segoe UI','Microsoft YaHei UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(255,255,255,0.10);color:rgba(255,255,255,0.95);}"
            "QPushButton:pressed{background:rgba(255,255,255,0.16);}"
        )
        self._sub_btn_style_light = (
            "QPushButton{background:transparent;border:none;padding:7px 16px 7px 28px;margin:0px;"
            "border-radius:8px;color:rgba(28,28,30,0.70);font-size:11px;text-align:left;"
            "font-family:'Segoe UI','Microsoft YaHei UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(0,0,0,0.06);color:rgba(28,28,30,0.95);}"
            "QPushButton:pressed{background:rgba(0,0,0,0.10);}"
        )
        self._sep_style_dark = "background-color: rgba(255, 255, 255, 16);"
        self._sep_style_light = "background-color: rgba(60, 60, 67, 18);"

    def add_action(self, text: str, callback, enabled: bool = True):
        """添加菜单项"""
        btn = QPushButton(text, self)
        btn.setEnabled(bool(enabled))
        btn.setCursor(QtCompat.PointingHandCursor)
        try:
            policy = getattr(Qt, 'NoFocus', None)
            if policy is None:
                policy = getattr(Qt.FocusPolicy, 'NoFocus', None)
            if policy is not None:
                btn.setFocusPolicy(policy)
        except Exception:
            pass
        btn.setStyleSheet(self._btn_style_dark if self._theme == "dark" else self._btn_style_light)
        btn.clicked.connect(lambda: self._trigger(callback))
        # 悬停到普通菜单项时收起子菜单
        original_enter = btn.enterEvent
        def _on_enter(e):
            self._collapse_submenu()
            if original_enter and callable(original_enter):
                original_enter(e)
        btn.enterEvent = _on_enter
        self._layout.addWidget(btn)
        return btn

    def add_submenu(self, text: str, items: list):
        """添加内联展开式子菜单

        Args:
            text: 菜单项文字（如 "移动到"）
            items: [(label, callback), ...] 子菜单项列表
        """
        # 触发按钮
        btn = QPushButton(text + "  ▸", self)
        btn.setCursor(QtCompat.PointingHandCursor)
        try:
            policy = getattr(Qt, 'NoFocus', None)
            if policy is None:
                policy = getattr(Qt.FocusPolicy, 'NoFocus', None)
            if policy is not None:
                btn.setFocusPolicy(policy)
        except Exception:
            pass
        btn.setStyleSheet(self._btn_style_dark if self._theme == "dark" else self._btn_style_light)
        self._layout.addWidget(btn)

        # 创建子菜单项（初始隐藏）
        sub_widgets = []
        sub_style = self._sub_btn_style_dark if self._theme == "dark" else self._sub_btn_style_light
        for label, callback in items:
            sub_btn = QPushButton(label, self)
            sub_btn.setCursor(QtCompat.PointingHandCursor)
            sub_btn.setStyleSheet(sub_style)
            sub_btn.clicked.connect(lambda checked=False, cb=callback: self._trigger(cb))
            sub_btn.hide()
            self._layout.addWidget(sub_btn)
            sub_widgets.append(sub_btn)

        self._sub_items_widgets = sub_widgets

        # 悬停展开
        original_enter = btn.enterEvent
        def _on_enter(e):
            self._expand_submenu()
            if original_enter and callable(original_enter):
                original_enter(e)
        btn.enterEvent = _on_enter

        return btn

    def _expand_submenu(self):
        """展开子菜单项"""
        if self._submenu_expanded:
            return
        self._submenu_expanded = True
        for w in self._sub_items_widgets:
            w.show()
        self.adjustSize()

    def _collapse_submenu(self):
        """收起子菜单项"""
        if not self._submenu_expanded:
            return
        self._submenu_expanded = False
        for w in self._sub_items_widgets:
            w.hide()
        self.adjustSize()

    def add_separator(self):
        """添加分隔线"""
        sep = QWidget(self)
        sep.setFixedHeight(1)
        sep.setStyleSheet(self._sep_style_dark if self._theme == "dark" else self._sep_style_light)
        self._layout.addWidget(sep)
        return sep

    def _trigger(self, callback):
        """触发回调并关闭菜单"""
        try:
            self.hide()
        finally:
            try:
                callback()
            except Exception as e:
                logging.getLogger(__name__).error(f"菜单动作执行失败: {e}")

    def popup(self, global_pos):
        """在指定位置显示菜单"""
        self.adjustSize()
        self._move_into_screen(global_pos)
        self.show()
        self.raise_()
        try:
            self.activateWindow()
            self.setFocus()
        except Exception:
            pass
        # 窗口显示后应用模糊效果和圆角裁剪
        self._apply_blur_effect()

    def _move_into_screen(self, global_pos):
        """确保菜单在屏幕内"""
        try:
            screen = QApplication.primaryScreen()
            geo = screen.availableGeometry() if screen else None
        except Exception:
            geo = None

        x = int(global_pos.x())
        y = int(global_pos.y())

        if geo is not None:
            if x + self.width() > geo.right():
                x = max(int(geo.left()), int(geo.right() - self.width()))
            if y + self.height() > geo.bottom():
                y = max(int(geo.top()), int(geo.bottom() - self.height()))

        self.move(x, y)

    def focusOutEvent(self, event):
        """失去焦点时隐藏"""
        try:
            self.hide()
        except Exception:
            pass
        return super().focusOutEvent(event)

    def keyPressEvent(self, event):
        """按 ESC 隐藏"""
        try:
            key = event.key()
            if key == QtCompat.Key_Escape:
                self.hide()
                return
        except Exception:
            pass
        return super().keyPressEvent(event)

    def _apply_blur_effect(self):
        """应用磨砂玻璃模糊效果 + 圆角裁剪（与主配置窗口风格一致）"""
        try:
            from ui.utils.window_effect import get_window_effect, is_win11, is_win10

            hwnd = int(self.winId())
            if not hwnd:
                return

            effect = get_window_effect()
            w = self.width()
            h = self.height()
            r = self._radius

            if is_win11():
                # Win11: DWM 原生圆角 + Acrylic 模糊
                effect.set_round_corners(hwnd, enable=True)
                # DWM DWMWCP_ROUND 圆角约 8px，同步 paintEvent 圆角半径以完美重合
                self._radius = 8
                if self._theme == "dark":
                    gradient_color = f"c81c1c1e"  # alpha=200, 深灰
                else:
                    gradient_color = f"c8f2f2f7"  # alpha=200, 浅灰
                effect.set_acrylic(hwnd, gradient_color, enable=True, blur=True)
            else:
                # Win10: 使用窗口区域裁剪 + DWM Blur Behind
                if w > 0 and h > 0:
                    effect.set_window_region(hwnd, w, h, r)
                    effect.set_dwm_blur_behind(hwnd, w, h, r, enable=True)
                # 应用半透明着色层
                if self._theme == "dark":
                    gradient_color = f"c81c1c1e"
                else:
                    gradient_color = f"c8f2f2f7"
                effect.set_acrylic(hwnd, gradient_color, enable=True, blur=False)

            self._blur_applied = True
        except Exception as e:
            logging.getLogger(__name__).debug(f"菜单模糊效果失败: {e}")

    def paintEvent(self, event):
        """绘制圆角背景（模糊层之上的半透明着色）"""
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.TextAntialiasing)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform)

        try:
            cm_source = QPainter.CompositionMode.CompositionMode_Source
            cm_over = QPainter.CompositionMode.CompositionMode_SourceOver
        except Exception:
            cm_source = getattr(QPainter, "CompositionMode_Source", None)
            cm_over = getattr(QPainter, "CompositionMode_SourceOver", None)

        if cm_source is not None:
            painter.setCompositionMode(cm_source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        if cm_over is not None:
            painter.setCompositionMode(cm_over)

        # 主题颜色：当模糊效果生效时降低不透明度以显示模糊
        if self._blur_applied:
            if self._theme == "dark":
                bg = QColor(30, 30, 30, 120)
                border = QColor(255, 255, 255, 38)
            else:
                bg = QColor(255, 255, 255, 120)
                border = QColor(0, 0, 0, 20)
        else:
            if self._theme == "dark":
                bg = QColor(30, 30, 30, 220)
                border = QColor(255, 255, 255, int(0.1 * 255))
            else:
                bg = QColor(255, 255, 255, 220)
                border = QColor(0, 0, 0, int(0.08 * 255))

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        painter.fillPath(path, bg)
        pen = QPen(border, 1)
        pen.setJoinStyle(QtCompat.RoundJoin)
        pen.setCapStyle(QtCompat.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()

    def resizeEvent(self, event):
        """窗口大小变化时重新应用模糊和圆角裁剪"""
        super().resizeEvent(event)
        if self._blur_applied and self.isVisible():
            self._apply_blur_effect()


class StyleSheet:
    """
    简约风格样式表生成器
    """
    
    @staticmethod
    def get_button_style(theme: str) -> str:
        """获取按钮样式 - 苹果奶白风格"""
        if theme == "dark":
            return """
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.12);
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 10px;
                    padding: 3px 12px;
                    color: rgba(255, 255, 255, 0.85);
                    font-size: 11px;
                    font-weight: 400;
                    min-height: 22px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.20);
                    border: 1px solid rgba(255, 255, 255, 0.25);
                }
                QPushButton:pressed {
                    background-color: rgba(255, 255, 255, 0.08);
                }
                QPushButton:default {
                    background-color: #0A84FF;
                    border: 1px solid #0A84FF;
                    color: white;
                }
                QPushButton:default:hover {
                    background-color: #0077EA;
                }
                QPushButton:disabled {
                    background-color: rgba(255, 255, 255, 0.06);
                    color: rgba(235, 235, 245, 0.3);
                }
            """
        else:
            return """
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.80);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 10px;
                    padding: 3px 12px;
                    color: rgba(28, 28, 30, 0.75);
                    font-size: 11px;
                    font-weight: 400;
                    min-height: 22px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.95);
                    border: 1px solid rgba(0, 0, 0, 0.10);
                }
                QPushButton:pressed {
                    background-color: rgba(240, 240, 245, 0.90);
                }
                QPushButton:default {
                    background-color: #007AFF;
                    border: 1px solid #007AFF;
                    color: white;
                }
                QPushButton:default:hover {
                    background-color: #0A84FF;
                }
                QPushButton:disabled {
                    background-color: rgba(0, 0, 0, 0.04);
                    color: rgba(60, 60, 67, 0.3);
                }
            """

    @staticmethod
    def get_input_style(theme: str) -> str:
        """获取输入框样式 - 紧凑版"""
        if theme == "dark":
            return """
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background-color: rgba(190, 190, 197, 0.22);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    padding: 4px 8px;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 400;
                    selection-background-color: #0A84FF;
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid #0A84FF;
                    background-color: rgba(190, 190, 197, 0.28);
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
                    background-color: rgba(190, 190, 197, 0.12);
                    color: rgba(235, 235, 245, 0.3);
                }
            """
        else:
            return """
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background-color: #ffffff;
                    border: 1px solid rgba(0, 0, 0, 0.12);
                    border-radius: 6px;
                    padding: 4px 8px;
                    color: #1c1c1e;
                    font-size: 11px;
                    font-weight: 400;
                    selection-background-color: rgba(0, 122, 255, 0.3);
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid #007AFF;
                    background-color: #ffffff;
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
                    background-color: #f5f5f7;
                    color: rgba(60, 60, 67, 0.3);
                }
            """

    @staticmethod
    def get_groupbox_style(theme: str) -> str:
        """获取分组框样式 - 紧凑风格"""
        if theme == "dark":
            return """
                QGroupBox {
                    font-weight: 400;
                    border: none;
                    margin-top: 2px;
                    padding-top: 14px;
                    font-size: 11px;
                    color: white;
                }
                QGroupBox::title {
                    subcontrol-origin: padding;
                    subcontrol-position: top left;
                    left: 0px;
                    padding: 0px 0px 3px 0px;
                    background-color: transparent;
                    color: #ffffff;
                }
            """
        else:
            return """
                QGroupBox {
                    font-weight: 400;
                    border: none;
                    margin-top: 2px;
                    padding-top: 14px;
                    font-size: 11px;
                    color: #1c1c1e;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 0px;
                    top: -6px;
                    padding: 0px 0px 3px 0px;
                    background-color: transparent;
                    color: #1c1c1e;
                }
            """
    
    @staticmethod
    def get_scrollbar_style(theme: str) -> str:
        """获取滚动条样式"""
        if theme == "dark":
            handle_color = "rgba(255, 255, 255, 80)"
            handle_hover = "rgba(255, 255, 255, 120)"
        else:
            handle_color = "rgba(0, 0, 0, 60)"
            handle_hover = "rgba(0, 0, 0, 100)"
            
        return f"""
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {handle_color};
                min-height: 30px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {handle_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QScrollBar:horizontal {{
                border: none;
                background: transparent;
                height: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {handle_color};
                min-width: 30px;
                border-radius: 3px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {handle_hover};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                background: none;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """
    
    @staticmethod
    def get_combobox_style(theme: str) -> str:
        """获取下拉框样式"""
        if theme == "dark":
            return """
                QComboBox {
                    background-color: rgba(190, 190, 197, 0.22);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 5px 8px;
                    padding-right: 25px;
                    color: rgba(255, 255, 255, 0.9);
                    min-height: 24px;
                    font-size: 12px;
                    margin: 0px;
                }
                QComboBox:hover {
                    border: 1px solid #0A84FF;
                    background-color: rgba(190, 190, 197, 0.30);
                }
                QComboBox:focus {
                    border: 1px solid #0A84FF;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                    subcontrol-position: center right;
                    subcontrol-origin: padding;
                    right: 5px;
                }
                QComboBox::down-arrow {
                    image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2.5 3.5L5 6L7.5 3.5' fill='none' stroke='white' stroke-width='1.2' stroke-linecap='round' stroke-linejoin='round'/></svg>");
                    width: 10px;
                    height: 10px;
                }
                QComboBox QAbstractItemView {
                    background-color: rgba(40, 40, 45, 200);
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 8px;
                    padding: 4px;
                    selection-background-color: rgba(10, 132, 255, 0.8);
                    selection-color: #ffffff;
                    color: #ffffff;
                    outline: none;
                }
                QComboBox QAbstractItemView::item {
                    padding: 4px 8px;
                    border-radius: 6px;
                    margin: 2px;
                }
                QComboBox QAbstractItemView::item:hover {
                    background-color: rgba(10, 132, 255, 0.4);
                }
                QComboBox QAbstractItemView::item:selected {
                    background-color: rgba(10, 132, 255, 0.8);
                }
            """
        else:
            return """
                QComboBox {
                    background-color: rgba(255, 255, 255, 120);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 6px;
                    padding: 5px 8px;
                    padding-right: 25px;
                    color: #1c1c1e;
                    min-height: 24px;
                    font-size: 12px;
                    margin: 0px;
                }
                QComboBox:hover {
                    border: 1px solid #007AFF;
                    background-color: rgba(255, 255, 255, 180);
                }
                QComboBox:focus {
                    border: 1px solid #007AFF;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                    subcontrol-position: center right;
                    subcontrol-origin: padding;
                    right: 5px;
                }
                QComboBox::down-arrow {
                    image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2.5 3.5L5 6L7.5 3.5' fill='none' stroke='black' stroke-width='1.2' stroke-linecap='round' stroke-linejoin='round'/></svg>");
                    width: 10px;
                    height: 10px;
                }
                QComboBox QAbstractItemView {
                    background-color: rgba(255, 255, 255, 210);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 8px;
                    padding: 4px;
                    selection-background-color: rgba(0, 122, 255, 0.8);
                    selection-color: #ffffff;
                    color: #1c1c1e;
                    outline: none;
                }
                QComboBox QAbstractItemView::item {
                    padding: 4px 8px;
                    border-radius: 6px;
                    margin: 2px;
                }
                QComboBox QAbstractItemView::item:hover {
                    background-color: rgba(0, 122, 255, 0.1);
                }
                QComboBox QAbstractItemView::item:selected {
                    background-color: rgba(0, 122, 255, 0.8);
                    color: #ffffff;
                }
            """
    
    @staticmethod
    def get_groupbox_style(theme: str) -> str:
        """获取分组框样式 - 极简风格"""
        if theme == "dark":
            return """
                QGroupBox {
                    font-weight: 400;
                    border: none;
                    margin-top: 10px;
                    padding-top: 24px;
                    font-size: 13px;
                    color: white;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 0px;
                    padding: 0px 0px 8px 0px;
                    background-color: transparent;
                    color: #ffffff;
                }
            """
        else:
            return """
                QGroupBox {
                    font-weight: 400;
                    border: none;
                    margin-top: 6px;
                    padding-top: 20px;
                    font-size: 13px;
                    color: #1c1c1e;
                }
                QGroupBox::title {
                    subcontrol-origin: padding;
                    subcontrol-position: top left;
                    left: 0px;
                    padding: 0px 0px 4px 0px;
                    background-color: transparent;
                    color: #1c1c1e;
                }
            """
    
    @staticmethod
    def get_slider_style(theme: str) -> str:
        """获取滑块样式"""
        accent = "#0A84FF" if theme == "dark" else "#007AFF"
        track_bg = "#3a3a3c" if theme == "dark" else "#D1D1D6"
        
        # 处理手柄边框，使其更柔和以避免毛刺感
        if theme == "dark":
            handle_border = "1px solid rgba(0, 0, 0, 0.2)"
            handle_bg = "#ffffff"
        else:
            handle_border = "1px solid rgba(0, 0, 0, 0.05)"
            handle_bg = "#ffffff"
        
        return f"""
            QSlider::groove:horizontal {{
                height: 4px;
                background: transparent;
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent};
                border-radius: 2px;
            }}
            QSlider::add-page:horizontal {{
                background: {track_bg};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {handle_bg};
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
                border: {handle_border};
            }}
            QSlider::handle:horizontal:hover {{
                background: #f8f8f8;
                border: 1px solid rgba(0, 0, 0, 0.1);
            }}
            QSlider::handle:horizontal:pressed {{
                background: #f0f0f0;
            }}
        """


class Glassmorphism:
    """
    磨砂玻璃拟态样式生成器
    提供 Glassmorphism + Neumorphism 混合效果
    """
    
    @staticmethod
    def get_glassmorphism_container_style(theme: str) -> str:
        """获取磨砂玻璃容器背景样式（用于主窗口背景）"""
        if theme == "dark":
            return """
                background-color: rgba(28, 28, 30, 160);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            """
        else:
            return """
                background-color: rgba(242, 242, 247, 120);
                border: 1px solid rgba(0, 0, 0, 0.05);
                border-radius: 12px;
            """
    
    @staticmethod
    def get_neumorphism_button_style(theme: str) -> str:
        """获取拟态按钮样式（带柔和阴影）"""
        if theme == "dark":
            return """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(85, 85, 90, 0.9),
                        stop:0.5 rgba(75, 75, 80, 0.9),
                        stop:1 rgba(65, 65, 70, 0.9));
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 10px;
                    padding: 4px 16px;
                    color: rgba(255, 255, 255, 0.95);
                    font-size: 12px;
                    font-weight: 400;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(95, 95, 100, 0.95),
                        stop:0.5 rgba(85, 85, 90, 0.95),
                        stop:1 rgba(75, 75, 80, 0.95));
                    border: 1px solid rgba(255, 255, 255, 0.25);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(55, 55, 60, 0.9),
                        stop:1 rgba(65, 65, 70, 0.9));
                    border: 1px solid rgba(255, 255, 255, 0.1);
                }
                QPushButton:default {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(10, 132, 255, 0.8),
                        stop:1 rgba(0, 100, 220, 0.8));
                    border: 1px solid rgba(255, 255, 255, 0.15);
                }
                QPushButton:disabled {
                    background: rgba(44, 44, 46, 0.4);
                    color: rgba(255, 255, 255, 0.3);
                }
            """
        else:
            return """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(255, 255, 255, 0.8),
                        stop:0.5 rgba(250, 250, 252, 0.8),
                        stop:1 rgba(240, 240, 245, 0.8));
                    border: 1px solid rgba(0, 0, 0, 0.06);
                    border-radius: 10px;
                    padding: 4px 16px;
                    color: rgba(28, 28, 30, 0.9);
                    font-size: 12px;
                    font-weight: 400;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(255, 255, 255, 0.9),
                        stop:1 rgba(245, 245, 250, 0.9));
                    border: 1px solid rgba(0, 0, 0, 0.1);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(235, 235, 240, 0.9),
                        stop:1 rgba(245, 245, 250, 0.9));
                }
                QPushButton:default {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(0, 122, 255, 0.8),
                        stop:1 rgba(0, 100, 220, 0.8));
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    color: #ffffff;
                }
                QPushButton:disabled {
                    background: rgba(242, 242, 247, 0.4);
                    color: rgba(60, 60, 67, 0.3);
                }
            """
    
    @staticmethod
    def get_flat_action_button_style(theme: str) -> str:
        """获取扁平操作按钮样式（与主配置窗口底部四按钮一致）"""
        if theme == "dark":
            btn_bg = "rgba(255,255,255,0.18)"
            btn_border = "rgba(255,255,255,0.22)"
            btn_hover = "rgba(255,255,255,0.28)"
            text_color = "rgba(255,255,255,0.85)"
        else:
            btn_bg = "rgba(255,255,255,0.75)"
            btn_border = "rgba(255,255,255,0.35)"
            btn_hover = "rgba(255,255,255,0.95)"
            text_color = "#1D1D1F"

        return f"""
            QPushButton {{
                font-size: 11px;
                padding: 4px 13px;
                background: {btn_bg};
                border: 1px solid {btn_border};
                border-radius: 10px;
                color: {text_color};
            }}
            QPushButton:hover {{ background-color: {btn_hover}; }}
            QPushButton:pressed {{ background-color: {btn_bg}; opacity: 0.8; }}
            QPushButton:disabled {{ background-color: rgba(255,255,255,0.3); color: #C7C7CC; }}
        """

    @staticmethod
    def get_neumorphism_input_style(theme: str) -> str:
        """获取拟态输入框样式"""
        if theme == "dark":
            return """
                /* Text Inputs */
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background: rgba(38, 38, 42, 0.7);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 3px 8px;
                    min-height: 24px;
                    font-size: 12px;
                    font-weight: 400;
                    margin: 0px;
                    color: rgba(255, 255, 255, 0.9);
                    selection-background-color: rgba(10, 132, 255, 0.5);
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid rgba(10, 132, 255, 0.8);
                    background: rgba(42, 42, 46, 0.85);
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
                    background: rgba(38, 38, 42, 0.3);
                    color: rgba(255, 255, 255, 0.3);
                }

                /* SpinBox (Container) */
                QSpinBox {
                    background: rgba(38, 38, 42, 0.7);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 3px 8px;
                    min-height: 24px;
                    font-size: 12px;
                    margin: 0px;
                    color: rgba(255, 255, 255, 0.9);
                    selection-background-color: rgba(10, 132, 255, 0.5);
                }
                QSpinBox:focus, QSpinBox:hover {
                    border: 1px solid rgba(10, 132, 255, 0.8);
                    background: rgba(42, 42, 46, 0.85);
                }
                QSpinBox:disabled {
                    background: rgba(38, 38, 42, 0.3);
                    color: rgba(255, 255, 255, 0.3);
                }

                /* SpinBox Inner Edit - Reset to transparent */
                QSpinBox QLineEdit {
                    background: transparent;
                    border: none;
                    margin: 0;
                    padding: 0;
                    min-height: 0;
                }
                QSpinBox QLineEdit:focus {
                    background: transparent;
                    border: none;
                }
            """
        else:
            return """
                /* Text Inputs */
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background: rgba(255, 255, 255, 0.7);
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 6px;
                    padding: 3px 8px;
                    min-height: 24px;
                    font-size: 12px;
                    font-weight: 400;
                    margin: 0px;
                    color: rgba(28, 28, 30, 0.9);
                    selection-background-color: rgba(10, 132, 255, 0.3);
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid rgba(0, 122, 255, 0.5);
                    background: rgba(255, 255, 255, 0.85);
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
                    background: rgba(242, 242, 247, 0.4);
                    color: rgba(60, 60, 67, 0.3);
                }

                /* SpinBox (Container) */
                QSpinBox {
                    background: rgba(255, 255, 255, 0.7);
                    border: 1px solid rgba(0, 0, 0, 0.06);
                    border-radius: 6px;
                    padding: 3px 8px;
                    min-height: 24px;
                    font-size: 12px;
                    margin: 0px;
                    color: rgba(28, 28, 30, 0.9);
                    selection-background-color: rgba(0, 122, 255, 0.2);
                }
                QSpinBox:focus, QSpinBox:hover {
                    border: 1px solid rgba(0, 122, 255, 0.5);
                    background: rgba(255, 255, 255, 0.85);
                }
                QSpinBox:disabled {
                    background: rgba(242, 242, 247, 0.4);
                    color: rgba(60, 60, 67, 0.3);
                }

                /* SpinBox Inner Edit - Reset to transparent */
                QSpinBox QLineEdit {
                    background: transparent;
                    border: none;
                    margin: 0;
                    padding: 0;
                    min-height: 0;
                }
                QSpinBox QLineEdit:focus {
                    background: transparent;
                    border: none;
                }
            """
    
    @staticmethod
    def get_neumorphism_groupbox_style(theme: str) -> str:
        """获取拟态分组框样式（内嵌效果）"""
        if theme == "dark":
            return """
                QGroupBox {
                    font-weight: 400;
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    margin-top: 18px;
                    padding-top: 10px;
                    font-size: 12px;
                    color: rgba(255, 255, 255, 0.9);
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 14px;
                    padding: 2px 10px;
                    background: transparent;
                    color: rgba(255, 255, 255, 0.5);
                    font-size: 11px;
                }
            """
        else:
            return """
                QGroupBox {
                    font-weight: 400;
                    background: rgba(0, 0, 0, 0.03);
                    border: 1px solid rgba(0, 0, 0, 0.06);
                    border-radius: 12px;
                    margin-top: 18px;
                    padding-top: 10px;
                    font-size: 12px;
                    color: rgba(28, 28, 30, 0.9);
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 14px;
                    padding: 2px 10px;
                    background: transparent;
                    color: rgba(0, 0, 0, 0.5);
                    font-size: 11px;
                }
            """
    
    @staticmethod
    def get_neumorphism_list_style(theme: str) -> str:
        """获取拟态列表样式"""
        if theme == "dark":
            return """
                QListWidget {
                    background: rgba(30, 30, 34, 0.5);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    outline: none;
                    padding: 4px;
                }
                QListWidget::item {
                    padding: 10px 12px;
                    border-radius: 8px;
                    margin: 2px 4px;
                    color: rgba(255, 255, 255, 0.85);
                }
                QListWidget::item:selected {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(10, 132, 255, 0.7),
                        stop:1 rgba(0, 100, 220, 0.7));
                    color: #ffffff;
                }
                QListWidget::item:hover:!selected {
                    background: rgba(255, 255, 255, 0.06);
                }
            """
        else:
            return """
                QListWidget {
                    background: rgba(240, 240, 245, 0.4);
                    border: 1px solid rgba(0, 0, 0, 0.05);
                    border-radius: 12px;
                    outline: none;
                    padding: 4px;
                }
                QListWidget::item {
                    padding: 10px 12px;
                    border-radius: 8px;
                    margin: 2px 4px;
                    color: rgba(28, 28, 30, 0.85);
                }
                QListWidget::item:selected {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(0, 122, 255, 0.7),
                        stop:1 rgba(0, 100, 220, 0.7));
                    color: #ffffff;
                }
                QListWidget::item:hover:!selected {
                    background: rgba(0, 0, 0, 0.03);
                }
            """
    
    @staticmethod
    def get_full_glassmorphism_stylesheet(theme: str) -> str:
        """获取完整的磨砂玻璃拟态样式表"""
        glass = Glassmorphism
        scrollbar = StyleSheet.get_scrollbar_style(theme)
        slider = StyleSheet.get_slider_style(theme)
        combobox = StyleSheet.get_combobox_style(theme)
        
        if theme == "dark":
            base = """
                QWidget {
                    background: transparent;
                    color: rgba(255, 255, 255, 0.9);
                    font-size: 13px;
                    font-weight: 400;
                }
                QLabel {
                    background: transparent;
                    color: rgba(255, 255, 255, 0.9);
                    font-size: 13px;
                    font-weight: 400;
                }
                QPushButton {
                    font-size: 13px;
                    font-weight: 400;
                    padding: 0px;
                    text-align: center;
                }
                QLineEdit, QTextEdit, QPlainTextEdit {
                    font-size: 13px;
                    font-weight: 400;
                }
                QCheckBox, QRadioButton {
                    font-size: 13px;
                    font-weight: 400;
                }
                QComboBox {
                    font-size: 13px;
                    font-weight: 400;
                }
                QListWidget {
                    font-size: 13px;
                    font-weight: 400;
                }
                QToolTip {
                    background: rgba(44, 44, 48, 240);
                    color: #ffffff;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-size: 11px;
                    font-weight: 400;
                }
                QScrollArea {
                    border: none;
                    background: transparent;
                }
                QStatusBar {
                    background: transparent;
                    color: rgba(142, 142, 147, 0.8);
                    font-size: 11px;
                    font-weight: 400;
                }
            """
        else:
            base = """
                QWidget {
                    background: transparent;
                    color: rgba(28, 28, 30, 0.9);
                    font-size: 13px;
                    font-weight: 400;
                }
                QLabel {
                    background: transparent;
                    color: rgba(28, 28, 30, 0.9);
                    font-size: 13px;
                    font-weight: 400;
                }
                QPushButton {
                    font-size: 13px;
                    font-weight: 400;
                    padding: 0px;
                    text-align: center;
                }
                QLineEdit, QTextEdit, QPlainTextEdit {
                    font-size: 13px;
                    font-weight: 400;
                }
                QCheckBox, QRadioButton {
                    font-size: 13px;
                    font-weight: 400;
                }
                QComboBox {
                    font-size: 13px;
                    font-weight: 400;
                }
                QListWidget {
                    font-size: 13px;
                    font-weight: 400;
                }
                QToolTip {
                    background: rgba(255, 255, 255, 240);
                    color: #1c1c1e;
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-size: 11px;
                    font-weight: 400;
                }
                QScrollArea {
                    border: none;
                    background: transparent;
                }
                QStatusBar {
                    background: transparent;
                    color: rgba(142, 142, 147, 0.8);
                    font-size: 11px;
                    font-weight: 400;
                }
            """
        
        return (
            base +
            glass.get_neumorphism_button_style(theme) +
            glass.get_neumorphism_input_style(theme) +
            glass.get_neumorphism_groupbox_style(theme) +
            glass.get_neumorphism_list_style(theme) +
            scrollbar +
            slider +
            combobox
        )


def get_menu_stylesheet(theme: str) -> str:
    """获取菜单样式表（用于 QMenu）— 半透明背景配合模糊效果"""
    if theme == "dark":
        return """
            QMenu {
                background-color: rgba(30, 30, 30, 120);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 12px;
                padding: 6px;
            }
            QMenu::item {
                background-color: transparent;
                color: #ffffff;
                padding: 8px 20px;
                border-radius: 8px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background-color: #0A84FF;
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: rgba(255, 255, 255, 110);
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(255, 255, 255, 16);
                margin: 6px 10px;
            }
        """
    else:
        return """
            QMenu {
                background-color: rgba(255, 255, 255, 120);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 12px;
                padding: 6px;
            }
            QMenu::item {
                background-color: transparent;
                color: #1c1c1e;
                padding: 8px 20px;
                border-radius: 8px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background-color: #007AFF;
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: rgba(60, 60, 67, 120);
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(60, 60, 67, 18);
                margin: 6px 10px;
            }
        """


def get_dialog_stylesheet(theme: str) -> str:
    """获取对话框完整样式表"""
    style = StyleSheet
    
    font_family = '"Source Han Sans SC", "Microsoft YaHei", "Segoe UI", sans-serif'
    
    if theme == "dark":
        text_primary = Colors.DARK_TEXT_PRIMARY
        text_secondary = Colors.DARK_TEXT_SECONDARY
    else:
        text_primary = Colors.LIGHT_TEXT_PRIMARY
        text_secondary = Colors.LIGHT_TEXT_SECONDARY

    base = f"""
        QWidget {{
            font-family: {font_family};
            font-size: 11px;
            color: {text_primary};
        }}
        QDialog {{
            background: transparent;
        }}
        QLabel {{
            color: {text_primary};
            background: transparent;
            border: none;
        }}
        QLabel#TitleLabel {{
            font-size: 13px;
            font-weight: 400;
            color: {text_primary};
            margin-bottom: 4px;
        }}
        QLabel#SubtitleLabel {{
            font-size: 10px;
            color: {text_secondary};
        }}
        QCheckBox {{
            spacing: 6px;
            color: {text_primary};
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 3px;
            border: 1px solid {text_secondary};
            background-color: transparent;
        }}
        QCheckBox::indicator:checked {{
            background-color: #007AFF;
            border-color: #007AFF;
            image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='white'><path d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/></svg>");
        }}
        QRadioButton {{
            spacing: 6px;
            color: {text_primary};
        }}
        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 8px;
            border: 1px solid {text_secondary};
            background-color: transparent;
        }}
        QRadioButton::indicator:checked {{
            background-color: #007AFF;
            border-color: #007AFF;
            image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='white'><circle cx='12' cy='12' r='5'/></svg>");
        }}
    """
    
    return (
        base +
        style.get_button_style(theme) +
        style.get_input_style(theme) +
        style.get_scrollbar_style(theme) +
        style.get_combobox_style(theme) +
        style.get_groupbox_style(theme) +
        style.get_slider_style(theme)
    )


def get_button_stylesheet(theme: str) -> str:
    """获取按钮样式表"""
    return StyleSheet.get_button_style(theme)


class CustomToolTip(QWidget):
    """完美圆角的自定义 Tooltip"""

    _instance = None
    _timer = None

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        from qt_compat import QLabel, QGraphicsDropShadowEffect
        self.label = QLabel(self)
        self.label.setWordWrap(False)
        self.label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)

        self._theme = "dark"
        self._update_style()

    def _update_style(self):
        if self._theme == "dark":
            bg = "rgba(44, 44, 48, 240)"
            text = "#ffffff"
            border = "rgba(255, 255, 255, 0.15)"
        else:
            bg = "rgba(255, 255, 255, 240)"
            text = "#1c1c1e"
            border = "rgba(0, 0, 0, 0.1)"

        self.label.setStyleSheet(f"""
            QLabel {{
                background: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }}
        """)

    def showText(self, text: str, pos, theme: str = "dark"):
        self._theme = theme
        self._update_style()
        self.label.setText(text)
        self.adjustSize()

        from qt_compat import QCursor
        cursor_pos = QCursor.pos()
        x = cursor_pos.x() + 15
        y = cursor_pos.y() + 20

        screen = QApplication.screenAt(cursor_pos)
        if screen:
            geo = screen.availableGeometry()
            if x + self.width() > geo.right():
                x = cursor_pos.x() - self.width() - 5
            if y + self.height() > geo.bottom():
                y = cursor_pos.y() - self.height() - 5

        self.move(x, y)
        self.show()
        self.raise_()

    @classmethod
    def showToolTip(cls, text: str, theme: str = "dark"):
        if cls._instance is None:
            cls._instance = CustomToolTip()

        if cls._timer:
            cls._timer.stop()

        from qt_compat import QTimer, QCursor
        cls._instance.showText(text, QCursor.pos(), theme)

        cls._timer = QTimer()
        cls._timer.setSingleShot(True)
        cls._timer.timeout.connect(cls._instance.hide)
        cls._timer.start(3000)

    @classmethod
    def hideToolTip(cls):
        if cls._instance:
            cls._instance.hide()
        if cls._timer:
            cls._timer.stop()
