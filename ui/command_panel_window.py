"""Independent command panel window."""

from __future__ import annotations

import logging
import os
import webbrowser

from core.command_execution_service import CommandExecutionRequest, CommandExecutionService
from core.command_registry import CommandParam, CommandResult
from core.data_models import ShortcutItem
from qt_compat import (
    QApplication,
    QCheckBox,
    QColor,
    QComboBox,
    QEvent,
    QFileDialog,
    QFont,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPainter,
    QPen,
    QPixmap,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSize,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QTextOption,
    QTimer,
    QWidget,
    pyqtSignal,
)
from ui.styles.style import Colors, PopupMenu
from ui.themed_tool_window import ThemedToolWindow

logger = logging.getLogger(__name__)

COMMAND_PANEL_SIZE_PRESETS = {
    "small": (300, 420),
    "medium": (433, 606),
    "large": (600, 840),
    "auto": None,
}

DISPLAY_TYPE_SIZE_DEFAULTS = {
    "text": "small",
    "kv": "small",
    "list": "medium",
    "table": "large",
    "log": "large",
    "progress": "small",
    "qr": "small",
    "confirm": "small",
}


class CommandHistoryDropButton(QPushButton):
    """Small self-painted down chevron used inside the command input."""

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setText("")
        self.setFlat(True)
        self.setAutoDefault(False)
        self.setDefault(False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            color = QColor(128, 128, 128, 85)
        else:
            color = QColor(128, 128, 128, 165)
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        cx = self.width() / 2 - 2
        cy = self.height() / 2 + 1
        half_w = 4.5
        half_h = 3.0
        painter.drawLine(int(cx - half_w), int(cy - half_h), int(cx), int(cy + half_h))
        painter.drawLine(int(cx), int(cy + half_h), int(cx + half_w), int(cy - half_h))


class CommandPanelWindow(ThemedToolWindow):
    """Command result, action, and future input surface."""

    result_ready = pyqtSignal(str, object, object, object)
    result_update = pyqtSignal(str, object, object)

    def __init__(self, data_manager, result_store, parent=None):
        self.data_manager = data_manager
        self.result_store = result_store
        self.execution_service = CommandExecutionService(result_store)
        self._current_result = None
        self._current_result_id = ""
        self._current_command_id = ""
        self._current_command_title = ""
        self._current_raw_input = ""
        self._current_args_text = ""
        self._current_context_meta = {}
        self._current_definition = None
        self._rendered_text = ""
        self._run_token = ""
        self._current_handle = None
        self._current_request = None
        self._current_shortcut = None
        self._param_widgets = {}
        self._history_expanded = False
        self._suppress_command_suggestions = False
        self._running = False
        self._closing_panel = False
        theme = getattr(data_manager.get_settings(), "theme", "light")
        super().__init__("命令面板", theme=theme, parent=parent)
        self._setup_ui()
        self._configure_window_interaction()
        self.setFocusPolicy(Qt.StrongFocus)
        self._apply_content_theme()
        self._apply_size_preset("medium")
        self.result_ready.connect(self._on_result_ready)
        self.result_update.connect(self._on_result_update)

    def _setup_ui(self):
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("搜索命令或参数")
        self.command_input.setCursor(Qt.IBeamCursor)
        self.command_input.setFocusPolicy(Qt.NoFocus)
        self.command_input.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.command_input.returnPressed.connect(self._rerun_from_input)
        self.command_input.textChanged.connect(self._on_command_input_changed)
        self.command_input.installEventFilter(self)
        app = QApplication.instance()
        if app is not None:
            try:
                app.focusChanged.connect(self._on_app_focus_changed)
            except Exception:
                pass

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 4, 0)
        input_row.setSpacing(8)

        self.command_input_group = QWidget()
        input_group_layout = QHBoxLayout(self.command_input_group)
        input_group_layout.setContentsMargins(0, 0, 0, 0)
        input_group_layout.setSpacing(0)
        input_group_layout.addWidget(self.command_input, 1)
        self.history_toggle_btn = CommandHistoryDropButton()
        self.history_toggle_btn.setFixedWidth(26)
        self.history_toggle_btn.setFixedHeight(28)
        self.history_toggle_btn.setToolTip("最近命令")
        self.history_toggle_btn.setFocusPolicy(Qt.NoFocus)
        self.history_toggle_btn.clicked.connect(self._show_history_menu)
        input_group_layout.addWidget(self.history_toggle_btn)
        input_row.addWidget(self.command_input_group, 1)

        self.run_btn = QPushButton("执行")
        self.run_btn.clicked.connect(self._rerun_from_input)
        input_row.addWidget(self.run_btn)
        self.cancel_btn = None
        self.content_layout.addLayout(input_row)

        self.param_container = QWidget()
        self.param_layout = QFormLayout(self.param_container)
        self.param_layout.setContentsMargins(0, 0, 4, 0)
        self.param_layout.setSpacing(6)
        self.param_container.setVisible(False)
        self.content_layout.addWidget(self.param_container)

        self.param_error_label = QLabel("")
        self.param_error_label.setWordWrap(True)
        self.param_error_label.setVisible(False)
        self.content_layout.addWidget(self.param_error_label)

        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        self.history_label = QLabel("最近命令")
        self.history_label.setVisible(False)
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(96)
        self.history_list.setVisible(False)
        self.history_list.itemClicked.connect(self._on_history_item_clicked)
        self.command_suggestion_popup = None
        self._command_suggestion_ids = []

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.text.setWordWrapMode(QTextOption.WrapAnywhere)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        font = QFont("Microsoft YaHei UI", 9)
        if not font.exactMatch():
            font = QFont("Segoe UI", 9)
        self.text.setFont(font)
        self.content_layout.addWidget(self.text, 1)

        self.table = QTableWidget()
        self.table.setVisible(False)
        self.content_layout.addWidget(self.table, 1)

        self.list_widget = QListWidget()
        self.list_widget.setVisible(False)
        self.content_layout.addWidget(self.list_widget, 1)

        self.progress_title = QLabel("")
        self.progress_title.setVisible(False)
        self.content_layout.addWidget(self.progress_title)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setVisible(False)
        self.content_layout.addWidget(self.progress_bar)
        self.progress_detail = QLabel("")
        self.progress_detail.setWordWrap(True)
        self.progress_detail.setVisible(False)
        self.content_layout.addWidget(self.progress_detail)

        self.qr_label = QLabel("")
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setVisible(False)
        self.content_layout.addWidget(self.qr_label, 1)

        self.copy_btn = QPushButton("复制")
        self.copy_btn.clicked.connect(self.copy_result)
        self.button_layout.addWidget(self.copy_btn)

        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_result)
        self.button_layout.addWidget(self.save_btn)

        self.rerun_btn = QPushButton("重新执行")
        self.rerun_btn.clicked.connect(self.rerun_current)
        self.rerun_btn.setEnabled(False)
        self.button_layout.addWidget(self.rerun_btn)

        self.action_buttons = []
        for _ in range(3):
            btn = QPushButton("")
            btn.hide()
            self.action_buttons.append(btn)
            self.button_layout.addWidget(btn)

        self.more_btn = QPushButton("更多")
        self.more_btn.clicked.connect(self._show_more_actions)
        self.more_btn.hide()
        self.button_layout.addWidget(self.more_btn)

        self.button_layout.addStretch()

        self.close_btn = None
        self._install_input_cancel_event_filters()

    def _install_input_cancel_event_filters(self):
        for widget in self.findChildren(QWidget):
            if widget is self.command_input:
                continue
            try:
                widget.installEventFilter(self)
            except Exception:
                pass

    def _configure_window_interaction(self):
        """Keep the panel from using QDialog's implicit Enter/Esc close behavior."""
        for button in self._panel_buttons():
            self._neutralize_button_default(button)
        try:
            self.close_btn_top.setToolTip("关闭")
            self.close_btn_top.setFocusPolicy(Qt.NoFocus)
            self._neutralize_button_default(self.close_btn_top)
            try:
                self.close_btn_top.clicked.disconnect()
            except Exception:
                pass
            self.close_btn_top.clicked.connect(self._close_panel)
        except Exception:
            pass

    def _panel_buttons(self):
        buttons = [
            getattr(self, "run_btn", None),
            getattr(self, "cancel_btn", None),
            getattr(self, "copy_btn", None),
            getattr(self, "save_btn", None),
            getattr(self, "rerun_btn", None),
            getattr(self, "history_toggle_btn", None),
            *getattr(self, "action_buttons", []),
            getattr(self, "more_btn", None),
        ]
        return [button for button in buttons if button is not None]

    @staticmethod
    def _neutralize_button_default(button):
        try:
            button.setAutoDefault(False)
            button.setDefault(False)
        except Exception:
            pass

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
        if hasattr(self, "status_label"):
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
            self.history_label.setStyleSheet(getattr(self.status_label, "styleSheet", lambda: "")())

    def _style_command_input(self):
        if self._theme == "dark":
            text = "rgba(255, 255, 255, 0.9)"
            placeholder = "rgba(255, 255, 255, 0.42)"
            border = "rgba(10, 132, 255, 0.82)"
            bg = "rgba(255, 255, 255, 0.13)"
        else:
            text = "rgba(28, 28, 30, 0.9)"
            placeholder = "rgba(60, 60, 67, 0.45)"
            border = "rgba(0, 122, 255, 0.78)"
            bg = "rgba(255, 255, 255, 0.70)"
        selection_bg = Colors.get_selection_bg(self._theme)
        selection_text = Colors.get_selection_text(self._theme)
        if hasattr(self, "command_input_group"):
            self.command_input_group.setStyleSheet(f"""
                QWidget {{
                    min-height: 28px;
                    border: 1px solid {border};
                    border-radius: 8px;
                    background: {bg};
                }}
            """)
        self.command_input.setStyleSheet(f"""
            QLineEdit {{
                min-height: 28px;
                padding: 0 10px;
                border: none;
                border-radius: 8px;
                background: transparent;
                color: {text};
                selection-background-color: {selection_bg};
                selection-color: {selection_text};
            }}
            QLineEdit::placeholder {{
                color: {placeholder};
            }}
        """)
        if hasattr(self, "history_toggle_btn"):
            self.history_toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    min-height: 28px;
                    padding: 0;
                    border: none;
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
            """)

    def _style_status_label(self):
        color = "rgba(255, 255, 255, 0.55)" if self._theme == "dark" else "rgba(60, 60, 67, 0.62)"
        self.status_label.setStyleSheet(f"font-size: 11px; color: {color}; background: transparent; padding-left: 2px;")

    def _style_param_error_label(self):
        color = "rgba(255, 99, 99, 0.92)" if self._theme == "dark" else "rgba(190, 40, 40, 0.92)"
        self.param_error_label.setStyleSheet(
            f"font-size: 11px; color: {color}; background: transparent; padding-left: 2px;"
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
        selection_bg = Colors.get_selection_bg(self._theme)
        selection_text = Colors.get_selection_text(self._theme)
        self.table.setStyleSheet(f"""
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
                border: none;
                border-right: 1px solid {grid};
                padding: 5px;
            }}
        """)
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
        label_style = f"font-size: 12px; color: {text}; background: transparent;"
        self.progress_title.setStyleSheet(label_style)
        self.progress_detail.setStyleSheet(label_style)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
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
        """)

    def _style_command_suggestions(self):
        return

    def set_theme(self, theme: str):
        super().set_theme(theme)
        self._apply_content_theme()

    def showEvent(self, event):
        self._closing_panel = False
        super().showEvent(event)
        self._clear_command_input_focus()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._reposition_command_suggestions()

    def hideEvent(self, event):
        self._closing_panel = True
        self._hide_command_suggestions()
        return super().hideEvent(event)

    def closeEvent(self, event):
        self._closing_panel = True
        self._hide_command_suggestions()
        return super().closeEvent(event)

    def _close_panel(self):
        self._closing_panel = True
        self._hide_command_suggestions()
        self._clear_command_input_focus()
        self.hide()

    def focus_command_input_later(self):
        if self._closing_panel:
            return
        QTimer.singleShot(0, self._focus_command_input)
        QTimer.singleShot(60, self._focus_command_input)
        QTimer.singleShot(160, self._focus_command_input)

    def _focus_command_input(self, move_to_end: bool = True):
        if self._closing_panel or not self.isVisible():
            return
        if not hasattr(self, "command_input"):
            return
        if self.command_input.isReadOnly():
            self.command_input.setReadOnly(False)
        self.command_input.setEnabled(True)
        self.setFocusProxy(self.command_input)
        self.command_input.setFocusPolicy(Qt.StrongFocus)
        self.command_input.setFocus(Qt.OtherFocusReason)
        if move_to_end:
            self.command_input.setCursorPosition(len(self.command_input.text()))
        self.command_input.update()

    def _clear_command_input_focus(self):
        try:
            self.setFocusProxy(None)
        except Exception:
            pass
        try:
            self.command_input.clearFocus()
            self.command_input.setFocusPolicy(Qt.NoFocus)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            event_type = event.type()
            if obj is self.command_input and event_type == QEvent.MouseButtonPress:
                self.command_input.setFocusPolicy(Qt.StrongFocus)
                self.setFocusProxy(self.command_input)
                self.command_input.setFocus(Qt.MouseFocusReason)
            elif obj is self.command_input and event_type == QEvent.FocusOut:
                QTimer.singleShot(0, self._hide_command_suggestions_if_input_inactive)
            elif obj is self.command_input and event_type == QEvent.FocusIn:
                if not self._closing_panel:
                    QTimer.singleShot(0, self._show_command_suggestions_for_current_input)
            elif event_type == QEvent.MouseButtonPress:
                if obj is getattr(self, "close_btn_top", None):
                    self._hide_command_suggestions()
                    return super().eventFilter(obj, event)
                if not self._is_command_input_or_suggestion_widget(obj):
                    self.command_input.clearFocus()
                    self._hide_command_suggestions()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if not self._is_point_inside_command_input(event.pos()):
            self.command_input.clearFocus()
            self._hide_command_suggestions()
        return super().mousePressEvent(event)

    def _on_app_focus_changed(self, _old, new):
        if new is self.command_input:
            return
        if self._is_command_input_or_suggestion_widget(new):
            return
        self._hide_command_suggestions()

    def _command_suggestions_visible(self) -> bool:
        popup = getattr(self, "command_suggestion_popup", None)
        return bool(popup is not None and popup.isVisible())

    def _hide_command_suggestions_if_input_inactive(self):
        if QApplication.focusWidget() is not self.command_input:
            self._hide_command_suggestions()

    def _show_command_suggestions_for_current_input(self):
        if QApplication.focusWidget() is self.command_input:
            self._show_command_suggestions(self.command_input.text())

    def _is_point_inside_command_input(self, pos) -> bool:
        group = getattr(self, "command_input_group", None)
        if group is None:
            return False
        try:
            top_left = group.mapTo(self, group.rect().topLeft())
            return group.rect().translated(top_left).contains(pos)
        except Exception:
            return False

    def _is_command_input_or_suggestion_widget(self, obj) -> bool:
        if obj is self.command_input or obj is getattr(self, "command_input_group", None):
            return True
        if isinstance(obj, QWidget):
            group = getattr(self, "command_input_group", None)
            if group is not None and (obj is group or group.isAncestorOf(obj)):
                return True
            popup = getattr(self, "command_suggestion_popup", None)
            if popup is not None and (obj is popup or popup.isAncestorOf(obj)):
                return True
        return False

    def accept(self):
        return

    def reject(self):
        return

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers() if hasattr(event, "modifiers") else Qt.NoModifier
        if key == Qt.Key_F4 and modifiers & Qt.AltModifier:
            event.accept()
            return
        if key == Qt.Key_Escape:
            if self._running:
                self.cancel_current()
            event.accept()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            focus = QApplication.focusWidget()
            if focus is self.command_input:
                if self._accept_current_command_suggestion():
                    event.accept()
                    return
                self._rerun_from_input()
            event.accept()
            return
        return super().keyPressEvent(event)

    def show_result(self, result_id: str):
        stored = self.result_store.get(result_id) if self.result_store is not None else None
        if stored is None:
            self.show_transient_result(CommandResult(success=False, message="未找到命令结果", error="结果不存在"))
            return
        self._set_running(False)
        self._current_result_id = stored.id
        self._current_result = stored.result
        self._current_shortcut = None
        self._current_command_id = stored.command_id
        self._current_command_title = stored.command_title
        self._current_raw_input = stored.raw_input
        self._current_args_text = self._parse_args_from_raw(stored.raw_input, stored.command_id)
        self._current_definition = self._lookup_command(stored.command_id)
        self._current_request = CommandExecutionRequest(
            command_id=stored.command_id,
            args_text=self._current_args_text,
            raw_input=stored.raw_input,
            source=stored.source,
            command_def=self._current_definition,
        )
        self.command_input.setText(stored.raw_input)
        self._defer_focus_command_input()
        self._hide_command_suggestions()
        self._render_params(self._current_definition)
        self._render_result(stored.result)
        self._update_subtitle("完成")
        self._refresh_history()

    def run_command(
        self, command_id: str = "", args_text: str = "", raw_input: str = "", context_meta: dict | None = None
    ):
        command_id = (command_id or "").strip()
        self._current_command_id = command_id
        self._current_shortcut = None
        self._current_args_text = args_text or ""
        self._current_raw_input = raw_input or (f"/{command_id} {args_text}".strip() if command_id else "")
        self._current_context_meta = dict(context_meta or {})
        self._current_definition = self._lookup_command(command_id)
        self._current_command_title = getattr(self._current_definition, "title", command_id) or command_id
        command_def = self._current_definition
        self.command_input.setText(self._current_raw_input)
        self._defer_focus_command_input()
        self._hide_command_suggestions()
        self._render_params(command_def)
        if getattr(command_def, "params", None) and not self._current_args_text:
            self._set_running(False)
            self._show_widget("text")
            self.text.setPlainText("请填写参数后执行。")
            self._rendered_text = "请填写参数后执行。"
            self._update_subtitle("等待输入")
            self._apply_size_for_result(CommandResult(display_type="text"), command_def)
            self._refresh_history()
            return
        self._execute_current_request()

    def run_shortcut(self, shortcut: ShortcutItem, raw_input: str = "", context_meta: dict | None = None):
        self._current_shortcut = shortcut
        self._current_definition = None
        self._current_command_id = getattr(shortcut, "id", "") or ""
        self._current_command_title = getattr(shortcut, "name", "") or self._current_command_id
        self._current_raw_input = raw_input or getattr(shortcut, "command", "") or self._current_command_title
        self._current_context_meta = dict(context_meta or {})
        self.command_input.setText(self._current_raw_input)
        self._defer_focus_command_input()
        self._hide_command_suggestions()
        self._render_shortcut_params(shortcut)
        if self._param_widgets:
            self._set_running(False)
            self._show_widget("text")
            self.text.setPlainText("请填写参数后执行。")
            self._rendered_text = "请填写参数后执行。"
            self._update_subtitle("等待输入")
            size_key = getattr(shortcut, "command_panel_size", "medium") or "medium"
            self._apply_size_for_result(CommandResult(display_type="text", payload={"window_size": size_key}), None)
            return
        self._execute_current_request()

    def _execute_current_request(self):
        if self._current_shortcut is not None:
            self._execute_current_shortcut_request()
            return
        command_def = self._current_definition
        args = self._collect_param_args(command_def)
        if args is None:
            return
        request = CommandExecutionRequest(
            command_id=self._current_command_id,
            args_text=self._current_args_text,
            raw_input=self._current_raw_input,
            context_meta=dict(self._current_context_meta),
            source=getattr(command_def, "source", ""),
            args=args,
            command_def=command_def,
        )
        self._current_request = request
        self._set_running(True)
        self._show_widget("text")
        self.text.setPlainText("执行中...")
        self._rendered_text = "执行中..."
        self._update_subtitle("执行中")
        self._apply_size_for_result(CommandResult(display_type="text"), command_def)
        handle = self.execution_service.run_registry_command(
            request,
            on_update=lambda token, result, cmd: self.result_update.emit(token, result, cmd),
            on_finished=lambda token, result, cmd, duration, result_id: self.result_ready.emit(
                token, result, cmd, {"duration": duration, "result_id": result_id}
            ),
        )
        self._current_handle = handle
        self._run_token = handle.request_id
        self._defer_focus_command_input()

    def _execute_current_shortcut_request(self):
        shortcut = self._current_shortcut
        args = self._collect_param_args(None)
        if args is None:
            return
        request = CommandExecutionRequest(
            command_id=getattr(shortcut, "id", "") or "",
            raw_input=self._current_raw_input,
            context_meta=dict(self._current_context_meta),
            source="shortcut",
            shortcut=shortcut,
            args=args,
        )
        self._current_request = request
        self._set_running(True)
        self._show_widget("text")
        self.text.setPlainText("执行中...")
        self._rendered_text = "执行中..."
        self._update_subtitle("执行中")
        size_key = getattr(shortcut, "command_panel_size", "medium") or "medium"
        self._apply_size_for_result(CommandResult(display_type="text", payload={"window_size": size_key}), None)
        def finished_callback(token, result, cmd, duration, result_id):
            self.result_ready.emit(token, result, cmd, {"duration": duration, "result_id": result_id})

        try:
            handle = self.execution_service.run_shortcut_command(
                request,
                on_update=lambda token, result, cmd: self.result_update.emit(token, result, cmd),
                on_finished=finished_callback,
            )
        except TypeError:
            handle = self.execution_service.run_shortcut_command(
                request,
                on_finished=finished_callback,
            )
        self._current_handle = handle
        self._run_token = handle.request_id
        self._defer_focus_command_input()

    def _defer_focus_command_input(self):
        return

    def show_transient_result(self, result: CommandResult, command_def=None):
        self._set_running(False)
        self._current_shortcut = None
        self._current_definition = command_def
        self._current_result_id = ""
        self._current_result = result
        self._render_result(result)
        self._update_subtitle("完成" if result.success else "失败")

    def _on_result_update(self, token: str, result: CommandResult, command_def):
        if token != self._run_token:
            return
        self._current_definition = command_def
        self._current_result = result
        self._render_result(result)
        self._update_subtitle("执行中")

    def _on_result_ready(self, token: str, result: CommandResult, command_def, duration: float):
        if token != self._run_token:
            return
        self._set_running(False)
        self._current_definition = command_def
        self._current_result = result
        result_id = ""
        actual_duration = duration
        if isinstance(duration, dict):
            result_id = str(duration.get("result_id") or "")
            actual_duration = duration.get("duration", 0.0)
        if result_id:
            self._current_result_id = result_id
        elif self.result_store is not None:
            self._current_result_id = self.result_store.add(
                result,
                command_id=getattr(command_def, "id", self._current_command_id),
                command_title=getattr(command_def, "title", self._current_command_title),
                raw_input=self._current_raw_input,
                source=getattr(command_def, "source", ""),
                duration=float(actual_duration or 0.0),
            )
        self._render_result(result)
        self._update_subtitle("完成" if result.success else "失败")
        self._refresh_history()

    def _render_params(self, command_def):
        self._clear_params()
        params = list(getattr(command_def, "params", []) or [])
        if not params:
            self.param_container.setVisible(False)
            self.param_error_label.setVisible(False)
            return
        for param in params:
            widget = self._create_param_widget(param)
            label = f"{param.name}{' *' if getattr(param, 'required', False) else ''}"
            self.param_layout.addRow(label, widget)
            self._param_widgets[param.name] = (param, widget)
        self.param_container.setVisible(True)
        self.param_error_label.setVisible(False)

    def _render_shortcut_params(self, shortcut):
        from core.data_models import ShortcutItem

        params = []
        for raw in ShortcutItem._normalize_command_params(getattr(shortcut, "command_params", [])):
            params.append(CommandParam(**raw))
        holder = type("ShortcutCommandDef", (), {"params": params})()
        self._render_params(holder)

    def _clear_params(self):
        self._param_widgets = {}
        while self.param_layout.count():
            item = self.param_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _create_param_widget(self, param: CommandParam):
        param_type = (param.type or "text").lower()
        if param_type == "choice":
            combo = QComboBox()
            combo.addItems([str(choice) for choice in (param.choices or [])])
            if param.default:
                idx = combo.findText(str(param.default))
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            return combo
        if param_type == "bool":
            checkbox = QCheckBox("")
            checkbox.setChecked(str(param.default).lower() in ("1", "true", "yes", "on", "是"))
            return checkbox
        if param_type in ("file", "folder"):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)
            edit = QLineEdit(str(param.default or ""))
            edit.setCursor(Qt.IBeamCursor)
            edit.setProperty("param_editor", True)
            button = QPushButton("选择")
            self._neutralize_button_default(button)

            def _choose():
                if param_type == "folder":
                    path = QFileDialog.getExistingDirectory(self, "选择文件夹", edit.text())
                else:
                    path, _ = QFileDialog.getOpenFileName(self, "选择文件", edit.text())
                if path:
                    edit.setText(path)

            button.clicked.connect(_choose)
            layout.addWidget(edit, 1)
            layout.addWidget(button)
            return row
        edit = QLineEdit(str(param.default or ""))
        edit.setCursor(Qt.IBeamCursor)
        if getattr(param, "sensitive", False):
            edit.setEchoMode(QLineEdit.Password)
        return edit

    def _collect_param_args(self, command_def) -> dict[str, str] | None:
        args = {}
        missing = []
        for name, (param, widget) in self._param_widgets.items():
            value = self._param_value(widget)
            if getattr(param, "required", False) and str(value).strip() == "":
                missing.append(name)
            args[name] = value
        if missing:
            message = f"请填写必填参数: {', '.join(missing)}"
            self.param_error_label.setText(message)
            self.param_error_label.setVisible(True)
            if self._current_result is None:
                self._show_widget("text")
                self.text.setPlainText(message)
            self._update_subtitle("参数不完整")
            return None
        self.param_error_label.setVisible(False)
        return args

    def _param_value(self, widget) -> str:
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QCheckBox):
            return "true" if widget.isChecked() else "false"
        if isinstance(widget, QLineEdit):
            return widget.text()
        edit = widget.findChild(QLineEdit) if hasattr(widget, "findChild") else None
        return edit.text() if edit is not None else ""

    def _on_command_input_changed(self, text: str):
        if self._suppress_command_suggestions:
            return
        if QApplication.focusWidget() is not self.command_input:
            return
        self._show_command_suggestions(text)

    def _show_command_suggestions(self, text: str):
        query = self._suggestion_query(text)
        if not query:
            self._hide_command_suggestions()
            return
        matches = self._find_command_suggestions(query)
        if not matches:
            self._hide_command_suggestions()
            return
        self._hide_command_suggestions()
        popup = PopupMenu(theme=self._theme, radius=8, parent=None)
        self._compact_history_menu(popup)
        width = self._history_menu_width()
        popup.setMinimumWidth(width)
        popup.setMaximumWidth(width)
        popup.setFixedWidth(width)
        self._command_suggestion_ids = []
        for cmd in matches:
            command_id = str(cmd.id)
            self._command_suggestion_ids.append(command_id)
            popup.add_action(command_id, lambda cid=command_id: self._apply_command_suggestion(cid), enabled=True)
        self.command_suggestion_popup = popup
        self._show_popup_menu_without_focus(popup)
        self._focus_command_input()

    def _show_popup_menu_without_focus(self, menu):
        try:
            flags = Qt.ToolTip | Qt.FramelessWindowHint
            no_focus_flag = getattr(Qt, "WindowDoesNotAcceptFocus", None)
            if no_focus_flag is not None:
                flags |= no_focus_flag
            menu.setWindowFlags(flags)
            menu.setAttribute(Qt.WA_ShowWithoutActivating, True)
            menu.setFocusPolicy(Qt.NoFocus)
        except Exception:
            pass
        self._move_popup_menu_to_input(menu)
        menu.show()
        menu.raise_()
        try:
            menu._apply_blur_effect()
        except Exception:
            pass

    def _move_popup_menu_to_input(self, menu):
        anchor = getattr(self, "command_input_group", self.command_input)
        pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        try:
            menu.adjustSize()
            menu._move_into_screen(pos)
        except Exception:
            menu.move(pos)

    def _reposition_command_suggestions(self):
        popup = getattr(self, "command_suggestion_popup", None)
        if popup is None or not popup.isVisible():
            return
        self._move_popup_menu_to_input(popup)

    @staticmethod
    def _suggestion_query(text: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return ""
        raw = raw[1:].strip() if raw.startswith("/") else raw
        first, _, _rest = raw.partition(" ")
        return first.strip()

    def _find_command_suggestions(self, query: str):
        try:
            from core import registry

            if registry is None:
                return []
            return list(registry.find(query))[:5]
        except Exception:
            return []

    def _hide_command_suggestions(self):
        try:
            if self.command_suggestion_popup is not None:
                self.command_suggestion_popup.hide()
        except Exception:
            pass

    def _on_command_suggestion_clicked(self, item):
        command_id = str(item.data(Qt.UserRole) or item.text() or "").strip()
        if command_id:
            self._apply_command_suggestion(command_id)

    def _accept_current_command_suggestion(self) -> bool:
        popup = getattr(self, "command_suggestion_popup", None)
        if popup is not None and popup.isVisible():
            return False
        return False

    def _apply_command_suggestion(self, command_id: str):
        command_id = (command_id or "").strip()
        if not command_id:
            return
        self._suppress_command_suggestions = True
        try:
            self.command_input.setText(f"/{command_id} ")
            self.command_input.setCursorPosition(len(self.command_input.text()))
        finally:
            self._suppress_command_suggestions = False
        self._hide_command_suggestions()
        self._focus_command_input()

    def _refresh_history(self):
        if self.result_store is None:
            return
        items = self.result_store.list()
        self.history_list.clear()
        for item in items:
            title = item.command_title or item.command_id or "命令结果"
            state = "成功" if item.result.success else "失败"
            duration = getattr(item, "duration", 0.0) or 0.0
            row = QListWidgetItem(f"{state}  {title}  {duration:.2f}s")
            row.setData(Qt.UserRole, item.id)
            self.history_list.addItem(row)
        visible = bool(items)
        self.history_label.setVisible(False)
        if hasattr(self, "history_toggle_btn"):
            self.history_toggle_btn.setText("")
            self.history_toggle_btn.setEnabled(visible)
            self.history_toggle_btn.setVisible(True)
        self.history_list.setVisible(False)

    def _toggle_history(self):
        self._show_history_menu()

    def _show_history_menu(self):
        self._hide_command_suggestions()
        if self.result_store is None:
            return
        items = self.result_store.list()
        if not items:
            return
        menu = PopupMenu(theme=self._theme, radius=8, parent=None)
        self._compact_history_menu(menu)
        width = self._history_menu_width()
        menu.setMinimumWidth(width)
        menu.setMaximumWidth(width)
        menu.setFixedWidth(width)
        for item in items:
            label = self._history_menu_label(item)
            menu.add_action(label, lambda result_id=item.id: self.show_result(str(result_id)), enabled=True)
        self._history_menu = menu
        anchor = getattr(self, "command_input_group", self.command_input)
        menu.popup(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _compact_history_menu(self, menu):
        if self._theme == "dark":
            text = "rgba(255,255,255,0.85)"
            hover = "rgba(255,255,255,0.10)"
            pressed = "rgba(255,255,255,0.16)"
            disabled = "rgba(255,255,255,110)"
        else:
            text = "rgba(28,28,30,0.85)"
            hover = "rgba(0,0,0,0.06)"
            pressed = "rgba(0,0,0,0.10)"
            disabled = "rgba(60,60,67,120)"
        compact_style = (
            "QPushButton{background:transparent;border:none;padding:4px 10px;margin:0px;"
            f"border-radius:6px;color:{text};font-size:11px;text-align:left;"
            "font-family:'Segoe UI','Microsoft YaHei UI',sans-serif;font-weight:400;}"
            f"QPushButton:hover{{background:{hover};color:{text};}}"
            f"QPushButton:pressed{{background:{pressed};}}"
            f"QPushButton:disabled{{color:{disabled};}}"
        )
        try:
            menu._layout.setContentsMargins(6, 6, 6, 6)
            menu._layout.setSpacing(2)
            menu._btn_style_dark = compact_style
            menu._btn_style_light = compact_style
        except Exception:
            pass

    def _history_menu_width(self) -> int:
        anchor = getattr(self, "command_input_group", self.command_input)
        return max(220, int(anchor.width()))

    @staticmethod
    def _history_menu_label(item) -> str:
        text = item.raw_input or item.command_title or item.command_id or "命令"
        text = " ".join(str(text).split())
        return text if len(text) <= 56 else f"{text[:53]}..."

    def _on_history_item_clicked(self, item):
        result_id = item.data(Qt.UserRole)
        if result_id:
            self.show_result(str(result_id))

    def cancel_current(self):
        handle = self._current_handle
        if handle is not None:
            handle.cancel()
        self._run_token = ""
        self._set_running(False)
        self._show_widget("text")
        self.text.setPlainText("命令执行已取消。")
        self._rendered_text = "命令执行已取消。"
        self._update_subtitle("已取消")

    def rerun_current(self):
        if self._current_shortcut is not None:
            self._execute_current_shortcut_request()
            return
        request = self._current_request
        if request is not None and request.command_id:
            self._current_command_id = request.command_id
            self._current_args_text = request.args_text
            self._current_raw_input = request.raw_input or self.command_input.text().strip()
            self._current_context_meta = dict(request.context_meta or {})
            self._current_definition = request.command_def or self._lookup_command(request.command_id)
            self._current_command_title = (
                getattr(self._current_definition, "title", request.command_id) or request.command_id
            )
            self.command_input.setText(self._current_raw_input)
            self._render_params(self._current_definition)
            self._execute_current_request()
            return
        self._rerun_from_input()

    @staticmethod
    def _parse_args_from_raw(raw_input: str, command_id: str) -> str:
        raw = (raw_input or "").strip()
        if not raw:
            return ""
        text = raw[1:].strip() if raw.startswith("/") else raw
        first, _, rest = text.partition(" ")
        return rest.strip() if first == command_id or first.endswith(command_id) else ""

    def _render_result(self, result: CommandResult):
        message = result.message or result.error or ("完成" if result.success else "执行失败")
        display_type = (result.display_type or "text").lower()
        if display_type in ("text", "log"):
            self._render_text_like(result, message, display_type)
        elif display_type == "table":
            self._render_table(result, message)
        elif display_type == "kv":
            self._render_kv(result, message)
        elif display_type == "list":
            self._render_list(result, message)
        elif display_type == "progress":
            self._render_progress(result, message)
        elif display_type == "qr":
            self._render_qr(result, message)
        elif display_type == "confirm":
            self._render_confirm(result, message)
        else:
            self._render_text_like(result, message, "text")
        self._render_actions(result)
        self._apply_size_for_result(result, self._current_definition)

    def _show_widget(self, name: str):
        widgets = {
            "text": self.text,
            "table": self.table,
            "list": self.list_widget,
            "progress_title": self.progress_title,
            "progress": self.progress_bar,
            "progress_detail": self.progress_detail,
            "qr": self.qr_label,
        }
        for key, widget in widgets.items():
            widget.setVisible(False)
        if name == "progress":
            self.progress_title.setVisible(True)
            self.progress_bar.setVisible(True)
            self.progress_detail.setVisible(True)
        else:
            widgets.get(name, self.text).setVisible(True)

    def _render_text_like(self, result: CommandResult, message: str, display_type: str):
        self._show_widget("text")
        payload = result.payload if isinstance(result.payload, dict) else {}
        font_family = "Consolas" if display_type == "log" or payload.get("monospace") else "Microsoft YaHei UI"
        font = QFont(font_family, 9)
        if not font.exactMatch() and font_family == "Consolas":
            font = QFont("Courier New", 9)
        self.text.setFont(font)
        self.text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.text.setWordWrapMode(QTextOption.WrapAnywhere)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._set_result_text_preserving_scroll(message, live_update=bool(payload.get("running")))
        self._rendered_text = message

    def _set_result_text_preserving_scroll(self, message: str, *, live_update: bool = False):
        scrollbar = self.text.verticalScrollBar()
        old_value = scrollbar.value()
        old_max = scrollbar.maximum()
        was_at_bottom = old_value >= max(0, old_max - 2)
        preserve_position = (live_update or self._running) and old_max > 0 and not was_at_bottom

        self.text.setPlainText(message)

        if preserve_position:
            scrollbar.setValue(min(old_value, scrollbar.maximum()))
        elif live_update or self._running:
            scrollbar.setValue(scrollbar.maximum())

    def _render_table(self, result: CommandResult, message: str):
        self._show_widget("table")
        payload = result.payload if isinstance(result.payload, dict) else {}
        rows = payload.get("rows") or []
        columns = payload.get("columns") or []
        if rows and not isinstance(rows[0], (list, tuple, dict)):
            rows = [[row] for row in rows]
        if rows and isinstance(rows[0], dict):
            if not columns:
                columns = list(rows[0].keys())
            matrix = [[row.get(col, "") for col in columns] for row in rows]
        else:
            matrix = [list(row) if isinstance(row, (list, tuple)) else [row] for row in rows]
            if not columns:
                col_count = max([len(row) for row in matrix] or [1])
                columns = [f"列 {idx + 1}" for idx in range(col_count)]
        self.table.clear()
        self.table.setColumnCount(len(columns) or 1)
        self.table.setRowCount(len(matrix))
        self.table.setHorizontalHeaderLabels([str(col) for col in (columns or ["结果"])])
        for row_idx, row in enumerate(matrix):
            for col_idx, value in enumerate(row[: self.table.columnCount()]):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        export_rows = ["\t".join(str(col) for col in (columns or ["结果"]))]
        export_rows.extend("\t".join(str(value) for value in row) for row in matrix)
        self._rendered_text = "\n".join(export_rows)
        if not matrix and message:
            self._render_text_like(result, message, "text")

    def _render_kv(self, result: CommandResult, message: str):
        payload = result.payload if isinstance(result.payload, dict) else {}
        items = payload.get("items")
        if items is None:
            items = [[key, value] for key, value in payload.items() if key != "window_size"]
        result.payload = {**payload, "columns": ["名称", "值"], "rows": items}
        self._render_table(result, message)

    def _render_list(self, result: CommandResult, message: str):
        self._show_widget("list")
        payload = result.payload if isinstance(result.payload, dict) else {}
        items = payload.get("items") or []
        self.list_widget.clear()
        fm = self.list_widget.fontMetrics()
        line_height = fm.height()
        vertical_padding = 17  # 8px padding top + 8px padding bottom + 1px border
        for item in items:
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("name") or "")
                status = str(item.get("status") or "")
                detail = str(item.get("detail") or item.get("output_summary") or item.get("error") or "")
                duration = item.get("duration", "")
                duration_text = f" ({duration:.2f}s)" if isinstance(duration, (int, float)) else ""
                text = f"[{status.upper() or 'INFO'}] {title}{duration_text}"
                if detail:
                    text += f"\n{detail}"
            else:
                text = str(item)
            qlwi = QListWidgetItem(text)
            line_count = text.count("\n") + 1
            qlwi.setSizeHint(QSize(0, line_count * line_height + vertical_padding))
            self.list_widget.addItem(qlwi)
        self._rendered_text = "\n".join(self.list_widget.item(i).text() for i in range(self.list_widget.count()))
        if not items:
            self.text.setPlainText(message)
            self._show_widget("text")
            self._rendered_text = message

    def _render_progress(self, result: CommandResult, message: str):
        self._show_widget("progress")
        payload = result.payload if isinstance(result.payload, dict) else {}
        title = str(payload.get("title") or message or "执行中")
        detail = str(payload.get("detail") or "")
        progress = result.progress
        current = payload.get("current")
        total = payload.get("total")
        if total:
            try:
                progress = float(current or 0) / float(total)
            except Exception:
                pass
        progress = max(0.0, min(1.0, float(progress or 0.0)))
        self.progress_title.setText(title)
        self.progress_detail.setText(detail)
        self.progress_bar.setValue(int(progress * 1000))
        self._rendered_text = "\n".join(part for part in [title, detail, f"{progress * 100:.0f}%"] if part)

    def _render_qr(self, result: CommandResult, message: str):
        payload = result.payload if isinstance(result.payload, dict) else {}
        image_path = payload.get("image_path")
        if image_path and os.path.exists(str(image_path)):
            self._show_widget("qr")
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                self.qr_label.setPixmap(pixmap.scaled(QSize(220, 220), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.qr_label.setText("")
                self._rendered_text = message
                return
        self._render_text_like(result, message, "text")

    def _render_confirm(self, result: CommandResult, message: str):
        payload = result.payload if isinstance(result.payload, dict) else {}
        detail = str(payload.get("detail") or payload.get("description") or "")
        body = "\n\n".join(part for part in [message, detail] if part)
        self._render_text_like(result, body or "Confirm action", "text")

    def _render_actions(self, result: CommandResult):
        self._all_actions = list(result.actions or [])
        for btn in self.action_buttons:
            btn.hide()
            try:
                btn.clicked.disconnect()
            except Exception:
                pass
        primary_actions = sorted(
            self._all_actions,
            key=lambda a: (not bool(getattr(a, "primary", False)), bool(getattr(a, "danger", False))),
        )
        for btn, action in zip(self.action_buttons, primary_actions[: len(self.action_buttons)]):
            btn.setText(action.label or self._action_default_label(action.type))
            btn.setEnabled(bool(getattr(action, "enabled", True)))
            btn.setProperty(
                "command_action_role",
                "danger"
                if getattr(action, "danger", False)
                else "primary"
                if getattr(action, "primary", False)
                else "",
            )
            self.style_buttons(btn)
            self._style_action_button(btn, action)
            self._neutralize_button_default(btn)
            btn.clicked.connect(lambda _checked=False, a=action: self._execute_action(a))
            btn.show()
        self.more_btn.setVisible(len(primary_actions) > len(self.action_buttons))
        self.copy_btn.setEnabled(bool(self._rendered_text))
        self.save_btn.setEnabled(bool(self._rendered_text))

    def _style_action_button(self, button, action):
        role = button.property("command_action_role")
        if not role:
            return
        if self._theme == "dark":
            primary_bg = "rgba(10, 132, 255, 0.82)"
            primary_hover = "rgba(64, 156, 255, 0.94)"
            danger_bg = "rgba(255, 69, 58, 0.78)"
            danger_hover = "rgba(255, 99, 92, 0.92)"
            disabled = "rgba(255, 255, 255, 0.28)"
        else:
            primary_bg = "rgba(0, 122, 255, 0.86)"
            primary_hover = "rgba(0, 98, 210, 0.92)"
            danger_bg = "rgba(215, 45, 45, 0.86)"
            danger_hover = "rgba(185, 35, 35, 0.94)"
            disabled = "rgba(60, 60, 67, 0.35)"
        if role == "danger":
            bg, hover = danger_bg, danger_hover
        else:
            bg, hover = primary_bg, primary_hover
        button.setStyleSheet(f"""
            QPushButton {{
                font-size: 11px;
                padding: 6px 10px;
                background: {bg};
                border: 1px solid {bg};
                border-radius: 6px;
                color: #ffffff;
            }}
            QPushButton:hover {{
                background-color: {hover};
                border: 1px solid {hover};
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background-color: rgba(0, 90, 200, 0.92);
                color: #ffffff;
            }}
            QPushButton:disabled {{
                color: {disabled};
                background: transparent;
                border: 1px solid rgba(128, 128, 128, 0.22);
            }}
        """)

    def _show_more_actions(self):
        actions = sorted(
            list(getattr(self, "_all_actions", [])),
            key=lambda a: (not bool(getattr(a, "primary", False)), bool(getattr(a, "danger", False))),
        )
        extra = actions[len(self.action_buttons) :]
        if not extra:
            return
        menu = PopupMenu(theme=self._theme, radius=10, parent=None)
        for action in extra:
            menu.add_action(
                action.label or self._action_default_label(action.type),
                lambda a=action: self._execute_action(a),
                enabled=bool(getattr(action, "enabled", True)),
            )
        menu.popup(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))

    def _update_subtitle(self, state: str):
        title = self._current_command_title or self._current_command_id or "命令"
        self.set_subtitle(f"{title} / {state}")
        self.status_label.setText(state)
        self.status_label.setVisible(False)

    def _set_running(self, running: bool):
        self._running = bool(running)
        self.run_btn.setEnabled(not running)
        if self.cancel_btn is not None:
            self.cancel_btn.setEnabled(running)
        self.rerun_btn.setEnabled((not running) and bool(self._current_command_id or self.command_input.text().strip()))

    def _rerun_from_input(self):
        raw = self.command_input.text().strip()
        if not raw:
            return
        if raw.startswith("/"):
            text = raw[1:].strip()
            command_id, _, args_text = text.partition(" ")
        else:
            command_id, _, args_text = raw.partition(" ")
        if command_id == self._current_command_id and self._param_widgets:
            self._current_args_text = args_text.strip()
            self._current_raw_input = raw
            self._execute_current_request()
            return
        self.run_command(
            command_id=command_id, args_text=args_text.strip(), raw_input=raw, context_meta=self._current_context_meta
        )

    def copy_result(self):
        text = self._rendered_text or self.text.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    def save_result(self):
        text = self._rendered_text or self.text.toPlainText()
        if not text:
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存命令结果", "", "文本文件 (*.txt);;所有文件 (*)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            except Exception as e:
                logger.warning("保存命令结果失败: %s", e)

    def _execute_action(self, action):
        if not getattr(action, "enabled", True):
            return
        if action.type == "copy" and action.value:
            QApplication.clipboard().setText(action.value)
        elif action.type in ("open_url", "create_shortcut") and action.value:
            webbrowser.open(action.value)
        elif action.type in ("open_file", "open_folder") and action.value:
            try:
                os.startfile(action.value)
            except Exception:
                logger.warning("打开路径失败: %s", action.value, exc_info=True)
        elif action.type == "save_text" and action.value:
            path, _ = QFileDialog.getSaveFileName(self, "保存文本", "", "文本文件 (*.txt);;所有文件 (*)")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(action.value)
        elif action.type == "save_file" and action.value:
            default_name = os.path.basename(action.value) if os.path.isfile(action.value) else "command-result"
            path, _ = QFileDialog.getSaveFileName(self, "保存文件", default_name, "所有文件 (*)")
            if path:
                import shutil

                shutil.copy2(action.value, path)
        elif action.type == "close_qr_server" and action.value:
            try:
                from core.commands import stop_qr_file_server

                stop_qr_file_server(int(action.value))
            except Exception as e:
                logger.warning("关闭 QR 文件服务器失败: %s", e)

    @staticmethod
    def _action_default_label(action_type: str) -> str:
        return {
            "copy": "复制",
            "open_url": "打开链接",
            "open_file": "打开文件",
            "open_folder": "打开文件夹",
            "save_text": "保存文本",
            "save_file": "保存文件",
            "create_shortcut": "创建快捷方式",
            "close_qr_server": "关闭服务器",
        }.get(action_type or "", action_type or "操作")

    def _lookup_command(self, command_id: str):
        if not command_id:
            return None
        try:
            from core import registry

            if registry is not None:
                return registry.get(command_id) or registry.get(registry.get_canonical(command_id))
        except Exception:
            pass
        return None

    def _apply_size_for_result(self, result: CommandResult, command_def=None):
        size_key = self._resolve_size_key(result, command_def)
        self._apply_size_preset(size_key)

    def _resolve_size_key(self, result: CommandResult, command_def=None) -> str:
        payload = result.payload if isinstance(result.payload, dict) else {}
        candidates = [
            payload.get("window_size"),
            getattr(command_def, "result_window_size", ""),
            DISPLAY_TYPE_SIZE_DEFAULTS.get((result.display_type or "text").lower()),
            "medium",
        ]
        for candidate in candidates:
            key = str(candidate or "").lower().strip()
            if key in COMMAND_PANEL_SIZE_PRESETS:
                return key
        return "medium"

    def _apply_size_preset(self, size_key: str):
        if size_key != "auto":
            width, height = COMMAND_PANEL_SIZE_PRESETS.get(size_key, COMMAND_PANEL_SIZE_PRESETS["medium"])
            self.setMinimumSize(QSize(0, 0))
            self.setMaximumSize(QSize(16777215, 16777215))
            self.setFixedSize(width, height)
            return

        small_w, small_h = COMMAND_PANEL_SIZE_PRESETS["small"]
        max_w, max_h = self._screen_max_size()
        text = self.text.toPlainText() if hasattr(self, "text") else ""
        line_count = max(1, len(text.splitlines()))
        longest = max([len(line) for line in text.splitlines()] or [0])
        width = min(max_w, max(small_w, min(760, 300 + longest * 7)))
        height = min(max_h, max(small_h, min(820, 260 + line_count * 18)))
        self.setMinimumSize(small_w, small_h)
        self.setMaximumSize(max_w, max_h)
        self.resize(width, height)

    def _screen_max_size(self) -> tuple[int, int]:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return 900, 700
        geo = screen.availableGeometry()
        return max(360, int(geo.width() * 0.8)), max(420, int(geo.height() * 0.8))
