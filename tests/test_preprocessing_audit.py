"""Unit tests for core/preprocessing/audit.py."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.preprocessing.audit import (
    _get_audit_log_path,
    log_rate_limit_exceeded,
    log_security_event,
    log_security_warning,
    log_validation_failure,
)


def test_get_audit_log_path_success(tmp_path):
    with patch("core.command_variables.get_config_dir", return_value=str(tmp_path)):
        p = _get_audit_log_path()
        assert p == os.path.join(str(tmp_path), "security_audit.log")


def test_get_audit_log_path_exception(monkeypatch):
    import core.command_variables as cv

    monkeypatch.setattr(cv, "get_config_dir", MagicMock(side_effect=Exception("error")))

    p = _get_audit_log_path()
    assert p == os.path.join("config", "security_audit.log")


def test_log_security_event_success(tmp_path):
    with patch("core.command_variables.get_config_dir", return_value=str(tmp_path)):
        log_security_event(
            event_type="test_event",
            severity="high",
            shortcut_id="s1",
            shortcut_name="name",
            command_type="cmd",
            issue_type="vuln",
            details="details",
            command_preview="echo hello",
            user_action="allowed",
        )

        log_path = Path(_get_audit_log_path())
        assert log_path.exists()

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1

        event = json.loads(lines[0])
        assert event["event_type"] == "test_event"
        assert event["severity"] == "high"
        assert event["shortcut_id"] == "s1"
        assert event["shortcut_name"] == "name"
        assert event["command_type"] == "cmd"
        assert event["issue_type"] == "vuln"
        assert event["details"] == "details"
        assert event["command_preview"] == "echo hello"
        assert event["user_action"] == "allowed"
        assert "timestamp" in event


def test_log_security_event_exception_handled():
    with patch("builtins.open", side_effect=OSError("write error")):
        log_security_event("event", "low")


def test_log_validation_failure(tmp_path):
    class MockError:
        severity = "critical"
        error_code = "bad_cmd"
        message = "unsafe input"

    with patch("core.command_variables.get_config_dir", return_value=str(tmp_path)):
        log_validation_failure("s1", [MockError()])
        log_validation_failure("s2", ["simple string error"])

        log_path = Path(_get_audit_log_path())
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        ev1 = json.loads(lines[0])
        assert ev1["event_type"] == "validation_failure"
        assert ev1["severity"] == "critical"
        assert ev1["issue_type"] == "bad_cmd"
        assert ev1["details"] == "unsafe input"

        ev2 = json.loads(lines[1])
        assert ev2["severity"] == "error"
        assert ev2["issue_type"] == "unknown"
        assert ev2["details"] == "simple string error"


def test_log_security_warning(tmp_path):
    class MockWarning:
        severity = "high"
        issue_type = "unsafe_var"
        description = "environment leak"

    with patch("core.command_variables.get_config_dir", return_value=str(tmp_path)):
        log_security_warning("s1", [MockWarning()])
        log_security_warning("s2", ["generic warning"])

        log_path = Path(_get_audit_log_path())
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        ev1 = json.loads(lines[0])
        assert ev1["event_type"] == "security_warning"
        assert ev1["severity"] == "high"
        assert ev1["issue_type"] == "unsafe_var"
        assert ev1["details"] == "environment leak"

        ev2 = json.loads(lines[1])
        assert ev2["severity"] == "medium"
        assert ev2["issue_type"] == "unknown"
        assert ev2["details"] == "generic warning"


def test_log_rate_limit_exceeded(tmp_path):
    with patch("core.command_variables.get_config_dir", return_value=str(tmp_path)):
        log_rate_limit_exceeded("s1", "burst")

        log_path = Path(_get_audit_log_path())
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1

        ev = json.loads(lines[0])
        assert ev["event_type"] == "rate_limit_exceeded"
        assert ev["severity"] == "medium"
        assert ev["shortcut_id"] == "s1"
        assert ev["issue_type"] == "rate_limit"
        assert "burst" in ev["details"]
