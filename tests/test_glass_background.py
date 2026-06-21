from __future__ import annotations

import os

import pytest

from core.config_validation import sanitize_settings_dict
from core.data_models import AppSettings
from ui.launcher_popup import glass_background

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_glass_settings_defaults_and_round_trip():
    settings = AppSettings()

    assert settings.glass_bg_alpha == 30
    assert settings.glass_blur_radius == 20
    assert settings.glass_edge_opacity == 0.9
    payload = settings.to_dict()
    restored = AppSettings.from_dict({**payload, "bg_mode": "glass"})

    assert restored.bg_mode == "glass"
    assert restored.glass_bg_alpha == 30
    assert restored.glass_blur_radius == 20
    assert restored.glass_edge_opacity == 0.9


def test_glass_settings_validation_clamps_native_parameters():
    result = sanitize_settings_dict(
        {
            "bg_mode": "glass",
            "glass_bg_alpha": 140,
            "glass_blur_radius": -2,
            "glass_edge_opacity": 4.0,
        }
    )

    assert result["bg_mode"] == "glass"
    assert result["glass_bg_alpha"] == 100
    assert result["glass_blur_radius"] == 0
    assert result["glass_edge_opacity"] == 1.0


def test_python_renderer_contract_has_versioned_four_buffer_renderer():
    assert glass_background.GLASS_ABI_VERSION == 1
    assert glass_background.BUFFER_COUNT == 4
    assert glass_background.TARGET_FPS >= 1
    assert glass_background.WDA_EXCLUDEFROMCAPTURE == 0x11


def test_python_renderer_build_config_uses_legacy_constants():
    class _StubSettings:
        glass_bg_alpha = 30
        glass_blur_radius = 20
        glass_edge_opacity = 0.9
        corner_radius = 8

    class _StubPopup:
        settings = _StubSettings()

    config = glass_background._build_config(_StubPopup(), margin=0.0, top_inset=0.0, scale=1.0)

    assert config["opacity"] == pytest.approx(0.3)
    assert config["brightness"] == pytest.approx(0.9)
    assert config["highlight"] == pytest.approx(0.9)
    assert config["blur_radius"] == pytest.approx(20.0)
    assert config["saturation"] == pytest.approx(2.5)
    assert config["corner_radius"] == pytest.approx(8.0)


def test_python_renderer_renders_pure_solid_frame():
    width = 32
    height = 32
    # Solid mid-gray RGBA buffer (BGRA layout per the function contract).
    pixel = bytes([0x80, 0x80, 0x80, 0xFF])
    captured = pixel * (width * height)
    rendered = glass_background._render_frame(
        captured,
        width,
        height,
        width * 4,
        blur_radius=0.0,
        saturation=1.0,
        highlight=0.0,
        brightness=0.9,
        opacity=0.0,
    )
    assert len(rendered) == width * height * 4
    assert rendered[:4] == captured[:4]


def test_python_renderer_applies_saturation_in_place():
    # Use a mid-luma color so the saturation algorithm has room to push each
    # channel away from the perceived luma without clamping either side to
    # the 0/255 limits.  The bytearray also holds an alpha byte, so the
    # spread metric is computed over the RGB triplet only.
    pixels = bytearray([100, 120, 140, 255])
    before = max(pixels[0], pixels[1], pixels[2]) - min(pixels[0], pixels[1], pixels[2])
    glass_background._apply_saturation(pixels, 2.5)
    r, g, b, a = pixels[2], pixels[1], pixels[0], pixels[3]
    after = max(r, g, b) - min(r, g, b)
    assert after > before
    assert a == 255


def test_python_renderer_saturation_identity_at_factor_one():
    pixels = bytearray([1, 2, 3, 4, 100, 110, 120, 130])
    glass_background._apply_saturation(pixels, 1.0)
    assert list(pixels) == [1, 2, 3, 4, 100, 110, 120, 130]


def test_python_renderer_saturation_for_rgb_3_channels():
    # Test 3-channel RGB saturation fallback
    pixels = bytearray([100, 120, 140])
    before = max(pixels[0], pixels[1], pixels[2]) - min(pixels[0], pixels[1], pixels[2])
    glass_background._apply_saturation(pixels, 2.5, channels=3)
    after = max(pixels[0], pixels[1], pixels[2]) - min(pixels[0], pixels[1], pixels[2])
    assert after > before
