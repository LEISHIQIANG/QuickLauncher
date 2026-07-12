from ui.utils.ui_scale import scale_qss, set_scale


def teardown_function():
    set_scale(100)


def test_scale_qss_keeps_border_strokes_unscaled_at_150_percent():
    set_scale(150)

    css = """
        QPushButton {
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-left: 3px solid #007aff;
            border-top-width: 2px;
            outline: 1px dashed red;
            border-radius: 6px;
            padding: 4px 8px;
        }
    """

    scaled = scale_qss(css)

    assert "border: 1px solid" in scaled
    assert "border-left: 3px solid" in scaled
    assert "border-top-width: 2px" in scaled
    assert "outline: 1px dashed" in scaled
    assert "border-radius: 9px" in scaled
    assert "padding: 6px 12px" in scaled


def test_scale_qss_still_protects_url_segments():
    set_scale(150)

    scaled = scale_qss("QLabel { image: url(C:/icons/16px/icon.png); margin: 8px; }")

    assert "url(C:/icons/16px/icon.png)" in scaled
    assert "margin: 12px" in scaled


def test_full_glassmorphism_stylesheet_does_not_double_scale_input_fonts():
    from ui.styles.style import Glassmorphism

    set_scale(150)

    style = Glassmorphism.get_full_glassmorphism_stylesheet("dark")

    assert "font-size: 18px" in style
    assert "font-size: 27px" not in style


def test_theme_helper_indicator_sizes_do_not_double_scale(monkeypatch):
    import ui.config_window.theme_helper as theme_helper

    monkeypatch.setattr(theme_helper, "create_ios_radio_icon", lambda *_args, **_kwargs: "C:/icons/radio.png")
    monkeypatch.setattr(theme_helper, "create_ios_checkbox_icon", lambda *_args, **_kwargs: "C:/icons/check.png")
    monkeypatch.setattr(theme_helper, "create_ios_switch_icon", lambda *_args, **_kwargs: "C:/icons/switch.png")

    set_scale(150)

    radio = theme_helper.get_radio_stylesheet("dark")
    checkbox = theme_helper.get_checkbox_stylesheet("dark")
    small = theme_helper.get_small_checkbox_stylesheet("dark")
    compact = theme_helper.get_compact_checkbox_stylesheet("dark")
    indicator_only = theme_helper.get_indicator_only_checkbox_stylesheet("dark")
    switch = theme_helper.get_switch_stylesheet("dark")

    assert "width: 21px" in radio
    assert "height: 21px" in radio
    assert "width: 21px" in checkbox
    assert "height: 21px" in checkbox
    assert "width: 16px" in small
    assert "height: 16px" in small
    assert "width: 20px" in compact
    assert "height: 20px" in compact
    assert "width: 16px" in indicator_only
    assert "height: 16px" in indicator_only
    assert "width: 44px" in switch
    assert "height: 27px" in switch

    assert "width: 32px" not in radio
    assert "width: 32px" not in checkbox
    assert "width: 66px" not in switch


def test_smooth_scroll_step_tracks_ui_scale(qapp):
    from ui.utils.smooth_scroll import SmoothScrollArea

    set_scale(150)
    area = SmoothScrollArea(scroll_step=100)

    try:
        assert area._scroll_step == 150
        assert area._scroll_timer.interval() == 16

        area.setScrollStep(80)
        assert area._scroll_step == 120
    finally:
        area.deleteLater()
