"""支持页面。"""

import logging
import random

from PyQt5.QtCore import QEasingCurve, Qt  # 引入核心 Qt 常量与缓动曲线
from PyQt5.QtGui import QLinearGradient, QRadialGradient
from PyQt5.QtWidgets import QGraphicsOpacityEffect

from core.i18n import tr
from qt_compat import (
    QBrush,
    QColor,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPoint,
    QPointF,
    QPushButton,
    QRect,
    QRectF,
    QtCompat,
    QTimer,
    QVBoxLayout,
    pyqtProperty,
)
from ui.config_window.support_dialog import _rounded_pixmap, _support_image_path
from ui.styles.themed_messagebox import ThemedMessageBox

logger = logging.getLogger(__name__)


class FloatingEmoji(QLabel):
    """漂浮的互动表情文字标签，作为独立的透明无边框窗口运行，可以自由飘出配置窗口范围，创造极富视觉张力的无边界感。"""

    _active_instances = []  # 用类级强引用管理器管理实例生命周期，防止 PyQt5 中无 Parent 的 Top-Level 窗口被自动 GC 销毁

    def __init__(self, text, start_global_pos, parent=None, is_auto=False):
        # 传入 None 作为父级，使其成为不受主窗口边界限制的顶级窗口
        super().__init__(None)
        FloatingEmoji._active_instances.append(self)

        # 1. 核心无边界参数配置：
        # - FramelessWindowHint: 去除边框和标题栏
        # - Tool: 避免在 Windows 任务栏或 Alt+Tab 切换器中创建图标
        # - WindowStaysOnTopHint: 置顶于主窗口之上漂浮
        # - WindowDoesNotAcceptFocus: 绝对的“鼠标穿透”，不夺取焦点、不阻挡任何点击事件
        self.setWindowFlags(
            QtCompat.FramelessWindowHint
            | QtCompat.Tool
            | QtCompat.WindowStaysOnTopHint
            | QtCompat.NoDropShadowWindowHint
            | Qt.WindowDoesNotAcceptFocus
        )

        # 开启透明背景与无激活展示属性
        self.setAttribute(QtCompat.WA_TranslucentBackground)
        self.setAttribute(QtCompat.WA_ShowWithoutActivating)

        # 区分自动气泡与手动连击的物理参数
        if is_auto:
            self.setStyleSheet("font-size: 16px; background: transparent; border: none;")
            initial_opacity = 0.70
            duration = 1800  # 升起得更慢、更轻
            max_dy = -120
            min_dy = -80
            max_dx = 20
        else:
            self.setStyleSheet("font-size: 26px; background: transparent; border: none; font-weight: 400;")
            initial_opacity = 1.0
            duration = 1200  # 点击时爆发力强
            max_dy = -200
            min_dy = -130
            max_dx = 60

        self.setText(text)
        self.adjustSize()

        # 在物理屏幕坐标系（全局坐标系）下精准定位粒子
        start_screen_pos = start_global_pos - QPoint(self.width() // 2, self.height() // 2)
        self.move(start_screen_pos)
        self.show()

        from qt_compat import QParallelAnimationGroup

        self.group = QParallelAnimationGroup(self)

        # 1. 【先快后慢】全局屏幕坐标位置上升动画
        self.pos_anim = QtCompat.QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(duration)
        self.pos_anim.setStartValue(self.pos())

        dx = random.randint(-max_dx, max_dx)
        dy = random.randint(max_dy, min_dy)
        self.pos_anim.setEndValue(self.pos() + QPoint(dx, dy))
        self.pos_anim.setEasingCurve(QEasingCurve.OutExpo)  # 指数级物理减速
        self.group.addAnimation(self.pos_anim)

        # 2. 【先实后虚】硬件级窗口透明度渐隐动画
        # 针对顶级窗口直接对 windowOpacity 进行硬件级 DWM 淡出，完全免于离屏缓存造成的 Viewport 裁剪与闪烁
        self.opacity_anim = QtCompat.QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(duration)
        self.opacity_anim.setStartValue(initial_opacity)
        self.opacity_anim.setEndValue(0.0)
        self.opacity_anim.setEasingCurve(QEasingCurve.InQuad)
        self.group.addAnimation(self.opacity_anim)

        self.group.finished.connect(self._on_anim_finished)
        self.group.start()

    def _on_anim_finished(self):
        if self in FloatingEmoji._active_instances:
            FloatingEmoji._active_instances.remove(self)
        self.deleteLater()


class WobblyCoffeeCup(QLabel):
    """可点击的咖啡杯标签，背部配有极简高级且高对比度可见的“呼吸氛围光环 (Breathing Aura Halo)”。
    支持自动低频像香气一样向全局屏幕发射无边界表情粒子，并在用户连击时瞬间爆发。"""

    def __init__(self, text="☕", parent=None):
        super().__init__(text, parent)
        self.setCursor(QtCompat.PointingHandCursor)
        self.setFixedSize(120, 120)
        self.setAlignment(QtCompat.AlignCenter)

        self.theme = "dark"
        self._offset = QPoint(0, 0)
        self._angle = 0.0
        self._halo_opacity = 0.0  # 默认关闭，由 showEvent 激活

        self._wobble_group = None

        # 1. 初始化呼吸动画，但并不立即启动
        self._breathing_anim = QtCompat.QPropertyAnimation(self, b"halo_opacity")
        self._breathing_anim.setDuration(2400)
        self._breathing_anim.setStartValue(0.15)
        self._breathing_anim.setKeyValueAt(0.5, 0.38)
        self._breathing_anim.setEndValue(0.15)
        self._breathing_anim.setEasingCurve(QtCompat.InOutQuart)
        self._breathing_anim.finished.connect(self._breathing_anim.start)

        # 2. 自动中低频热气飘出定时器（常态为 0.8s 喷发一次）
        self.current_interval = 800
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self.on_auto_spawn)

    @pyqtProperty(QPoint)
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, val):
        self._offset = val
        self.update()

    @pyqtProperty(float)
    def angle(self):
        return self._angle

    @angle.setter
    def angle(self, val):
        self._angle = val
        self.update()

    @pyqtProperty(float)
    def halo_opacity(self):
        return self._halo_opacity

    @halo_opacity.setter
    def halo_opacity(self, val):
        self._halo_opacity = val
        self.update()

    def pause_effects(self):
        """停止所有背景呼吸动画和蒸汽喷吐定时器，释放 CPU/GPU 算力。"""
        if hasattr(self, "auto_timer") and self.auto_timer.isActive():
            self.auto_timer.stop()
        if hasattr(self, "_breathing_anim"):
            self._breathing_anim.stop()
        self._halo_opacity = 0.0
        self.update()

    def resume_effects(self):
        """进入页面时激活或恢复呼吸灯与低频蒸汽飘散。"""
        self.current_interval = 800
        self._halo_opacity = 0.15

        if hasattr(self, "auto_timer"):
            self.auto_timer.setInterval(self.current_interval)
            self.auto_timer.start()

        if hasattr(self, "_breathing_anim"):
            self._breathing_anim.start()

    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            self.wobble()
            self.spawn_heart()
            self.flash_halo()

            # 点击瞬间爆发性地向屏幕发射 3 个大气泡粒子
            for _ in range(3):
                self.spawn_heart(is_auto=False)

            # 加速喷吐！间隔瞬间滑落到极速 80ms
            self.current_interval = 80
            self.auto_timer.setInterval(self.current_interval)
            self.auto_timer.start()  # 重启定时器
        super().mousePressEvent(event)

    def on_auto_spawn(self):
        """低频定时吐气。如果处于加速状态，间隔时间会按照阻尼物理平滑衰减退回到 0.8s 的慢节奏。"""
        self.spawn_heart(is_auto=True)

        # 阻尼过渡衰减算法（指数级平滑衰减退回 800ms）
        if self.current_interval < 800:
            self.current_interval = min(800, int(self.current_interval * 1.30 + 15))
            self.auto_timer.setInterval(self.current_interval)

    def wobble(self):
        self._offset = QPoint(0, 0)
        self._angle = 0.0

        from qt_compat import QParallelAnimationGroup

        self._wobble_group = QParallelAnimationGroup(self)

        anim_angle = QtCompat.QPropertyAnimation(self, b"angle")
        anim_angle.setDuration(500)
        anim_angle.setStartValue(0.0)
        anim_angle.setKeyValueAt(0.15, -18.0)
        anim_angle.setKeyValueAt(0.3, 14.0)
        anim_angle.setKeyValueAt(0.45, -10.0)
        anim_angle.setKeyValueAt(0.6, 6.0)
        anim_angle.setKeyValueAt(0.75, -3.0)
        anim_angle.setEndValue(0.0)
        anim_angle.setEasingCurve(QtCompat.InOutQuart)

        anim_pos = QtCompat.QPropertyAnimation(self, b"offset")
        anim_pos.setDuration(500)
        anim_pos.setStartValue(QPoint(0, 0))
        anim_pos.setKeyValueAt(0.25, QPoint(0, -15))
        anim_pos.setKeyValueAt(0.45, QPoint(0, 4))
        anim_pos.setKeyValueAt(0.65, QPoint(0, -4))
        anim_pos.setKeyValueAt(0.8, QPoint(0, 1))
        anim_pos.setEndValue(QPoint(0, 0))
        anim_pos.setEasingCurve(QtCompat.OutCubic)

        self._wobble_group.addAnimation(anim_angle)
        self._wobble_group.addAnimation(anim_pos)
        self._wobble_group.start()

    def flash_halo(self):
        """点击时呼吸灯微亮一下，展现轻微点击回馈。"""
        self._breathing_anim.stop()

        flash = QtCompat.QPropertyAnimation(self, b"halo_opacity")
        flash.setDuration(350)
        flash.setStartValue(0.65)  # 闪烁峰值
        flash.setEndValue(0.15)
        flash.setEasingCurve(QtCompat.OutCubic)

        def restart_breath():
            self._breathing_anim.start()

        flash.finished.connect(restart_breath)
        flash.start()
        self._flash_anim = flash

    def update_style(self, theme):
        self.theme = theme
        self.update()

    def spawn_heart(self, is_auto=False):
        """生成气泡粒子。将杯心物理坐标直接 mapToGlobal（转换为屏幕级坐标系），从而能够突破窗口边缘飞舞。"""
        # 自动浮现模式只喷涂咖啡杯升起的热气/爱心（☕, ❤️, ✨, 💖, 🍃, 💨）
        if is_auto:
            emojis = ["☕", "❤️", "✨", "💖", "🍃", "💨"]
        else:
            emojis = ["❤️", "💖", "✨", "☕", "🎉", "👍", "Thanks!", "+1"]

        emoji = random.choice(emojis)

        # 精确转换为底层屏幕坐标系，以便粒子独立于窗口自由飞跃
        cup_local_center = QPoint(self.width() // 2, self.height() // 2)
        global_screen_pos = self.mapToGlobal(cup_local_center)

        FloatingEmoji(emoji, global_screen_pos, None, is_auto=is_auto)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect()
        cx = rect.center().x() + self._offset.x()
        cy = rect.center().y() + self._offset.y()

        # 1. 绘制背部纯弥散的柔和呼吸发光 Aura (半径扩大至 50px，直径 100px)
        halo_radius = 50.0
        halo_gradient = QRadialGradient(QPointF(cx, cy), halo_radius)

        alpha_val = int(255 * self._halo_opacity)

        # 主题与高对比度可见度设计
        if self.theme == "dark":
            # 暗色主题：高级温润的金白蚀环光晕
            glow_color = QColor(255, 235, 190, alpha_val)
        else:
            # 亮色主题：纯白背景下白色不可见，采用清新暖阳橙黄光圈，极度舒适优雅
            glow_color = QColor(255, 180, 100, alpha_val)

        halo_gradient.setColorAt(0.0, glow_color)
        halo_gradient.setColorAt(1.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 0))

        painter.setPen(QtCompat.NoPen)
        painter.setBrush(QBrush(halo_gradient))
        painter.drawEllipse(QRectF(cx - halo_radius, cy - halo_radius, halo_radius * 2, halo_radius * 2))

        # 2. 绘制 Emoji 主体 (居中)
        painter.translate(cx, cy)
        painter.rotate(self._angle)

        font = painter.font()
        font.setPointSize(36)
        painter.setFont(font)
        painter.drawText(QRect(-30, -30, 60, 60), QtCompat.AlignCenter, self.text())
        painter.end()


class DrinkCard(QFrame):
    """虚拟饮品卡片，带极简克制的高级聚光灯跟随光效与微弱对角扫光，描边保持精致的单像素宽。"""

    from qt_compat import pyqtSignal

    clicked = pyqtSignal(str, float)

    def __init__(self, emoji, name, price, color_hex, theme="dark", parent=None):
        super().__init__(parent)
        self.emoji = emoji
        self.name = name
        self.price = price
        self.color_hex = color_hex
        self.theme = theme
        self.accent_color = QColor(color_hex)

        self.setCursor(QtCompat.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFixedWidth(100)
        self.setFixedHeight(110)

        self._hover_progress = 0.0
        self._scale = 1.0
        self._sweep_progress = 0.0
        self._mouse_pos = QPoint(50, 55)

        self._hover_anim = None
        self._click_anim = None
        self._sweep_anim = None

    @pyqtProperty(float)
    def hover_progress(self):
        return self._hover_progress

    @hover_progress.setter
    def hover_progress(self, val):
        self._hover_progress = val
        self.update()

    @pyqtProperty(float)
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, val):
        self._scale = val
        self.update()

    @pyqtProperty(float)
    def sweep_progress(self):
        return self._sweep_progress

    @sweep_progress.setter
    def sweep_progress(self, val):
        self._sweep_progress = val
        self.update()

    def mouseMoveEvent(self, event):
        self._mouse_pos = event.pos()
        self.update()
        super().mouseMoveEvent(event)

    def enterEvent(self, event):
        anim = QtCompat.QPropertyAnimation(self, b"hover_progress")
        anim.setDuration(220)
        anim.setStartValue(self._hover_progress)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QtCompat.OutCubic)
        anim.start()
        self._hover_anim = anim
        super().enterEvent(event)

    def leaveEvent(self, event):
        anim = QtCompat.QPropertyAnimation(self, b"hover_progress")
        anim.setDuration(180)
        anim.setStartValue(self._hover_progress)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QtCompat.OutCubic)
        anim.start()
        self._hover_anim = anim
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            anim = QtCompat.QPropertyAnimation(self, b"scale")
            anim.setDuration(200)
            anim.setStartValue(1.0)
            anim.setKeyValueAt(0.4, 0.9)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QtCompat.InOutQuart)
            anim.start()
            self._click_anim = anim

            sweep = QtCompat.QPropertyAnimation(self, b"sweep_progress")
            sweep.setDuration(650)
            sweep.setStartValue(0.0)
            sweep.setEndValue(1.0)
            sweep.setEasingCurve(QtCompat.InOutQuart)
            sweep.start()
            self._sweep_anim = sweep

            self.clicked.emit(self.name, self.price)
        super().mousePressEvent(event)

    def update_style(self, theme):
        self.theme = theme
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect()
        cx = rect.center().x()
        cy = rect.center().y()
        painter.translate(cx, cy)
        painter.scale(self._scale, self._scale)
        painter.translate(-cx, -cy)

        # 调配深浅色底色与极淡的描边基色
        if self.theme == "dark":
            base_bg = QColor(255, 255, 255, 10)  # rgba(255, 255, 255, 0.04)
            base_border = QColor(255, 255, 255, 12)  # 极淡的暗红线
            text_color = QColor(255, 255, 255, 240)
            sub_color = QColor(255, 255, 255, 128)
            hover_bg = QColor(255, 255, 255, 20)  # rgba(255, 255, 255, 0.08)
        else:
            base_bg = QColor(0, 0, 0, 5)  # rgba(0, 0, 0, 0.02)
            base_border = QColor(0, 0, 0, 10)  # 极淡的淡灰描边
            text_color = QColor(28, 28, 30, 230)
            sub_color = QColor(28, 28, 30, 128)
            hover_bg = QColor(255, 255, 255, 217)  # rgba(255, 255, 255, 0.85)

        p = self._hover_progress

        # 颜色线性差值
        r = int(base_bg.red() * (1 - p) + hover_bg.red() * p)
        g = int(base_bg.green() * (1 - p) + hover_bg.green() * p)
        b = int(base_bg.blue() * (1 - p) + hover_bg.blue() * p)
        a = int(base_bg.alpha() * (1 - p) + hover_bg.alpha() * p)
        bg_color = QColor(r, g, b, a)

        # 描边淡一点 (最大描边 alpha 仅限 110 与 75)
        max_border_alpha = 110 if self.theme == "dark" else 75
        br = int(base_border.red() * (1 - p) + self.accent_color.red() * p)
        bg_val = int(base_border.green() * (1 - p) + self.accent_color.green() * p)
        bb = int(base_border.blue() * (1 - p) + self.accent_color.blue() * p)
        ba = int(base_border.alpha() * (1 - p) + max_border_alpha * p)
        border_color = QColor(br, bg_val, bb, ba)

        # 1. 绘制基本卡片路径与背景
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, rect.width() - 2, rect.height() - 2), 14, 14)
        painter.fillPath(path, QBrush(bg_color))

        # 2. [简约淡光效] 径向鼠标聚光灯跟随光环 (Hover spotlight reveal - Opacity 降低一倍以保证简约)
        if p > 0.0 and self._mouse_pos:
            spotlight_rad = 70.0
            spotlight = QRadialGradient(QPointF(self._mouse_pos), spotlight_rad)

            glow_intensity = int(32 * p) if self.theme == "dark" else int(20 * p)
            g_color = QColor(self.accent_color)
            g_color.setAlpha(glow_intensity)

            spotlight.setColorAt(0.0, g_color)
            spotlight.setColorAt(1.0, QColor(0, 0, 0, 0))

            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(spotlight))
            painter.drawPath(path)

        # 3. 绘制精致单像素描边 (描边淡且细，恒定为 1.0 宽度)
        pen = QPen(border_color, 1.0)
        painter.setPen(pen)
        painter.drawPath(path)

        # 4. [简约淡光效] 金属质感对角扫光 (扫光亮度降低，极为素雅)
        if 0.0 < self._sweep_progress < 1.0:
            w = rect.width()
            h = rect.height()

            x = -w + self._sweep_progress * (3.5 * w)

            shimmer = QLinearGradient(x, 0, x + 40, h)
            fade_curve = 1.0 - abs(self._sweep_progress - 0.5) * 2.0
            shimmer_alpha = int(40 * max(0.0, fade_curve))  # 降低亮度

            shimmer.setColorAt(0.0, QColor(255, 255, 255, 0))
            shimmer.setColorAt(0.5, QColor(255, 255, 255, shimmer_alpha))
            shimmer.setColorAt(1.0, QColor(255, 255, 255, 0))

            painter.save()
            painter.setClipPath(path)
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(shimmer))
            painter.drawPath(path)
            painter.restore()

        # 5. 绘制 Emoji (已修复: 使用标准画笔 QPen(text_color) 绘制，杜绝 NoPen 导致的 Emoji 完全隐身)
        emoji_font = painter.font()
        emoji_size = int(28 + p * 4)
        emoji_font.setPointSize(emoji_size)
        painter.setFont(emoji_font)
        painter.setPen(QPen(text_color))  # 改用实体画笔绘制，确保表情 100% 渲染显示
        painter.drawText(QRect(0, 10, rect.width(), 42), QtCompat.AlignCenter, self.emoji)

        # 6. 绘制标题
        name_font = painter.font()
        name_font.setPointSize(10)
        name_font.setBold(False)
        painter.setFont(name_font)
        painter.setPen(QPen(text_color))
        painter.drawText(QRect(0, 56, rect.width(), 20), QtCompat.AlignCenter, self.name)

        # 7. 绘制价格
        price_font = painter.font()
        price_font.setPointSize(9)
        price_font.setBold(False)
        painter.setFont(price_font)
        painter.setPen(QPen(sub_color))
        painter.drawText(QRect(0, 76, rect.width(), 20), QtCompat.AlignCenter, f"¥{self.price:.2f}")

        painter.end()


class SettingsSupportPageMixin:
    def _setup_support_page(self, page):
        # 1. 页面头部卡片组件
        layout, group = page.add_group(tr("支持一下"))

        container = QFrame(page)
        container.setObjectName("SupportPageContainer")
        container.setStyleSheet("background: transparent; border: none;")

        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(0, 5, 0, 5)
        v_layout.setSpacing(15)

        # 头部说明区域
        header_widget = QFrame(container)
        header_widget.setStyleSheet("background: transparent; border: none;")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        header_layout.setAlignment(QtCompat.AlignCenter)

        # 咖啡杯互动挂件
        self._cup_widget = WobblyCoffeeCup("☕", container)
        header_layout.addWidget(self._cup_widget)

        self._support_title_lbl = QLabel(tr("请开发者喝杯咖啡吧"))
        self._support_title_lbl.setAlignment(QtCompat.AlignCenter)
        header_layout.addWidget(self._support_title_lbl)

        self._support_desc_lbl = QLabel(
            tr(
                "QuickLauncher 是一款开源且免费的桌面效率工具，由开发者在业余时间独立开发维护。\n"
                "您的赞助将被全额用于产品的日常维护与服务器开销。非常感谢您的暖心支持！❤️"
            )
        )
        self._support_desc_lbl.setAlignment(QtCompat.AlignCenter)
        self._support_desc_lbl.setWordWrap(True)
        header_layout.addWidget(self._support_desc_lbl)

        v_layout.addWidget(header_widget)

        # 2. 虚拟饮品吧 (2x2 网格)
        drink_bar_widget = QFrame(container)
        drink_bar_widget.setStyleSheet("background: transparent; border: none;")
        drink_grid = QGridLayout(drink_bar_widget)
        drink_grid.setContentsMargins(0, 0, 0, 0)
        drink_grid.setSpacing(12)
        drink_grid.setAlignment(QtCompat.AlignCenter)

        drinks_data = [
            ("💧", tr("纯净矿泉水"), 2.00, "#34C759", 0, 0),
            ("☕", tr("香浓拿铁"), 5.19, "#FF9500", 0, 1),
            ("🍵", tr("沁心绿茶"), 9.90, "#00C7BE", 1, 0),
            ("🍹", tr("芝芝莓莓"), 15.00, "#FF2D55", 1, 1),
        ]

        for emoji, name, price, color, row, col in drinks_data:
            card = DrinkCard(emoji, name, price, color, "dark", container)
            card.clicked.connect(self._on_drink_clicked)
            drink_grid.addWidget(card, row, col)

        v_layout.addWidget(drink_bar_widget)

        # 互动反馈消息标签
        self._reaction_label = QLabel(tr("👇 点击上方任一饮品，获取赞助二维码 (也可点击咖啡杯互动哦)"))
        self._reaction_label.setAlignment(QtCompat.AlignCenter)
        self._reaction_label.setWordWrap(True)
        v_layout.addWidget(self._reaction_label)

        # 3. 折叠式二维码容器 (默认隐藏，小巧美观)
        self._qr_container = QFrame(container)
        self._qr_container.setObjectName("QRContainer")
        self._qr_container.setFixedWidth(280)

        qr_outer_layout = QHBoxLayout()
        qr_outer_layout.addStretch()  # 左侧拉伸，使二维码卡片在整个配置页面绝对水平居中
        qr_outer_layout.addWidget(self._qr_container)
        qr_outer_layout.addStretch()  # 右侧拉伸，使二维码卡片在整个配置页面绝对水平居中

        qr_layout = QVBoxLayout(self._qr_container)
        qr_layout.setContentsMargins(12, 12, 12, 12)
        qr_layout.setSpacing(10)
        qr_layout.setAlignment(QtCompat.AlignCenter)

        # 二维码图片标签 (130x130)
        self._qr_image_label = QLabel(self._qr_container)
        self._qr_image_label.setFixedSize(130, 130)
        self._qr_image_label.setAlignment(QtCompat.AlignCenter)
        self._qr_image_label.setStyleSheet("background: transparent; border: none;")

        support_img_path = _support_image_path()
        pixmap = QPixmap(support_img_path)
        if pixmap.isNull():
            pixmap = QPixmap(130, 130)
            pixmap.fill(QColor(128, 128, 128))
        else:
            pixmap = pixmap.scaled(120, 120, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
            pixmap = _rounded_pixmap(pixmap, 10)

        self._qr_image_label.setPixmap(pixmap)
        qr_layout.addWidget(self._qr_image_label, 0, QtCompat.AlignCenter)  # 明确赋予居中对齐标识，防止左偏

        # 二维码操作按钮 (换用极简现代的 unicode 标识符 ⛶ 和 ✕ 代替普通 emoji)
        qr_btn_layout = QHBoxLayout()
        qr_btn_layout.setSpacing(8)
        qr_btn_layout.addStretch()  # 左侧拉伸，使按钮组在容器内完美水平居中

        self._view_fullscreen_btn = QPushButton(tr("⛶ 放大查看"), self._qr_container)
        self._view_fullscreen_btn.clicked.connect(self._on_support)
        self._view_fullscreen_btn.setProperty("is_custom_styled_btn", True)

        self._close_qr_btn = QPushButton(tr("✕ 关闭二维码"), self._qr_container)
        self._close_qr_btn.clicked.connect(self._close_qr)
        self._close_qr_btn.setProperty("is_custom_styled_btn", True)

        qr_btn_layout.addWidget(self._view_fullscreen_btn)
        qr_btn_layout.addWidget(self._close_qr_btn)
        qr_btn_layout.addStretch()  # 右侧拉伸，使按钮组在容器内完美水平居中
        qr_layout.addLayout(qr_btn_layout)

        v_layout.addLayout(qr_outer_layout)
        self._qr_container.hide()

        # 4. 底部功能型胶囊按钮
        footer_widget = QFrame(container)
        footer_widget.setStyleSheet("background: transparent; border: none;")
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 10, 0, 0)
        footer_layout.setSpacing(12)
        footer_layout.setAlignment(QtCompat.AlignCenter)

        self._star_btn = QPushButton(tr("⭐ 点个 Star 鼓励一下"), footer_widget)
        self._star_btn.clicked.connect(self._on_star_clicked)

        self._feedback_btn = QPushButton(tr("💬 反馈建议 / 进群交流"), footer_widget)
        self._feedback_btn.clicked.connect(self._on_feedback_clicked)

        footer_layout.addWidget(self._star_btn)
        footer_layout.addWidget(self._feedback_btn)

        v_layout.addWidget(footer_widget)

        # 加入页面主布局
        layout.addWidget(container)

        # 属性保存供动态主题更新调用
        page._support_title_lbl = self._support_title_lbl
        page._support_desc_lbl = self._support_desc_lbl
        page._reaction_label = self._reaction_label
        page._qr_container = self._qr_container
        page._view_fullscreen_btn = self._view_fullscreen_btn
        page._close_qr_btn = self._close_qr_btn
        page._cup_widget = self._cup_widget  # 将咖啡杯引用存于 page，以便 apply_theme 时找到它

        # 主题与休眠/唤醒钩子修补，实现动态主题适配及绝对的节电/零占用休眠
        original_apply_theme = page.apply_theme

        def custom_apply_theme(theme):
            original_apply_theme(theme)
            self._update_support_page_theme(page, theme)

        page.apply_theme = custom_apply_theme

        # 重写 QWidget 的 showEvent 与 hideEvent 钩子
        # 确保只有当用户点击切换到“支持一下”面板时，定时器与动画才开始运转；一旦离开该页面，底层定时器瞬间彻底关闭，实现 0% CPU 占用
        original_show = page.showEvent
        original_hide = page.hideEvent

        def custom_show(event):
            if original_show:
                original_show(event)
            if hasattr(self, "_cup_widget") and self._cup_widget:
                self._cup_widget.resume_effects()

        def custom_hide(event):
            if original_hide:
                original_hide(event)
            if hasattr(self, "_cup_widget") and self._cup_widget:
                self._cup_widget.pause_effects()

        page.showEvent = custom_show
        page.hideEvent = custom_hide

    def _update_support_page_theme(self, page, theme):
        """动态更新子卡片与描述文本颜色以匹配主题。"""
        for card in page.findChildren(DrinkCard):
            card.update_style(theme)

        # 联动更新咖啡杯呼吸灯的主题色彩
        if hasattr(page, "_cup_widget"):
            page._cup_widget.update_style(theme)

        desc_color = "#b0b0b5" if theme == "dark" else "#666666"
        title_color = "#ffffff" if theme == "dark" else "#1c1c1e"

        if hasattr(self, "_support_title_lbl"):
            self._support_title_lbl.setStyleSheet(
                f"font-size: 16px; font-weight: 400; color: {title_color}; background: transparent; border: none;"
            )
        if hasattr(self, "_support_desc_lbl"):
            self._support_desc_lbl.setStyleSheet(
                f"font-size: 11px; color: {desc_color}; line-height: 1.4; background: transparent; border: none;"
            )
        if hasattr(self, "_reaction_label"):
            self._reaction_label.setStyleSheet(
                f"font-size: 11px; color: {desc_color}; background: transparent; border: none;"
            )

        if hasattr(self, "_qr_container"):
            card_bg = "rgba(255, 255, 255, 0.05)" if theme == "dark" else "rgba(0, 0, 0, 0.03)"
            card_border = "rgba(255, 255, 255, 0.08)" if theme == "dark" else "rgba(0, 0, 0, 0.06)"
            self._qr_container.setStyleSheet(f"""
                QFrame#QRContainer {{
                    background-color: {card_bg};
                    border: 1px solid {card_border};
                    border-radius: 16px;
                }}
            """)

            # 动态应用精致的、独立于全局 Compact 按钮的高对比度微章按钮样式表
            if theme == "dark":
                btn_style_fullscreen = """
                    QPushButton {
                        font-size: 11px;
                        padding: 6px 12px;
                        background: rgba(255, 255, 255, 0.08);
                        border: 1px solid rgba(255, 255, 255, 0.12);
                        border-radius: 8px;
                        color: rgba(255, 255, 255, 0.85);
                        font-weight: 400;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.15);
                        border: 1px solid rgba(255, 255, 255, 0.25);
                        color: #ffffff;
                    }
                    QPushButton:pressed {
                        background: rgba(255, 255, 255, 0.05);
                    }
                """
                btn_style_close = """
                    QPushButton {
                        font-size: 11px;
                        padding: 6px 12px;
                        background: rgba(255, 82, 82, 0.1);
                        border: 1px solid rgba(255, 82, 82, 0.18);
                        border-radius: 8px;
                        color: #ff5252;
                        font-weight: 400;
                    }
                    QPushButton:hover {
                        background: rgba(255, 82, 82, 0.18);
                        border: 1px solid rgba(255, 82, 82, 0.35);
                        color: #ff7979;
                    }
                    QPushButton:pressed {
                        background: rgba(255, 82, 82, 0.05);
                    }
                """
            else:
                btn_style_fullscreen = """
                    QPushButton {
                        font-size: 11px;
                        padding: 6px 12px;
                        background: rgba(0, 0, 0, 0.04);
                        border: 1px solid rgba(0, 0, 0, 0.08);
                        border-radius: 8px;
                        color: rgba(28, 28, 30, 0.8);
                        font-weight: 400;
                    }
                    QPushButton:hover {
                        background: rgba(0, 0, 0, 0.08);
                        border: 1px solid rgba(0, 0, 0, 0.18);
                        color: #1c1c1e;
                    }
                    QPushButton:pressed {
                        background: rgba(0, 0, 0, 0.02);
                    }
                """
                btn_style_close = """
                    QPushButton {
                        font-size: 11px;
                        padding: 6px 12px;
                        background: rgba(211, 47, 47, 0.06);
                        border: 1px solid rgba(211, 47, 47, 0.15);
                        border-radius: 8px;
                        color: #d32f2f;
                        font-weight: 400;
                    }
                    QPushButton:hover {
                        background: rgba(211, 47, 47, 0.12);
                        border: 1px solid rgba(211, 47, 47, 0.3);
                        color: #c62828;
                    }
                    QPushButton:pressed {
                        background: rgba(211, 47, 47, 0.03);
                    }
                """
            self._view_fullscreen_btn.setStyleSheet(btn_style_fullscreen)
            self._close_qr_btn.setStyleSheet(btn_style_close)

    def _on_drink_clicked(self, name, price):
        """点击虚拟饮品：爆发式向全局屏幕发射无边界粒子，并平滑渐显二维码。"""
        # 1. 在被点击的饮品卡片物理中心，向屏幕爆发式喷涌出粒子
        sender_card = self.sender()
        if sender_card:
            card_center = QPoint(sender_card.width() // 2, sender_card.height() // 2)
            global_pos = sender_card.mapToGlobal(card_center)

            # 根据饮品品类，定制具有专属氛围色彩的微章粒子组合
            emoji_presets = {
                tr("纯净矿泉水"): ["💧", "🧊", "✨", "❤️", "👍"],
                tr("香浓拿铁"): ["☕", "💖", "✨", "🔥", "🎉"],
                tr("沁心绿茶"): ["🍵", "🍃", "✨", "💚", "🍀"],
                tr("芝芝莓莓"): ["🍹", "🍓", "🌸", "✨", "🌈"],
            }
            emojis = emoji_presets.get(name, ["❤️", "✨", "🎉"])
            for _ in range(4):
                FloatingEmoji(random.choice(emojis), global_pos, None, is_auto=False)

        # 2. 定制温馨的反应消息
        reactions = {
            tr("纯净矿泉水"): tr("「感谢这瓶清爽的矿泉水！开发者喝完活力满满，瞬间充满干劲～ 💧🧊」"),
            tr("香浓拿铁"): tr("「哇，是一杯拿铁咖啡！开发者大受鼓舞，今晚又要敲几百行代码了！🚀☕」"),
            tr("沁心绿茶"): tr("「静心品茗，灵感如潮。感谢您的支持与厚爱，愿您每天工作顺心！🍃🍵」"),
            tr("芝芝莓莓"): tr("「超棒的芝芝莓莓！开发者开心到起飞，甜度直接拉满啦！🍓✨🌈」"),
        }
        msg = reactions.get(name, tr("「感谢您的支持！赞助金额: ¥{price:.2f} ❤️」", price=price))
        self._reaction_label.setText(msg)

        # 3. 平滑渐显主页面里的折叠式二维码卡片
        if hasattr(self, "_qr_anim") and self._qr_anim:
            self._qr_anim.stop()
            self._qr_anim = None

        if self._qr_container.isHidden():
            self._qr_container.show()

        if not self._qr_container.graphicsEffect():
            self.qr_effect = QGraphicsOpacityEffect(self._qr_container)
            self._qr_container.setGraphicsEffect(self.qr_effect)
        else:
            self.qr_effect = self._qr_container.graphicsEffect()

        curr_opacity = self.qr_effect.opacity()

        anim = QtCompat.QPropertyAnimation(self.qr_effect, b"opacity")
        anim.setDuration(350)
        anim.setStartValue(curr_opacity)
        anim.setEndValue(1.0)

        def cleanup_effect():
            if self._qr_container.graphicsEffect():
                self._qr_container.setGraphicsEffect(None)

        anim.finished.connect(cleanup_effect)
        anim.start()
        self._qr_anim = anim

    def _close_qr(self):
        """渐隐折叠隐藏二维码，并在淡出前重新挂载 graphicsEffect 以保证渐变顺滑，带状态打断支持。"""
        if hasattr(self, "_qr_anim") and self._qr_anim:
            self._qr_anim.stop()
            self._qr_anim = None

        if not self._qr_container.isHidden():
            # 重新建立并挂载 graphicsEffect 用于关闭时的淡出淡化
            self.qr_effect = QGraphicsOpacityEffect(self._qr_container)
            self._qr_container.setGraphicsEffect(self.qr_effect)

            curr_opacity = self.qr_effect.opacity()

            anim = QtCompat.QPropertyAnimation(self.qr_effect, b"opacity")
            anim.setDuration(250)
            anim.setStartValue(curr_opacity)
            anim.setEndValue(0.0)
            anim.finished.connect(self._qr_container.hide)
            anim.start()
            self._qr_anim = anim
            self._reaction_label.setText(tr("👇 点击上方任一饮品，获取赞助二维码 (也可点击咖啡杯互动哦)"))

    def _on_support(self):
        """触发全新全屏玻璃拟态收款弹窗，并智能携带当前点击的饮料数据。"""
        try:
            # 尝试通过 reaction_label 的文本内容推测出选中的饮品数据，以提供场景联动的全屏无边界收款体验
            reaction_text = self._reaction_label.text()
            drink_name = None
            price = None
            color_hex = "#FF9500"

            drinks_data = [
                (tr("纯净矿泉水"), 2.00, "#34C759"),
                (tr("香浓拿铁"), 5.19, "#FF9500"),
                (tr("沁心绿茶"), 9.90, "#00C7BE"),
                (tr("芝芝莓莓"), 15.00, "#FF2D55"),
            ]
            for name, p, col in drinks_data:
                if name in reaction_text:
                    drink_name = name
                    price = p
                    color_hex = col
                    break

            from ui.config_window.support_dialog import SupportDialog

            dlg = SupportDialog(drink_name=drink_name, price=price, color_hex=color_hex, parent=self)
            dlg.exec_()
        except Exception as e:
            logger.exception("无法拉起全屏收款窗口")
            ThemedMessageBox.critical(self, tr("错误"), str(e))

    def _on_star_clicked(self):
        """前往开源社区点星。"""
        import webbrowser

        webbrowser.open("https://github.com/LEISHIQIANG/QuickLauncher")

    def _on_feedback_clicked(self):
        """前往问题反馈页。"""
        import webbrowser

        webbrowser.open("https://github.com/LEISHIQIANG/QuickLauncher/issues")
