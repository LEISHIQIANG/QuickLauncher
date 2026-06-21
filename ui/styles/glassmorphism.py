"""Glassmorphism facade — delegates all neumorphism styles to :mod:`ui.styles.qss`.

Every method produces byte-for-byte identical output to the original.
``scale_qss()`` is applied where the original code used it.
"""

from __future__ import annotations

from ui.utils.ui_scale import get_scale_percent, scale_qss

from .qss import button as _btn
from .qss import compose_full_stylesheet
from .qss import groupbox as _gb
from .qss import input as _inp
from .qss import list as _lst


class Glassmorphism:

    _full_stylesheet_cache: dict[tuple[str, int], str] = {}

    @classmethod
    def clear_stylesheet_cache(cls) -> None:
        cls._full_stylesheet_cache.clear()

    @staticmethod
    def get_glassmorphism_container_style(theme: str) -> str:
        if theme == "dark":
            return (
                "\n"
                "                background-color: rgba(28, 28, 30, 160);\n"
                "                border: 1px solid rgba(255, 255, 255, 0.08);\n"
                "                border-radius: 12px;\n"
                "            "
            )
        return (
            "\n"
            "                background-color: rgba(242, 242, 247, 120);\n"
            "                border: 1px solid rgba(0, 0, 0, 0.05);\n"
            "                border-radius: 12px;\n"
            "            "
        )

    @classmethod
    def get_full_glassmorphism_stylesheet(cls, theme: str) -> str:
        key = (theme, get_scale_percent())
        if key in cls._full_stylesheet_cache:
            return cls._full_stylesheet_cache[key]
        raw = compose_full_stylesheet(theme, variant="neumorphism")
        result = scale_qss(raw)
        cls._full_stylesheet_cache[key] = result
        return result

    # -- Backward-compatible delegates ---------------------------------

    @staticmethod
    def get_neumorphism_button_style(theme: str) -> str:
        return _btn.get_neumorphism_style(theme)

    @staticmethod
    def get_neumorphism_input_style(theme: str) -> str:
        return _inp.get_neumorphism_style(theme)

    @staticmethod
    def get_neumorphism_groupbox_style(theme: str) -> str:
        return _gb.get_neumorphism_style(theme)

    @staticmethod
    def get_neumorphism_list_style(theme: str) -> str:
        return _lst.get_neumorphism_style(theme)

    @staticmethod
    def get_flat_action_button_style(theme: str) -> str:
        return scale_qss(_btn.get_flat_style(theme))

    @staticmethod
    def get_action_button_style(theme: str, is_compact: bool = False, is_delete: bool = False) -> str:
        if is_delete:
            return scale_qss(_btn.get_delete_style(theme))
        return scale_qss(_btn.get_action_style(theme, compact=is_compact))
