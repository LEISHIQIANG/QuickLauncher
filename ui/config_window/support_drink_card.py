"""DrinkCard — extracted from settings_support_page."""

from __future__ import annotations

from qt_compat import (
    QBrush,
    QColor,
    QFrame,
    QLinearGradient,
    QPainter,
    QPoint,
    QPointF,
    QRadialGradient,
    QRect,
    QRectF,
    QSize,
    QSizePolicy,
    QtCompat,
    pyqtProperty,
    pyqtSignal,
)
from ui.utils.interruptible_animation import stop_animation, stop_named_animations
from ui.utils.pixel_snap import make_cosmetic_pen
from ui.utils.ui_scale import sp

_DRINK_CARD_MIN_WIDTH = 72
_DRINK_CARD_MAX_WIDTH = 100
_DRINK_CARD_HEIGHT = 114


class DrinkCard(QFrame):
    """虚拟饮品卡片，带极简克制的高级聚光灯跟随光效与微弱对角扫光，描边保持精致的单像素宽。"""

    clicked = pyqtSignal(str, float)

    def __init__(self, icon_key, name, price, color_hex, theme="dark", parent=None):
        super().__init__(parent)
        self.icon_key = icon_key
        self.name = name
        self.price = price
        self.color_hex = color_hex
        self.theme = theme
        self.accent_color = QColor(color_hex)

        self.setCursor(QtCompat.PointingHandCursor)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumSize(sp(_DRINK_CARD_MIN_WIDTH), sp(_DRINK_CARD_HEIGHT))
        self.setMaximumSize(sp(_DRINK_CARD_MAX_WIDTH), sp(_DRINK_CARD_HEIGHT))
        self.resize(self.sizeHint())

        self._hover_progress = 0.0
        self._scale = 1.0
        self._sweep_progress = 0.0
        self._mouse_pos = QPoint(self.width() // 2, self.height() // 2)

        self._hover_anim = None
        self._click_anim = None
        self._sweep_anim = None
        self._cached_bg_path = None

    def sizeHint(self):
        return QSize(sp(_DRINK_CARD_MAX_WIDTH), sp(_DRINK_CARD_HEIGHT))

    def minimumSizeHint(self):
        return QSize(sp(_DRINK_CARD_MIN_WIDTH), sp(_DRINK_CARD_HEIGHT))

    def stop_animations(self):
        stop_animation(getattr(self, "_hover_anim", None), owner="DrinkCard.stop_animations")
        stop_animation(getattr(self, "_click_anim", None), owner="DrinkCard.stop_animations")
        stop_animation(getattr(self, "_sweep_anim", None), owner="DrinkCard.stop_animations")

    def _get_hover_progress(self):
        return self._hover_progress

    def _set_hover_progress(self, val):
        self._hover_progress = val
        self.update()

    hover_progress = pyqtProperty(float, fget=_get_hover_progress, fset=_set_hover_progress)

    def _get_scale(self):
        return self._scale

    def _set_scale(self, val):
        self._scale = val
        self.update()

    scale = pyqtProperty(float, fget=_get_scale, fset=_set_scale)

    def _get_sweep_progress(self):
        return self._sweep_progress

    def _set_sweep_progress(self, val):
        self._sweep_progress = val
        self.update()

    sweep_progress = pyqtProperty(float, fget=_get_sweep_progress, fset=_set_sweep_progress)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        self._mouse_pos = pos
        self.update()

    def enterEvent(self, event):
        stop_animation(self._hover_anim, owner="DrinkCard.hover")
        anim = QtCompat.QPropertyAnimation(self, b"hover_progress")
        anim.setDuration(220)
        anim.setStartValue(self._hover_progress)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QtCompat.OutCubic)
        anim.start()
        self._hover_anim = anim
        super().enterEvent(event)

    def leaveEvent(self, event):
        stop_animation(self._hover_anim, owner="DrinkCard.hover")
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
            stop_named_animations(self, "_click_anim", "_sweep_anim")
            anim = QtCompat.QPropertyAnimation(self, b"scale")
            anim.setDuration(200)
            anim.setStartValue(1.0)
            anim.setKeyValueAt(0.5, 0.9)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QtCompat.OutBack)
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

    def _icon_rect(self, card_rect):
        return QRectF(sp(24), sp(8), card_rect.width() - sp(44), sp(44))

    def _paint_drink_icon(self, painter, icon_rect):
        """绘制饮品图标 (使用 QPainter 绘制矢量图形)"""
        r = icon_rect
        cx = r.center().x()
        cy = r.center().y()
        w = r.width()
        h = r.height()
        accent = self.accent_color
        pen_width = max(1.0, sp(1.5))

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # 绘制饮品杯 (杯身)
        cup_color = QColor(accent)
        cup_color.setAlpha(180)
        painter.setPen(make_cosmetic_pen(cup_color, pen_width, 1))
        painter.setBrush(QBrush(QColor(accent.red(), accent.green(), accent.blue(), 30)))
        body = QRectF(cx - w * 0.18, cy - h * 0.15, w * 0.36, h * 0.50)
        painter.drawRoundedRect(body, sp(4), sp(4))

        # 杯口
        rim = QRectF(cx - w * 0.22, cy - h * 0.20, w * 0.44, h * 0.10)
        painter.setBrush(QBrush(accent))
        painter.setPen(QtCompat.NoPen)
        painter.drawRoundedRect(rim, sp(2), sp(2))

        # 饮料液面
        liquid_h = h * 0.30
        liquid_top = body.top() + body.height() - liquid_h
        if liquid_top < body.top():
            liquid_top = body.top()
        liquid = QRectF(cx - w * 0.16, liquid_top, w * 0.32, liquid_h)
        liquid_color = QColor(accent)
        liquid_color.setAlpha(200)
        painter.setBrush(QBrush(liquid_color))
        painter.setPen(QtCompat.NoPen)
        painter.drawRoundedRect(liquid, sp(2), sp(2))

        # 吸管
        straw_color = QColor(accent)
        straw_color.setAlpha(160)
        painter.setPen(make_cosmetic_pen(straw_color, max(1.0, sp(1.2, 1))))
        painter.drawLine(QPointF(cx + w * 0.12, body.top() + sp(2)), QPointF(cx + w * 0.12, body.top() - h * 0.18))
        painter.drawLine(QPointF(cx + w * 0.12, body.top() - h * 0.18), QPointF(cx + w * 0.22, body.top() - h * 0.12))

        # 装饰小圆点
        dot_color = QColor(accent)
        dot_color.setAlpha(100)
        painter.setBrush(QBrush(dot_color))
        painter.setPen(QtCompat.NoPen)
        painter.drawEllipse(QRectF(cx - w * 0.08, body.top() + h * 0.12, w * 0.06, h * 0.06))
        painter.drawEllipse(QRectF(cx + w * 0.02, body.top() + h * 0.25, w * 0.06, h * 0.06))

        # 小花装饰
        flower_color = QColor("#FF5C8A")
        painter.setBrush(QBrush(flower_color))
        painter.setPen(QtCompat.NoPen)
        painter.drawEllipse(QRectF(cx - w * 0.09, icon_rect.top() + h * 0.0, w * 0.18, h * 0.18))
        painter.setPen(make_cosmetic_pen(QColor("#FFFFFF", 170), pen_width, 1))
        painter.drawLine(QPointF(cx - w * 0.13, cy - h * 0.02), QPointF(cx + w * 0.09, cy - h * 0.02))

        painter.restore()

    def paintEvent(self, event):
        # noqa: paint_perf - hot-path paintEvent with cached state
        from qt_compat import QPainterPath as _QPainterPath

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect()
        cx = rect.center().x()
        cy = rect.center().y()
        painter.translate(cx, cy)
        painter.scale(self._scale, self._scale)
        painter.translate(-cx, -cy)

        from ui.styles.design_tokens import StatusScale as _status

        base_bg = _status(f"support_card_bg_{self.theme}")
        base_border = _status(f"support_card_border_{self.theme}")
        text_color = _status(f"support_text_primary_{self.theme}")
        sub_color = _status(f"support_text_secondary_{self.theme}")
        hover_bg = _status(f"support_card_hover_{self.theme}")

        p = self._hover_progress

        r = int(base_bg.red() * (1 - p) + hover_bg.red() * p)
        g = int(base_bg.green() * (1 - p) + hover_bg.green() * p)
        b = int(base_bg.blue() * (1 - p) + hover_bg.blue() * p)
        a = int(base_bg.alpha() * (1 - p) + hover_bg.alpha() * p)
        bg_color = QColor(r, g, b, a)

        max_border_alpha = 110 if self.theme == "dark" else 75
        br = int(base_border.red() * (1 - p) + self.accent_color.red() * p)
        bg_val = int(base_border.green() * (1 - p) + self.accent_color.green() * p)
        bb = int(base_border.blue() * (1 - p) + self.accent_color.blue() * p)
        ba = int(base_border.alpha() * (1 - p) + max_border_alpha * p)
        border_color = QColor(br, bg_val, bb, ba)

        if self._cached_bg_path is None:
            path = _QPainterPath()
            path.addRoundedRect(QRectF(1, 1, rect.width() - 2, rect.height() - 2), 14, 14)
            self._cached_bg_path = path
        else:
            path = self._cached_bg_path
        painter.fillPath(path, QBrush(bg_color))

        if p > 0.0 and self._mouse_pos:
            spotlight_rad = 70.0
            spotlight = QRadialGradient(QPointF(self._mouse_pos), spotlight_rad)
            glow_intensity = int(32 * p) if self.theme == "dark" else int(20 * p)
            g_color = QColor(self.accent_color)
            g_color.setAlpha(glow_intensity)
            spotlight.setColorAt(0.0, g_color)
            spotlight.setColorAt(1.0, QColor(QtCompat.transparent))
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(spotlight))
            painter.drawPath(path)

        painter.setPen(make_cosmetic_pen(border_color))
        painter.drawPath(path)

        if 0.0 < self._sweep_progress < 1.0:
            w = rect.width()
            h = rect.height()
            x = -w + self._sweep_progress * (3.5 * w)
            shimmer = QLinearGradient(x, 0, x + 40, h)
            fade_curve = 1.0 - abs(self._sweep_progress - 0.5) * 2.0
            shimmer_alpha = int(40 * max(0.0, fade_curve))
            shimmer.setColorAt(0.0, QColor(QtCompat.transparent))
            from ui.styles.design_tokens import TextScale

            _sc = QColor(TextScale.primary_dark)
            _sc.setAlpha(shimmer_alpha)
            shimmer.setColorAt(0.5, _sc)
            shimmer.setColorAt(1.0, QColor(QtCompat.transparent))
            painter.save()
            painter.setClipPath(path)
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(shimmer))
            painter.drawPath(path)
            painter.restore()

        self._paint_drink_icon(painter, self._icon_rect(rect))

        name_font = painter.font()
        name_font.setFamily("Microsoft YaHei UI")
        name_font.setPixelSize(sp(12))
        name_font.setBold(False)
        painter.setFont(name_font)
        painter.setPen(make_cosmetic_pen(text_color, 1))
        painter.drawText(QRect(sp(5), sp(60), rect.width() - sp(8), sp(20)), QtCompat.AlignCenter, self.name)

        price_font = painter.font()
        price_font.setFamily("Microsoft YaHei UI")
        price_font.setPixelSize(sp(12))
        price_font.setBold(False)
        painter.setFont(price_font)
        painter.setPen(make_cosmetic_pen(sub_color, 1))
        painter.drawText(QRect(sp(5), sp(80), rect.width() - sp(8), sp(20)), QtCompat.AlignCenter, f"¥{self.price:.2f}")

        painter.end()

    def resizeEvent(self, event):
        self._cached_bg_path = None
        super().resizeEvent(event)


__all__ = ["DrinkCard"]
