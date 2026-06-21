"""Semantic animation helpers.

This module exposes the *public* animation API used across the UI layer.
The intent is that every call site reads like a sentence – for example
``fade_in(widget)`` – while the implementation reuses the existing
:mod:`ui.utils.interruptible_animation` stop/query helpers.

Architecture (per §4.10.3 of ``UI_OPTIMIZATION_PLAN.md``):

::

    ui.utils.interruptible_animation  ──►  ui.utils.animations  ──►  components
       (stop/query primitives)            (semantic helpers)        (callers)

The wrappers in this file never re-implement ``stop()`` / ``isRunning()``
logic; they delegate to the primitives. New code should prefer the
helpers here over instantiating :class:`QPropertyAnimation` directly.
"""

from __future__ import annotations

import logging
import weakref
from collections.abc import Iterable
from typing import Any

from qt_compat import (
    QParallelAnimationGroup,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QWidget,
)
from ui.styles.motion import Duration, Easing, make_easing_curve
from ui.utils.interruptible_animation import (
    is_animation_running,
    stop_animation,
    stop_named_animations,
)

logger = logging.getLogger(__name__)

__all__ = [
    "fade_in",
    "fade_out",
    "scale_in",
    "slide_in",
    "chain",
    "parallel",
    "cancel_all",
    "DisposableAnimation",
    "DisposableWidget",
]


# ---------------------------------------------------------------------------
# Public semantic API
# ---------------------------------------------------------------------------


def _resolve_duration(base_duration_ms: int) -> int:
    return base_duration_ms


def _new_property_animation(target: QWidget, prop: bytes) -> QPropertyAnimation:
    anim = QPropertyAnimation(target, prop)
    anim.setEasingCurve(make_easing_curve(Easing.STANDARD))
    return anim


def fade_in(
    target: QWidget,
    duration_ms: int = Duration.FADE_IN,
    *,
    on_finished=None,
) -> QPropertyAnimation:
    """Animate ``target`` opacity 0 → 1.

    The animation is attached to the target as ``_fade_anim`` and any
    pre-existing animation with the same name is stopped first.
    """

    stop_named_animations(target, "_fade_anim")
    duration_ms = _resolve_duration(duration_ms)
    anim = _new_property_animation(target, b"windowOpacity")
    anim.setDuration(int(duration_ms))
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    if on_finished is not None:
        anim.finished.connect(on_finished)
    target._fade_anim = anim
    anim.start()
    return anim


def fade_out(
    target: QWidget,
    duration_ms: int = Duration.FADE_OUT,
    *,
    hide_on_finish: bool = True,
    on_finished=None,
) -> QPropertyAnimation:
    """Animate ``target`` opacity 1 → 0.

    Hides the widget when the animation finishes (unless
    ``hide_on_finish=False``).
    """

    stop_named_animations(target, "_fade_anim")
    duration_ms = _resolve_duration(duration_ms)

    def _finish() -> None:
        if hide_on_finish:
            try:
                target.hide()
            except RuntimeError:
                logger.debug("animation target was deleted before hide", exc_info=True)
        if on_finished is not None:
            on_finished()

    anim = _new_property_animation(target, b"windowOpacity")
    anim.setDuration(int(duration_ms))
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.finished.connect(_finish)
    target._fade_anim = anim
    anim.start()
    return anim


def scale_in(
    target: QWidget,
    *,
    from_scale: float = 0.95,
    to_scale: float = 1.0,
    duration_ms: int = Duration.SCALE_IN,
) -> QPropertyAnimation:
    """Animate ``target`` geometry around its centre.

    Implemented as a window-opacity sibling when no ``_scale_anim``
    property exists; otherwise the existing property animation is
    reused. The animation does **not** fight with user-driven geometry
    changes – the start value is sampled from ``target.geometry()`` at
    call time.
    """

    stop_named_animations(target, "_scale_anim")
    duration_ms = _resolve_duration(duration_ms)
    geom = target.geometry()
    cx = geom.center()
    start_w = max(1, int(geom.width() * from_scale))
    start_h = max(1, int(geom.height() * from_scale))
    end_w = geom.width()
    end_h = geom.height()
    start = geom.__class__(cx.x() - start_w // 2, cx.y() - start_h // 2, start_w, start_h)
    end = geom.__class__(cx.x() - end_w // 2, cx.y() - end_h // 2, end_w, end_h)

    anim = _new_property_animation(target, b"geometry")
    anim.setDuration(int(duration_ms))
    anim.setStartValue(start)
    anim.setEndValue(end)
    target._scale_anim = anim
    anim.start()
    return anim


def slide_in(
    target: QWidget,
    direction: str = "up",
    *,
    distance: int = 24,
    duration_ms: int = Duration.SLIDE_IN,
) -> QPropertyAnimation:
    """Animate ``target`` sliding into place from ``direction``.

    ``direction`` is one of ``"up"``, ``"down"``, ``"left"``, ``"right"``.
    A 0 → 1 fade is performed in parallel via :func:`fade_in`.
    """

    stop_named_animations(target, "_slide_anim")
    duration_ms = _resolve_duration(duration_ms)
    geom = target.geometry()
    if direction == "up":
        offset = (0, distance)
    elif direction == "down":
        offset = (0, -distance)
    elif direction == "left":
        offset = (distance, 0)
    elif direction == "right":
        offset = (-distance, 0)
    else:
        offset = (0, distance)
    start = geom.__class__(geom.x() + offset[0], geom.y() + offset[1], geom.width(), geom.height())

    fade_in(target, duration_ms=duration_ms)
    anim = _new_property_animation(target, b"pos")
    anim.setDuration(int(duration_ms))
    anim.setStartValue(start.topLeft())
    anim.setEndValue(geom.topLeft())
    target._slide_anim = anim
    anim.start()
    return anim


def chain(*animations: QPropertyAnimation) -> QSequentialAnimationGroup:
    """Run animations one after the other."""

    group = QSequentialAnimationGroup()
    for anim in animations:
        if anim is not None:
            group.addAnimation(anim)
    group.start()
    return group


def parallel(*animations: QPropertyAnimation) -> QParallelAnimationGroup:
    """Run animations concurrently."""

    group = QParallelAnimationGroup()
    for anim in animations:
        if anim is not None:
            group.addAnimation(anim)
    group.start()
    return group


def cancel_all(target: QWidget, names: Iterable[str] | None = None) -> None:
    """Stop every animation previously registered on ``target``.

    Pass ``names`` to limit the cleanup to specific attribute names; by
    default the helper stops the conventional names set by the
    ``fade_in`` / ``scale_in`` / ``slide_in`` helpers.
    """

    if not isinstance(target, QWidget):
        return
    conventional = ("_fade_anim", "_scale_anim", "_slide_anim", "_current_anim")
    all_names = tuple(names) if names else conventional
    stop_named_animations(target, *all_names)
    for attr in conventional:
        anim = getattr(target, attr, None)
        if anim is not None and not is_animation_running(anim):
            try:
                setattr(target, attr, None)
            except (AttributeError, TypeError):
                logger.debug("animation reference could not be cleared: %s", attr, exc_info=True)


# ---------------------------------------------------------------------------
# Owner-disposable primitives
# ---------------------------------------------------------------------------


class DisposableAnimation(QPropertyAnimation):
    """``QPropertyAnimation`` that auto-cancels the owner's previous one.

    On ``start()`` the animation looks up ``_current_anim`` on the target
    widget, stops it via :func:`stop_named_animations` and replaces it
    with itself. The net effect is that two overlapping animations on
    the same property never co-exist.
    """

    def __init__(self, target, prop, parent=None):
        super().__init__(target, prop, parent)
        self._owner_ref: weakref.ref[QWidget] | None = None
        if isinstance(target, QWidget):
            self._owner_ref = weakref.ref(target)

    def start(self, policy: Any = None) -> None:
        if self._owner_ref is not None:
            owner = self._owner_ref()
            if owner is not None:
                stop_named_animations(owner, "_current_anim")
                try:
                    owner._current_anim = self
                except AttributeError:
                    logger.debug("animation owner rejects runtime attributes", exc_info=True)
        if policy is None:
            super().start()
        else:
            super().start(policy)


class DisposableWidget:
    """Mixin that cleans up animations on hide/close.

    Subclasses override :attr:`_animation_names` to list the attributes
    that hold ``QPropertyAnimation`` instances.
    """

    _animation_names: tuple[str, ...] = ()

    def hideEvent(self, event) -> None:
        try:
            stop_named_animations(self, *self._animation_names)
        except Exception:  # pragma: no cover - defensive
            logger.debug("stop_named_animations failed", exc_info=True)
        super().hideEvent(event)  # type: ignore[misc]

    def closeEvent(self, event) -> None:
        try:
            stop_named_animations(self, *self._animation_names)
        except Exception:  # pragma: no cover - defensive
            logger.debug("stop_named_animations failed", exc_info=True)
        super().closeEvent(event)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Diagnostic helpers
# ---------------------------------------------------------------------------


def is_running(animation) -> bool:
    """Return ``True`` if the supplied animation is currently running."""

    return is_animation_running(animation)


def stop(animation, *, owner: str = "") -> None:
    """Stop a single animation, swallowing ``RuntimeError``/``TypeError``."""

    stop_animation(animation, owner=owner)
