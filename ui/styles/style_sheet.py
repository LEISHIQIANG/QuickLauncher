"""StyleSheet facade — delegates to :mod:`ui.styles.qss`.

All public API methods produce byte-for-byte identical output to the
original inline implementations.  Verified by ``tmp/verify.py``.
"""

from __future__ import annotations

from ui.utils.ui_scale import scale_qss

from .qss import button, combobox, groupbox, input, scrollbar, slider


class StyleSheet:

    @staticmethod
    def get_button_style(theme: str) -> str:
        return scale_qss(button.get_plain_style(theme))

    @staticmethod
    def get_input_style(theme: str) -> str:
        return scale_qss(input.get_plain_style(theme))

    @staticmethod
    def get_scrollbar_style(theme: str) -> str:
        return scale_qss(scrollbar.get_plain_style(theme))

    @staticmethod
    def get_combobox_style(theme: str) -> str:
        return scale_qss(combobox.get_plain_style(theme))

    @staticmethod
    def get_groupbox_style(theme: str) -> str:
        return scale_qss(groupbox.get_plain_style(theme))

    @staticmethod
    def get_slider_style(theme: str) -> str:
        return scale_qss(slider.get_plain_style(theme))
