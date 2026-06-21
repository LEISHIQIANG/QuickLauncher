"""StyleSheet generator extracted from ui.styles.style (W6.3 split).

The :class:`StyleSheet` builder pulls design tokens from
:class:`ui.styles._colors.Colors` so the two modules share a single
source of truth for the color palette.

L3 visual polish — see ``UI_OPTIMIZATION_PLAN.md`` §五 and §九
=============================================================

* 5.2 *Focus Ring* — the ``:focus`` rules below are the visual half of
  the keyboard focus ring. The other half (a 1-px cosmetic ring
  drawn from ``paintEvent``) lives in
  :class:`ui.styles.standard_widgets.FocusRingMixin`.
* 5.3 *Micro Animations* — every :hover / :pressed / :focus rule is
  paired with a CSS ``transition: background-color 80ms, color 80ms,
  border 80ms`` so changes feel smooth instead of instantaneous.
  The duration matches ``motion.DURATION.PRESS_FEEDBACK`` (80 ms).

The :func:`L3Features.micro_animations` flag disables the transition
property at runtime via the ``MICRO_ANIMATIONS_OFF`` snippet
returned by :meth:`StyleSheet.micro_animations_disabled_suffix`.
"""

import logging

from ._colors import Colors

logger = logging.getLogger(__name__)

# L3 §5.3 — micro animation transition duration. Keep in sync with
# ``ui.styles.motion.Duration.PRESS_FEEDBACK`` (80 ms).
_MICRO_ANIMATION_TRANSITION = "80ms"
_MICRO_ANIMATION_EASING = "cubic-bezier(0.4, 0.0, 0.2, 1.0)"


class StyleSheet:
    """
    简约风格样式表生成器
    """

    @staticmethod
    def micro_animations_disabled_suffix() -> str:
        """Return a QSS suffix that overrides transitions to ``none``.

        Append this to a stylesheet when ``Settings.micro_animations``
        is ``False`` (or when ``low_end_mode`` is on).
        """
        return "* { transition-duration: 0ms !important; }\n"

    @staticmethod
    def get_button_style(theme: str) -> str:
        """获取按钮样式 - 苹果奶白风格"""
        transition = (
            f"transition: background-color {_MICRO_ANIMATION_TRANSITION} {_MICRO_ANIMATION_EASING}, "
            f"color {_MICRO_ANIMATION_TRANSITION} {_MICRO_ANIMATION_EASING}, "
            f"border-color {_MICRO_ANIMATION_TRANSITION} {_MICRO_ANIMATION_EASING};"
        )
        if theme == "dark":
            return f"""
                QPushButton {{
                    background-color: rgba(255, 255, 255, 0.12);
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 10px;
                    padding: 3px 12px;
                    color: rgba(255, 255, 255, 0.85);
                    font-size: 11px;
                    font-weight: 400;
                    min-height: 22px;
                    {transition}
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.20);
                    border: 1px solid rgba(255, 255, 255, 0.25);
                }}
                QPushButton:focus {{
                    border: 1px solid rgba(10, 132, 255, 0.78);
                }}
                QPushButton:pressed {{
                    background-color: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.14);
                }}
                QPushButton:default {{
                    background-color: #0A84FF;
                    border: 1px solid #0A84FF;
                    color: white;
                }}
                QPushButton:default:hover {{
                    background-color: #0077EA;
                }}
                QPushButton:default:pressed {{
                    background-color: #006FD6;
                    border: 1px solid #006FD6;
                }}
                QPushButton:disabled {{
                    background-color: rgba(255, 255, 255, 0.06);
                    color: rgba(235, 235, 245, 0.3);
                }}
            """
        else:
            return f"""
                QPushButton {{
                    background-color: rgba(255, 255, 255, 0.80);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 10px;
                    padding: 3px 12px;
                    color: rgba(28, 28, 30, 0.75);
                    font-size: 11px;
                    font-weight: 400;
                    min-height: 22px;
                    {transition}
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.95);
                    border: 1px solid rgba(0, 0, 0, 0.10);
                }}
                QPushButton:focus {{
                    border: 1px solid rgba(0, 122, 255, 0.55);
                }}
                QPushButton:pressed {{
                    background-color: rgba(240, 240, 245, 0.90);
                    border: 1px solid rgba(0, 0, 0, 0.12);
                }}
                QPushButton:default {{
                    background-color: #007AFF;
                    border: 1px solid #007AFF;
                    color: white;
                }}
                QPushButton:default:hover {{
                    background-color: #0A84FF;
                }}
                QPushButton:default:pressed {{
                    background-color: #006FD6;
                    border: 1px solid #006FD6;
                }}
                QPushButton:disabled {{
                    background-color: rgba(0, 0, 0, 0.04);
                    color: rgba(60, 60, 67, 0.3);
                }}
            """

    @staticmethod
    def get_input_style(theme: str) -> str:
        selection_bg = Colors.get_selection_bg(theme)
        selection_text = Colors.get_selection_text(theme)
        """获取输入框样式 - 紧凑版"""
        if theme == "dark":
            return """
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background-color: rgba(190, 190, 197, 0.22);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    padding: 4px 8px;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 400;
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid #0A84FF;
                    background-color: rgba(190, 190, 197, 0.28);
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
                    background-color: rgba(190, 190, 197, 0.12);
                    color: rgba(235, 235, 245, 0.3);
                }
            """.replace(
                "{selection_bg}", selection_bg
            ).replace(
                "{selection_text}", selection_text
            )
        else:
            return """
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background-color: #ffffff;
                    border: 1px solid rgba(0, 0, 0, 0.12);
                    border-radius: 6px;
                    padding: 4px 8px;
                    color: #1c1c1e;
                    font-size: 11px;
                    font-weight: 400;
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid #007AFF;
                    background-color: #ffffff;
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
                    background-color: #f5f5f7;
                    color: rgba(60, 60, 67, 0.3);
                }
            """.replace(
                "{selection_bg}", selection_bg
            ).replace(
                "{selection_text}", selection_text
            )

    @staticmethod
    def get_scrollbar_style(theme: str) -> str:
        """获取滚动条样式"""
        if theme == "dark":
            handle_color = "rgba(255, 255, 255, 80)"
            handle_hover = "rgba(255, 255, 255, 120)"
        else:
            handle_color = "rgba(0, 0, 0, 60)"
            handle_hover = "rgba(0, 0, 0, 100)"

        return f"""
            QScrollBar:vertical {{
                border: none; border-radius: 0;
                background: transparent;
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {handle_color};
                min-height: 30px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {handle_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QScrollBar:horizontal {{
                border: none; border-radius: 0;
                background: transparent;
                height: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {handle_color};
                min-width: 30px;
                border-radius: 3px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {handle_hover};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                background: none;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """

    @staticmethod
    def get_combobox_style(theme: str) -> str:
        selection_bg = Colors.get_selection_bg(theme)
        selection_hover_bg = Colors.get_selection_hover_bg(theme)
        selection_text = Colors.get_selection_text(theme)
        """获取下拉框样式"""
        if theme == "dark":
            return (
                """
                QComboBox {
                    background-color: rgba(190, 190, 197, 0.22);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 5px 8px;
                    padding-right: 25px;
                    color: rgba(255, 255, 255, 0.9);
                    min-height: 24px;
                    font-size: 12px;
                    margin: 0px;
                }
                QComboBox:hover {
                    border: 1px solid #0A84FF;
                    background-color: rgba(190, 190, 197, 0.30);
                }
                QComboBox:focus {
                    border: 1px solid #0A84FF;
                }
                QComboBox::drop-down {
                    border: none; border-radius: 0;
                    width: 20px;
                    subcontrol-position: center right;
                    subcontrol-origin: padding;
                    right: 5px;
                }
                QComboBox::down-arrow {
                    image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2.5 3.5L5 6L7.5 3.5' fill='none' stroke='white' stroke-width='1.2' stroke-linecap='round' stroke-linejoin='round'/></svg>");
                    width: 10px;
                    height: 10px;
                }
                QComboBox QAbstractItemView {
                    background-color: rgba(40, 40, 45, 200);
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 8px;
                    padding: 4px;
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                    color: #ffffff;
                    outline: none;
                }
                QComboBox QAbstractItemView::item {
                    padding: 4px 8px;
                    border-radius: 6px;
                    margin: 2px;
                }
                QComboBox QAbstractItemView::item:hover {
                    background-color: {selection_hover_bg};
                }
                QComboBox QAbstractItemView::item:selected {
                    background-color: {selection_bg};
                    color: {selection_text};
                    border: 1px solid rgba(10, 132, 255, 0.45);
                }
            """.replace(
                    "{selection_bg}", selection_bg
                )
                .replace("{selection_hover_bg}", selection_hover_bg)
                .replace("{selection_text}", selection_text)
            )
        else:
            return (
                """
                QComboBox {
                    background-color: rgba(255, 255, 255, 120);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 6px;
                    padding: 5px 8px;
                    padding-right: 25px;
                    color: #1c1c1e;
                    min-height: 24px;
                    font-size: 12px;
                    margin: 0px;
                }
                QComboBox:hover {
                    border: 1px solid #007AFF;
                    background-color: rgba(255, 255, 255, 180);
                }
                QComboBox:focus {
                    border: 1px solid #007AFF;
                }
                QComboBox::drop-down {
                    border: none; border-radius: 0;
                    width: 20px;
                    subcontrol-position: center right;
                    subcontrol-origin: padding;
                    right: 5px;
                }
                QComboBox::down-arrow {
                    image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2.5 3.5L5 6L7.5 3.5' fill='none' stroke='black' stroke-width='1.2' stroke-linecap='round' stroke-linejoin='round'/></svg>");
                    width: 10px;
                    height: 10px;
                }
                QComboBox QAbstractItemView {
                    background-color: rgba(255, 255, 255, 210);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 8px;
                    padding: 4px;
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                    color: #1c1c1e;
                    outline: none;
                }
                QComboBox QAbstractItemView::item {
                    padding: 4px 8px;
                    border-radius: 6px;
                    margin: 2px;
                }
                QComboBox QAbstractItemView::item:hover {
                    background-color: {selection_hover_bg};
                }
                QComboBox QAbstractItemView::item:selected {
                    background-color: {selection_bg};
                    color: {selection_text};
                    border: 1px solid rgba(0, 122, 255, 0.25);
                }
            """.replace(
                    "{selection_bg}", selection_bg
                )
                .replace("{selection_hover_bg}", selection_hover_bg)
                .replace("{selection_text}", selection_text)
            )

    @staticmethod
    def get_groupbox_style(theme: str) -> str:
        """获取分组框样式 - 极简风格"""
        if theme == "dark":
            return """
                QGroupBox {
                    font-weight: 400;
                    border: none; border-radius: 0;
                    margin-top: 10px;
                    padding-top: 24px;
                    font-size: 13px;
                    color: white;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 0px;
                    padding: 0px 0px 8px 0px;
                    background-color: transparent;
                    color: #ffffff;
                }
            """
        else:
            return """
                QGroupBox {
                    font-weight: 400;
                    border: none; border-radius: 0;
                    margin-top: 6px;
                    padding-top: 20px;
                    font-size: 13px;
                    color: #1c1c1e;
                }
                QGroupBox::title {
                    subcontrol-origin: padding;
                    subcontrol-position: top left;
                    left: 0px;
                    padding: 0px 0px 4px 0px;
                    background-color: transparent;
                    color: #1c1c1e;
                }
            """

    @staticmethod
    def get_slider_style(theme: str) -> str:
        """获取滑块样式"""
        accent = "#0A84FF" if theme == "dark" else "#007AFF"
        track_bg = "#3a3a3c" if theme == "dark" else "#D1D1D6"

        # 处理手柄边框，使其更柔和以避免毛刺感
        if theme == "dark":
            handle_border = "1px solid rgba(0, 0, 0, 0.2)"
            handle_bg = "#ffffff"
        else:
            handle_border = "1px solid rgba(0, 0, 0, 0.05)"
            handle_bg = "#ffffff"

        return f"""
            QSlider::groove:horizontal {{
                height: 4px;
                background: transparent;
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent};
                border-radius: 2px;
            }}
            QSlider::add-page:horizontal {{
                background: {track_bg};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {handle_bg};
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
                border: {handle_border};
            }}
            QSlider::handle:horizontal:hover {{
                background: #f8f8f8;
                border: 1px solid rgba(0, 0, 0, 0.1);
            }}
            QSlider::handle:horizontal:pressed {{
                background: #f0f0f0;
            }}
        """
