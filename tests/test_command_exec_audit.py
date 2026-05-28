from core.command_exec import build_command_execution_audit, known_shell_execution_entries
from core.data_models import ShortcutItem, ShortcutType


def test_command_execution_audit_marks_shell_without_confirmation():
    item = ShortcutItem(type=ShortcutType.COMMAND, name="Echo")
    item.command_type = "cmd"
    item.command = "echo ok"
    item.run_as_admin = True

    audit = build_command_execution_audit(item)

    assert audit.uses_shell is True
    assert audit.run_as_admin is True
    assert audit.requires_confirmation is False
    assert "shell_command" in audit.risk_codes


def test_command_execution_audit_marks_destructive_confirmation():
    item = ShortcutItem(type=ShortcutType.COMMAND, name="Delete")
    item.command_type = "bash"
    item.command = "rm -rf /tmp/old"

    audit = build_command_execution_audit(item)

    assert audit.uses_shell is False
    assert audit.requires_confirmation is True
    assert "rm_rf" in audit.risk_codes
    assert "critical" in audit.risk_levels


def test_known_shell_execution_entries_are_reviewed_and_unique():
    entries = known_shell_execution_entries()

    identifiers = [entry["identifier"] for entry in entries]
    assert len(identifiers) == len(set(identifiers))
    assert any(entry["python_shell_true"] for entry in entries)
    for entry in entries:
        assert entry["module"]
        assert entry["input_source"]
        assert entry["reason"]
        assert entry["mitigation"]
