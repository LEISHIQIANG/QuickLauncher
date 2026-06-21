"""Public style functions extracted from ui.styles.style (W6.3 split).

These three helpers (:func:`get_menu_stylesheet`,
:func:`get_dialog_stylesheet`, :func:`get_button_stylesheet`) are the
canonical entry points for theme-aware Qt stylesheet generation.
"""

import logging

from ui.utils.ui_scale import scale_qss

from ._colors import Colors
from .style_sheet import StyleSheet

logger = logging.getLogger(__name__)


def get_menu_stylesheet(theme: str) -> str:
    selection_bg = Colors.get_selection_bg(theme)
    selection_text = Colors.get_selection_text(theme)
    """获取菜单样式表（用于 QMenu）— 半透明背景配合模糊效果"""
    if theme == "dark":
        css = """
            QMenu {
                background-color: rgba(30, 30, 30, 120);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 12px;
                padding: 6px;
            }
            QMenu::item {
                background-color: transparent;
                color: #ffffff;
                padding: 8px 20px;
                border-radius: 8px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background-color: {selection_bg};
                color: {selection_text};
            }
            QMenu::item:disabled {
                color: rgba(255, 255, 255, 110);
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(255, 255, 255, 16);
                margin: 6px 10px;
            }
        """.replace(
            "{selection_bg}", selection_bg
        ).replace(
            "{selection_text}", selection_text
        )
    else:
        css = """
            QMenu {
                background-color: rgba(255, 255, 255, 120);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 12px;
                padding: 6px;
            }
            QMenu::item {
                background-color: transparent;
                color: #1c1c1e;
                padding: 8px 20px;
                border-radius: 8px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background-color: {selection_bg};
                color: {selection_text};
            }
            QMenu::item:disabled {
                color: rgba(60, 60, 67, 120);
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(60, 60, 67, 18);
                margin: 6px 10px;
            }
        """.replace(
            "{selection_bg}", selection_bg
        ).replace(
            "{selection_text}", selection_text
        )
    return scale_qss(css)


def get_dialog_stylesheet(theme: str, settings=None) -> str:
    """获取对话框完整样式表 (L3 §9: 通过 settings 控制焦点环和微动画)"""
    style = StyleSheet

    from ui.utils.font_manager import get_font_css

    font_family = get_font_css().removeprefix("font-family: ").removesuffix(";")

    if theme == "dark":
        text_primary = Colors.DARK_TEXT_PRIMARY
        text_secondary = Colors.DARK_TEXT_SECONDARY
    else:
        text_primary = Colors.LIGHT_TEXT_PRIMARY
        text_secondary = Colors.LIGHT_TEXT_SECONDARY

    base = f"""
        QWidget {{
            font-family: {font_family};
            font-size: 11px;
            color: {text_primary};
        }}
        QDialog {{
            background: transparent;
        }}
        QLabel {{
            color: {text_primary};
            background: transparent;
            border: none; border-radius: 0;
        }}
        QLabel#TitleLabel {{
            color: {text_primary};
            margin-bottom: 4px;
        }}
        QLabel#SubtitleLabel {{
            font-size: 10px;
            color: {text_secondary};
        }}
        QCheckBox {{
            spacing: 6px;
            color: {text_primary};
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 3px;
            border: 1px solid {text_secondary};
            background-color: transparent;
        }}
        QCheckBox::indicator:checked {{
            background-color: #007AFF;
            border-color: #007AFF;
            image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='white'><path d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/></svg>");
        }}
        QRadioButton {{
            spacing: 6px;
            color: {text_primary};
        }}
        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 8px;
            border: 1px solid {text_secondary};
            background-color: transparent;
        }}
        QRadioButton::indicator:checked {{
            background-color: #007AFF;
            border-color: #007AFF;
            image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='white'><circle cx='12' cy='12' r='5'/></svg>");
        }}
    """

    focus_qss = ""
    transitions_suffix = ""
    try:
        from ui.styles.l3_features import micro_animations, show_focus_ring

        if show_focus_ring(settings):
            from ui.styles.focus_ring import focus_ring_qss

            focus_qss = focus_ring_qss(theme)
        if not micro_animations(settings):
            transitions_suffix = "* { transition: none !important; transition-property: none !important; transition-duration: 0ms !important; }\n"
    except Exception:
        import logging

        logging.getLogger(__name__).debug("L3 hooks in dialog stylesheet failed", exc_info=True)

    return scale_qss(
        base
        + style.get_button_style(theme)
        + style.get_input_style(theme)
        + style.get_scrollbar_style(theme)
        + style.get_combobox_style(theme)
        + style.get_groupbox_style(theme)
        + style.get_slider_style(theme)
        + focus_qss
        + transitions_suffix
    )


def get_button_stylesheet(theme: str, settings=None) -> str:
    """获取按钮样式表。

    L3 §5.3 — :func:`L3Features.micro_animations` 关闭时追加
    :meth:`StyleSheet.micro_animations_disabled_suffix` 把所有 transition
    强制设为 0ms；这是从 QSS 层做的"零成本"兜底，无需每个调用方逐个判
    断。
    """
    base = StyleSheet.get_button_style(theme)
    try:
        from .l3_features import micro_animations

        if not micro_animations(settings):
            base += StyleSheet.micro_animations_disabled_suffix()
    except Exception as exc:  # pragma: no cover - defensive
        import logging

        logging.getLogger(__name__).debug("L3 hook failed: %s", exc, exc_info=True)
    return scale_qss(base)
