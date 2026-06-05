"""Small helpers for temporarily pausing global hooks."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def mouse_hook_paused(hook=None, *, restore_previous: bool = False, log_label: str = "mouse hook") -> Iterator[None]:
    """Pause a mouse hook for a short critical section.

    When ``restore_previous`` is false, this mirrors the existing dialog behavior:
    pause on entry and unpause on exit only if the pause succeeded. Recording
    widgets use ``restore_previous=True`` so an already-paused hook stays paused.
    """
    paused = False
    previous_state: bool | None = None

    if hook is not None:
        if restore_previous:
            try:
                previous_state = bool(hook.is_paused())
            except Exception as exc:
                logger.debug("读取%s暂停状态失败: %s", log_label, exc, exc_info=True)
        try:
            hook.set_paused(True)
            paused = True
        except Exception as exc:
            logger.debug("暂停%s失败: %s", log_label, exc, exc_info=True)

    try:
        yield
    finally:
        if hook is not None and paused:
            if not (restore_previous and previous_state is None):
                try:
                    hook.set_paused(bool(previous_state) if restore_previous else False)
                except Exception as exc:
                    logger.debug("恢复%s暂停状态失败: %s", log_label, exc, exc_info=True)
