"""Small self-contained widgets used by :mod:`ui.command_panel_window`.

Extracted in 1.6.3.4 so the main command-panel file can focus on the
:class:`CommandPanelWindow` orchestration logic.

* :class:`CommandHistoryDropButton` — a self-painted down-chevron used
  next to the command input.
* :class:`CommandStatusIndicator` — an animated radial-ripple dot:
  blue expanding concentric rings while running, green static dot on success.
"""

from __future__ import annotations

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
from ui.styles.design_tokens import StatusScale
from ui.utils.pixel_snap import make_cosmetic_pen
from ui.utils.ui_scale import sp, spf


class CommandHistoryDropButton(QPushButton):
    """Small self-painted down chevron used inside the command input."""

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setText("")
        self.setFlat(True)
        self.setAutoDefault(False)
        self.setDefault(False)

    def paintEvent(self, event):  # noqa: paint_perf
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)
            if not self.isEnabled():
                # 禁用态灰色 33% (alpha 85)
                color = QColor(128, 128, 128, 85)
            else:
                # 启用态灰色 65% (alpha 165)
                color = QColor(128, 128, 128, 165)
            # 使用 make_cosmetic_pen 保证下拉箭头线在 125%+ DPI 下不发胖
            pen = make_cosmetic_pen(color, 1)
            pen.setWidthF(1.6)
            painter.setPen(pen)
            cx = self.width() / 2 - spf(4.0)
            cy = self.height() / 2 + spf(1)
            half_w = spf(4.5)
            half_h = spf(3.0)
            painter.drawLine(int(cx - half_w), int(cy - half_h), int(cx), int(cy + half_h))
            painter.drawLine(int(cx), int(cy + half_h), int(cx + half_w), int(cy - half_h))
        finally:
            painter.end()


class CommandStatusIndicator(QWidget):
    """Animated status dot with expanding radial-ripple rings.

    * **running** — blue central dot surrounded by 3 staggered concentric
      rings that expand outward and fade, creating a radar-pulse effect.
    * **success** — green solid dot, ripple stopped.
    * **failure / warning / neutral** — coloured solid dot, no animation.

    Uses :attr:`StatusScale` tokens for consistent palette alignment with
    the rest of the UI (toasts, popups, result cards).
    """

    _RIPPLE_COUNT = 4
    _RIPPLE_STAGGER = 1.0 / _RIPPLE_COUNT
    _TIMER_MS = 30
    _STEP = 0.045

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kind = "neutral"
        self._theme = "light"
        self._phases: list[float] = []
        self._timer = QTimer(self)
        self._timer.setInterval(self._TIMER_MS)
        self._timer.timeout.connect(self._advance_ripple)
        self.setFixedSize(sp(30), sp(30))

    # -- public -----------------------------------------------------------

    def set_status(self, kind: str, theme: str) -> None:
        self._kind = str(kind or "neutral")
        self._theme = str(theme or "light")
        if self._kind == "running":
            self._phases = [i * self._RIPPLE_STAGGER for i in range(self._RIPPLE_COUNT)]
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def is_ripple_active(self) -> bool:
        return self._timer.isActive()  # type: ignore[no-any-return]

    # -- animation --------------------------------------------------------

    def _advance_ripple(self) -> None:
        for i in range(len(self._phases)):
            self._phases[i] += self._STEP
            if self._phases[i] >= 0.98:
                self._phases[i] = 0.0
        self.update()

    # -- painting ---------------------------------------------------------

    def paintEvent(self, event):  # noqa: paint_perf
        del event

        # Status colours drawn from the same design tokens as status
        # indicators, toasts and result cards.
        colors = {
            "running": QColor(StatusScale.info),  # 10, 132, 255
            "success": QColor(StatusScale.success),  # 48, 209, 88
            "failure": QColor(StatusScale.error),  # 255, 69, 58
            "warning": QColor(StatusScale.warning),  # 255, 159, 10
            "neutral": QColor(142, 142, 147),
        }
        color = QColor(colors.get(self._kind, colors["neutral"]))
        if self._theme == "light":
            color = color.darker(112)

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            max_radius = min(cx, cy) - spf(3.0)

            # ---- radial ripple rings (running only) ----------------------
            if self._kind == "running":
                for phase in self._phases:
                    if phase < 0.015:
                        continue  # skip invisible / just-reset rings
                    r = phase * max_radius
                    alpha = int((1.0 - phase) * 180)
                    ring = QColor(color)
                    ring.setAlpha(alpha)
                    painter.setPen(QPen(ring, spf(2.2)))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(QRectF(cx - r, cy - r, r * 2.0, r * 2.0))

            # ---- central dot (always visible) ----------------------------
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            core_radius = spf(3.8 if self._kind == "running" else 5.0)
            painter.drawEllipse(
                QRectF(
                    cx - core_radius,
                    cy - core_radius,
                    core_radius * 2.0,
                    core_radius * 2.0,
                )
            )
        finally:
            painter.end()


__all__ = ["CommandHistoryDropButton", "CommandStatusIndicator"]
