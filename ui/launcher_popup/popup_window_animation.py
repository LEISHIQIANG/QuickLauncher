"""Show / hide animation helpers for :class:`LauncherPopup`.

Extracted from :mod:`ui.launcher_popup.popup_window` as part of the
P1-06 file-split pass.  Owns the fade-in / fade-out ``QPropertyAnimation``
sequences (``opacity_anim`` / ``reveal_anim``) and the
``hide_anim_group`` parallel animation group.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from qt_compat import QtCompat
from ui.styles.l3_features import L3Features, window_animations
from ui.utils.interruptible_animation import is_animation_running, stop_named_animations

logger = logging.getLogger(__name__)


class PopupWindowAnimationMixin:
    """Show / hide reveal-progress + opacity animations.

    The host class is expected to expose:

    * :pyattr:`_reveal_progress` — float ``[0, 1]`` read by the
      ``revealProgress`` ``pyqtProperty`` (see
      :meth:`getRevealProgress` / :meth:`setRevealProgress`).
    * :pyattr:`windowOpacity` — Qt property for fade-in / out.
    * :pyattr:`_is_hiding` — bool flag indicating hide animation in flight.
    """

    def show(self):
        """Show with a stable fade-in start state."""
        host = cast(Any, self)
        if not host.isVisible():
            host.prepare_show_animation_state()
        elif getattr(host, "_is_hiding", False):
            host._is_hiding = False
            stop_named_animations(host, "hide_anim_group")
            host._start_show_animation()
            host.raise_()
            return
        super().show()

    def _start_show_animation(self):
        """窗口出现动画 - 从中心向外扩散"""
        host = cast(Any, self)
        # L3 §5.6 — 如果 window_animations 关闭，则直接设到 1.0，跳过动画
        if not window_animations(getattr(host, "settings", None)):
            try:
                host.setWindowOpacity(1.0)
            except Exception:
                logger.debug("Failed to set popup opacity without animation", exc_info=True)
            try:
                host._reveal_progress = 1.0
            except Exception:
                logger.debug("Failed to set popup reveal progress without animation", exc_info=True)
            try:
                host.update()
            except Exception:
                logger.debug("Failed to update popup without animation", exc_info=True)
            return
        stop_named_animations(host, "anim_group", "hide_anim_group")
        generation = host._next_visibility_animation_generation()
        start_opacity = max(0.0, min(1.0, float(host.windowOpacity())))
        start_reveal = max(0.0, min(1.0, float(getattr(host, "_reveal_progress", 0.0))))

        # L3 §5.6 — 应用 motion_scale 到所有动画时长
        show_ms = int(L3Features.effective_animation_duration("DIALOG_OPEN", getattr(host, "settings", None)))
        if show_ms <= 0:
            show_ms = 100

        # 透明度动画
        host.opacity_anim = QtCompat.QPropertyAnimation(host, b"windowOpacity")
        host.opacity_anim.setDuration(show_ms)
        host.opacity_anim.setStartValue(start_opacity)
        host.opacity_anim.setEndValue(1.0)
        host.opacity_anim.setEasingCurve(QtCompat.OutCubic)

        # 扩散进度动画
        host.reveal_anim = QtCompat.QPropertyAnimation(host, b"revealProgress")
        host.reveal_anim.setDuration(show_ms)
        host.reveal_anim.setStartValue(start_reveal)
        host.reveal_anim.setEndValue(1.0)
        host.reveal_anim.setEasingCurve(QtCompat.OutCubic)

        host.anim_group = QtCompat.QParallelAnimationGroup()
        host.anim_group.addAnimation(host.opacity_anim)
        host.anim_group.addAnimation(host.reveal_anim)
        host.anim_group.finished.connect(lambda generation=generation: host._finish_show_animation(generation))
        host.anim_group.start()

    def _finish_show_animation(self, generation: int | None = None):
        host = cast(Any, self)
        if generation is not None and not host._is_visibility_animation_current(generation):
            return
        if getattr(host, "_is_hiding", False):
            return
        host._reveal_progress = 1.0
        host.setWindowOpacity(1.0)
        host.update()

    def hide(self):
        """隐藏窗口（带动画）"""
        host = cast(Any, self)
        if hasattr(host, "_is_hiding") and host._is_hiding:
            return
        host._is_hiding = True

        # 停止可能正在运行的显示动画
        if is_animation_running(getattr(host, "anim_group", None)):
            host.anim_group.stop()

        host._start_hide_animation()

    def _start_hide_animation(self):
        """窗口消失动画 - 从外向中心收缩"""
        host = cast(Any, self)
        stop_named_animations(host, "hide_anim_group")
        generation = host._next_visibility_animation_generation()
        # 透明度动画
        host.hide_opacity_anim = QtCompat.QPropertyAnimation(host, b"windowOpacity")
        host.hide_opacity_anim.setDuration(100)
        host.hide_opacity_anim.setStartValue(host.windowOpacity())
        host.hide_opacity_anim.setEndValue(0.0)
        host.hide_opacity_anim.setEasingCurve(QtCompat.OutCubic)

        # 收缩进度动画
        host.hide_reveal_anim = QtCompat.QPropertyAnimation(host, b"revealProgress")
        host.hide_reveal_anim.setDuration(100)
        host.hide_reveal_anim.setStartValue(host._reveal_progress)
        host.hide_reveal_anim.setEndValue(0.0)
        host.hide_reveal_anim.setEasingCurve(QtCompat.OutCubic)

        host.hide_anim_group = QtCompat.QParallelAnimationGroup()
        host.hide_anim_group.addAnimation(host.hide_opacity_anim)
        host.hide_anim_group.addAnimation(host.hide_reveal_anim)
        host.hide_anim_group.finished.connect(lambda generation=generation: host._on_hide_finished(generation))
        host.hide_anim_group.start()

    def _on_hide_finished(self, generation: int | None = None):
        """动画结束后真正隐藏窗口"""
        host = cast(Any, self)
        if generation is not None and not host._is_visibility_animation_current(generation):
            return
        if not getattr(host, "_is_hiding", False):
            return
        host._is_hiding = False
        host._reveal_progress = 0.0
        super().hide()  # type: ignore[misc]


__all__ = ["PopupWindowAnimationMixin"]
