"""Styling mixin extracted from command_panel_window."""

from __future__ import annotations

import logging

from qt_compat import (
    QLineEdit,
)
from ui.styles.design_tokens import selection_bg_qss, selection_text_qss
from ui.utils.ui_scale import scale_qss

logger = logging.getLogger(__name__)


class CommandPanelStyleMixin:
    _theme: str

    def _apply_content_theme(self):
        if hasattr(self, "text"):
            self.style_plain_text(self.text)
        if hasattr(self, "list_widget"):
            self.style_list_widget(self.list_widget)
        if hasattr(self, "table"):
            self._style_table()
        buttons = [
            getattr(self, "run_btn", None),
            getattr(self, "cancel_btn", None),
            getattr(self, "copy_btn", None),
            getattr(self, "save_btn", None),
            getattr(self, "rerun_btn", None),
            getattr(self, "history_toggle_btn", None),
            *getattr(self, "action_buttons", []),
            getattr(self, "more_btn", None),
            getattr(self, "close_btn", None),
        ]
        self.style_buttons(*(button for button in buttons if button is not None))
        if hasattr(self, "command_input"):
            self._style_command_input()
        if hasattr(self, "_param_widgets"):
            self._style_param_inputs()
        if hasattr(self, "status_indicator"):
            self._style_status_label()
        if hasattr(self, "param_error_label"):
            self._style_param_error_label()
        if hasattr(self, "progress_bar"):
            self._style_progress()
        if hasattr(self, "history_list"):
            self.style_list_widget(self.history_list)
        if hasattr(self, "command_suggestion_popup"):
            self._style_command_suggestions()
        if hasattr(self, "history_label"):
            self.history_label.setStyleSheet(
                scale_qss("font-size: 11px; color: rgba(60,60,67,0.72); background: transparent;")
            )

    def _style_command_input(self):
        text, placeholder, border, bg = self._command_input_colors()
        selection_bg = selection_bg_qss(self._theme)
        selection_text = selection_text_qss(self._theme)
        if hasattr(self, "command_input_group"):
            self.command_input_group.setStyleSheet(
                scale_qss(
                    f"""
                QWidget {{
                    min-height: 28px;
                    border: 1px solid {border};
                    border-radius: 8px;
                    background: {bg};
                }}
            """
                )
            )
        self.command_input.setStyleSheet(
            scale_qss(
                f"""
            QLineEdit {{
                min-height: 28px;
                padding: 0 10px;
                border-radius: 0; border: none;
                border-radius: 8px;
                background: transparent;
                color: {text};
                selection-background-color: {selection_bg};
                selection-color: {selection_text};
            }}
            QLineEdit::placeholder {{
                color: {placeholder};
            }}
        """
            )
        )
        if hasattr(self, "history_toggle_btn"):
            self.history_toggle_btn.setStyleSheet(
                scale_qss(
                    f"""
                QPushButton {{
                    min-height: 28px;
                    padding: 0;
                    border-radius: 0; border: none;
                    border-top-right-radius: 8px;
                    border-bottom-right-radius: 8px;
                    background: transparent;
                    color: {placeholder};
                }}
                QPushButton:hover {{
                    background: transparent;
                    color: {text};
                }}
                QPushButton:pressed {{
                    background: transparent;
                    color: {text};
                }}
                QPushButton:checked, QPushButton:focus {{
                    background: transparent;
                    outline: none;
                }}
                QPushButton:disabled {{
                    color: rgba(128, 128, 128, 0.30);
                    background: transparent;
                }}
            """
                )
            )

    def _command_input_colors(self):
        if self._theme == "dark":
            return (
                "rgba(255, 255, 255, 0.9)",
                "rgba(255, 255, 255, 0.42)",
                "rgba(10, 132, 255, 0.82)",
                "rgba(255, 255, 255, 0.13)",
            )
        return (
            "rgba(28, 28, 30, 0.9)",
            "rgba(60, 60, 67, 0.45)",
            "rgba(0, 122, 255, 0.78)",
            "rgba(255, 255, 255, 0.70)",
        )

    def _style_param_input(self, edit: QLineEdit):
        text, placeholder, border, bg = self._command_input_colors()
        selection_bg = selection_bg_qss(self._theme)
        selection_text = selection_text_qss(self._theme)
        edit.setStyleSheet(
            scale_qss(
                f"""
            QLineEdit {{
                min-height: 28px;
                padding: 0 10px;
                border: 1px solid {border};
                border-radius: 8px;
                background: {bg};
                color: {text};
                selection-background-color: {selection_bg};
                selection-color: {selection_text};
            }}
            QLineEdit::placeholder {{
                color: {placeholder};
            }}
        """
            )
        )

    def _style_param_inputs(self):
        for _param, widget in self._param_widgets.values():
            if isinstance(widget, QLineEdit):
                self._style_param_input(widget)
                continue
            edit = widget.findChild(QLineEdit) if hasattr(widget, "findChild") else None
            if edit is not None:
                self._style_param_input(edit)

    def _style_status_label(self):
        kind = str(self.status_indicator._kind)
        self.status_indicator.set_status(kind, self._theme)

    def _style_param_error_label(self):
        color = "rgba(255, 99, 99, 0.92)" if self._theme == "dark" else "rgba(190, 40, 40, 0.92)"
        self.param_error_label.setStyleSheet(
            scale_qss(f"font-size: 11px; color: {color}; background: transparent; padding-left: 2px;")
        )

    def _style_table(self):
        if self._theme == "dark":
            text = "rgba(255, 255, 255, 0.9)"
            grid = "rgba(255, 255, 255, 0.12)"
            bg = "rgba(255, 255, 255, 0.04)"
            header = "rgba(255, 255, 255, 0.08)"
        else:
            text = "rgba(28, 28, 30, 0.9)"
            grid = "rgba(0, 0, 0, 0.08)"
            bg = "rgba(0, 0, 0, 0.02)"
            header = "rgba(0, 0, 0, 0.04)"
        selection_bg = selection_bg_qss(self._theme)
        selection_text = selection_text_qss(self._theme)
        self.table.setStyleSheet(
            scale_qss(
                f"""
            QTableWidget {{
                background: {bg};
                border: 1px solid {grid};
                border-radius: 8px;
                color: {text};
                gridline-color: {grid};
                selection-background-color: {selection_bg};
                selection-color: {selection_text};
            }}
            QHeaderView::section {{
                background: {header};
                color: {text};
                border-radius: 0; border: none;
                border-right: 1px solid {grid};
                padding: 5px;
            }}
        """
            )
        )
        self.style_scrollbars(self.table)

    def _style_progress(self):
        if self._theme == "dark":
            text = "rgba(255, 255, 255, 0.85)"
            bg = "rgba(255, 255, 255, 0.10)"
            chunk = "rgba(10, 132, 255, 0.86)"
        else:
            text = "rgba(28, 28, 30, 0.85)"
            bg = "rgba(0, 0, 0, 0.08)"
            chunk = "rgba(0, 122, 255, 0.82)"
        label_style = scale_qss(f"font-size: 12px; color: {text}; background: transparent;")
        self.progress_title.setStyleSheet(label_style)
        self.progress_detail.setStyleSheet(label_style)
        self.progress_bar.setStyleSheet(
            scale_qss(
                f"""
            QProgressBar {{
                border-radius: 0; border: none;
                border-radius: 4px;
                background: {bg};
                height: 8px;
                text-align: center;
                color: transparent;
            }}
            QProgressBar::chunk {{
                border-radius: 4px;
                background: {chunk};
            }}
        """
            )
        )

    def _style_command_suggestions(self):
        return
