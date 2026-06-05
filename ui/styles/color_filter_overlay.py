"""Color filter overlay widget for window color grading (Win11 advanced mode).

Adapted from config_window_experiment/window_shell.py
"""

from __future__ import annotations

import logging

from qt_compat import (
    QColor,
    QPainter,
    Qt,
    QtCompat,
    QWidget,
)

logger = logging.getLogger(__name__)


class ColorFilterOverlay(QWidget):
    """Full-window transparent overlay that applies color grading effects.

    Renders four filter effects via paintEvent:
    1. Black point (黑场) - shadow lift/darken
    2. White point (白场) - highlight boost/darken
    3. Mid gamma (中间调) - midtone adjustment
    4. Temperature (色温) - warm/cool color shift

    All parameters range from 0 to 100, with 50 = neutral (no effect).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._black_point = 50
        self._white_point = 50
        self._mid_gamma = 50
        self._temperature = 50

    def set_params(self, black_point: int, white_point: int, mid_gamma: int, temperature: int):
        """Set all four filter parameters (0-100, 50=neutral)."""
        self._black_point = max(0, min(100, int(black_point)))
        self._white_point = max(0, min(100, int(white_point)))
        self._mid_gamma = max(0, min(100, int(mid_gamma)))
        self._temperature = max(0, min(100, int(temperature)))
        self.update()

    @property
    def is_neutral(self) -> bool:
        """Return True if all parameters are at neutral (50)."""
        return (
            self._black_point == 50
            and self._white_point == 50
            and self._mid_gamma == 50
            and self._temperature == 50
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)

        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        # --- Black point (黑场) ---
        bp = self._black_point - 50  # -50 to +50
        if bp > 0:
            # Darken shadows: black overlay with alpha proportional to bp
            alpha = int(255 * bp / 50 * 0.35)
            if alpha > 0:
                painter.fillRect(0, 0, w, h, QColor(0, 0, 0, alpha))
        elif bp < 0:
            # Lift shadows: white overlay
            alpha = int(255 * abs(bp) / 50 * 0.18)
            if alpha > 0:
                painter.fillRect(0, 0, w, h, QColor(255, 255, 255, alpha))

        # --- White point (白场) ---
        wp = self._white_point - 50
        if wp > 0:
            alpha = int(255 * wp / 50 * 0.22)
            if alpha > 0:
                painter.fillRect(0, 0, w, h, QColor(255, 255, 255, alpha))
        elif wp < 0:
            alpha = int(255 * abs(wp) / 50 * 0.20)
            if alpha > 0:
                painter.fillRect(0, 0, w, h, QColor(0, 0, 0, alpha))

        # --- Mid gamma (中间调) ---
        mg = self._mid_gamma - 50
        if mg < 0:
            alpha = int(255 * abs(mg) / 50 * 0.25)
            if alpha > 0:
                painter.fillRect(0, 0, w, h, QColor(0, 0, 0, alpha))
        elif mg > 0:
            alpha = int(255 * mg / 50 * 0.12)
            if alpha > 0:
                painter.fillRect(0, 0, w, h, QColor(255, 255, 255, alpha))

        # --- Temperature (色温) ---
        tp = self._temperature - 50
        if tp < 0:
            # Cool: blue tint
            alpha = int(255 * abs(tp) / 50 * 0.12)
            if alpha > 0:
                painter.fillRect(0, 0, w, h, QColor(40, 80, 200, alpha))
        elif tp > 0:
            # Warm: orange tint
            alpha = int(255 * tp / 50 * 0.12)
            if alpha > 0:
                painter.fillRect(0, 0, w, h, QColor(220, 130, 40, alpha))
