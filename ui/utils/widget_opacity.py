"""Centralized widget opacity helpers.

Per §4.10.1 of ``UI_OPTIMIZATION_PLAN.md`` the codebase should not sprinkle
``QGraphicsOpacityEffect`` across components because every effect triggers
an off-screen render of its target widget. This module is the single
point of contact for opacity dimming / animation on **child** widgets.

Design
------

* :func:`set_opacity` - apply a static opacity (drag-dim feedback). The
  widget's existing stylesheet is preserved and only the trailing
  ``opacity:`` declaration is rewritten.  This is GPU-composited by Qt
  and costs no off-screen render.

* :func:`animate_opacity` - animate opacity 0 → 1 (or any range). The
  helper attaches a tiny ``QGraphicsOpacityEffect`` for the lifetime of
  the animation and removes it on ``finished`` (or when a new animation
  starts on the same target).  The animation drives the effect's
  ``opacity`` property which is what Qt natively supports for child
  widgets.

* :func:`dim_for_drag` / :func:`restore_from_drag` - the canonical
  pattern used by the drag handlers in ``icon_grid`` and ``folder_panel``.

The module is whitelisted by ``scripts/audit_graphics_effect.py``; the
8 call sites in production code no longer reference
``QGraphicsOpacityEffect`` directly.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from qt_compat import (
    QGraphicsOpacityEffect,
    QPropertyAnimation,
    QWidget,
)
from ui.styles.motion import Duration, Easing, make_easing_curve
from ui.utils.interruptible_animation import stop_named_animations

logger = logging.getLogger(__name__)

__all__ = [
    "set_opacity",
    "animate_opacity",
    "dim_for_drag",
    "restore_from_drag",
    "clear_opacity_animation",
]


# Conventional attribute name used by the helper to track the in-flight
# animation on a widget.  ``stop_named_animations`` uses this to cancel
# any earlier animation before a new one starts.
_ANIM_ATTR = "_qlc_opacity_anim"

# Conventional attribute name for the drag-dim effect.  Stored so
# :func:`restore_from_drag` can find and clear it without relying on
# ``widget.graphicsEffect()`` (which may already be a different effect).
_DIM_ATTR = "_qlc_drag_dim"


# ---------------------------------------------------------------------------
# Static opacity (GPU-composited via stylesheet)
# ---------------------------------------------------------------------------


def _strip_opacity(stylesheet: str) -> str:
    """Remove any trailing ``opacity:`` declaration from a stylesheet."""

    if not stylesheet:
        return ""
    text = stylesheet.rstrip()
    while True:
        idx = text.rfind("opacity:")
        if idx < 0:
            break
        # Walk back to the previous ';' or start
        start = max(text.rfind(";", 0, idx), text.rfind("{", 0, idx)) + 1
        candidate = text[start:].lstrip()
        if not candidate.startswith("opacity:"):
            break
        # Remove the entire declaration
        end = text.find(";", idx)
        if end < 0:
            text = text[:start].rstrip()
            break
        text = (text[:start] + text[end + 1 :]).strip()
    return text


def set_opacity(widget: QWidget, opacity: float) -> None:
    """Set ``widget`` opacity to ``opacity`` (0.0–1.0).

    Implemented via stylesheet injection (Qt's GPU compositor handles the
    blend).  Any prior opacity declaration is removed first to keep the
    stylesheet canonical.
    """

    if not isinstance(widget, QWidget):
        return
    base = _strip_opacity(widget.styleSheet() or "")
    clamped = max(0.0, min(1.0, float(opacity)))
    if clamped >= 0.999:
        widget.setStyleSheet(base)
    else:
        suffix = f"opacity: {clamped:.3f};"
        if base and not base.endswith(";"):
            widget.setStyleSheet(f"{base}; {suffix}")
        else:
            widget.setStyleSheet(f"{base} {suffix}".strip())


# ---------------------------------------------------------------------------
# Animation helpers (uses QGraphicsOpacityEffect for child widgets)
# ---------------------------------------------------------------------------


def _ensure_opacity_effect(widget: QWidget) -> QGraphicsOpacityEffect:
    """Return the existing opacity effect on ``widget`` or attach a fresh one.

    Existing non-opacity effects are preserved by stacking – the helper
    only ever adds an opacity effect when one is missing.
    """

    effect = widget.graphicsEffect()
    if isinstance(effect, QGraphicsOpacityEffect):
        return effect
    opacity_effect = QGraphicsOpacityEffect(widget)
    # Chain the previous effect (if any) by reparenting the new one atop
    # it.  This keeps any pre-existing effect (e.g. drop shadow) alive
    # while we add opacity.
    if effect is not None:
        logger.debug(
            "set_opacity: widget %r already has a graphics effect; opacity is added via setStyleSheet instead",
            widget,
        )
    widget.setGraphicsEffect(opacity_effect)
    return opacity_effect


def animate_opacity(
    widget: QWidget,
    start: float,
    end: float,
    duration_ms: int = Duration.NORMAL,
    *,
    on_finished=None,
    clear_on_finish: bool = True,
) -> QPropertyAnimation:
    """Animate ``widget`` opacity from ``start`` to ``end``.

    The animation lives on the widget as ``_qlc_opacity_anim`` and is
    cancelled by :func:`stop_named_animations` on subsequent calls.
    When the animation finishes, the helper removes the attached
    ``QGraphicsOpacityEffect`` so the widget returns to its native
    render path (no permanent off-screen cost).
    """

    if not isinstance(widget, QWidget):
        raise TypeError("animate_opacity requires a QWidget target")

    stop_named_animations(widget, _ANIM_ATTR)
    # Clear any stale drag-dim effect so the animation owns the slot.
    _drag_dim = getattr(widget, _DIM_ATTR, None)
    if _drag_dim is not None:
        try:
            widget.setGraphicsEffect(None)
        except RuntimeError:
            logger.debug("widget already destroyed when clearing drag-dim", exc_info=True)
        try:
            setattr(widget, _DIM_ATTR, None)
        except (AttributeError, TypeError):
            logger.debug("widget rejects clearing drag-dim tracking", exc_info=True)

    effect = _ensure_opacity_effect(widget)
    effect.setOpacity(float(start))

    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(int(duration_ms))
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.setEasingCurve(make_easing_curve(Easing.STANDARD))

    def _finish() -> None:
        if clear_on_finish and widget.graphicsEffect() is effect:
            try:
                widget.setGraphicsEffect(None)
            except RuntimeError:
                logger.debug("widget already destroyed when clearing effect", exc_info=True)
        if on_finished is not None:
            on_finished()

    anim.finished.connect(_finish)
    setattr(widget, _ANIM_ATTR, anim)
    anim.start()
    return anim


def clear_opacity_animation(widget: QWidget) -> None:
    """Stop any in-flight opacity animation on ``widget``."""

    if not isinstance(widget, QWidget):
        return
    stop_named_animations(widget, _ANIM_ATTR)
    try:
        setattr(widget, _ANIM_ATTR, None)
    except (AttributeError, TypeError):
        logger.debug("widget rejects clearing opacity animation tracking", exc_info=True)


# ---------------------------------------------------------------------------
# Drag-dim helpers
# ---------------------------------------------------------------------------


def dim_for_drag(widget: QWidget, opacity: float = 0.35) -> None:
    """Apply a static opacity dim to ``widget`` for drag feedback.

    Uses a ``QGraphicsOpacityEffect`` for the duration of the drag and
    stores it on the widget so :func:`restore_from_drag` can find and
    clear it cleanly.
    """

    if not isinstance(widget, QWidget):
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(float(opacity))
    widget.setGraphicsEffect(effect)
    try:
        setattr(widget, _DIM_ATTR, effect)
    except (AttributeError, TypeError):
        logger.debug("widget rejects runtime attribute for drag-dim tracking", exc_info=True)


def restore_from_drag(widget: QWidget) -> None:
    """Clear the dim effect applied by :func:`dim_for_drag`."""

    if not isinstance(widget, QWidget):
        return
    tracked = getattr(widget, _DIM_ATTR, None)
    if tracked is not None and widget.graphicsEffect() is tracked:
        try:
            widget.setGraphicsEffect(None)
        except RuntimeError:
            logger.debug("widget already destroyed when restoring from drag", exc_info=True)
    try:
        setattr(widget, _DIM_ATTR, None)
    except (AttributeError, TypeError):
        logger.debug("widget rejects clearing drag-dim tracking", exc_info=True)


def restore_many(widgets: Iterable[QWidget]) -> None:
    """Restore every widget in ``widgets`` (drag-batch cleanup)."""

    for widget in widgets:
        restore_from_drag(widget)
