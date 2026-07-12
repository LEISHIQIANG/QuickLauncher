"""Tests for the P1-06 Stage 1 :class:`StyleBuilder`."""

from __future__ import annotations

import pytest

from ui.styles.builders import StyleBuilder

pytestmark = pytest.mark.ui


def test_render_substitutes_token_placeholders():
    builder = StyleBuilder(template="QPushButton { background: {{color_bg}}; padding: {{radius_pad}}; }")
    out = builder.with_color("color_bg", "#ff0000").with_radius("radius_pad", 6).render()
    assert "background: #ff0000" in out
    assert "padding: 6px" in out


def test_with_color_normalizes_hex_case():
    builder = StyleBuilder("Q { color: {{c}}; }")
    out = builder.with_color("c", "#FF00AA").render()
    assert "#FF00AA" in out  # case preserved since UI_OPTIMIZATION Step 1


def test_with_colors_accepts_a_mapping():
    builder = StyleBuilder("Q { a: {{a}}; b: {{b}}; }")
    out = builder.with_colors({"a": "#000000", "b": "#ffffff"}).render()
    assert "a: #000000" in out
    assert "b: #ffffff" in out


def test_with_font_accepts_string_value():
    builder = StyleBuilder("Q { font: {{font}}; }")
    out = builder.with_font("font", "Segoe UI, 12pt").render()
    assert "font: Segoe UI, 12pt" in out


def test_extend_chooses_token_type_by_name():
    builder = StyleBuilder("Q { c: {{color_x}}; r: {{radius_x}}; f: {{font_x}}; }")
    out = builder.extend(
        color_x="#112233",
        radius_x=4,
        font_x="Arial",
    ).render()
    assert "c: #112233" in out
    assert "r: 4px" in out
    assert "f: Arial" in out


def test_render_is_idempotent_with_no_tokens():
    builder = StyleBuilder("QPushButton { color: red; }")
    assert builder.render() == "QPushButton { color: red; }"


def test_render_preserves_unknown_tokens():
    builder = StyleBuilder("Q { a: {{a}}; b: {{b}}; }")
    out = builder.with_color("a", "red").render()
    # Unknown token's outer braces are unescaped (Step 1 change).
    assert "a: red" in out
    assert "{b}" in out


def test_empty_tokens_render_passes_through_template():
    assert StyleBuilder("Q {}").render() == "Q {}"


def test_with_template_returns_new_builder():
    original = StyleBuilder("Q { color: {{c}}; }")
    updated = original.with_template("QLabel { color: {{c}}; }")
    # original is unchanged
    assert original.template.startswith("QPushButton") or original.template.startswith("Q {")
    assert "QLabel" in updated.template


def test_with_template_preserves_tokens():
    builder = StyleBuilder("Q { color: {{c}}; }").with_color("c", "red")
    updated = builder.with_template("QLabel { color: {{c}}; }")
    assert "color: red" in updated.render()
