"""L3 视觉精致化 / 流畅度特性 Feature Flag 控制器。

Per ``UI_OPTIMIZATION_PLAN.md`` §五 (L3 视觉精致化) 与 §九 (配套设置字段)，
所有 L3 特性都通过 ``Settings`` 字段门禁，灰度期 (S8 之前) 默认开启或关闭，
用户可在 Settings 面板手动覆盖。``L3Features`` 把这些开关聚合到一个 helper
上，方便在 paintEvent / showEvent / 动画入口点处单行查询。

提供的能力
----------

* :func:`is_low_end_mode` — 总开关（最优先判定）
* :func:`motion_scale` — 全局动效缩放（无障碍偏好）
* :func:`show_focus_ring` — 键盘 Tab 焦点环 (5.2)
* :func:`micro_animations` — 按钮 :pressed 80ms 颜色过渡 (5.3)
* :func:`window_animations` — 弹窗出现/消失动画 (5.6)
* :func:`experimental_pixel_snap` — 像素对齐实验性开关 (5.1)
* :func:`elevation_profile` — 阴影强度档位 (5.4)
* :func:`glass_quality` — 毛玻璃管线档位 (5.5)
* :func:`effective_animation_duration` — 应用 motion_scale 后的最终时长

所有读取都接受一个 ``settings`` 关键字参数（默认 ``None``），调用方传
入当前 ``data_manager.get_settings()`` 即可。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from ui.styles.motion import Duration

T = TypeVar("T")

__all__ = [
    "L3Features",
    "is_low_end_mode",
    "motion_scale",
    "show_focus_ring",
    "micro_animations",
    "window_animations",
    "experimental_pixel_snap",
    "elevation_profile",
    "glass_quality",
    "effective_animation_duration",
    "resolved_elevation_level",
]


def _resolve(getter: Callable[[Any], T], settings: Any, default: T) -> T:
    """Return ``getter(settings)`` if ``settings`` is not None else ``default``."""
    if settings is None:
        return default
    try:
        return getter(settings)
    except AttributeError:
        return default


def is_low_end_mode(settings=None) -> bool:
    """Return True when low-end mode is active (kills most L3 features)."""
    return _resolve(lambda s: bool(getattr(s, "low_end_mode", False)), settings, False)


def motion_scale(settings=None) -> float:
    """Return the global motion scale factor (0.5..2.0)."""
    value = _resolve(lambda s: float(getattr(s, "motion_scale", 1.0)), settings, 1.0)
    return max(0.5, min(2.0, value))


def show_focus_ring(settings=None) -> bool:
    """Return True when the keyboard focus ring should be drawn.

    Suppressed automatically in low-end mode.
    """
    if is_low_end_mode(settings):
        return False
    return _resolve(lambda s: bool(getattr(s, "show_focus_ring", True)), settings, True)


def micro_animations(settings=None) -> bool:
    """Return True when :pressed micro animations are enabled.

    Suppressed in low-end mode (5.3).
    """
    if is_low_end_mode(settings):
        return False
    return _resolve(lambda s: bool(getattr(s, "micro_animations", True)), settings, True)


def window_animations(settings=None) -> bool:
    """Return True when dialog / popup show+hide animations are enabled (5.6)."""
    if is_low_end_mode(settings):
        return False
    return _resolve(lambda s: bool(getattr(s, "window_animations", True)), settings, True)


def experimental_pixel_snap(settings=None) -> bool:
    """Return True when experimental pixel snap is enabled (5.1).

    Off by default during the S0..S7 phase. Promote to True during the
    S8 grayscale window. ``_resolve`` always reads the value from the
    settings payload; ``is_low_end_mode`` does **not** suppress this flag
    because it is opt-in and the user has explicitly chosen it.
    """
    return _resolve(lambda s: bool(getattr(s, "experimental_pixel_snap", False)), settings, False)


def elevation_profile(settings=None) -> str:
    """Return the elevation profile: ``auto`` / ``low`` / ``high`` (5.4).

    * ``auto`` — picks ``elev_1/2/3`` on Win11 and ``elev_1`` on Win10
    * ``low``  — pins every platform to ``elev_1``
    * ``high`` — uses ``elev_2/3`` (1.7.0 has no ``elev_4`` yet)
    """
    if is_low_end_mode(settings):
        return "low"
    value = _resolve(
        lambda s: str(getattr(s, "elevation_profile", "auto") or "auto"),
        settings,
        "auto",
    )
    if value not in ("auto", "low", "high"):
        return "auto"
    return value


def glass_quality(settings=None) -> str:
    """Return the glass quality profile: ``auto`` / ``low`` / ``high`` (5.5)."""
    if is_low_end_mode(settings):
        return "low"
    value = _resolve(
        lambda s: str(getattr(s, "glass_quality", "auto") or "auto"),
        settings,
        "auto",
    )
    if value not in ("auto", "low", "high"):
        return "auto"
    return value


def resolved_elevation_level(base_level: int, settings=None, *, is_win10: bool = False) -> int:
    """Resolve an elevation token level for the selected quality profile."""
    base = max(0, min(3, int(base_level)))
    profile = elevation_profile(settings)
    if profile == "low" or is_win10:
        return min(base, 1)
    if profile == "high":
        return min(3, max(2, base + 1))
    return base


def effective_animation_duration(
    key: str,
    settings=None,
) -> int:
    """Resolve a ``Duration`` key to its effective milliseconds.

    Applies the user's ``motion_scale`` preference. Returns ``0`` if
    ``window_animations`` is disabled (callers should skip the animation
    entirely in that case).
    """
    if not window_animations(settings):
        return 0
    base = Duration.apply_scale(Duration.__dict__.get(key, Duration.NORMAL), motion_scale(settings))
    return int(base)


class L3Features:
    """Class-style facade for :func:`is_low_end_mode` and friends.

    All methods are static; instantiate the class only when you need a
    convenient namespace (e.g. ``L3Features.motion_scale(settings)``).
    """

    is_low_end_mode = staticmethod(is_low_end_mode)
    motion_scale = staticmethod(motion_scale)
    show_focus_ring = staticmethod(show_focus_ring)
    micro_animations = staticmethod(micro_animations)
    window_animations = staticmethod(window_animations)
    experimental_pixel_snap = staticmethod(experimental_pixel_snap)
    elevation_profile = staticmethod(elevation_profile)
    glass_quality = staticmethod(glass_quality)
    resolved_elevation_level = staticmethod(resolved_elevation_level)
    effective_animation_duration = staticmethod(effective_animation_duration)
