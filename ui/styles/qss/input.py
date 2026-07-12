"""QLineEdit/QTextEdit/QPlainTextEdit styles."""

from __future__ import annotations

from ui.styles.builders import StyleBuilder
from ui.styles.design_tokens import selection_bg_qss, selection_text_qss
from ui.styles.qss.tokens import get_input_neum_tokens, get_input_plain_tokens

# ---- Plain ----

_PLAIN = (
    "\n"
    "                QLineEdit, QTextEdit, QPlainTextEdit {{\n"
    "                    background-color: {{color_input_bg}};\n"
    "                    border: 1px solid {{color_input_border}};\n"
    "                    border-radius: {{radius_input}};\n"
    "                    padding: {{input_padding}};\n"
    "                    color: {{color_input_text}};\n"
    "                    font-size: {{input_font_size}};\n"
    "                    font-weight: {{input_font_weight}};\n"
    "                    selection-background-color: {{color_input_selection_bg}};\n"
    "                    selection-color: {{color_input_selection_text}};\n"
    "                }}\n"
    "                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{\n"
    "                    border: 1px solid {{color_input_focus_border}};\n"
    "                    background-color: {{color_input_focus_bg}};\n"
    "                }}\n"
    "                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{\n"
    "                    background-color: {{color_input_disabled_bg}};\n"
    "                    color: {{color_input_disabled_text}};\n"
    "                }}\n"
    "            "
)

# ---- Neumorphism (includes QSpinBox) ----

_NEUM = (
    "\n"
    "                /* Text Inputs */\n"
    "                QLineEdit, QTextEdit, QPlainTextEdit {{\n"
    "                    background: {{color_input_bg}};\n"
    "                    border: 1px solid {{color_input_border}};\n"
    "                    border-radius: {{radius_input}};\n"
    "                    padding: {{input_padding}};\n"
    "                    min-height: {{input_min_height}};\n"
    "                    font-size: {{input_font_size}};\n"
    "                    font-weight: {{input_font_weight}};\n"
    "                    margin: 0px;\n"
    "                    color: {{color_input_text}};\n"
    "                    selection-background-color: {{color_input_selection_bg}};\n"
    "                    selection-color: {{color_input_selection_text}};\n"
    "                }}\n"
    "                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{\n"
    "                    border: 1px solid {{color_input_focus_border}};\n"
    "                    background: {{color_input_focus_bg}};\n"
    "                }}\n"
    "                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{\n"
    "                    background: {{color_input_disabled_bg}};\n"
    "                    color: {{color_input_disabled_text}};\n"
    "                }}\n"
    "\n"
    "                /* SpinBox (Container) */\n"
    "                QSpinBox {{\n"
    "                    background: {{color_spin_bg}};\n"
    "                    border: 1px solid {{color_spin_border}};\n"
    "                    border-radius: {{radius_spin}};\n"
    "                    padding: {{input_padding}};\n"
    "                    min-height: {{input_min_height}};\n"
    "                    font-size: {{input_font_size}};\n"
    "                    margin: 0px;\n"
    "                    color: {{color_spin_text}};\n"
    "                    selection-background-color: {{color_input_selection_bg}};\n"
    "                    selection-color: {{color_input_selection_text}};\n"
    "                }}\n"
    "                QSpinBox:focus, QSpinBox:hover {{\n"
    "                    border: 1px solid {{color_spin_focus_border}};\n"
    "                    background: {{color_spin_focus_bg}};\n"
    "                }}\n"
    "                QSpinBox:disabled {{\n"
    "                    background: {{color_spin_disabled_bg}};\n"
    "                    color: {{color_spin_disabled_text}};\n"
    "                }}\n"
    "\n"
    "                /* SpinBox Inner Edit - Reset to transparent */\n"
    "                QSpinBox QLineEdit {{\n"
    "                    background: transparent;\n"
    "                    border-radius: 0; border: none;\n"
    "                    margin: 0;\n"
    "                    padding: 0;\n"
    "                    min-height: 0;\n"
    "                }}\n"
    "                QSpinBox QLineEdit:focus {{\n"
    "                    background: transparent;\n"
    "                    border-radius: 0; border: none;\n"
    "                }}\n"
    "            "
)


def get_plain_style(theme: str) -> str:
    tokens = get_input_plain_tokens(theme)
    tokens["color_input_selection_bg"] = selection_bg_qss(theme)
    tokens["color_input_selection_text"] = selection_text_qss(theme)
    return StyleBuilder(template=_PLAIN).extend(**tokens).render()


def get_neumorphism_style(theme: str) -> str:
    tokens = get_input_neum_tokens(theme)
    tokens["color_input_selection_bg"] = selection_bg_qss(theme)
    tokens["color_input_selection_text"] = selection_text_qss(theme)
    tokens["radius_spin"] = 6
    return StyleBuilder(template=_NEUM).extend(**tokens).render()
