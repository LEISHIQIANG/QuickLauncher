from ui.utils.dpi_event_filter import _dpi_x_from_wparam, _scale_percent_from_dpi


def test_wm_dpichanged_dpi_is_extracted_from_wparam_low_word():
    wparam = (144 << 16) | 144

    assert _dpi_x_from_wparam(wparam) == 144
    assert _scale_percent_from_dpi(144) == 150


def test_wm_dpichanged_ignores_invalid_wparam_values():
    assert _dpi_x_from_wparam(None) == 0
    assert _scale_percent_from_dpi(0) == 0
