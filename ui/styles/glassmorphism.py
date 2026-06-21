"""Glassmorphism stylesheet helpers — extracted from style."""

from __future__ import annotations

import logging

from ui.utils.ui_scale import get_scale_percent, scale_qss

from ._colors import Colors
from .style_sheet import StyleSheet

logger = logging.getLogger(__name__)


class Glassmorphism:
    """
    磨砂玻璃拟态样式生成器
    提供 Glassmorphism + Neumorphism 混合效果
    """

    # 样式表缓存：避免每次调用都重新生成大量字符串拼接
    _full_stylesheet_cache: dict[tuple[str, int], str] = {}

    @classmethod
    def clear_stylesheet_cache(cls) -> None:
        """清除缓存的样式表（DPI 缩放变化时调用）"""
        cls._full_stylesheet_cache.clear()

    @staticmethod
    def get_glassmorphism_container_style(theme: str) -> str:
        """获取磨砂玻璃容器背景样式（用于主窗口背景）"""
        if theme == "dark":
            return """
                background-color: rgba(28, 28, 30, 160);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            """
        else:
            return """
                background-color: rgba(242, 242, 247, 120);
                border: 1px solid rgba(0, 0, 0, 0.05);
                border-radius: 12px;
            """

    @staticmethod
    def get_neumorphism_button_style(theme: str) -> str:
        """获取拟态按钮样式（带柔和阴影）"""
        if theme == "dark":
            return """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(85, 85, 90, 0.9),
                        stop:0.5 rgba(75, 75, 80, 0.9),
                        stop:1 rgba(65, 65, 70, 0.9));
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 10px;
                    padding: 4px 16px;
                    color: rgba(255, 255, 255, 0.95);
                    font-size: 12px;
                    font-weight: 400;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(95, 95, 100, 0.95),
                        stop:0.5 rgba(85, 85, 90, 0.95),
                        stop:1 rgba(75, 75, 80, 0.95));
                    border: 1px solid rgba(255, 255, 255, 0.25);
                }
                QPushButton:focus {
                    border: 1px solid rgba(10, 132, 255, 0.78);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(55, 55, 60, 0.9),
                        stop:1 rgba(65, 65, 70, 0.9));
                    border: 1px solid rgba(255, 255, 255, 0.1);
                }
                QPushButton:default {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(10, 132, 255, 0.8),
                        stop:1 rgba(0, 100, 220, 0.8));
                    border: 1px solid rgba(255, 255, 255, 0.15);
                }
                QPushButton:disabled {
                    background: rgba(44, 44, 46, 0.4);
                    color: rgba(255, 255, 255, 0.3);
                }
            """
        else:
            return """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(255, 255, 255, 0.8),
                        stop:0.5 rgba(250, 250, 252, 0.8),
                        stop:1 rgba(240, 240, 245, 0.8));
                    border: 1px solid rgba(0, 0, 0, 0.06);
                    border-radius: 10px;
                    padding: 4px 16px;
                    color: rgba(28, 28, 30, 0.9);
                    font-size: 12px;
                    font-weight: 400;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(255, 255, 255, 0.9),
                        stop:1 rgba(245, 245, 250, 0.9));
                    border: 1px solid rgba(0, 0, 0, 0.1);
                }
                QPushButton:focus {
                    border: 1px solid rgba(0, 122, 255, 0.55);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(235, 235, 240, 0.9),
                        stop:1 rgba(245, 245, 250, 0.9));
                    border: 1px solid rgba(0, 0, 0, 0.12);
                }
                QPushButton:default {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(0, 122, 255, 0.8),
                        stop:1 rgba(0, 100, 220, 0.8));
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    color: #ffffff;
                }
                QPushButton:disabled {
                    background: rgba(242, 242, 247, 0.4);
                    color: rgba(60, 60, 67, 0.3);
                }
            """

    @staticmethod
    def get_flat_action_button_style(theme: str) -> str:
        """获取扁平操作按钮样式（与主配置窗口底部四按钮一致）"""
        if theme == "dark":
            btn_bg = "rgba(255,255,255,0.18)"
            btn_border = "rgba(255,255,255,0.22)"
            btn_hover = "rgba(255,255,255,0.28)"
            text_color = "rgba(255,255,255,0.85)"
        else:
            btn_bg = "rgba(255,255,255,0.75)"
            btn_border = "rgba(255,255,255,0.35)"
            btn_hover = "rgba(255,255,255,0.95)"
            text_color = "#1D1D1F"

        return scale_qss(
            f"""
            QPushButton {{
                font-size: 11px;
                padding: 4px 13px;
                background: {btn_bg};
                border: 1px solid {btn_border};
                border-radius: 10px;
                color: {text_color};
            }}
            QPushButton:hover {{ background-color: {btn_hover}; }}
            QPushButton:pressed {{ background-color: {btn_bg}; opacity: 0.8; }}
            QPushButton:disabled {{ background-color: rgba(255,255,255,0.3); color: #C7C7CC; }}
        """
        )

    @staticmethod
    def get_action_button_style(theme: str, is_compact: bool = False, is_delete: bool = False) -> str:
        """获取设置/配置窗口按钮的统一精细样式 (保证视觉 100% 一致)"""
        if is_delete:
            if theme == "dark":
                return scale_qss(
                    """
                    QPushButton {
                        font-size: 10px;
                        padding: 2px 4px;
                        margin: 0px;
                        background: rgba(244, 67, 54, 0.15);
                        border: 1px solid rgba(244, 67, 54, 0.3);
                        border-radius: 4px;
                        color: #ff5252;
                        font-weight: 400;
                    }
                    QPushButton:hover {
                        background-color: rgba(244, 67, 54, 0.25);
                        border: 1px solid rgba(244, 67, 54, 0.5);
                        color: #ff7979;
                    }
                    QPushButton:pressed { opacity: 0.7; }
                    QPushButton:disabled {
                        color: rgba(128,128,128,0.4);
                        background: rgba(128,128,128,0.08);
                        border: 1px solid rgba(128,128,128,0.15);
                    }
                """
                )
            else:
                return scale_qss(
                    """
                    QPushButton {
                        font-size: 10px;
                        padding: 2px 4px;
                        margin: 0px;
                        background: rgba(211, 47, 47, 0.08);
                        border: 1px solid rgba(211, 47, 47, 0.25);
                        border-radius: 4px;
                        color: #d32f2f;
                        font-weight: 400;
                    }
                    QPushButton:hover {
                        background-color: rgba(211, 47, 47, 0.15);
                        border: 1px solid rgba(211, 47, 47, 0.45);
                        color: #c62828;
                    }
                    QPushButton:pressed { opacity: 0.7; }
                    QPushButton:disabled {
                        color: rgba(128,128,128,0.4);
                        background: rgba(128,128,128,0.08);
                        border: 1px solid rgba(128,128,128,0.15);
                    }
                """
                )

        if theme == "dark":
            btn_bg = "rgba(255,255,255,0.18)"
            btn_border = "rgba(255,255,255,0.22)"
            btn_hover = "rgba(255,255,255,0.28)"
            btn_hover_text = "rgba(255,255,255,0.95)"
            text_color = "rgba(255,255,255,0.85)"
        else:
            btn_bg = "rgba(255,255,255,0.75)"
            btn_border = "rgba(255,255,255,0.35)"
            btn_hover = "rgba(255,255,255,0.95)"
            btn_hover_text = "rgba(28,28,30,0.9)"
            text_color = "rgba(28,28,30,0.75)"

        if is_compact:
            return scale_qss(
                f"""
                QPushButton {{
                    font-size: 10px;
                    padding: 2px 4px;
                    margin: 0px;
                    background: {btn_bg};
                    border: 1px solid {btn_border};
                    border-radius: 4px;
                    color: {text_color};
                    font-weight: 400;
                }}
                QPushButton:hover {{
                    background-color: {btn_hover};
                    color: {btn_hover_text};
                }}
                QPushButton:pressed {{ opacity: 0.7; }}
                QPushButton:disabled {{
                    color: rgba(128,128,128,0.4);
                    background: rgba(128,128,128,0.08);
                    border: 1px solid rgba(128,128,128,0.15);
                }}
                QPushButton:checked {{
                    background-color: rgba(10,132,255,0.85);
                    color: white;
                    border: 1px solid rgba(10,132,255,0.9);
                }}
            """
            )
        else:
            return scale_qss(
                f"""
                QPushButton {{
                    font-size: 11px;
                    padding: 5px 12px;
                    background: {btn_bg};
                    border: 1px solid {btn_border};
                    border-radius: 8px;
                    color: {text_color};
                    font-weight: 400;
                }}
                QPushButton:hover {{
                    background-color: {btn_hover};
                    color: {btn_hover_text};
                }}
                QPushButton:pressed {{ opacity: 0.7; }}
                QPushButton:disabled {{
                    color: rgba(128,128,128,0.4);
                    background: rgba(128,128,128,0.08);
                    border: 1px solid rgba(128,128,128,0.15);
                }}
                QPushButton:checked {{
                    background-color: rgba(10,132,255,0.85);
                    color: white;
                    border: 1px solid rgba(10,132,255,0.9);
                }}
            """
            )

    @staticmethod
    def get_neumorphism_input_style(theme: str) -> str:
        selection_bg = Colors.get_selection_bg(theme)
        selection_text = Colors.get_selection_text(theme)
        """获取拟态输入框样式"""
        if theme == "dark":
            return """
                /* Text Inputs */
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background: rgba(38, 38, 42, 0.7);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 3px 8px;
                    min-height: 24px;
                    font-size: 12px;
                    font-weight: 400;
                    margin: 0px;
                    color: rgba(255, 255, 255, 0.9);
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid rgba(10, 132, 255, 0.8);
                    background: rgba(42, 42, 46, 0.85);
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
                    background: rgba(38, 38, 42, 0.3);
                    color: rgba(255, 255, 255, 0.3);
                }

                /* SpinBox (Container) */
                QSpinBox {
                    background: rgba(38, 38, 42, 0.7);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 3px 8px;
                    min-height: 24px;
                    font-size: 12px;
                    margin: 0px;
                    color: rgba(255, 255, 255, 0.9);
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                }
                QSpinBox:focus, QSpinBox:hover {
                    border: 1px solid rgba(10, 132, 255, 0.8);
                    background: rgba(42, 42, 46, 0.85);
                }
                QSpinBox:disabled {
                    background: rgba(38, 38, 42, 0.3);
                    color: rgba(255, 255, 255, 0.3);
                }

                /* SpinBox Inner Edit - Reset to transparent */
                QSpinBox QLineEdit {
                    background: transparent;
                    border-radius: 0; border: none;
                    margin: 0;
                    padding: 0;
                    min-height: 0;
                }
                QSpinBox QLineEdit:focus {
                    background: transparent;
                    border-radius: 0; border: none;
                }
            """.replace(
                "{selection_bg}", selection_bg
            ).replace(
                "{selection_text}", selection_text
            )
        else:
            return """
                /* Text Inputs */
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background: rgba(255, 255, 255, 0.7);
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 6px;
                    padding: 3px 8px;
                    min-height: 24px;
                    font-size: 12px;
                    font-weight: 400;
                    margin: 0px;
                    color: rgba(28, 28, 30, 0.9);
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid rgba(0, 122, 255, 0.5);
                    background: rgba(255, 255, 255, 0.85);
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
                    background: rgba(242, 242, 247, 0.4);
                    color: rgba(60, 60, 67, 0.3);
                }

                /* SpinBox (Container) */
                QSpinBox {
                    background: rgba(255, 255, 255, 0.7);
                    border: 1px solid rgba(0, 0, 0, 0.06);
                    border-radius: 6px;
                    padding: 3px 8px;
                    min-height: 24px;
                    font-size: 12px;
                    margin: 0px;
                    color: rgba(28, 28, 30, 0.9);
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                }
                QSpinBox:focus, QSpinBox:hover {
                    border: 1px solid rgba(0, 122, 255, 0.5);
                    background: rgba(255, 255, 255, 0.85);
                }
                QSpinBox:disabled {
                    background: rgba(242, 242, 247, 0.4);
                    color: rgba(60, 60, 67, 0.3);
                }

                /* SpinBox Inner Edit - Reset to transparent */
                QSpinBox QLineEdit {
                    background: transparent;
                    border-radius: 0; border: none;
                    margin: 0;
                    padding: 0;
                    min-height: 0;
                }
                QSpinBox QLineEdit:focus {
                    background: transparent;
                    border-radius: 0; border: none;
                }
            """.replace(
                "{selection_bg}", selection_bg
            ).replace(
                "{selection_text}", selection_text
            )

    @staticmethod
    def get_neumorphism_groupbox_style(theme: str) -> str:
        """获取拟态分组框样式（内嵌效果）"""
        if theme == "dark":
            return """
                QGroupBox {
                    font-weight: 400;
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    margin-top: 18px;
                    padding-top: 10px;
                    font-size: 12px;
                    color: rgba(255, 255, 255, 0.9);
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 14px;
                    padding: 2px 10px;
                    background: transparent;
                    color: rgba(255, 255, 255, 0.5);
                    font-size: 11px;
                }
            """
        else:
            return """
                QGroupBox {
                    font-weight: 400;
                    background: rgba(0, 0, 0, 0.03);
                    border: 1px solid rgba(0, 0, 0, 0.06);
                    border-radius: 12px;
                    margin-top: 18px;
                    padding-top: 10px;
                    font-size: 12px;
                    color: rgba(28, 28, 30, 0.9);
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 14px;
                    padding: 2px 10px;
                    background: transparent;
                    color: rgba(0, 0, 0, 0.5);
                    font-size: 11px;
                }
            """

    @staticmethod
    def get_neumorphism_list_style(theme: str) -> str:
        selection_bg = Colors.get_selection_bg(theme)
        selection_hover_bg = Colors.get_selection_hover_bg(theme)
        selection_text = Colors.get_selection_text(theme)
        """获取拟态列表样式"""
        if theme == "dark":
            return (
                """
                QListWidget {
                    background: rgba(30, 30, 34, 0.5);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    outline: none;
                    padding: 4px;
                }
                QListWidget::item {
                    padding: 10px 12px;
                    border-radius: 8px;
                    margin: 2px 4px;
                    color: rgba(255, 255, 255, 0.85);
                }
                QListWidget::item:selected {
                    background: {selection_bg};
                    color: {selection_text};
                    border: 1px solid rgba(10, 132, 255, 0.42);
                }
                QListWidget::item:hover:!selected {
                    background: {selection_hover_bg};
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
                QListWidget {
                    background: rgba(240, 240, 245, 0.4);
                    border: 1px solid rgba(0, 0, 0, 0.05);
                    border-radius: 12px;
                    outline: none;
                    padding: 4px;
                }
                QListWidget::item {
                    padding: 10px 12px;
                    border-radius: 8px;
                    margin: 2px 4px;
                    color: rgba(28, 28, 30, 0.85);
                }
                QListWidget::item:selected {
                    background: {selection_bg};
                    color: {selection_text};
                    border: 1px solid rgba(0, 122, 255, 0.22);
                }
                QListWidget::item:hover:!selected {
                    background: {selection_hover_bg};
                }
            """.replace(
                    "{selection_bg}", selection_bg
                )
                .replace("{selection_hover_bg}", selection_hover_bg)
                .replace("{selection_text}", selection_text)
            )

    @staticmethod
    def get_full_glassmorphism_stylesheet(theme: str) -> str:
        """获取完整的磨砂玻璃拟态样式表（带缓存）"""
        cache_key = (theme, get_scale_percent())
        if cache_key in Glassmorphism._full_stylesheet_cache:
            return Glassmorphism._full_stylesheet_cache[cache_key]
        glass = Glassmorphism
        scrollbar = StyleSheet.get_scrollbar_style(theme)
        slider = StyleSheet.get_slider_style(theme)
        combobox = StyleSheet.get_combobox_style(theme)

        if theme == "dark":
            base = """
                QWidget {
                    background: transparent;
                    color: rgba(255, 255, 255, 0.9);
                    font-size: 13px;
                    font-weight: 400;
                }
                QLabel {
                    background: transparent;
                    color: rgba(255, 255, 255, 0.9);
                    font-size: 13px;
                    font-weight: 400;
                }
                QPushButton {
                    font-size: 13px;
                    font-weight: 400;
                    padding: 0px;
                    text-align: center;
                }
                QLineEdit, QTextEdit, QPlainTextEdit {
                    font-size: 13px;
                    font-weight: 400;
                }
                QCheckBox, QRadioButton {
                    font-size: 13px;
                    font-weight: 400;
                }
                QComboBox {
                    font-size: 13px;
                    font-weight: 400;
                }
                QListWidget {
                    font-size: 13px;
                    font-weight: 400;
                }
                QToolTip {
                    background: rgba(44, 44, 48, 240);
                    color: #ffffff;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-size: 11px;
                    font-weight: 400;
                }
                QScrollArea {
                    border-radius: 0; border: none;
                    background: transparent;
                }
                QStatusBar {
                    background: transparent;
                    color: rgba(142, 142, 147, 0.8);
                    font-size: 11px;
                    font-weight: 400;
                }
            """
        else:
            base = """
                QWidget {
                    background: transparent;
                    color: rgba(28, 28, 30, 0.9);
                    font-size: 13px;
                    font-weight: 400;
                }
                QLabel {
                    background: transparent;
                    color: rgba(28, 28, 30, 0.9);
                    font-size: 13px;
                    font-weight: 400;
                }
                QPushButton {
                    font-size: 13px;
                    font-weight: 400;
                    padding: 0px;
                    text-align: center;
                }
                QLineEdit, QTextEdit, QPlainTextEdit {
                    font-size: 13px;
                    font-weight: 400;
                }
                QCheckBox, QRadioButton {
                    font-size: 13px;
                    font-weight: 400;
                }
                QComboBox {
                    font-size: 13px;
                    font-weight: 400;
                }
                QListWidget {
                    font-size: 13px;
                    font-weight: 400;
                }
                QToolTip {
                    background: rgba(255, 255, 255, 240);
                    color: #1c1c1e;
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-size: 11px;
                    font-weight: 400;
                }
                QScrollArea {
                    border-radius: 0; border: none;
                    background: transparent;
                }
                QStatusBar {
                    background: transparent;
                    color: rgba(142, 142, 147, 0.8);
                    font-size: 11px;
                    font-weight: 400;
                }
            """

        result = scale_qss(
            base
            + glass.get_neumorphism_button_style(theme)
            + glass.get_neumorphism_input_style(theme)
            + glass.get_neumorphism_groupbox_style(theme)
            + glass.get_neumorphism_list_style(theme)
            + scrollbar
            + slider
            + combobox
        )
        Glassmorphism._full_stylesheet_cache[cache_key] = result
        return result


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
    """获取对话框完整样式表"""
    if settings is None:
        try:
            from ui.runtime_settings import current_settings

            settings = current_settings()
        except Exception as exc:
            logger.debug("Failed to load default settings: %s", exc, exc_info=True)

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
            border-radius: 0; border: none;
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
    try:
        from ui.styles.l3_features import show_focus_ring

        if show_focus_ring(settings):
            from ui.styles.focus_ring import focus_ring_qss

            focus_qss = focus_ring_qss(theme)
    except Exception as exc:
        logger.debug("Focus ring QSS load failed: %s", exc, exc_info=True)

    transitions_suffix = ""
    try:
        from ui.styles.l3_features import micro_animations

        if not micro_animations(settings):
            transitions_suffix = "* { transition: none !important; transition-property: none !important; transition-duration: 0ms !important; }\n"
    except Exception as exc:
        logger.debug("L3 micro-animations load failed: %s", exc, exc_info=True)

    full_css = (
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
    return scale_qss(full_css)


def get_button_stylesheet(theme: str, settings=None) -> str:
    """获取按钮样式表"""
    if settings is None:
        try:
            from ui.runtime_settings import current_settings

            settings = current_settings()
        except Exception as exc:
            logger.debug("Failed to load default settings: %s", exc, exc_info=True)

    base = StyleSheet.get_button_style(theme)

    transitions_suffix = ""
    try:
        from ui.styles.l3_features import micro_animations

        if not micro_animations(settings):
            transitions_suffix = "* { transition: none !important; transition-property: none !important; transition-duration: 0ms !important; }\n"
    except Exception as exc:
        logger.debug("L3 micro-animations load failed: %s", exc, exc_info=True)

    return scale_qss(base + transitions_suffix)
