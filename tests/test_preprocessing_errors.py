"""Tests for core.preprocessing.errors."""

from __future__ import annotations

from core.preprocessing.errors import (
    PreprocessingResult,
    SecurityWarning,
    ValidationError,
)

# ---------------------------------------------------------------------------
# ValidationError
# ---------------------------------------------------------------------------


def test_validation_error_defaults():
    err = ValidationError(field="cmd", error_code="INVALID", message="bad")
    assert err.severity == "error"
    assert err.suggestion == ""


def test_validation_error_to_dict():
    err = ValidationError(
        field="cmd",
        error_code="INVALID",
        message="bad command",
        severity="warning",
        suggestion="check spelling",
    )
    d = err.to_dict()
    assert d == {
        "field": "cmd",
        "error_code": "INVALID",
        "message": "bad command",
        "severity": "warning",
        "suggestion": "check spelling",
    }


def test_validation_error_to_dict_defaults():
    err = ValidationError(field="x", error_code="E1", message="m")
    d = err.to_dict()
    assert d["severity"] == "error"
    assert d["suggestion"] == ""


# ---------------------------------------------------------------------------
# SecurityWarning
# ---------------------------------------------------------------------------


def test_security_warning_defaults():
    w = SecurityWarning(issue_type="injection", severity="high", description="d")
    assert w.mitigation == ""
    assert w.allow_override is False


def test_security_warning_to_dict():
    w = SecurityWarning(
        issue_type="injection",
        severity="critical",
        description="shell injection risk",
        mitigation="escape args",
        allow_override=True,
    )
    d = w.to_dict()
    assert d == {
        "issue_type": "injection",
        "severity": "critical",
        "description": "shell injection risk",
        "mitigation": "escape args",
        "allow_override": True,
    }


def test_security_warning_to_dict_defaults():
    w = SecurityWarning(issue_type="x", severity="low", description="d")
    d = w.to_dict()
    assert d["mitigation"] == ""
    assert d["allow_override"] is False


# ---------------------------------------------------------------------------
# PreprocessingResult - basic
# ---------------------------------------------------------------------------


def test_result_defaults():
    r = PreprocessingResult()
    assert r.success is True
    assert r.should_block is False
    assert r.errors == []
    assert r.warnings == []
    assert r.metadata == {}


def test_result_to_dict_empty():
    r = PreprocessingResult()
    d = r.to_dict()
    assert d["success"] is True
    assert d["errors"] == []
    assert d["warnings"] == []
    assert d["should_block"] is False
    assert d["metadata"] == {}


# ---------------------------------------------------------------------------
# PreprocessingResult.add_error
# ---------------------------------------------------------------------------


def test_add_error_sets_success_false():
    r = PreprocessingResult()
    err = ValidationError(field="f", error_code="E1", message="m")
    r.add_error(err)
    assert r.success is False
    assert r.should_block is True
    assert len(r.errors) == 1


def test_add_error_severity_info_does_not_block():
    r = PreprocessingResult()
    err = ValidationError(field="f", error_code="E1", message="m", severity="info")
    r.add_error(err)
    # severity != "error" so success stays True, should_block stays False
    assert r.success is True
    assert r.should_block is False


def test_add_error_severity_warning_does_not_block():
    r = PreprocessingResult()
    err = ValidationError(field="f", error_code="E1", message="m", severity="warning")
    r.add_error(err)
    assert r.success is True
    assert r.should_block is False


def test_add_multiple_errors():
    r = PreprocessingResult()
    r.add_error(ValidationError(field="a", error_code="E1", message="m1"))
    r.add_error(ValidationError(field="b", error_code="E2", message="m2", severity="info"))
    assert r.success is False  # first error set it
    assert len(r.errors) == 2


# ---------------------------------------------------------------------------
# PreprocessingResult.add_warning
# ---------------------------------------------------------------------------


def test_add_warning_low_severity_no_block():
    r = PreprocessingResult()
    w = SecurityWarning(issue_type="x", severity="low", description="d")
    r.add_warning(w)
    assert r.should_block is False
    assert r.success is True


def test_add_warning_high_severity_blocks():
    r = PreprocessingResult()
    w = SecurityWarning(issue_type="x", severity="high", description="d")
    r.add_warning(w)
    assert r.should_block is True
    assert r.success is True  # warnings don't change success


def test_add_warning_critical_severity_blocks():
    r = PreprocessingResult()
    w = SecurityWarning(issue_type="x", severity="critical", description="d")
    r.add_warning(w)
    assert r.should_block is True


def test_add_warning_high_with_override_does_not_block():
    r = PreprocessingResult()
    w = SecurityWarning(issue_type="x", severity="high", description="d", allow_override=True)
    r.add_warning(w)
    assert r.should_block is False


def test_add_warning_critical_with_override_does_not_block():
    r = PreprocessingResult()
    w = SecurityWarning(issue_type="x", severity="critical", description="d", allow_override=True)
    r.add_warning(w)
    assert r.should_block is False


def test_add_warning_medium_no_block():
    r = PreprocessingResult()
    w = SecurityWarning(issue_type="x", severity="medium", description="d")
    r.add_warning(w)
    assert r.should_block is False


def test_add_multiple_warnings():
    r = PreprocessingResult()
    r.add_warning(SecurityWarning(issue_type="a", severity="low", description="d1"))
    r.add_warning(SecurityWarning(issue_type="b", severity="high", description="d2"))
    assert r.should_block is True
    assert len(r.warnings) == 2


# ---------------------------------------------------------------------------
# PreprocessingResult.to_dict with content
# ---------------------------------------------------------------------------


def test_result_to_dict_with_errors_and_warnings():
    r = PreprocessingResult()
    r.add_error(ValidationError(field="f", error_code="E1", message="bad"))
    r.add_warning(SecurityWarning(issue_type="s", severity="low", description="d"))
    r.metadata["key"] = "value"

    d = r.to_dict()
    assert d["success"] is False
    assert d["should_block"] is True
    assert len(d["errors"]) == 1
    assert d["errors"][0]["field"] == "f"
    assert len(d["warnings"]) == 1
    assert d["warnings"][0]["issue_type"] == "s"
    assert d["metadata"] == {"key": "value"}
