"""QScrollBar style — matches StyleSheet.get_scrollbar_style()."""

from __future__ import annotations

from ui.styles.builders import StyleBuilder
from ui.styles.qss.tokens import get_scrollbar_tokens

_TEMPLATE = (
    "\n"
    "            QScrollBar:vertical {{\n"
    "                border: none; border-radius: 0;\n"
    "                background: transparent;\n"
    "                width: {{scrollbar_width}};\n"
    "                margin: 0px;\n"
    "            }}\n"
    "            QScrollBar::handle:vertical {{\n"
    "                background: {{color_scrollbar_handle}};\n"
    "                min-height: 30px;\n"
    "                border-radius: {{radius_scrollbar_handle}};\n"
    "            }}\n"
    "            QScrollBar::handle:vertical:hover {{\n"
    "                background: {{color_scrollbar_handle_hover}};\n"
    "            }}\n"
    "            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{\n"
    "                height: 0px;\n"
    "                background: none;\n"
    "            }}\n"
    "            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{\n"
    "                background: none;\n"
    "            }}\n"
    "            QScrollBar:horizontal {{\n"
    "                border: none; border-radius: 0;\n"
    "                background: transparent;\n"
    "                height: {{scrollbar_height}};\n"
    "                margin: 0px;\n"
    "            }}\n"
    "            QScrollBar::handle:horizontal {{\n"
    "                background: {{color_scrollbar_handle}};\n"
    "                min-width: 30px;\n"
    "                border-radius: {{radius_scrollbar_handle}};\n"
    "            }}\n"
    "            QScrollBar::handle:horizontal:hover {{\n"
    "                background: {{color_scrollbar_handle_hover}};\n"
    "            }}\n"
    "            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{\n"
    "                width: 0px;\n"
    "                background: none;\n"
    "            }}\n"
    "            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{\n"
    "                background: none;\n"
    "            }}\n"
    "        "
)


def get_plain_style(theme: str) -> str:
    tokens = get_scrollbar_tokens(theme)
    return StyleBuilder(template=_TEMPLATE).extend(**tokens).render()
