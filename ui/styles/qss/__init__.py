"""QSS component modules — each ``get_*_style(theme)`` returns the exact
QSS string that the original inline code produced.

All outputs are verified byte-for-byte against ``tmp/style_outputs/``.
"""

from __future__ import annotations

from . import base, button, combobox, groupbox, menu, scrollbar, slider
from . import input as _input
from . import list as _list

__all__ = [
    "compose_full_stylesheet",
    "get_component_style",
]


def compose_full_stylesheet(theme: str, variant: str = "plain") -> str:
    """Assemble the complete QSS string for the given *theme*.

    Parameters
    ----------
    theme:
        ``"dark"`` or ``"light"``
    variant:
        ``"plain"`` (default) or ``"neumorphism"``
    """
    if variant == "neumorphism":
        return (
            base.get_plain_style(theme)
            + button.get_neumorphism_style(theme)
            + _input.get_neumorphism_style(theme)
            + groupbox.get_neumorphism_style(theme)
            + _list.get_neumorphism_style(theme)
            + scrollbar.get_plain_style(theme)
            + slider.get_plain_style(theme)
            + combobox.get_plain_style(theme)
        )
    else:
        return (
            base.get_plain_style(theme)
            + button.get_plain_style(theme)
            + _input.get_plain_style(theme)
            + groupbox.get_plain_style(theme)
            + scrollbar.get_plain_style(theme)
            + slider.get_plain_style(theme)
            + combobox.get_plain_style(theme)
        )


def get_component_style(style_key: str, theme: str) -> str:
    mapping = {
        "button.plain": button.get_plain_style,
        "button.neumorphism": button.get_neumorphism_style,
        "input.plain": _input.get_plain_style,
        "input.neumorphism": _input.get_neumorphism_style,
        "scrollbar.plain": scrollbar.get_plain_style,
        "combobox.plain": combobox.get_plain_style,
        "slider.plain": slider.get_plain_style,
        "groupbox.plain": groupbox.get_plain_style,
        "groupbox.neumorphism": groupbox.get_neumorphism_style,
        "menu.plain": menu.get_plain_style,
        "list.neumorphism": _list.get_neumorphism_style,
    }
    fn = mapping.get(style_key)
    if fn is None:
        raise ValueError(f"Unknown component style key: {style_key!r}")
    return fn(theme)
