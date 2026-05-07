"""内置图标选择对话框"""
import sys
import os
import math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from qt_compat import (
    QVBoxLayout, QGridLayout, QLabel, QScrollArea,
    QWidget, QFrame, QtCompat, pyqtSignal, QPixmap, QTimer, QCursor, QApplication, QEvent,
    QDialog, QColor, Qt
)
from core import ShortcutItem
from core.builtin_icons import BuiltinIconsManager
from .base_dialog import BaseDialog
from ui.styles.style import Glassmorphism
from ui.utils.dialog_helper import center_dialog_on_main_window


class BuiltinIconWidget(QFrame):
    """内置图标控件（紧凑版）"""
    clicked = pyqtSignal(ShortcutItem)

    def __init__(self, item: ShortcutItem, theme: str = "dark", icon_size: int = 26, cell_size: int = 42):
        super().__init__()
        self.item = item
        self.theme = theme
        self.icon_size = icon_size
        self.setFixedSize(cell_size, cell_size)
        self.setCursor(QtCompat.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.setAlignment(QtCompat.AlignCenter)

        # 图标底框
        frame_size = icon_size + 10
        self.icon_frame = QFrame()
        self.icon_frame.setObjectName("builtinIconFrame")
        self.icon_frame.setFixedSize(frame_size, frame_size)

        frame_layout = QVBoxLayout(self.icon_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setAlignment(QtCompat.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(icon_size, icon_size)
        self.icon_label.setAlignment(QtCompat.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent;")
        frame_layout.addWidget(self.icon_label)

        layout.addWidget(self.icon_frame, alignment=QtCompat.AlignCenter)

        self.name_label = QLabel(item.name[:4])
        self.name_label.setAlignment(QtCompat.AlignCenter)
        self.name_label.setStyleSheet("font-size: 8px; background: transparent; border: none;")
        layout.addWidget(self.name_label)

        self._load_icon()
        self._set_normal_style()

    def _load_icon(self):
        if self.item.icon_path and os.path.exists(self.item.icon_path):
            pixmap = QPixmap(self.item.icon_path).scaled(
                self.icon_size, self.icon_size, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation
            )
            self.icon_label.setPixmap(pixmap)

    def _frame_style(self, hover=False):
        if hover:
            bg = "rgba(255,255,255,0.14)" if self.theme == "dark" else "rgba(0,0,0,0.08)"
        else:
            bg = "rgba(255,255,255,0.08)" if self.theme == "dark" else "rgba(0,0,0,0.04)"
        border = "1px solid rgba(255,255,255,0.12)" if self.theme == "dark" else "1px solid rgba(0,0,0,0.06)"
        return f"QFrame#builtinIconFrame {{ background: {bg}; border: {border}; border-radius: 6px; }}"

    def _set_normal_style(self):
        self.setStyleSheet("BuiltinIconWidget { background: transparent; border: none; }")
        self.icon_frame.setStyleSheet(self._frame_style(hover=False))

    def _set_hover_style(self):
        self.setStyleSheet("BuiltinIconWidget { background: transparent; border: none; }")
        self.icon_frame.setStyleSheet(self._frame_style(hover=True))

    def enterEvent(self, event):
        self._set_hover_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_normal_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            self.clicked.emit(self.item)


class BuiltinIconsDialog(QDialog):
    """内置图标选择对话框"""
    icon_selected = pyqtSignal(ShortcutItem)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent_window = parent
        self.manager = BuiltinIconsManager()
        self.setWindowTitle("内置图标")

        # 使用 Popup 配合 NoDropShadowWindowHint
        # Popup 标志自带“点击外部自动关闭”特性
        # NoDropShadowWindowHint 消除系统底层可能自带的陈旧/异常阴影
        self.setWindowFlags(
            QtCompat.Popup | 
            QtCompat.FramelessWindowHint | 
            QtCompat.NoDropShadowWindowHint
        )
        self.setAttribute(QtCompat.WA_TranslucentBackground, True)
        self.setAttribute(QtCompat.WA_DeleteOnClose, True)

        # 双重保障：失焦自动关闭定时器
        self._close_timer = QTimer(self)
        self._close_timer.setInterval(200)
        self._close_timer.timeout.connect(self._check_auto_close)

        from ui.utils.window_effect import is_win11
        self.corner_radius = 8 if is_win11() else 12
        self._acrylic_applied = False
        self._closing = False
        self.theme = self._get_theme_from_parent()

        # 设置颜色
        if self.theme == "dark":
            self.bg_color = QColor(28, 28, 30, 180)
            self.border_color = QColor(190, 190, 197, 60)
        else:
            self.bg_color = QColor(242, 242, 247, 160)
            self.border_color = QColor(229, 229, 234, 150)

        self._setup_ui()
        self._apply_theme()

    def _get_theme_from_parent(self):
        """从父窗口获取主题"""
        if self._parent_window:
            try:
                parent = self._parent_window
                while parent:
                    if hasattr(parent, 'data_manager'):
                        return parent.data_manager.get_settings().theme
                    parent = parent.parent() if hasattr(parent, 'parent') else None
            except:
                pass
        return "dark"

    def paintEvent(self, event):
        """半透明模糊背景绘制 - 与 ThemedMessageBox 一致"""
        from qt_compat import QPainter, QPainterPath, QPen
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

        tint_color = QColor(self.bg_color)
        if is_win10():
            tint_color.setAlpha(min(tint_color.alpha(), 150))
        else:
            tint_color.setAlpha(min(tint_color.alpha(), 100))
        painter.fillPath(path, tint_color)

        pen_color = QColor(self.border_color)
        pen_color.setAlpha(min(pen_color.alpha(), 120))
        painter.setPen(QPen(pen_color, 1.0))
        painter.drawPath(path)

    def showEvent(self, event):
        """显示时应用效果"""
        super().showEvent(event)
        # 启动自动检查定时器
        self._close_timer.start()

        center_dialog_on_main_window(self)
        
        # 启用原生 DWM 阴影和圆角
        if not getattr(self, '_effects_applied', False):
            self._effects_applied = True
            from ui.utils.window_effect import enable_window_shadow_and_round_corners
            enable_window_shadow_and_round_corners(self, radius=self.corner_radius)
            
            # 延迟应用亚克力效果以确保窗口已创建
            QTimer.singleShot(10, self._apply_acrylic)

    def _apply_acrylic(self):
        """应用磨砂玻璃效果"""
        try:
            from ui.utils.window_effect import enable_acrylic_for_config_window
            enable_acrylic_for_config_window(self, self.theme, blur_amount=30, radius=self.corner_radius)
        except Exception:
            pass

    def _setup_ui(self):
        items = self.manager.get_items()
        cols = 6
        rows = math.ceil(len(items) / cols)
        cell = 62  # 固定cell尺寸，留出文字空间
        pad = 15

        width = pad * 2 + cols * cell
        height = pad * 2 + rows * cell
        self.setFixedSize(width, height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        container = QWidget(self)
        container.setGeometry(0, 0, width, height)
        container.setStyleSheet("background: transparent;")

        icon_size = 30
        for i, item in enumerate(items):
            widget = BuiltinIconWidget(item, self.theme, icon_size=icon_size, cell_size=cell)
            widget.setParent(container)
            col = i % cols
            row = i // cols
            widget.setGeometry(pad + col * cell, pad + row * cell, cell, cell)
            widget.clicked.connect(self._on_icon_clicked)
            widget.show()

    def _apply_theme(self):
        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(self.theme)
        self.setStyleSheet(base_style + "QDialog { background: transparent; }")


    def _check_auto_close(self):
        """检查是否需要自动关闭"""
        if not self.isActiveWindow():
            self.reject()

    def _on_icon_clicked(self, item: ShortcutItem):
        self.icon_selected.emit(item)
        self.accept()
