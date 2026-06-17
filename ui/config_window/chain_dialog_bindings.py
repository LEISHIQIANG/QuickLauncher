"""Chain-dialog binding-field mixin.

Extracted from :mod:`ui.config_window.chain_dialog` as part of the
P1-06 file-split pass.  Hosts the ``input_binding`` /
``param_bindings`` / ``args`` text-edit helpers that round-trip
between the form widgets and the in-memory ``self._steps`` list.
"""

from __future__ import annotations


class ChainDialogBindingsMixin:
    """Round-trip helpers for the chain-step binding form fields.

    The host class is expected to expose:

    * :pyattr:`_selected_index` — current step index (or ``-1``)
    * :pyattr:`_steps` — list of step dicts
    * :pyattr:`_binding_loading` — re-entrancy guard
    * :pyattr:`input_binding_edit` / :pyattr:`param_bindings_edit` /
      :pyattr:`step_args_edit` — ``QLineEdit`` / ``QPlainTextEdit``
    """

    def _load_selected_binding_fields(self):
        if not all(hasattr(self, name) for name in ("input_binding_edit", "param_bindings_edit", "step_args_edit")):
            return
        self._binding_loading = True
        try:
            if not (0 <= self._selected_index < len(self._steps)):
                self.input_binding_edit.setText("")
                self.param_bindings_edit.setPlainText("")
                self.step_args_edit.setPlainText("")
                self.input_binding_edit.setEnabled(False)
                self.param_bindings_edit.setEnabled(False)
                self.step_args_edit.setEnabled(False)
                return
            step = self._steps[self._selected_index]
            self.input_binding_edit.setEnabled(True)
            self.param_bindings_edit.setEnabled(True)
            self.step_args_edit.setEnabled(True)
            self.input_binding_edit.setText(str(step.get("input_binding") or ""))
            self.param_bindings_edit.setPlainText(self._format_mapping(step.get("param_bindings") or {}))
            self.step_args_edit.setPlainText(self._format_mapping(step.get("args") or {}))
        finally:
            self._binding_loading = False

    def _sync_selected_binding_fields(self):
        if self._binding_loading or not (0 <= self._selected_index < len(self._steps)):
            return
        step = self._steps[self._selected_index]
        step["input_binding"] = self.input_binding_edit.text().strip()
        step["param_bindings"] = self._parse_mapping(self.param_bindings_edit.toPlainText())
        step["args"] = self._parse_mapping(self.step_args_edit.toPlainText())
        self._refresh_risk_analysis()

    @staticmethod
    def _parse_mapping(text: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in str(text or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                values[key] = value
        return values

    @staticmethod
    def _format_mapping(values: dict) -> str:
        if not isinstance(values, dict):
            return ""
        return "\n".join(f"{key}={value}" for key, value in values.items() if str(key).strip() and str(value).strip())


__all__ = ["ChainDialogBindingsMixin"]
