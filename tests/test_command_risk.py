import logging

from core.command_risk import assess_command_risk, audit_command_execution
from core.data_models import ShortcutItem, ShortcutType


def test_command_risk_detects_admin_and_delete_command():
    item = ShortcutItem(type=ShortcutType.COMMAND, name="Danger")
    item.command_type = "cmd"
    item.command = "rmdir /s /q C:\\Temp\\old"
    item.run_as_admin = True

    codes = {risk.code for risk in assess_command_risk(item)}

    assert "run_as_admin" in codes
    assert "shell_command" in codes
    assert "delete_tree" in codes


def test_admin_execution_is_info_level():
    item = ShortcutItem(type=ShortcutType.COMMAND, name="Admin")
    item.command_type = "cmd"
    item.command = "whoami"
    item.run_as_admin = True

    risks = {risk.code: risk.level for risk in assess_command_risk(item)}

    assert risks["run_as_admin"] == "info"


def test_admin_only_command_audit_logs_at_info(caplog):
    item = ShortcutItem(type=ShortcutType.COMMAND, name="Admin")
    item.command_type = "builtin"
    item.command = "/hosts"
    item.run_as_admin = True

    with caplog.at_level(logging.INFO, logger="core.command_risk"):
        audit_command_execution(item, item.command, command_type=item.command_type)

    assert any(record.levelno == logging.INFO for record in caplog.records)
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)


def test_command_risk_detects_inline_python():
    item = ShortcutItem(type=ShortcutType.COMMAND, name="Py")
    item.command_type = "python"
    item.python_execution_mode = "legacy_inline"

    assert [risk.code for risk in assess_command_risk(item)] == ["python_inline"]


def test_command_risk_detects_runtime_variables():
    item = ShortcutItem(type=ShortcutType.COMMAND, name="Variables")
    item.command_type = "cmd"
    item.command = "echo {clipboard:q} {selected_text:q}"

    codes = {risk.code for risk in assess_command_risk(item)}

    assert "clipboard_variable" in codes
    assert "selected_text_variable" in codes
