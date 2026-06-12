"""
轻量级 Toast 通知弹窗
- 小巧简约矩形设计
- 屏幕中央显示
- 自动消失（约1.5秒）
- 支持明暗主题
"""

import logging

from qt_compat import (
    QApplication,
    QColor,
    QLabel,
    QPainter,
    QPainterPath,
    Qt,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from ui.styles.window_chrome import apply_custom_window_chrome
from ui.utils.font_manager import get_qfont
from ui.utils.ui_scale import scale_qss, sp, spf

logger = logging.getLogger(__name__)


class ToastNotification(QWidget):
    """轻量级 Toast 通知弹窗 - 小巧简约风格"""

    # 单例引用，确保同时只显示一个
    _current_instance = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self._start_fade_out)

        # 淡出动画 - 用定时器模拟
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(20)  # 50fps
        self._fade_timer.timeout.connect(self._fade_step)
        self._fade_opacity = 1.0
        self._acrylic_applied = False

        # 窗口属性：无边框、置顶、工具窗口、透明背景、不获取焦点
        apply_custom_window_chrome(self, kind="tool", topmost=True, translucent=True, delete_on_close=False)
        # 不获取焦点
        try:
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        except Exception:
            try:
                self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            except Exception as exc:
                logger.debug("设置窗口属性失败: %s", exc, exc_info=True)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.label = QLabel()
        self.label.setAlignment(QtCompat.AlignCenter)
        layout.addWidget(self.label)

        # 设置固定高度
        self.setFixedHeight(sp(40))

    def paintEvent(self, event):
        """绘制圆角矩形背景 - 与主配置窗口完全一致"""
        from ui.utils.window_effect import is_win10, paint_win10_rounded_surface

        painter = QPainter(self)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            radius = sp(8)

            if self._theme == "error":
                bg_color = QColor(229, 57, 53, 210)
                border_color = QColor(255, 205, 210, 180)
            elif self._theme == "dark":
                bg_color = QColor(28, 28, 30, 180)
                border_color = QColor(190, 190, 197, 60)
            else:
                bg_color = QColor(242, 242, 247, 160)
                border_color = QColor(229, 229, 234, 150)

            if is_win10():
                paint_win10_rounded_surface(painter, self, bg_color, border_color, radius, max_border_alpha=80)
                return

            inset = spf(0.5)
            path = QPainterPath()
            path.addRoundedRect(inset, inset, self.width() - inset * 2, self.height() - inset * 2, radius, radius)

            tint_color = QColor(bg_color)
            tint_color.setAlpha(min(tint_color.alpha(), 100))
            painter.fillPath(path, tint_color)

            pen_color = QColor(border_color)
            pen_color.setAlpha(40)
            from qt_compat import QPen

            pen = QPen(pen_color, 0.3)
            pen.setJoinStyle(QtCompat.RoundJoin)
            pen.setCapStyle(QtCompat.RoundCap)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawPath(path)
        finally:
            painter.end()

    def show_toast(self, text: str, theme: str = "dark", duration_ms: int = 1500, target_widget=None):
        """显示 Toast 通知

        Args:
            text: 显示文字
            theme: 主题 ("dark" / "light" / "error")
            duration_ms: 显示时长(毫秒)
            target_widget: 目标定位挂接控件，若传入则定位至该控件所在主窗口的右下角
        """
        # 关闭已有的 toast
        if ToastNotification._current_instance and ToastNotification._current_instance is not self:
            try:
                old = ToastNotification._current_instance
                old.hide()
                old.deleteLater()
            except Exception as exc:
                logger.debug("隐藏当前Toast实例失败: %s", exc, exc_info=True)
        ToastNotification._current_instance = self

        self._theme = theme

        # 停止进行中的淡出
        self._fade_timer.stop()
        self._auto_hide_timer.stop()
        self._fade_opacity = 1.0
        self.setWindowOpacity(1.0)

        # 配置文字样式
        if theme in ("dark", "error"):
            color = "#FFFFFF"
        else:
            color = "#1c1c1e"

        self.label.setStyleSheet(
            scale_qss(
                f"""
            QLabel {{
                color: {color};
                font-size: 13px;
                font-weight: 400;
                padding: 0 24px;
                background: transparent;
            }}
        """
            )
        )
        self.label.setFont(get_qfont(13, 400))
        self.label.setText(text)

        # 根据文字长度调整宽度
        fm = self.label.fontMetrics()
        text_width = fm.horizontalAdvance(text) if hasattr(fm, "horizontalAdvance") else fm.width(text)
        self.setFixedWidth(max(text_width + sp(60), sp(180)))

        # 定位逻辑：有挂接控件定位右下角，无则居中
        positioned = False
        if target_widget is not None:
            try:
                target_window = target_widget.window()
                geo = target_window.geometry()
                # 动作链窗口右下角弹窗提示，保留一些边距（24px）
                x = geo.right() - self.width() - sp(24)
                y = geo.bottom() - self.height() - sp(24)
                self.move(x, y)
                positioned = True
            except Exception as exc:
                logger.debug("根据目标窗口定位失败: %s", exc, exc_info=True)

        if not positioned:
            screen = None
            try:
                screen = QApplication.primaryScreen()
            except Exception as exc:
                logger.debug("获取主屏幕失败: %s", exc, exc_info=True)
            if screen:
                geo = screen.availableGeometry()
                x = geo.left() + (geo.width() - self.width()) // 2
                y = geo.top() + (geo.height() - self.height()) // 2
                self.move(x, y)

        self.show()
        self.raise_()

        # 应用模糊效果
        if not self._acrylic_applied:
            self._acrylic_applied = True
            QTimer.singleShot(10, self._apply_acrylic)

        # 启动自动隐藏计时器
        self._auto_hide_timer.start(duration_ms)

    def _start_fade_out(self):
        """开始淡出"""
        self._fade_opacity = 1.0
        self._fade_timer.start()

    def _fade_step(self):
        """淡出步进"""
        self._fade_opacity -= 0.05  # 约 400ms 完成淡出 (20ms * 20 steps)
        if self._fade_opacity <= 0:
            self._fade_timer.stop()
            self.hide()
            self._fade_opacity = 1.0
            self.setWindowOpacity(1.0)
        else:
            self.setWindowOpacity(self._fade_opacity)

    def _apply_acrylic(self):
        """应用模糊效果 - 与主配置窗口一致"""
        try:
            from ui.utils.window_effect import enable_acrylic_for_config_window, get_window_effect, is_win11

            hwnd = int(self.winId())
            if not hwnd:
                return
            effect = get_window_effect()
            radius = sp(8)

            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
                effect.enable_window_shadow(hwnd, radius)
                enable_acrylic_for_config_window(self, self._theme, blur_amount=10)
            else:
                enable_acrylic_for_config_window(self, self._theme, blur_amount=8, radius=radius)
        except Exception as exc:
            logger.debug("应用窗口特效失败: %s", exc, exc_info=True)

    def hideEvent(self, event):
        """隐藏时停止计时器"""
        try:
            self._auto_hide_timer.stop()
        except Exception as exc:
            logger.debug("停止自动隐藏定时器失败: %s", exc, exc_info=True)
        try:
            self._fade_timer.stop()
        except Exception as exc:
            logger.debug("停止淡出定时器失败: %s", exc, exc_info=True)
        self._fade_opacity = 1.0
        try:
            self.setWindowOpacity(1.0)
        except Exception as exc:
            logger.debug("设置窗口不透明度失败: %s", exc, exc_info=True)
        self._acrylic_applied = False
        # 清理单例引用，允许 GC 回收隐藏的 Toast 实例
        if ToastNotification._current_instance is self:
            ToastNotification._current_instance = None
        super().hideEvent(event)
