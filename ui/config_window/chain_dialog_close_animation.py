"""Chain-dialog close-animation mixin.

Extracted from :mod:`ui.config_window.chain_dialog` as part of the
P1-06 file-split pass.  Owns the fade-and-slide close animation
timer and the ``done`` override that triggers it.
"""

from __future__ import annotations

import logging

from qt_compat import QTimer
from ui.utils.interruptible_animation import set_precise_timer
from ui.utils.ui_scale import sp

logger = logging.getLogger(__name__)


class ChainDialogCloseAnimationMixin:
    """Fade-and-slide animation played when the dialog closes.

    The host class is expected to expose:

    * :pyattr:`_closing_with_animation` — re-entrancy guard
    * :pyattr:`_pending_done_result` — accepted/rejected code to call later
    * :pyattr:`_close_anim_timer` — ``QTimer`` slot
    * :pyattr:`_dialog_finished` — already-finished flag (set by ``QDialog``)
    * :pyattr:`_anim_timer` — optional show-animation timer (stopped on close)
    """

    def closeEvent(self, event):
        """Clean up background threads and timers on close."""
        self._close_anim_generation = int(getattr(self, "_close_anim_generation", 0) or 0) + 1
        # Cancel any in-flight test thread.  The test-runner mixin
        # is expected to provide this method; ``getattr`` keeps the
        # close animation mixin usable even when it is composed
        # without the test-runner mixin.
        cleanup = getattr(self, "_cleanup_chain_test_thread", None)
        if callable(cleanup):
            cleanup()
        # Stop close-animation timer
        close_anim_timer = getattr(self, "_close_anim_timer", None)
        if close_anim_timer is not None:
            try:
                close_anim_timer.stop()
            except Exception:  # noqa: BLE001
                logger.debug("停止 close_anim_timer 失败", exc_info=True)
        super().closeEvent(event)

    def done(self, result):
        if getattr(self, "_closing_with_animation", False):
            return
        if not self.isVisible() or getattr(self, "_dialog_finished", False):
            super().done(result)
            return

        self._closing_with_animation = True
        self._pending_done_result = result
        self._close_anim_generation = int(getattr(self, "_close_anim_generation", 0) or 0) + 1
        generation = self._close_anim_generation

        anim_timer = getattr(self, "_anim_timer", None)
        if anim_timer is not None:
            try:
                anim_timer.stop()
            except Exception as exc:  # noqa: BLE001
                logger.debug("停止动画定时器失败: %s", exc, exc_info=True)

        self._close_anim_origin_pos = self.pos()
        self._close_anim_step = 0
        self._close_anim_duration_ms = 170
        self._close_anim_interval_ms = 16
        self._close_anim_total_steps = max(1, self._close_anim_duration_ms // self._close_anim_interval_ms)

        self._close_anim_timer = QTimer(self)
        self._close_anim_timer.setInterval(self._close_anim_interval_ms)
        set_precise_timer(self._close_anim_timer, owner="ChainDialog._close_anim_timer")
        self._close_anim_timer.timeout.connect(lambda generation=generation: self._on_close_animation_tick(generation))
        self._close_anim_timer.start()

    def _on_close_animation_tick(self, generation: int | None = None):
        if generation is not None and generation != int(getattr(self, "_close_anim_generation", -1) or -1):
            return
        self._close_anim_step += 1
        progress = self._close_anim_step / self._close_anim_total_steps
        if progress >= 1.0:
            progress = 1.0

        eased = progress * progress
        self.setWindowOpacity(max(0.0, 1.0 - progress * 1.25))  # type: ignore[attr-defined]
        origin = self._close_anim_origin_pos
        self.move(origin.x(), origin.y() + int(eased * sp(16)))  # type: ignore[attr-defined]

        if progress >= 1.0:
            if generation is not None and generation != int(getattr(self, "_close_anim_generation", -1) or -1):
                return
            timer = getattr(self, "_close_anim_timer", None)
            if timer is not None:
                timer.stop()
            self._closing_with_animation = False
            super().done(self._pending_done_result)  # type: ignore[misc]


__all__ = ["ChainDialogCloseAnimationMixin"]
