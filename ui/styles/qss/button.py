"""QPushButton styles — plain, neumorphism, flat, delete, action.
Each template matches the exact indentation of the original glassmorphism.py.
"""

from __future__ import annotations

from ui.styles.builders import StyleBuilder
from ui.styles.qss.tokens import (
    TRANSITION_CSS,
    get_button_action_compact_tokens,
    get_button_action_tokens,
    get_button_delete_tokens,
    get_button_flat_tokens,
    get_button_neum_tokens,
    get_button_plain_tokens,
)

# ---- Plain (from StyleSheet, 16-sp indent) ----

_PLAIN = (
    "\n"
    "                QPushButton {{\n"
    "                    background-color: {{color_btn_bg}};\n"
    "                    border: 1px solid {{color_btn_border}};\n"
    "                    border-radius: {{radius_btn}};\n"
    "                    padding: {{btn_padding}};\n"
    "                    color: {{color_btn_text}};\n"
    "                    font-size: {{btn_font_size}};\n"
    "                    font-weight: {{btn_font_weight}};\n"
    "                    min-height: {{btn_min_height}};\n"
    "                    {{transition_css}}\n"
    "                }}\n"
    "                QPushButton:hover {{\n"
    "                    background-color: {{color_btn_hover_bg}};\n"
    "                    border: 1px solid {{color_btn_hover_border}};\n"
    "                }}\n"
    "                QPushButton:focus {{\n"
    "                    border: 1px solid {{color_btn_focus_border}};\n"
    "                }}\n"
    "                QPushButton:pressed {{\n"
    "                    background-color: {{color_btn_pressed_bg}};\n"
    "                    border: 1px solid {{color_btn_pressed_border}};\n"
    "                }}\n"
    "                QPushButton:default {{\n"
    "                    background-color: {{color_btn_default_bg}};\n"
    "                    border: 1px solid {{color_btn_default_border}};\n"
    "                    color: white;\n"
    "                }}\n"
    "                QPushButton:default:hover {{\n"
    "                    background-color: {{color_btn_default_hover_bg}};\n"
    "                }}\n"
    "                QPushButton:default:pressed {{\n"
    "                    background-color: {{color_btn_default_pressed_bg}};\n"
    "                    border: 1px solid {{color_btn_default_pressed_border}};\n"
    "                }}\n"
    "                QPushButton:disabled {{\n"
    "                    background-color: {{color_btn_disabled_bg}};\n"
    "                    color: {{color_btn_disabled_text}};\n"
    "                }}\n"
    "            "
)

# ---- Neumorphism (from Glassmorphism, 16-sp indent, multi-line gradients) ----

_NEUM = (
    "\n"
    "                QPushButton {{\n"
    "                    background: {{color_btn_bg}};\n"
    "                    border: 1px solid {{color_btn_border}};\n"
    "                    border-radius: {{radius_btn}};\n"
    "                    padding: {{btn_padding}};\n"
    "                    color: {{color_btn_text}};\n"
    "                    font-size: {{btn_font_size}};\n"
    "                    font-weight: {{btn_font_weight}};\n"
    "                }}\n"
    "                QPushButton:hover {{\n"
    "                    background: {{color_btn_hover_bg}};\n"
    "                    border: 1px solid {{color_btn_hover_border}};\n"
    "                }}\n"
    "                QPushButton:focus {{\n"
    "                    border: 1px solid {{color_btn_focus_border}};\n"
    "                }}\n"
    "                QPushButton:pressed {{\n"
    "                    background: {{color_btn_pressed_bg}};\n"
    "                    border: 1px solid {{color_btn_pressed_border}};\n"
    "                }}\n"
    "                QPushButton:default {{\n"
    "                    background: {{color_btn_default_bg}};\n"
    "                    border: 1px solid {{color_btn_default_border}};\n"
    "                }}\n"
    "                QPushButton:disabled {{\n"
    "                    background: {{color_btn_disabled_bg}};\n"
    "                    color: {{color_btn_disabled_text}};\n"
    "                }}\n"
    "            "
)

# ---- Flat action (from Glassmorphism, 12-sp indent, inside scale_qss) ----

_FLAT = (
    "\n"
    "            QPushButton {{\n"
    "                font-size: {{btn_font_size}};\n"
    "                padding: {{btn_padding}};\n"
    "                background: {{color_btn_bg}};\n"
    "                border: 1px solid {{color_btn_border}};\n"
    "                border-radius: {{radius_btn}};\n"
    "                color: {{color_btn_text}};\n"
    "            }}\n"
    "            QPushButton:hover {{ background-color: {{color_btn_hover_bg}}; }}\n"
    "            QPushButton:pressed {{ background-color: {{color_btn_pressed_bg}}; opacity: 0.8; }}\n"
    "            QPushButton:disabled {{ background-color: {{color_btn_disabled_bg}}; color: {{color_btn_disabled_text}}; }}\n"
    "        "
)

# ---- Delete button (from Glassmorphism, 12-sp indent, inside scale_qss) ----

_DEL = (
    "\n"
    "            QPushButton {{\n"
    "                font-size: {{btn_font_size}};\n"
    "                padding: {{btn_padding}};\n"
    "                margin: 0px;\n"
    "                background: {{color_btn_bg}};\n"
    "                border: 1px solid {{color_btn_border}};\n"
    "                border-radius: {{radius_btn}};\n"
    "                color: {{color_btn_text}};\n"
    "                font-weight: {{btn_font_weight}};\n"
    "            }}\n"
    "            QPushButton:hover {{\n"
    "                background-color: {{color_btn_hover_bg}};\n"
    "                border: 1px solid {{color_btn_hover_border}};\n"
    "                color: {{color_btn_hover_text}};\n"
    "            }}\n"
    "            QPushButton:pressed {{ opacity: 0.7; }}\n"
    "            QPushButton:disabled {{\n"
    "                color: {{color_btn_disabled_text}};\n"
    "                background: {{color_btn_disabled_bg}};\n"
    "                border: 1px solid {{color_btn_disabled_border}};\n"
    "            }}\n"
    "        "
)

# ---- Action button (from Glassmorphism, 12-sp indent, inside scale_qss) ----

_ACT = (
    "\n"
    "            QPushButton {{\n"
    "                font-size: {{btn_font_size}};\n"
    "                padding: {{btn_padding}};\n"
    "                background: {{color_btn_bg}};\n"
    "                border: 1px solid {{color_btn_border}};\n"
    "                border-radius: {{radius_btn}};\n"
    "                color: {{color_btn_text}};\n"
    "                font-weight: {{btn_font_weight}};\n"
    "            }}\n"
    "            QPushButton:hover {{\n"
    "                background-color: {{color_btn_hover_bg}};\n"
    "                color: {{color_btn_hover_text}};\n"
    "            }}\n"
    "            QPushButton:pressed {{ opacity: 0.7; }}\n"
    "            QPushButton:disabled {{\n"
    "                color: {{color_btn_disabled_text}};\n"
    "                background: {{color_btn_disabled_bg}};\n"
    "                border: 1px solid {{color_btn_disabled_border}};\n"
    "            }}\n"
    "            QPushButton:checked {{\n"
    "                background-color: {{color_btn_checked_bg}};\n"
    "                color: {{color_btn_checked_text}};\n"
    "                border: 1px solid {{color_btn_checked_border}};\n"
    "            }}\n"
    "        "
)


# ---- Public API ----


def get_plain_style(theme: str) -> str:
    t = get_button_plain_tokens(theme)
    t["transition_css"] = TRANSITION_CSS
    return StyleBuilder(template=_PLAIN).extend(**t).render()


def get_neumorphism_style(theme: str) -> str:
    return StyleBuilder(template=_NEUM).extend(**get_button_neum_tokens(theme)).render()


def get_flat_style(theme: str) -> str:
    return StyleBuilder(template=_FLAT).extend(**get_button_flat_tokens(theme)).render()


def get_delete_style(theme: str) -> str:
    return StyleBuilder(template=_DEL).extend(**get_button_delete_tokens(theme)).render()


def get_action_style(theme: str, compact: bool = False) -> str:
    tokens = get_button_action_compact_tokens(theme) if compact else get_button_action_tokens(theme)
    return StyleBuilder(template=_ACT).extend(**tokens).render()
