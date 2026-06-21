"""QListWidget style (neumorphism) — matches Glassmorphism.get_neumorphism_list_style."""

from __future__ import annotations

from ui.styles.builders import StyleBuilder
from ui.styles.design_tokens import selection_bg_qss, selection_hover_bg_qss, selection_text_qss

_DARK = (
    "\n"
    "                QListWidget {\n"
    "                    background: rgba(30, 30, 34, 0.5);\n"
    "                    border: 1px solid rgba(255, 255, 255, 0.08);\n"
    "                    border-radius: 12px;\n"
    "                    outline: none;\n"
    "                    padding: 4px;\n"
    "                }\n"
    "                QListWidget::item {\n"
    "                    padding: 10px 12px;\n"
    "                    border-radius: 8px;\n"
    "                    margin: 2px 4px;\n"
    "                    color: rgba(255, 255, 255, 0.85);\n"
    "                }\n"
    "                QListWidget::item:selected {\n"
    "                    background: {{sel_bg}};\n"
    "                    color: {{sel_text}};\n"
    "                    border: 1px solid rgba(10, 132, 255, 0.42);\n"
    "                }\n"
    "                QListWidget::item:hover:!selected {\n"
    "                    background: {{sel_hover_bg}};\n"
    "                }\n"
    "            "
)

_LIGHT = (
    "\n"
    "                QListWidget {\n"
    "                    background: rgba(240, 240, 245, 0.4);\n"
    "                    border: 1px solid rgba(0, 0, 0, 0.05);\n"
    "                    border-radius: 12px;\n"
    "                    outline: none;\n"
    "                    padding: 4px;\n"
    "                }\n"
    "                QListWidget::item {\n"
    "                    padding: 10px 12px;\n"
    "                    border-radius: 8px;\n"
    "                    margin: 2px 4px;\n"
    "                    color: rgba(28, 28, 30, 0.85);\n"
    "                }\n"
    "                QListWidget::item:selected {\n"
    "                    background: {{sel_bg}};\n"
    "                    color: {{sel_text}};\n"
    "                    border: 1px solid rgba(0, 122, 255, 0.22);\n"
    "                }\n"
    "                QListWidget::item:hover:!selected {\n"
    "                    background: {{sel_hover_bg}};\n"
    "                }\n"
    "            "
)


def get_neumorphism_style(theme: str) -> str:
    tmpl = _DARK if theme == "dark" else _LIGHT
    t = {
        "sel_bg": selection_bg_qss(theme),
        "sel_text": selection_text_qss(theme),
        "sel_hover_bg": selection_hover_bg_qss(theme),
    }
    return StyleBuilder(template=tmpl).extend(**t).render()
