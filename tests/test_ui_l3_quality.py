from types import SimpleNamespace

from ui.launcher_popup.glass_types import _blur_downsample
from ui.styles.focus_ring import pressed_transition_qss
from ui.styles.l3_features import (
    elevation_profile,
    glass_quality,
    motion_scale,
    resolved_elevation_level,
    window_animations,
)
from ui.styles.style_sheet import StyleSheet


def _settings(**overrides):
    values = {
        "low_end_mode": False,
        "motion_scale": 1.0,
        "window_animations": True,
        "elevation_profile": "auto",
        "glass_quality": "auto",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_low_end_mode_forces_runtime_quality_fallbacks():
    settings = _settings(
        low_end_mode=True,
        elevation_profile="high",
        glass_quality="high",
        window_animations=True,
    )

    assert elevation_profile(settings) == "low"
    assert glass_quality(settings) == "low"
    assert window_animations(settings) is False
    assert resolved_elevation_level(3, settings) == 1


def test_l3_values_are_clamped_and_elevation_profiles_resolve():
    assert motion_scale(_settings(motion_scale=8.0)) == 2.0
    assert motion_scale(_settings(motion_scale=0.1)) == 0.5
    assert resolved_elevation_level(1, _settings(elevation_profile="high")) == 2
    assert resolved_elevation_level(3, _settings(elevation_profile="auto"), is_win10=True) == 1


def test_glass_downsample_profiles_follow_quality_and_resolution():
    assert _blur_downsample(1000, 1000, "low") == (150, 150)
    assert _blur_downsample(1000, 1000, "high") == (250, 250)
    assert _blur_downsample(2000, 1500, "auto") == (400, 300)
    assert _blur_downsample(1000, 1000, "auto") == (250, 250)


def test_qss_does_not_emit_unsupported_css_transitions():
    assert pressed_transition_qss() == ""
    assert StyleSheet.micro_animations_disabled_suffix() == ""
    assert "transition:" not in StyleSheet.get_button_style("dark")
