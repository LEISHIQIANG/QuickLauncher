"""Small self-contained widgets used by :mod:`ui.command_panel_window`.

Extracted in 1.6.3.4 so the main command-panel file can focus on the
:class:`CommandPanelWindow` orchestration logic.

* :class:`CommandHistoryDropButton` — a self-painted down-chevron used
  next to the command input.
* :class:`CommandStatusIndicator` — a tiny dot with a breathing ripple
  while a command is running.
"""

from __future__ import annotations

import math

from qt_compat import (
    QColor,
    QPainter,
    QPen,
    QPushButton,
    QRectF,
    Qt,
    QtCompat,
    QTimer,
    QWidget,
)
from ui.utils.ui_scale import sp, spf


class CommandHistoryDropButton(QPushButton):
    """Small self-painted down chevron used inside the command input."""

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setText("")
        self.setFlat(True)
        self.setAutoDefault(False)
        self.setDefault(False)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)
            if not self.isEnabled():
                color = QColor(128, 128, 128, 85)
            else:
                color = QColor(128, 128, 128, 165)
            pen = QPen(color, 1.6)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            cx = self.width() / 2 - spf(2)
            cy = self.height() / 2 + spf(1)
            half_w = spf(4.5)
            half_h = spf(3.0)
            painter.drawLine(int(cx - half_w), int(cy - half_h), int(cx), int(cy + half_h))
            painter.drawLine(int(cx), int(cy + half_h), int(cx + half_w), int(cy - half_h))
        finally:
            painter.end()


class CommandStatusIndicator(QWidget):
    """Small status dot with a breathing ripple while a command is running."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kind = "neutral"
        self._theme = "light"
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._advance_ripple)
        self.setFixedSize(sp(18), sp(18))

    def set_status(self, kind: str, theme: str):
        self._kind = str(kind or "neutral")
        self._theme = str(theme or "light")
        self._phase = 0.0
        if self._kind == "running":
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def is_ripple_active(self) -> bool:
        return self._timer.isActive()  # type: ignore[no-any-return]

    def _advance_ripple(self):
        self._phase = (self._phase + 0.18) % (math.pi * 2)
        self.update()

    def paintEvent(self, event):
        del event
        colors = {
            "running": QColor(10, 132, 255),
            "success": QColor(48, 209, 88),
            "failure": QColor(255, 69, 58),
            "warning": QColor(255, 159, 10),
            "neutral": QColor(142, 142, 147),
        }
        color = QColor(colors.get(self._kind, colors["neutral"]))
        if self._theme == "light":
            color = color.darker(112)

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            center_x = self.width() / 2
            center_y = self.height() / 2
            if self._kind == "running":
                wave = (math.sin(self._phase) + 1.0) / 2.0
                radius = spf(4.3) + wave * spf(3.0)
                ring = QColor(color)
                ring.setAlpha(int(105 - wave * 62))
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(ring, spf(1.2)))
                painter.drawEllipse(QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2))

            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            core_radius = spf(2.8 if self._kind == "running" else 3.5)
            painter.drawEllipse(
                QRectF(
                    center_x - core_radius,
                    center_y - core_radius,
                    core_radius * 2,
                    core_radius * 2,
                )
            )
        finally:
            painter.end()


__all__ = ["CommandHistoryDropButton", "CommandStatusIndicator"]
