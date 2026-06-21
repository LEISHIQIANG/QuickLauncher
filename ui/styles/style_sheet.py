"""StyleSheet facade — delegates to :mod:`ui.styles.qss`.

All public API methods produce byte-for-byte identical output to the
original inline implementations.  Verified by ``tmp/verify.py``.
"""

from __future__ import annotations

from .qss import button, combobox, groupbox, input, scrollbar, slider


class StyleSheet:

    @staticmethod
    def micro_animations_disabled_suffix() -> str:
        # Qt Style Sheets do not implement CSS transitions.
        return ""

    @staticmethod
    def get_button_style(theme: str) -> str:
        return button.get_plain_style(theme)

    @staticmethod
    def get_input_style(theme: str) -> str:
        return input.get_plain_style(theme)

    @staticmethod
    def get_scrollbar_style(theme: str) -> str:
        return scrollbar.get_plain_style(theme)

    @staticmethod
    def get_combobox_style(theme: str) -> str:
        return combobox.get_plain_style(theme)

    @staticmethod
    def get_groupbox_style(theme: str) -> str:
        return groupbox.get_plain_style(theme)

    @staticmethod
    def get_slider_style(theme: str) -> str:
        return slider.get_plain_style(theme)
