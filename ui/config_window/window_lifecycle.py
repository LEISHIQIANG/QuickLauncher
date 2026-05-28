"""Lifecycle guards for delayed config-window callbacks."""

from __future__ import annotations

import logging

from qt_compat import QTimer

logger = logging.getLogger(__name__)


class WindowLifecycleController:
    """Drop stale delayed callbacks after a window generation changes or closes."""

    def __init__(self, owner, timer_attrs: tuple[str, ...] = ()):
        self.owner = owner
        self.timer_attrs = tuple(timer_attrs)
        self.generation = 0
        self.closing = False

    def next_generation(self) -> int:
        self.generation += 1
        return self.generation

    def open_generation(self) -> int:
        self.closing = False
        return self.next_generation()

    def close_generation(self) -> int:
        self.closing = True
        return self.next_generation()

    def run_if_current(self, generation: int | None, callback, *args) -> bool:
        if self.closing:
            return False
        if generation is not None and generation != self.generation:
            return False
        try:
            callback(*args)
            return True
        except Exception as exc:
            logger.debug("config window delayed callback failed: %s", exc)
            return False

    def defer(self, delay_ms: int, callback, *args, generation: int | None = None) -> None:
        QTimer.singleShot(
            int(delay_ms),
            lambda generation=generation, callback=callback, args=args: self.run_if_current(
                generation, callback, *args
            ),
        )

    def stop_timers(self, *extra_timer_attrs: str) -> None:
        for attr_name in (*self.timer_attrs, *extra_timer_attrs):
            timer = getattr(self.owner, attr_name, None)
            if timer is None:
                continue
            try:
                timer.stop()
            except Exception:
                pass
