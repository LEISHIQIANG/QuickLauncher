"""QGroupBox styles — plain and neumorphism."""

from __future__ import annotations

from ui.styles.builders import StyleBuilder
from ui.styles.qss.tokens import get_groupbox_neum_tokens, get_groupbox_plain_tokens

_PLAIN = (
    "\n"
    "                QGroupBox {{\n"
    "                    font-weight: 400;\n"
    "                    border: none; border-radius: 0;\n"
    "                    margin-top: {{gb_margin_top}};\n"
    "                    padding-top: {{gb_padding_top}};\n"
    "                    font-size: {{gb_font_size}};\n"
    "                    color: {{color_gb_text}};\n"
    "                }}\n"
    "                QGroupBox::title {{\n"
    "                    subcontrol-origin: {{gb_title_origin}};\n"
    "                    subcontrol-position: top left;\n"
    "                    left: 0px;\n"
    "                    padding: 0px 0px {{gb_title_padding_bottom}} 0px;\n"
    "                    background-color: transparent;\n"
    "                    color: {{color_gb_title_text}};\n"
    "                }}\n"
    "            "
)

_NEUM = (
    "\n"
    "                QGroupBox {{\n"
    "                    font-weight: 400;\n"
    "                    background: {{color_gb_bg}};\n"
    "                    border: 1px solid {{color_gb_border}};\n"
    "                    border-radius: {{radius_gb}};\n"
    "                    margin-top: {{gb_margin_top}};\n"
    "                    padding-top: {{gb_padding_top}};\n"
    "                    font-size: {{gb_font_size}};\n"
    "                    color: {{color_gb_text}};\n"
    "                }}\n"
    "                QGroupBox::title {{\n"
    "                    subcontrol-origin: margin;\n"
    "                    subcontrol-position: top left;\n"
    "                    left: {{gb_title_left}};\n"
    "                    padding: {{gb_title_padding}};\n"
    "                    background: transparent;\n"
    "                    color: {{color_gb_title_text}};\n"
    "                    font-size: {{gb_title_font_size}};\n"
    "                }}\n"
    "            "
)


def get_plain_style(theme: str) -> str:
    return StyleBuilder(template=_PLAIN).extend(**get_groupbox_plain_tokens(theme)).render()


def get_neumorphism_style(theme: str) -> str:
    return StyleBuilder(template=_NEUM).extend(**get_groupbox_neum_tokens(theme)).render()
