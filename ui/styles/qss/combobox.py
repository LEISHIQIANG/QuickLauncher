"""QComboBox style — matches StyleSheet.get_combobox_style()."""

from __future__ import annotations

from ui.styles.builders import StyleBuilder
from ui.styles.qss.tokens import get_combobox_tokens

_TEMPLATE = (
    "\n"
    "                QComboBox {{\n"
    "                    background-color: {{color_cb_bg}};\n"
    "                    border: 1px solid {{color_cb_border}};\n"
    "                    border-radius: {{radius_cb}};\n"
    "                    padding: {{cb_padding}};\n"
    "                    padding-right: 25px;\n"
    "                    color: {{color_cb_text}};\n"
    "                    min-height: {{cb_min_height}};\n"
    "                    font-size: {{cb_font_size}};\n"
    "                    margin: 0px;\n"
    "                }}\n"
    "                QComboBox:hover {{\n"
    "                    border: 1px solid {{color_cb_hover_border}};\n"
    "                    background-color: {{color_cb_hover_bg}};\n"
    "                }}\n"
    "                QComboBox:focus {{\n"
    "                    border: 1px solid {{color_cb_focus_border}};\n"
    "                }}\n"
    "                QComboBox::drop-down {{\n"
    "                    border: none; border-radius: 0;\n"
    "                    width: 20px;\n"
    "                    subcontrol-position: center right;\n"
    "                    subcontrol-origin: padding;\n"
    "                    right: 5px;\n"
    "                }}\n"
    "                QComboBox::down-arrow {{\n"
    '                    image: url("{{cb_arrow_svg}}");\n'
    "                    width: 10px;\n"
    "                    height: 10px;\n"
    "                }}\n"
    "                QComboBox QAbstractItemView {{\n"
    "                    background-color: {{color_cb_menu_bg}};\n"
    "                    border: 1px solid {{color_cb_menu_border}};\n"
    "                    border-radius: {{radius_cb_menu}};\n"
    "                    padding: 4px;\n"
    "                    selection-background-color: {{color_cb_selection_bg}};\n"
    "                    selection-color: {{color_cb_selection_text}};\n"
    "                    color: {{color_cb_menu_text}};\n"
    "                    outline: none;\n"
    "                }}\n"
    "                QComboBox QAbstractItemView::item {{\n"
    "                    padding: 4px 8px;\n"
    "                    border-radius: {{radius_cb_item}};\n"
    "                    margin: 2px;\n"
    "                }}\n"
    "                QComboBox QAbstractItemView::item:hover {{\n"
    "                    background-color: {{color_cb_item_hover_bg}};\n"
    "                }}\n"
    "                QComboBox QAbstractItemView::item:selected {{\n"
    "                    background-color: {{color_cb_selection_bg}};\n"
    "                    color: {{color_cb_selection_text}};\n"
    "                    border: 1px solid {{color_cb_selected_border}};\n"
    "                }}\n"
    "            "
)


def get_plain_style(theme: str) -> str:
    tokens = get_combobox_tokens(theme)
    return StyleBuilder(template=_TEMPLATE).extend(**tokens).render()
