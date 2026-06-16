"""Small helpers for interruption-friendly Qt animations."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def stop_animation(animation, *, owner: str = "") -> None:
    if animation is None:
        return
    try:
        animation.stop()
    except RuntimeError as exc:
        logger.debug("停止动画时对象已失效 [%s]: %s", owner, exc, exc_info=True)
    except (AttributeError, TypeError) as exc:
        logger.debug("停止动画失败 [%s]: %s", owner, exc, exc_info=True)


def is_animation_running(animation) -> bool:
    if animation is None:
        return False
    try:
        return int(animation.state()) != 0
    except (AttributeError, RuntimeError, TypeError):
        return False


def stop_named_animations(owner, *names: str) -> None:
    for name in names:
        stop_animation(getattr(owner, name, None), owner=f"{owner.__class__.__name__}.{name}")


def set_precise_timer(timer, *, owner: str = "") -> None:
    """Prefer precise timing for visual animations without making callers Qt-version aware."""
    if timer is None:
        return
    try:
        from qt_compat import Qt

        timer.setTimerType(Qt.PreciseTimer)  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError, TypeError) as exc:
        logger.debug("设置精确定时器失败 [%s]: %s", owner, exc, exc_info=True)
