"""QSlider style — matches StyleSheet.get_slider_style()."""

from __future__ import annotations

from ui.styles.builders import StyleBuilder
from ui.styles.qss.tokens import get_slider_tokens

_TEMPLATE = (
    "\n"
    "            QSlider::groove:horizontal {{\n"
    "                height: {{slider_groove_height}};\n"
    "                background: transparent;\n"
    "                border-radius: {{radius_slider_groove}};\n"
    "            }}\n"
    "            QSlider::sub-page:horizontal {{\n"
    "                background: {{color_slider_accent}};\n"
    "                border-radius: {{radius_slider_groove}};\n"
    "            }}\n"
    "            QSlider::add-page:horizontal {{\n"
    "                background: {{color_slider_track}};\n"
    "                border-radius: {{radius_slider_groove}};\n"
    "            }}\n"
    "            QSlider::handle:horizontal {{\n"
    "                background: {{color_slider_handle_bg}};\n"
    "                width: {{slider_handle_size}};\n"
    "                height: {{slider_handle_size}};\n"
    "                margin: {{slider_handle_margin}};\n"
    "                border-radius: {{radius_slider_handle}};\n"
    "                border: {{slider_handle_border}};\n"
    "            }}\n"
    "            QSlider::handle:horizontal:hover {{\n"
    "                background: {{color_slider_handle_hover_bg}};\n"
    "                border: 1px solid {{color_slider_handle_hover_border}};\n"
    "            }}\n"
    "            QSlider::handle:horizontal:pressed {{\n"
    "                background: {{color_slider_handle_pressed_bg}};\n"
    "            }}\n"
    "        "
)


def get_plain_style(theme: str) -> str:
    tokens = get_slider_tokens(theme)
    return StyleBuilder(template=_TEMPLATE).extend(**tokens).render()
