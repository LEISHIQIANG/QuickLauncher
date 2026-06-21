"""Reusable smooth wheel scrolling for Qt scroll areas."""

import time

from qt_compat import (
    QColor,
    QLinearGradient,
    QPainter,
    QRectF,
    QScrollArea,
    Qt,
    QtCompat,
    QTimer,
    QWidget,
    pyqtProperty,
)
from ui.utils.ui_scale import sp


def _clamp(value, low, high):
    return max(low, min(high, value))


class _EdgeFeedbackOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._top_opacity = 0.0
        self._bottom_opacity = 0.0
        self._top_anim = None
        self._bottom_anim = None
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

    def _get_top_opacity(self):
        return self._top_opacity

    def _set_top_opacity(self, value):
        self._top_opacity = float(value)
        self.update()

    topOpacity = pyqtProperty(float, _get_top_opacity, _set_top_opacity)

    def _get_bottom_opacity(self):
        return self._bottom_opacity

    def _set_bottom_opacity(self, value):
        self._bottom_opacity = float(value)
        self.update()

    bottomOpacity = pyqtProperty(float, _get_bottom_opacity, _set_bottom_opacity)

    def flash(self, edge, opacity):
        prop = b"topOpacity" if edge == "top" else b"bottomOpacity"
        anim_attr = "_top_anim" if edge == "top" else "_bottom_anim"
        old_anim = getattr(self, anim_attr, None)
        if old_anim:
            old_anim.stop()

        current = self._top_opacity if edge == "top" else self._bottom_opacity
        start = max(float(current), float(opacity))
        anim = QtCompat.QPropertyAnimation(self, prop)
        anim.setDuration(420)
        anim.setStartValue(start)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QtCompat.OutCubic)
        setattr(self, anim_attr, anim)
        anim.start()

    def paintEvent(self, event):  # noqa: paint_perf
        painter = QPainter(self)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            height = max(sp(32), min(sp(72), int(self.height() * 0.14)))
            width = self.width()

            if self._top_opacity > 0.001:
                gradient = QLinearGradient(0, 0, 0, height)
                color = QColor(255, 255, 255, int(44 * self._top_opacity))
                shadow = QColor(0, 0, 0, int(22 * self._top_opacity))
                gradient.setColorAt(0.0, color)
                gradient.setColorAt(0.24, shadow)
                gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.fillRect(QRectF(0, 0, width, height), gradient)

            if self._bottom_opacity > 0.001:
                gradient = QLinearGradient(0, self.height(), 0, self.height() - height)
                color = QColor(255, 255, 255, int(44 * self._bottom_opacity))
                shadow = QColor(0, 0, 0, int(22 * self._bottom_opacity))
                gradient.setColorAt(0.0, color)
                gradient.setColorAt(0.24, shadow)
                gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.fillRect(QRectF(0, self.height() - height, width, height), gradient)
        finally:
            painter.end()


class SmoothScrollArea(QScrollArea):
    """QScrollArea with animated wheel scrolling and edge feedback."""

    def __init__(self, parent=None, scroll_step=126, duration=260):
        super().__init__(parent)
        self._scroll_step_base = int(scroll_step)
        self._scroll_step = sp(self._scroll_step_base)
        self._duration = int(duration)
        self._scroll_pos = 0.0
        self._velocity = 0.0
        self._last_tick = 0.0

        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(16)
        self._scroll_timer.setTimerType(Qt.PreciseTimer)
        self._scroll_timer.timeout.connect(self._tick_scroll)

        self._edge_overlay = _EdgeFeedbackOverlay(self.viewport())
        self._edge_overlay.hide()

    def setWidget(self, widget):
        super().setWidget(widget)
        self._scroll_pos = float(self.verticalScrollBar().value())
        self._velocity = 0.0

    def setScrollStep(self, scroll_step):
        self._scroll_step_base = int(scroll_step)
        self._scroll_step = sp(self._scroll_step_base)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._edge_overlay.setGeometry(self.viewport().rect())
        self._edge_overlay.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self._edge_overlay.setGeometry(self.viewport().rect())
        self._edge_overlay.raise_()

    def wheelEvent(self, event):
        delta = self._wheel_delta(event)
        if abs(delta) < 0.01:
            event.ignore()
            return

        bar = self.verticalScrollBar()
        minimum = bar.minimum()
        maximum = bar.maximum()
        current = bar.value()
        if not self._scroll_timer.isActive():
            self._scroll_pos = float(current)

        movement = -delta
        next_pos = self._scroll_pos + movement
        target = _clamp(next_pos, minimum, maximum)

        if minimum < maximum and (target != current or abs(self._velocity) > 0.01):
            self._velocity += movement * 0.18
            max_velocity = max(48.0, float(sp(64)))
            self._velocity = _clamp(self._velocity, -max_velocity, max_velocity)
            if not self._scroll_timer.isActive():
                self._last_tick = time.monotonic()
                self._scroll_timer.start()

        overshoot = next_pos - target
        if abs(overshoot) > 0.01 or minimum == maximum:
            edge = "top" if delta > 0 else "bottom"
            strength = _clamp(abs(overshoot) / max(80.0, self._scroll_step), 0.35, 1.0)
            self._flash_edge(edge, strength)

        event.accept()

    def _wheel_delta(self, event):
        pixel_delta = event.pixelDelta()
        if not pixel_delta.isNull():
            return pixel_delta.y()

        angle_delta = event.angleDelta().y()
        if angle_delta:
            return (angle_delta / 120.0) * self._scroll_step
        return 0.0

    def _tick_scroll(self):
        bar = self.verticalScrollBar()
        minimum = bar.minimum()
        maximum = bar.maximum()
        now = time.monotonic()
        elapsed = max(0.004, min(0.04, now - self._last_tick)) if self._last_tick else 1 / 60
        self._last_tick = now
        frame = elapsed / (1 / 60)

        if minimum >= maximum:
            self._velocity = 0.0
            self._scroll_timer.stop()
            return

        self._scroll_pos += self._velocity * frame

        if self._scroll_pos < minimum:
            self._scroll_pos = float(minimum)
            self._velocity = 0.0
            self._flash_edge("top", 0.28)
        elif self._scroll_pos > maximum:
            self._scroll_pos = float(maximum)
            self._velocity = 0.0
            self._flash_edge("bottom", 0.28)

        rounded = int(round(self._scroll_pos))
        if rounded != bar.value():
            bar.setValue(rounded)

        self._velocity *= 0.885**frame
        if abs(self._velocity) < 0.18:
            self._velocity = 0.0
            self._scroll_pos = float(bar.value())
            self._scroll_timer.stop()

    def _flash_edge(self, edge, strength):
        self._edge_overlay.show()
        self._edge_overlay.raise_()
        self._edge_overlay.flash(edge, 0.14 * strength)
