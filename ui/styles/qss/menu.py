"""QMenu style — matches original _public_functions.get_menu_stylesheet."""

from __future__ import annotations

from ui.styles.builders import StyleBuilder
from ui.styles.design_tokens import selection_bg_qss, selection_text_qss

_DARK = (
    "\n"
    "            QMenu {\n"
    "                background-color: rgba(30, 30, 30, 120);\n"
    "                border: 1px solid rgba(255, 255, 255, 0.15);\n"
    "                border-radius: 12px;\n"
    "                padding: 6px;\n"
    "            }\n"
    "            QMenu::item {\n"
    "                background-color: transparent;\n"
    "                color: #ffffff;\n"
    "                padding: 8px 20px;\n"
    "                border-radius: 8px;\n"
    "                margin: 2px 4px;\n"
    "            }\n"
    "            QMenu::item:selected {\n"
    "                background-color: {{sel_bg}};\n"
    "                color: {{sel_text}};\n"
    "            }\n"
    "            QMenu::item:disabled {\n"
    "                color: rgba(255, 255, 255, 110);\n"
    "            }\n"
    "            QMenu::separator {\n"
    "                height: 1px;\n"
    "                background-color: rgba(255, 255, 255, 16);\n"
    "                margin: 6px 10px;\n"
    "            }\n"
    "        "
)

_LIGHT = (
    "\n"
    "            QMenu {\n"
    "                background-color: rgba(255, 255, 255, 120);\n"
    "                border: 1px solid rgba(0, 0, 0, 0.08);\n"
    "                border-radius: 12px;\n"
    "                padding: 6px;\n"
    "            }\n"
    "            QMenu::item {\n"
    "                background-color: transparent;\n"
    "                color: #1c1c1e;\n"
    "                padding: 8px 20px;\n"
    "                border-radius: 8px;\n"
    "                margin: 2px 4px;\n"
    "            }\n"
    "            QMenu::item:selected {\n"
    "                background-color: {{sel_bg}};\n"
    "                color: {{sel_text}};\n"
    "            }\n"
    "            QMenu::item:disabled {\n"
    "                color: rgba(60, 60, 67, 120);\n"
    "            }\n"
    "            QMenu::separator {\n"
    "                height: 1px;\n"
    "                background-color: rgba(60, 60, 67, 18);\n"
    "                margin: 6px 10px;\n"
    "            }\n"
    "        "
)


def get_plain_style(theme: str) -> str:
    tmpl = _DARK if theme == "dark" else _LIGHT
    t = {"sel_bg": selection_bg_qss(theme), "sel_text": selection_text_qss(theme)}
    return StyleBuilder(template=tmpl).extend(**t).render()
