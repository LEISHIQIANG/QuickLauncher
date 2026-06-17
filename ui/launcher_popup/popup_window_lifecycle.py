"""Lifecycle / animation helpers for :class:`LauncherPopup`.

Extracted from :mod:`ui.launcher_popup.popup_window` as part of
the P1-06 file-split pass.  Owns the lifecycle generation token,
visibility animation generation and the ``_run_if_lifecycle_current``
helper that every other mixin uses to discard callbacks after a
new show / hide cycle.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from qt_compat import QTimer
from ui.utils.interruptible_animation import stop_named_animations

logger = logging.getLogger(__name__)


class PopupWindowLifecycleMixin:
    """Generation-token lifecycle plumbing for :class:`LauncherPopup`.

    The host class is expected to expose:

    * :pyattr:`_lifecycle_generation` — int counter
    * :pyattr:`_visibility_animation_generation` — int counter
    * :pyattr:`_closing` — bool flag set during teardown
    * :pyattr:`_auto_close_timer` / :pyattr:`_indicator_timer` /
      :pyattr:`_search_cursor_timer` / :pyattr:`_search_anim_timer` /
      :pyattr:`_preload_batch_timer` / :pyattr:`_bg_load_timer` —
      named ``QTimer`` instances
    """

    def _next_lifecycle_generation(self) -> int:
        self._lifecycle_generation = int(getattr(self, "_lifecycle_generation", 0) or 0) + 1
        return self._lifecycle_generation

    def _next_visibility_animation_generation(self) -> int:
        self._visibility_animation_generation = int(getattr(self, "_visibility_animation_generation", 0) or 0) + 1
        return self._visibility_animation_generation

    def _is_visibility_animation_current(self, generation: int) -> bool:
        return generation == int(getattr(self, "_visibility_animation_generation", -1) or -1)

    def _run_if_lifecycle_current(self, generation: int, callback, *args) -> bool:
        if generation != int(getattr(self, "_lifecycle_generation", -1) or -1):
            return False
        if bool(getattr(self, "_closing", False)):
            return False
        try:
            callback(*args)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("discarded popup lifecycle callback failed: %s", exc)
            return False

    def _defer_lifecycle_callback(self, delay_ms: int, callback, *args, generation: int | None = None) -> None:
        token = int(self._lifecycle_generation if generation is None else generation)
        QTimer.singleShot(
            int(delay_ms),
            lambda token=token, callback=callback, args=args: self._run_if_lifecycle_current(  # type: ignore[arg-type]
                token, callback, *args
            ),
        )

    def _stop_lifecycle_timers(self) -> None:
        for timer_name in (
            "_auto_close_timer",
            "_indicator_timer",
            "_search_cursor_timer",
            "_search_anim_timer",
            "_preload_batch_timer",
            "_bg_load_timer",
        ):
            timer = self.__dict__.get(timer_name)
            if timer is None:
                continue
            try:
                timer.stop()
            except Exception as exc:  # noqa: BLE001
                logger.debug("停止定时器失败: %s", exc, exc_info=True)

    def _start_auto_close_timer_if_visible(self) -> None:
        host = cast(Any, self)
        if host.isVisible() and not host._auto_close_timer.isActive():
            host._auto_close_timer.start()

    def prepare_show_animation_state(self):
        """Set a deterministic hidden animation state before the native window is shown."""
        host = cast(Any, self)
        host._is_hiding = False

        stop_named_animations(host, "anim_group", "hide_anim_group")

        host._reveal_progress = 0.0
        host.setWindowOpacity(0.0)
        host.update()


__all__ = ["PopupWindowLifecycleMixin"]
