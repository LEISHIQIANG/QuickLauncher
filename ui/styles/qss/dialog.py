"""Dialog stylesheet composition — matches original get_dialog_stylesheet()."""

from __future__ import annotations

import logging

from ui.styles.qss import button, combobox, groupbox, input, scrollbar, slider
from ui.utils.font_manager import get_font_css
from ui.utils.ui_scale import scale_qss

logger = logging.getLogger(__name__)


def get_dialog_stylesheet(theme: str, settings=None) -> str:
    """Return complete dialog QSS — base + each component in original order."""

    font_family = get_font_css().removeprefix("font-family: ").removesuffix(";")
    text_primary = "#FFFFFF" if theme == "dark" else "#1C1C1E"
    text_secondary = "#8E8E93"

    base = (
        f"\n"
        f"        QWidget {{\n"
        f"            font-family: {font_family};\n"
        f"            font-size: 11px;\n"
        f"            color: {text_primary};\n"
        f"        }}\n"
        f"        QDialog {{\n"
        f"            background: transparent;\n"
        f"        }}\n"
        f"        QLabel {{\n"
        f"            color: {text_primary};\n"
        f"            background: transparent;\n"
        f"            border: none; border-radius: 0;\n"
        f"        }}\n"
        f"        QLabel#TitleLabel {{\n"
        f"            color: {text_primary};\n"
        f"            margin-bottom: 4px;\n"
        f"        }}\n"
        f"        QLabel#SubtitleLabel {{\n"
        f"            font-size: 10px;\n"
        f"            color: {text_secondary};\n"
        f"        }}\n"
        f"        QCheckBox {{\n"
        f"            spacing: 6px;\n"
        f"            color: {text_primary};\n"
        f"        }}\n"
        f"        QCheckBox::indicator {{\n"
        f"            width: 16px;\n"
        f"            height: 16px;\n"
        f"            border-radius: 3px;\n"
        f"            border: 1px solid {text_secondary};\n"
        f"            background-color: transparent;\n"
        f"        }}\n"
        f"        QCheckBox::indicator:checked {{\n"
        f"            background-color: #007AFF;\n"
        f"            border-color: #007AFF;\n"
        f"            image: url(\"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='white'><path d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/></svg>\");\n"
        f"        }}\n"
        f"        QRadioButton {{\n"
        f"            spacing: 6px;\n"
        f"            color: {text_primary};\n"
        f"        }}\n"
        f"        QRadioButton::indicator {{\n"
        f"            width: 16px;\n"
        f"            height: 16px;\n"
        f"            border-radius: 8px;\n"
        f"            border: 1px solid {text_secondary};\n"
        f"            background-color: transparent;\n"
        f"        }}\n"
        f"        QRadioButton::indicator:checked {{\n"
        f"            background-color: #007AFF;\n"
        f"            border-color: #007AFF;\n"
        f"            image: url(\"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='white'><circle cx='12' cy='12' r='5'/></svg>\");\n"
        f"        }}\n"
        "    "
    )

    focus_qss = ""
    try:
        from ui.styles.focus_ring import focus_ring_qss

        focus_qss = focus_ring_qss(theme)
    except Exception as exc:
        logger.debug("Focus ring QSS load failed: %s", exc, exc_info=True)

    full_css = (
        base
        + button.get_plain_style(theme)
        + input.get_plain_style(theme)
        + scrollbar.get_plain_style(theme)
        + combobox.get_plain_style(theme)
        + groupbox.get_plain_style(theme)
        + slider.get_plain_style(theme)
        + focus_qss
    )
    return scale_qss(full_css)
