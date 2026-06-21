"""Motion tokens for QuickLauncher.

Centralised animation timing and easing constants. New code should pull
durations from :mod:`ui.styles.motion` (or :mod:`ui.styles.design_tokens`)
instead of inlining integer millisecond values, so that accessibility
preferences (``Settings.motion_scale``) and the global theme switch can
adjust every animation consistently.

Two layers are exposed:

* :class:`Duration` – integer milliseconds.
* :class:`Easing` – string cubic-bezier curves accepted by Qt's
  ``QPropertyAnimation.setEasingCurve(QEasingCurve.BezierSpline)``.

The actual ``QPropertyAnimation`` / ``QSequentialAnimationGroup`` glue
lives in :mod:`ui.utils.animations`, which delegates the stop/query
logic to the existing :mod:`ui.utils.interruptible_animation` helpers.
"""

from __future__ import annotations

from qt_compat import QEasingCurve, QPointF

__all__ = [
    "Duration",
    "Easing",
    "make_easing_curve",
]


class Duration:
    """Animation duration tokens (milliseconds).

    Names follow the Material 3 motion vocabulary where possible; the
    numeric values mirror the §3.3 spec in ``UI_OPTIMIZATION_PLAN.md``.
    """

    INSTANT = 50
    FAST = 120
    NORMAL = 200
    SLOW = 320
    X_SLOW = 480

    # Specific UI scenarios – chosen so that the user can perceive the
    # change but the animation finishes within one perception window.
    FADE_IN = 200
    FADE_OUT = 160
    SLIDE_IN = 240
    SCALE_IN = 220
    RIPPLE = 280
    TOOLTIP = 120
    THEME_SWITCH = 200
    DIALOG_OPEN = 280
    DIALOG_CLOSE = 200
    FOCUS_RING = 80
    PRESS_FEEDBACK = 80
    HOVER_TRANSITION = 120

    @staticmethod
    def apply_scale(value: int, scale: float | None = None) -> int:
        """Apply the user ``motion_scale`` preference (0.5–2.0)."""

        if scale is None or scale == 1.0:
            return int(value)
        try:
            return max(0, min(1000, int(round(value * float(scale)))))
        except (TypeError, ValueError):
            return int(value)


class Easing:
    """Cubic-bezier easing curves as CSS strings + parsed coordinates.

    The constants in this class are also the *canonical* source of truth
    referenced by :mod:`ui.styles.design_tokens` (``EasingScale``). Keep
    both copies in sync if you tweak the values.
    """

    STANDARD = "cubic-bezier(0.4, 0.0, 0.2, 1.0)"
    EMPHASIZED = "cubic-bezier(0.2, 0.0, 0.0, 1.0)"
    ACCELERATE = "cubic-bezier(0.4, 0.0, 1.0, 1.0)"
    DECELERATE = "cubic-bezier(0.0, 0.0, 0.2, 1.0)"
    LINEAR = "linear"

    # Internal coordinate table used by ``make_easing_curve``.
    _COORDS = {
        STANDARD: (0.4, 0.0, 0.2, 1.0),
        EMPHASIZED: (0.2, 0.0, 0.0, 1.0),
        ACCELERATE: (0.4, 0.0, 1.0, 1.0),
        DECELERATE: (0.0, 0.0, 0.2, 1.0),
    }

    @staticmethod
    def coordinate(easing_str: str) -> tuple[float, float, float, float]:
        return Easing._COORDS.get(easing_str, (0.4, 0.0, 0.2, 1.0))


def make_easing_curve(name: str = Easing.STANDARD) -> QEasingCurve:
    """Build a :class:`QEasingCurve` for the given easing name.

    The result is a ``BezierSpline`` with two control points. ``name`` may
    be any of the constants in :class:`Easing` or a raw cubic-bezier CSS
    string – unknown values fall back to ``Easing.STANDARD``.
    """

    c1x, c1y, c2x, c2y = Easing.coordinate(name)
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(c1x, c1y), QPointF(c2x, c2y), QPointF(1.0, 1.0))
    return curve
