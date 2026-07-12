"""Comprehensive tests for core/config_repairs.py."""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from core.config_repairs import (
    RepairIssue,
    RepairReport,
    apply_config_repairs,
    scan_config_repairs,
)

# ── RepairIssue.to_dict ─────────────────────────────────────────────────────


def test_repair_issue_to_dict_basic():
    issue = RepairIssue(code="test", path="x.y", message="something broke")
    d = issue.to_dict()
    assert d["code"] == "test"
    assert d["path"] == "x.y"
    assert d["message"] == "something broke"
    assert d["before"] == ""
    assert d["after"] == ""
    assert d["fixed"] is False


def test_repair_issue_to_dict_with_all_fields():
    issue = RepairIssue(
        code="legacy_variable_syntax",
        path="folders[0].items[1].command",
        message="Migrated legacy single-brace variable syntax",
        before="{clipboard}",
        after="{{clipboard}}",
        fixed=True,
    )
    d = issue.to_dict()
    assert d["code"] == "legacy_variable_syntax"
    assert d["path"] == "folders[0].items[1].command"
    assert d["message"] == "Migrated legacy single-brace variable syntax"
    assert d["before"] == "{clipboard}"
    assert d["after"] == "{{clipboard}}"
    assert d["fixed"] is True


# ── RepairReport properties and methods ─────────────────────────────────────


def test_repair_report_empty():
    report = RepairReport()
    assert report.issues == []
    assert report.repaired == 0
    assert report.changed is False
    assert report.problem_count == 0


def test_repair_report_add_fixed_issue():
    report = RepairReport()
    issue = RepairIssue(code="c", path="p", message="m", fixed=True)
    report.add(issue)
    assert report.repaired == 1
    assert report.changed is True
    assert report.problem_count == 0


def test_repair_report_add_unfixed_issue():
    report = RepairReport()
    issue = RepairIssue(code="c", path="p", message="m", fixed=False)
    report.add(issue)
    assert report.repaired == 0
    assert report.changed is False
    assert report.problem_count == 1


def test_repair_report_mixed_issues():
    report = RepairReport()
    report.add(RepairIssue(code="a", path="p1", message="m", fixed=True))
    report.add(RepairIssue(code="b", path="p2", message="m", fixed=False))
    report.add(RepairIssue(code="c", path="p3", message="m", fixed=True))
    assert report.repaired == 2
    assert report.changed is True
    assert report.problem_count == 1


def test_repair_report_extend():
    r1 = RepairReport()
    r1.add(RepairIssue(code="a", path="p1", message="m", fixed=True))
    r2 = RepairReport()
    r2.add(RepairIssue(code="b", path="p2", message="m", fixed=False))
    r2.add(RepairIssue(code="c", path="p3", message="m", fixed=True))
    r1.extend(r2)
    assert r1.repaired == 2  # 1 own + 1 from r2
    assert len(r1.issues) == 3
    assert r1.problem_count == 1


def test_repair_report_extend_empty():
    r1 = RepairReport()
    r1.add(RepairIssue(code="a", path="p1", message="m", fixed=True))
    r1.extend(RepairReport())
    assert r1.repaired == 1
    assert len(r1.issues) == 1


def test_repair_report_to_dict():
    report = RepairReport()
    report.add(RepairIssue(code="x", path="p", message="m", fixed=True))
    report.add(RepairIssue(code="y", path="q", message="n", fixed=False))
    d = report.to_dict()
    assert d["changed"] is True
    assert d["repaired"] == 1
    assert d["problem_count"] == 1
    assert len(d["issues"]) == 2
    assert d["issues"][0]["code"] == "x"
    assert d["issues"][1]["code"] == "y"


def test_repair_report_to_dict_empty():
    d = RepairReport().to_dict()
    assert d["changed"] is False
    assert d["repaired"] == 0
    assert d["problem_count"] == 0
    assert d["issues"] == []


# ── scan_config_repairs with mocked dependencies ────────────────────────────


def _mock_migrate(monkeypatch, return_value=None):
    """Mock migrate_legacy_variable_syntax to return its input or a fixed value."""
    fn = MagicMock(side_effect=lambda text, include_url=False: return_value if return_value is not None else text)
    monkeypatch.setattr("core.config_repairs.migrate_legacy_variable_syntax", fn)
    return fn


def _mock_find_unknown(monkeypatch, unknowns=None):
    """Mock find_unknown_variable_specs to return a fixed list."""
    fn = MagicMock(return_value=unknowns or [])
    monkeypatch.setattr("core.config_repairs.find_unknown_variable_specs", fn)
    return fn


def test_scan_with_clean_data_no_issues(monkeypatch):
    _mock_migrate(monkeypatch)
    _mock_find_unknown(monkeypatch)
    from core.data_models import AppData

    data = AppData()
    data.folders = []
    report = scan_config_repairs(data)
    assert report.repaired == 0
    assert len(report.issues) == 0


def test_scan_with_empty_folders(monkeypatch):
    _mock_migrate(monkeypatch)
    _mock_find_unknown(monkeypatch)
    report = scan_config_repairs({"folders": [], "version": "1.0"})
    assert report.repaired == 0
    assert len(report.issues) == 0


def test_scan_detects_legacy_syntax_not_applied(monkeypatch):
    """Scan mode detects legacy syntax but does NOT apply the fix."""
    _mock_migrate(monkeypatch, return_value="{{clipboard}}")
    _mock_find_unknown(monkeypatch)
    from core.data_models import AppData, Folder, ShortcutItem, ShortcutType

    item = ShortcutItem()
    item.id = "1"
    item.type = ShortcutType.COMMAND
    item.command = "{clipboard}"
    folder = Folder()
    folder.id = "f1"
    folder.items = [item]
    data = AppData()
    data.folders = [folder]
    report = scan_config_repairs(data)
    legacy_issues = [i for i in report.issues if i.code == "legacy_variable_syntax"]
    assert len(legacy_issues) >= 1
    for issue in legacy_issues:
        assert issue.fixed is False


def test_apply_detects_and_fixes_legacy_syntax(monkeypatch):
    """Apply mode detects legacy syntax AND applies the fix."""
    _mock_migrate(monkeypatch, return_value="{{clipboard}}")
    _mock_find_unknown(monkeypatch)
    from core.data_models import AppData, Folder, ShortcutItem, ShortcutType

    item = ShortcutItem()
    item.id = "1"
    item.type = ShortcutType.COMMAND
    item.command = "{clipboard}"
    folder = Folder()
    folder.id = "f1"
    folder.items = [item]
    data = AppData()
    data.folders = [folder]
    report = apply_config_repairs(data)
    legacy_issues = [i for i in report.issues if i.code == "legacy_variable_syntax"]
    assert len(legacy_issues) >= 1
    for issue in legacy_issues:
        assert issue.fixed is True
    assert report.repaired >= 1
    assert report.changed is True


def test_scan_detects_unknown_variables(monkeypatch):
    _mock_migrate(monkeypatch)
    _mock_find_unknown(monkeypatch, unknowns=["badvar"])
    from core.data_models import AppData, Folder, ShortcutItem, ShortcutType

    item = ShortcutItem()
    item.id = "1"
    item.type = ShortcutType.COMMAND
    item.command = "{{badvar}}"
    folder = Folder()
    folder.id = "f1"
    folder.items = [item]
    data = AppData()
    data.folders = [folder]
    report = scan_config_repairs(data)
    unknown_issues = [i for i in report.issues if i.code == "unknown_variable"]
    assert len(unknown_issues) >= 1
    for issue in unknown_issues:
        assert issue.fixed is False
        assert "badvar" in issue.message


def test_scan_with_dict_input(monkeypatch):
    _mock_migrate(monkeypatch)
    _mock_find_unknown(monkeypatch)
    data = {"folders": [], "version": "1.0"}
    report = scan_config_repairs(data)
    assert report.repaired == 0
    assert report.changed is False


def test_scan_with_invalid_type_returns_issue():
    """Non-dict, non-AppData input produces an invalid_config issue."""
    report = scan_config_repairs(42)  # type: ignore[arg-type]
    assert len(report.issues) == 1
    assert report.issues[0].code == "invalid_config"
    assert report.issues[0].path == "$"
    assert report.issues[0].fixed is False


def test_scan_with_none_returns_issue():
    report = scan_config_repairs(None)  # type: ignore[arg-type]
    assert len(report.issues) == 1
    assert report.issues[0].code == "invalid_config"


def test_scan_with_string_returns_issue():
    report = scan_config_repairs("not a config")  # type: ignore[arg-type]
    assert len(report.issues) == 1
    assert report.issues[0].code == "invalid_config"


def test_apply_with_invalid_type_returns_issue():
    report = apply_config_repairs(3.14)  # type: ignore[arg-type]
    assert len(report.issues) == 1
    assert report.issues[0].code == "invalid_config"


def test_url_type_checks_url_and_browser_args_fields(monkeypatch):
    """URL-type shortcuts should check 'url' and 'preferred_browser_args' fields."""
    migrate_fn = MagicMock(side_effect=lambda text, include_url=False: text)
    find_fn = MagicMock(return_value=[])
    monkeypatch.setattr("core.config_repairs.migrate_legacy_variable_syntax", migrate_fn)
    monkeypatch.setattr("core.config_repairs.find_unknown_variable_specs", find_fn)
    from core.data_models import AppData, Folder, ShortcutItem, ShortcutType

    item = ShortcutItem()
    item.id = "1"
    item.type = ShortcutType.URL
    item.url = "https://example.com"
    item.preferred_browser_args = "--incognito"
    folder = Folder()
    folder.id = "f1"
    folder.items = [item]
    data = AppData()
    data.folders = [folder]
    scan_config_repairs(data)
    # migrate should have been called for both url and preferred_browser_args
    call_args = list(migrate_fn.call_args_list)
    assert len(call_args) >= 2


def test_file_type_checks_target_args_field(monkeypatch):
    """FILE-type shortcuts should check 'target_args' field."""
    migrate_fn = MagicMock(side_effect=lambda text, include_url=False: text)
    find_fn = MagicMock(return_value=[])
    monkeypatch.setattr("core.config_repairs.migrate_legacy_variable_syntax", migrate_fn)
    monkeypatch.setattr("core.config_repairs.find_unknown_variable_specs", find_fn)
    from core.data_models import AppData, Folder, ShortcutItem, ShortcutType

    item = ShortcutItem()
    item.id = "1"
    item.type = ShortcutType.FILE
    item.target_args = "--flag"
    folder = Folder()
    folder.id = "f1"
    folder.items = [item]
    data = AppData()
    data.folders = [folder]
    scan_config_repairs(data)
    assert migrate_fn.called


def test_apply_with_dict_does_not_modify_original(monkeypatch):
    """When passing a dict to apply_config_repairs, the original dict is not mutated
    because _repair_config converts dict to AppData with apply=False."""
    _mock_migrate(monkeypatch, return_value="{{fixed}}")
    _mock_find_unknown(monkeypatch)
    data = {"folders": [], "version": "1.0"}
    report = apply_config_repairs(data)
    # Dict input goes through apply=False path
    assert report.changed is False
