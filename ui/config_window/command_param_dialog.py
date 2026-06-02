"""Structured command-parameter editor dialog."""

from __future__ import annotations

from core.data_models import ShortcutItem
from qt_compat import QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout


class CommandParamDialog(QDialog):
    """Small form for one command parameter."""

    TYPES = ["text", "textarea", "password", "choice", "bool", "number", "file", "folder"]
    SOURCES = ["", "clipboard", "selected_text", "selected_file", "selected_file_dir", "last"]
    VALIDATORS = ["", "path", "file", "folder", "url", "domain", "ip", "port", "json", "regex", "number"]

    def __init__(self, param: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("参数")
        data = ShortcutItem._normalize_command_params([param or {"name": "param"}])
        self._initial = data[0] if data else {"name": "param"}
        self._setup_ui()
        self._load(self._initial)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(6)

        self.name_edit = QLineEdit()
        self.label_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(self.TYPES)
        self.required_cb = QCheckBox("")
        self.default_edit = QLineEdit()
        self.choices_edit = QLineEdit()
        self.placeholder_edit = QLineEdit()
        self.help_edit = QLineEdit()
        self.source_combo = QComboBox()
        self.source_combo.addItems(self.SOURCES)
        self.validator_combo = QComboBox()
        self.validator_combo.addItems(self.VALIDATORS)
        self.pattern_edit = QLineEdit()
        self.min_edit = QLineEdit()
        self.max_edit = QLineEdit()
        self.sensitive_cb = QCheckBox("")
        self.remember_cb = QCheckBox("")
        self.multiline_cb = QCheckBox("")
        self.advanced_cb = QCheckBox("")

        form.addRow("name", self.name_edit)
        form.addRow("label", self.label_edit)
        form.addRow("type", self.type_combo)
        form.addRow("required", self.required_cb)
        form.addRow("default", self.default_edit)
        form.addRow("choices", self.choices_edit)
        form.addRow("placeholder", self.placeholder_edit)
        form.addRow("help", self.help_edit)
        form.addRow("source", self.source_combo)
        form.addRow("validator", self.validator_combo)
        form.addRow("pattern", self.pattern_edit)
        form.addRow("min", self.min_edit)
        form.addRow("max", self.max_edit)
        form.addRow("sensitive", self.sensitive_cb)
        form.addRow("remember", self.remember_cb)
        form.addRow("multiline", self.multiline_cb)
        form.addRow("advanced", self.advanced_cb)
        layout.addLayout(form)

        row = QHBoxLayout()
        row.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        row.addWidget(cancel_btn)
        row.addWidget(ok_btn)
        layout.addLayout(row)

    def _load(self, param: dict):
        self.name_edit.setText(str(param.get("name") or ""))
        self.label_edit.setText(str(param.get("label") or ""))
        self.type_combo.setCurrentText(str(param.get("type") or "text"))
        self.required_cb.setChecked(bool(param.get("required", False)))
        self.default_edit.setText(str(param.get("default") or ""))
        self.choices_edit.setText("|".join(str(choice) for choice in param.get("choices", [])))
        self.placeholder_edit.setText(str(param.get("placeholder") or ""))
        self.help_edit.setText(str(param.get("help") or ""))
        self.source_combo.setCurrentText(str(param.get("source") or ""))
        self.validator_combo.setCurrentText(str(param.get("validator") or ""))
        self.pattern_edit.setText(str(param.get("pattern") or ""))
        self.min_edit.setText(str(param.get("min_value") or ""))
        self.max_edit.setText(str(param.get("max_value") or ""))
        self.sensitive_cb.setChecked(bool(param.get("sensitive", False)))
        self.remember_cb.setChecked(bool(param.get("remember", True)))
        self.multiline_cb.setChecked(bool(param.get("multiline", False)))
        self.advanced_cb.setChecked(bool(param.get("advanced", False)))

    def param(self) -> dict:
        raw = {
            "name": self.name_edit.text().strip(),
            "label": self.label_edit.text().strip(),
            "type": self.type_combo.currentText(),
            "required": self.required_cb.isChecked(),
            "default": self.default_edit.text(),
            "choices": [part.strip() for part in self.choices_edit.text().split("|") if part.strip()],
            "placeholder": self.placeholder_edit.text().strip(),
            "help": self.help_edit.text().strip(),
            "source": self.source_combo.currentText(),
            "validator": self.validator_combo.currentText(),
            "pattern": self.pattern_edit.text(),
            "min_value": self.min_edit.text().strip(),
            "max_value": self.max_edit.text().strip(),
            "sensitive": self.sensitive_cb.isChecked(),
            "remember": self.remember_cb.isChecked(),
            "multiline": self.multiline_cb.isChecked(),
            "advanced": self.advanced_cb.isChecked(),
        }
        normalized = ShortcutItem._normalize_command_params([raw])
        return normalized[0] if normalized else {}
