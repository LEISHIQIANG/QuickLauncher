"""Command parameter rendering and collection.

Extracted from :class:`ui.command_panel_window.CommandPanelWindow` in 1.6.3.6
to keep the param-rendering and param-collection code in a focused file.

The functions all take the panel as the first argument and read/write
the following panel attributes:

* ``self._param_widgets`` / ``self._input_param_names`` /
  ``self._current_input_values`` — per-render state
* ``self.param_layout`` / ``self.param_container`` /
  ``self.param_error_label`` / ``self.param_preview_label`` — Qt widgets
* ``self._style_param_input`` / ``self._neutralize_button_default`` —
  styling helpers on the panel
* ``self._show_widget`` / ``self._update_subtitle`` — result-area helpers

Public API on :class:`CommandPanelWindow` is unchanged.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from core.command_io import discover_input_variables, resolve_param_default
from core.command_param_validation import validate_param_value
from core.command_registry import CommandParam
from qt_compat import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    Qt,
    QWidget,
)
from ui.utils.safe_file_dialog import get_existing_directory, get_open_file_name
from ui.utils.ui_scale import sp

if TYPE_CHECKING:
    from .command_panel_window import CommandPanelWindow

logger = logging.getLogger(__name__)


# ── rendering ────────────────────────────────────────────────────


def clear_params(panel: CommandPanelWindow) -> None:
    panel._param_widgets = {}
    panel._input_param_names = {}
    panel._current_input_values = {}
    while panel.param_layout.count():
        item = panel.param_layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def render_params(panel: CommandPanelWindow, command_def) -> None:
    clear_params(panel)
    params = list(getattr(command_def, "params", []) or [])
    if not params:
        panel.param_container.setVisible(False)
        panel.param_error_label.setVisible(False)
        return
    for param in params:
        default_value = resolve_param_default(
            param,
            context_meta=panel._current_context_meta,
            last_args=panel._last_args_for_params,
        )
        widget = create_param_widget(panel, param, default_value)
        connect_param_preview_signal(panel, widget)
        label_text = getattr(param, "label", "") or param.name
        label = f"{label_text}{' *' if getattr(param, 'required', False) else ''}"
        panel.param_layout.addRow(label, widget)
        panel._param_widgets[param.name] = (param, widget)
    panel.param_container.setVisible(True)
    panel.param_error_label.setVisible(False)


def render_shortcut_params(panel: CommandPanelWindow, shortcut) -> None:
    from core.data_models import ShortcutItem

    params = []
    for raw in ShortcutItem._normalize_command_params(getattr(shortcut, "command_params", [])):
        params.append(CommandParam(**raw))
    holder = type("ShortcutCommandDef", (), {"params": params})()
    render_params(panel, holder)
    render_shortcut_input_params(panel, shortcut)


def render_shortcut_input_params(panel: CommandPanelWindow, shortcut) -> None:
    context_values = dict((panel._current_context_meta or {}).get("input_values") or {})
    context_value = str((panel._current_context_meta or {}).get("input") or "")
    for key, prompt in discover_input_variables(getattr(shortcut, "command", "") or ""):
        if key in context_values or (key == "input" and context_value):
            panel._current_input_values[key] = str(context_values.get(key) or context_value)
            continue
        name = f"__input__{key}"
        label = prompt or "input"
        param = CommandParam(
            name=name,
            type="textarea",
            required=True,
            label=label,
            multiline=True,
            remember=False,
        )
        widget = create_param_widget(panel, param, "")
        connect_param_preview_signal(panel, widget)
        panel.param_layout.addRow(f"{label} *", widget)
        panel._param_widgets[name] = (param, widget)
        panel._input_param_names[name] = key
    panel.param_container.setVisible(bool(panel._param_widgets))
    update_param_preview(panel)


def create_param_widget(
    panel: CommandPanelWindow,
    param: CommandParam,
    default_value: str | None = None,
):
    param_type = (param.type or "text").lower()
    value = str(default_value if default_value is not None else param.default or "")
    if param_type == "choice":
        combo = QComboBox()
        combo.addItems([str(choice) for choice in (param.choices or [])])
        if value:
            idx = combo.findText(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        if getattr(param, "help", ""):
            combo.setToolTip(str(param.help))
        panel._style_param_combobox(combo)
        return combo
    if param_type == "bool":
        checkbox = QCheckBox("")
        checkbox.setChecked(value.lower() in ("1", "true", "yes", "on", "是"))
        if getattr(param, "help", ""):
            checkbox.setToolTip(str(param.help))
        return checkbox
    if param_type == "textarea" or getattr(param, "multiline", False):
        edit = QPlainTextEdit(value)
        edit.setMinimumHeight(sp(72))
        if getattr(param, "placeholder", ""):
            edit.setPlaceholderText(str(param.placeholder))
        if getattr(param, "help", ""):
            edit.setToolTip(str(param.help))
        return edit
    if param_type in ("file", "folder"):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(sp(6))
        edit = QLineEdit(value)
        edit.setCursor(Qt.IBeamCursor)  # type: ignore[unused-ignore, attr-defined]
        edit.setProperty("param_editor", True)
        panel._style_param_input(edit)
        if getattr(param, "placeholder", ""):
            edit.setPlaceholderText(str(param.placeholder))
        if getattr(param, "help", ""):
            row.setToolTip(str(param.help))
        button = QPushButton("选择")
        panel._neutralize_button_default(button)
        panel._style_param_file_button(button)

        def _choose():
            if param_type == "folder":
                path = get_existing_directory(panel, "选择文件夹", edit.text())
            else:
                path, _ = get_open_file_name(panel, "选择文件", edit.text())
            if path:
                edit.setText(path)

        button.clicked.connect(_choose)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return row
    edit = QLineEdit(value)
    edit.setCursor(Qt.IBeamCursor)  # type: ignore[unused-ignore, attr-defined]
    panel._style_param_input(edit)
    if getattr(param, "placeholder", ""):
        edit.setPlaceholderText(str(param.placeholder))
    if getattr(param, "help", ""):
        edit.setToolTip(str(param.help))
    if getattr(param, "sensitive", False) or param_type == "password":
        edit.setEchoMode(QLineEdit.Password)
    return edit


def connect_param_preview_signal(panel: CommandPanelWindow, widget) -> None:
    try:
        if isinstance(widget, QComboBox):
            widget.currentTextChanged.connect(lambda _=None: update_param_preview(panel))
        elif isinstance(widget, QCheckBox):
            widget.stateChanged.connect(lambda _=None: update_param_preview(panel))
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(lambda _=None: update_param_preview(panel))
        elif isinstance(widget, QPlainTextEdit):
            widget.textChanged.connect(update_param_preview)
        else:
            edit = widget.findChild(QLineEdit) if hasattr(widget, "findChild") else None
            if edit is not None:
                edit.textChanged.connect(lambda _=None: update_param_preview(panel))
    except Exception as exc:
        logger.debug("连接参数预览信号失败: %s", exc, exc_info=True)


# ── collection ──────────────────────────────────────────────────


def param_value(widget) -> str:
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, QCheckBox):
        return "true" if widget.isChecked() else "false"
    if isinstance(widget, QLineEdit):
        return widget.text()
    if isinstance(widget, QPlainTextEdit):
        return widget.toPlainText()
    edit = widget.findChild(QLineEdit) if hasattr(widget, "findChild") else None
    return edit.text() if edit is not None else ""


def collect_param_args(panel: CommandPanelWindow, command_def) -> dict[str, str] | None:
    args: dict[str, str] = {}
    errors: list[str] = []
    input_values = dict((panel._current_context_meta or {}).get("input_values") or {})
    for name, (param, widget) in panel._param_widgets.items():
        value = param_value(widget)
        error = validate_param_value(param, value)
        if error:
            errors.append(error)
        input_key = panel._input_param_names.get(name)
        if input_key:
            input_values[input_key] = value
            continue
        args[name] = value
    if (
        errors
        and panel._current_shortcut is None
        and panel._current_args_text.strip()
        and not any(str(value).strip() for value in args.values())
    ):
        panel.param_error_label.setVisible(False)
        panel._current_input_values = input_values
        return {}
    if errors:
        message = "\n".join(errors)
        panel.param_error_label.setText(message)
        panel.param_error_label.setVisible(True)
        if panel._current_result is None:
            panel._show_widget("text")
            panel.text.setPlainText(message)
        panel._update_subtitle("参数不完整")
        return None
    panel.param_error_label.setVisible(False)
    panel._current_input_values = input_values
    update_param_preview(panel, args)
    return args


def update_param_preview(
    panel: CommandPanelWindow,
    args: dict[str, str] | None = None,
) -> None:
    if not getattr(panel, "_param_widgets", None):
        panel.param_preview_label.setVisible(False)
        panel.param_preview_label.setText("")
        return
    values: dict[str, str] = dict(args or {})
    input_values: dict[str, str] = {}
    for name, (_param, widget) in panel._param_widgets.items():
        value = param_value(widget)
        input_key = panel._input_param_names.get(name)
        if input_key:
            input_values[input_key] = value
            continue
        values[name] = value
    masked = {
        name: ("******" if bool(getattr(param, "sensitive", False)) and values.get(name) else values.get(name, ""))
        for name, (param, _widget) in panel._param_widgets.items()
        if name in values
    }
    if panel._current_shortcut is not None:
        command = str(getattr(panel._current_shortcut, "command", "") or "")

        def repl(match):
            key = match.group(1).strip()
            return str(masked.get(key, values.get(key, match.group(0))))

        preview = re.sub(r"\{\{param:([^}:]+)(?::q)?\}\}", repl, command)
        if input_values:
            preview += "    " + " ".join(f"input={value}" for value in input_values.values())
    else:
        preview_args = " ".join(f"{key}={value}" for key, value in masked.items() if str(value))
        preview = f"/{panel._current_command_id} {preview_args}".strip()
    panel.param_preview_label.setText(f"预览: {preview}" if preview else "")
    panel.param_preview_label.setVisible(bool(preview))


__all__ = [
    "clear_params",
    "render_params",
    "render_shortcut_params",
    "render_shortcut_input_params",
    "create_param_widget",
    "connect_param_preview_signal",
    "param_value",
    "collect_param_args",
    "update_param_preview",
]
