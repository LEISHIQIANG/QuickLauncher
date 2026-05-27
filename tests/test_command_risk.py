import core.command_risk as command_risk
from core.command_risk import assess_command_risk
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


def test_powershell_execution_is_marked():
    item = ShortcutItem(type=ShortcutType.COMMAND, name="PowerShell")
    item.command_type = "powershell"
    item.command = "Get-Process"

    codes = {risk.code for risk in assess_command_risk(item)}

    assert "powershell_command" in codes


def test_command_risk_module_does_not_expose_execution_audit():
    assert not hasattr(command_risk, "audit_command_execution")


def test_command_risk_detects_runtime_variables():
    item = ShortcutItem(type=ShortcutType.COMMAND, name="Variables")
    item.command_type = "cmd"
    item.command = "echo {{clipboard:q}} {{selected_text:q}}"

    codes = {risk.code for risk in assess_command_risk(item)}

    assert "clipboard_variable" in codes
    assert "selected_text_variable" in codes


def test_command_risk_detects_expanded_dangerous_patterns():
    item = ShortcutItem(type=ShortcutType.COMMAND, name="Danger")
    item.command_type = "cmd"
    item.command = "powershell -ExecutionPolicy Bypass; sc stop Spooler; taskkill /f /im app.exe"

    codes = {risk.code for risk in assess_command_risk(item)}

    assert "powershell_exec_policy" in codes
    assert "service_control" in codes
    assert "taskkill_force" in codes
