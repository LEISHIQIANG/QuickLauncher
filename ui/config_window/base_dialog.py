"""
统一的对话框基类 - 与主配置窗口保持一致的 alpha 处理
"""

import logging
import os
from datetime import datetime

from qt_compat import QColor, QDialog, QPainter, QPainterPath, QPen, QtCompat, QTimer
from runtime_paths import config_dir, is_packaged_runtime
from ui.styles.theme_controller import resolve_theme
from ui.styles.window_chrome import apply_custom_window_chrome
from ui.utils.dialog_helper import center_dialog_on_main_window
from ui.utils.interruptible_animation import set_precise_timer
from ui.utils.ui_scale import sp, spf
from ui.utils.window_effect import (
    enable_acrylic_for_config_window,
    get_window_effect,
    is_win10,
    is_win11,
    paint_win10_rounded_surface,
)

logger = logging.getLogger(__name__)


def _is_debug_trace_enabled() -> bool:
    value = os.environ.get("QL_TRACE_DIALOG_CRASH", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _trace_to_crash_log(msg: str):
    """写一条时间戳追踪到 crash.log，用于定位闪退发生在哪个操作。"""
    if not _is_debug_trace_enabled():
        return

    try:
        log_dir = str(config_dir())
        with open(os.path.join(log_dir, "crash.log"), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception as exc:
        logger.debug("写入崩溃日志失败: %s", exc, exc_info=True)


class BaseDialog(QDialog):
    """统一的对话框基类"""

    @staticmethod
    def _is_compiled():
        """检测是否为 Nuitka 编译版本 — 跳过不可靠的 Qt 回调操作"""
        return bool(globals().get("__compiled__", False)) or is_packaged_runtime()

    def __init__(self, parent=None):
        super().__init__(parent)
        apply_custom_window_chrome(self, kind="window", translucent=True)
        self.setWindowOpacity(0)

        self.corner_radius = sp(8)
        self.theme = ""
        self._shadow_applied = False
        self._dialog_finished = False
        self._initial_show_completed = False
        self._drag_pos = None
        self._dialog_animation_generation = 0

        # 使用 QColor 对象存储颜色（与主配置窗口一致）
        self.bg_color = QColor(28, 28, 30, 180)
        self.border_color = QColor(190, 190, 197, 60)
        self._apply_theme_colors()

    def _apply_theme_colors(self):
        """应用主题颜色 - 与主配置窗口保持一致"""
        theme = self._get_theme_from_parent()
        self.theme = theme

        if theme == "dark":
            self.bg_color = QColor(28, 28, 30, 180)
            self.border_color = QColor(190, 190, 197, 60)
        else:
            self.bg_color = QColor(242, 242, 247, 160)
            self.border_color = QColor(229, 229, 234, 150)

    def _get_theme_from_parent(self) -> str:
        """从父级链或统一主题控制器解析主题。"""
        parent = self.parent()
        while parent is not None:
            theme = resolve_theme(parent, default="")
            if theme:
                return theme
            try:
                parent = parent.parent()
            except Exception:
                break
        return resolve_theme(self)

    def _next_dialog_animation_generation(self) -> int:
        self._dialog_animation_generation = int(getattr(self, "_dialog_animation_generation", 0) or 0) + 1
        return self._dialog_animation_generation  # type: ignore[no-any-return]

    def _is_dialog_animation_current(self, generation: int) -> bool:
        return generation == int(getattr(self, "_dialog_animation_generation", -1) or -1)

    def _stop_dialog_animation_timer(self) -> None:
        anim_timer = getattr(self, "_anim_timer", None)
        if anim_timer is None:
            return
        try:
            if anim_timer.isActive():
                anim_timer.stop()
        except Exception as exc:
            logger.debug("停止对话框动画定时器失败: %s", exc, exc_info=True)

    def paintEvent(self, event):
        _trace_to_crash_log(f"paintEvent.0: {type(self).__name__}")
        painter = QPainter(self)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            if is_win10():
                paint_win10_rounded_surface(painter, self, self.bg_color, self.border_color, self.corner_radius)
                return

            inset = spf(1.0) if is_win10() else spf(0.5)

            path = QPainterPath()
            path.addRoundedRect(
                inset,
                inset,
                self.width() - inset * 2,
                self.height() - inset * 2,
                self.corner_radius,
                self.corner_radius,
            )

            tint_color = QColor(self.bg_color)
            if is_win10():
                tint_color.setAlpha(min(tint_color.alpha(), 220))
            else:
                tint_color.setAlpha(min(tint_color.alpha(), 100))
            painter.fillPath(path, tint_color)

            pen_color = QColor(self.border_color)
            pen_color.setAlpha(min(pen_color.alpha(), 120))
            pen = QPen(pen_color, 1)
            pen.setJoinStyle(QtCompat.RoundJoin)
            pen.setCapStyle(QtCompat.RoundCap)
            painter.setPen(pen)
            painter.drawPath(path)
        finally:
            painter.end()
        _trace_to_crash_log(f"paintEvent.9: {type(self).__name__}")

    def showEvent(self, event):
        """显示时应用效果"""
        if self._initial_show_completed:
            super().showEvent(event)
            return
        self._initial_show_completed = True
        _trace_to_crash_log(f"showEvent.0: {type(self).__name__}")
        self._dialog_finished = False
        _trace_to_crash_log(f"showEvent.1 adjustSize: {type(self).__name__}")
        self.adjustSize()
        _trace_to_crash_log(f"showEvent.2 center: {type(self).__name__}")
        center_dialog_on_main_window(self)

        target_pos = self.pos()
        # 预先移到动画起点，初始设置透明度为 0
        self.setWindowOpacity(0.0)
        self.move(target_pos.x(), target_pos.y() + sp(24))

        super().showEvent(event)

        if not self._shadow_applied:
            self._shadow_applied = True
            self._effects_timer = QTimer(self)
            self._effects_timer.setSingleShot(True)
            self._effects_timer.timeout.connect(self._apply_effects)
            self._effects_timer.start(100)

        _trace_to_crash_log(f"showEvent.3 anim: {type(self).__name__}")
        self._start_show_animation(target_pos)
        _trace_to_crash_log(f"showEvent.4 done: {type(self).__name__}")

    def _apply_effects(self):
        """应用窗口特效"""
        _trace_to_crash_log(f"_apply_effects.0: {type(self).__name__}")
        if self._dialog_finished or not self.isVisible():
            _trace_to_crash_log(
                f"_apply_effects.skip: {type(self).__name__} finished={self._dialog_finished} visible={self.isVisible()}"
            )
            return
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return
            effect = get_window_effect()
            theme = self.theme
            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
            else:
                w, h = self.width(), self.height()
                if w > 0 and h > 0:
                    effect.set_window_region(hwnd, w, h, self.corner_radius)
            enable_acrylic_for_config_window(self, theme, blur_amount=10)
        except Exception as exc:
            logger.debug("应用窗口特效失败: %s", exc, exc_info=True)

    def done(self, result):
        _trace_to_crash_log(f"done: {type(self).__name__} result={result}")
        self._dialog_finished = True
        self._next_dialog_animation_generation()
        effects_timer = getattr(self, "_effects_timer", None)
        if effects_timer is not None:
            try:
                effects_timer.stop()
            except Exception as exc:
                logger.debug("停止特效定时器失败: %s", exc, exc_info=True)
        self._stop_dialog_animation_timer()
        super().done(result)

    def _start_show_animation(self, target_pos=None):
        """苹果风格的高质感弹性滑入动画 - 100% 兼容编译及免崩溃设计"""
        if self._dialog_finished:
            return
        generation = self._next_dialog_animation_generation()
        self._stop_dialog_animation_timer()

        if target_pos is None:
            target_pos = self.pos()
        self._anim_start_pos = self.pos()
        self._anim_target_pos = target_pos
        self._anim_start_opacity = max(0.0, min(1.0, float(self.windowOpacity())))

        # 动画参数
        self._anim_step = 0
        self._anim_duration_ms = 240  # 240ms 极速且流畅的动效
        self._anim_interval_ms = 16  # 16ms (60 FPS) 完美同步显示器刷新率，防止 DWM 阻塞
        self._anim_total_steps = max(1, self._anim_duration_ms // self._anim_interval_ms)

        # 创建并启动定时器
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(self._anim_interval_ms)
        set_precise_timer(self._anim_timer, owner=f"{type(self).__name__}._anim_timer")
        self._anim_timer.timeout.connect(lambda generation=generation: self._on_animation_tick(generation))
        self._anim_timer.start()

    def _on_animation_tick(self, generation: int | None = None):
        if generation is not None and not self._is_dialog_animation_current(generation):
            return
        if self._dialog_finished:
            if hasattr(self, "_anim_timer"):
                self._anim_timer.stop()
            return

        self._anim_step += 1
        progress = self._anim_step / self._anim_total_steps

        if progress >= 1.0:
            progress = 1.0
            if hasattr(self, "_anim_timer"):
                self._anim_timer.stop()

        # Easing curve: EaseOutCubic (平滑指数级物理减速，无回弹，滑入极度丝滑且收尾无顿感)
        t = progress - 1.0
        eased = t * t * t + 1.0

        # 加速透明度淡入：在 67% 的进度时透明度就达到 1.0，从而提前关闭 DWM 混合层以消除卡顿
        start_opacity = float(getattr(self, "_anim_start_opacity", 0.0))
        self.setWindowOpacity(min(1.0, start_opacity + (1.0 - start_opacity) * progress * 1.5))

        start_pos = getattr(self, "_anim_start_pos", self.pos())
        target_pos = self._anim_target_pos
        current_x = int(start_pos.x() + (target_pos.x() - start_pos.x()) * eased)  # type: ignore[union-attr]
        current_y = int(start_pos.y() + (target_pos.y() - start_pos.y()) * eased)  # type: ignore[union-attr]
        self.move(current_x, current_y)

    def mousePressEvent(self, event):
        """鼠标按下 - 支持拖动"""
        if event.button() == QtCompat.LeftButton:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            if pos.y() <= sp(50):
                self._next_dialog_animation_generation()
                self._stop_dialog_animation_timer()
                self._drag_pos = (
                    event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                )
                event.accept()
            else:
                self._drag_pos = None

    def mouseMoveEvent(self, event):
        """鼠标移动 - 拖动窗口"""
        if self._drag_pos is not None and event.buttons() & QtCompat.LeftButton:
            new_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            self.move(self.pos() + (new_pos - self._drag_pos))
            self._drag_pos = new_pos
            event.accept()

    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        self._drag_pos = None
        super().mouseReleaseEvent(event)
