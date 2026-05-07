"""
统一的对话框基类 - 与主配置窗口保持一致的 alpha 处理
"""

import logging

from qt_compat import (
    QDialog, QPainter, QColor, QPainterPath, QPen, QTimer, QPoint,
    QtCompat
)
from ui.utils.window_effect import get_window_effect, is_win11, is_win10, enable_acrylic_for_config_window
from ui.utils.dialog_helper import center_dialog_on_main_window

logger = logging.getLogger(__name__)


class BaseDialog(QDialog):
    """统一的对话框基类"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(QtCompat.FramelessWindowHint | QtCompat.Window)
        self.setAttribute(QtCompat.WA_TranslucentBackground, True)
        self.setWindowOpacity(0)

        self.corner_radius = 8 if is_win11() else 12
        self.theme = "dark"
        self._shadow_applied = False
        self._drag_pos = None

        # 使用 QColor 对象存储颜色（与主配置窗口一致）
        self.bg_color = QColor(28, 28, 30, 180)
        self.border_color = QColor(190, 190, 197, 60)

    def _apply_theme_colors(self):
        """应用主题颜色 - 与主配置窗口保持一致"""
        theme = self._get_theme_from_parent()
        self.theme = theme

        if theme == "dark":
            self.bg_color = QColor(28, 28, 30, 180)
            self.border_color = QColor(190, 190, 197, 60)
        else:
            self.bg_color = QColor(242, 242, 247, 160)
            self.border_color = QColor(229, 229, 234, 150)

    def _get_theme_from_parent(self) -> str:
        """从父窗口获取主题 - 向上遍历查找"""
        if self.parent():
            try:
                parent = self.parent()
                while parent:
                    if hasattr(parent, 'data_manager'):
                        return parent.data_manager.get_settings().theme
                    parent = parent.parent()
            except Exception as e:
                logger.debug(f"获取主题失败: {e}")

    def paintEvent(self, event):
        """绘制背景 - 完全按照RoundedWindow的逻辑"""
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)

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

        # 磨砂玻璃模式：与RoundedWindow完全一致
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
        """显示时应用效果"""
        super().showEvent(event)
        self.adjustSize()
        center_dialog_on_main_window(self)

        if not self._shadow_applied:
            self._shadow_applied = True
            QTimer.singleShot(100, self._apply_effects)

        self._start_show_animation()

    def _apply_effects(self):
        """应用窗口特效"""
        try:
            hwnd = int(self.winId())
            effect = get_window_effect()
            theme = self.theme
            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
            else:
                w, h = self.width(), self.height()
                if w > 0 and h > 0:
                    effect.set_window_region(hwnd, w, h, self.corner_radius)
            enable_acrylic_for_config_window(self, theme, blur_amount=10)
        except Exception:
            pass

    def _start_show_animation(self):
        """窗口出现动画"""
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

    def mousePressEvent(self, event):
        """鼠标按下 - 支持拖动"""
        if event.button() == QtCompat.LeftButton:
            pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            if pos.y() <= 50:
                self._drag_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                event.accept()
            else:
                self._drag_pos = None

    def mouseMoveEvent(self, event):
        """鼠标移动 - 拖动窗口"""
        if self._drag_pos is not None and event.buttons() & QtCompat.LeftButton:
            new_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            self.move(self.pos() + (new_pos - self._drag_pos))
            self._drag_pos = new_pos
            event.accept()

    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        self._drag_pos = None
        super().mouseReleaseEvent(event)
