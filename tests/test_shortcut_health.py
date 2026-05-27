from core.data_models import AppData, Folder, ShortcutItem, ShortcutType
from core.shortcut_health import apply_health_fixes, check_shortcuts


class Manager:
    def __init__(self, data):
        self.data = data
        self.history_marks = []

    def _find_shortcut_with_folder(self, shortcut_id):
        for folder in self.data.folders:
            for item in folder.items:
                if item.id == shortcut_id:
                    return folder, item
        return None, None

    def batch_update(self, immediate=False):
        class Ctx:
            def __enter__(self_nonlocal):
                return self

            def __exit__(self_nonlocal, *args):
                return False

        return Ctx()

    def save(self, immediate=False):
        return None

    def _mark_history(self, title, detail):
        self.history_marks.append((title, detail))


def test_health_check_reports_missing_target_and_icon(tmp_path):
    item = ShortcutItem(id="missing", name="Missing", type=ShortcutType.FILE)
    item.target_path = str(tmp_path / "missing.exe")
    item.icon_path = str(tmp_path / "missing.ico")
    data = AppData(folders=[Folder(id="f", name="Folder", items=[item])])

    issue_types = {issue.issue_type for issue in check_shortcuts(data)}

    assert "missing_target" in issue_types
    assert "missing_icon" in issue_types


def test_apply_health_fixes_deletes_missing_target(tmp_path):
    item = ShortcutItem(id="missing", name="Missing", type=ShortcutType.FILE)
    item.target_path = str(tmp_path / "missing.exe")
    data = AppData(folders=[Folder(id="f", name="Folder", items=[item])])

    issues = check_shortcuts(data)
    target_issue = next(issue for issue in issues if issue.issue_type == "missing_target")

    result = apply_health_fixes(Manager(data), [target_issue.id])

    assert result["applied"] == 1
    assert data.folders[0].items == []


def test_apply_health_fixes_marks_history_before_repair(tmp_path):
    item = ShortcutItem(id="missing", name="Missing", type=ShortcutType.FILE)
    item.target_path = str(tmp_path / "missing.exe")
    data = AppData(folders=[Folder(id="f", name="Folder", items=[item])])
    manager = Manager(data)
    issue = next(issue for issue in check_shortcuts(data) if issue.issue_type == "missing_target")

    result = apply_health_fixes(manager, [issue.id])

    assert result["applied"] == 1
    assert manager.history_marks


def test_apply_health_fixes_skips_redundant_icon_fix_after_delete(tmp_path):
    item = ShortcutItem(id="missing", name="Missing", type=ShortcutType.FILE)
    item.target_path = str(tmp_path / "missing.exe")
    item.icon_path = str(tmp_path / "missing.ico")
    data = AppData(folders=[Folder(id="f", name="Folder", items=[item])])

    issues = check_shortcuts(data)
    fix_ids = [issue.id for issue in issues if issue.fix_action]

    result = apply_health_fixes(Manager(data), fix_ids)

    assert result["applied"] == 1
    assert result["skipped"] == 1
    assert result["failed"] == 0
    assert data.folders[0].items == []


def test_apply_health_fixes_clears_missing_working_dir(tmp_path):
    target = tmp_path / "app.exe"
    target.write_text("", encoding="utf-8")
    item = ShortcutItem(id="bad_workdir", name="App", type=ShortcutType.FILE)
    item.target_path = str(target)
    item.working_dir = str(tmp_path / "missing-workdir")
    data = AppData(folders=[Folder(id="f", name="Folder", items=[item])])

    issue = next(issue for issue in check_shortcuts(data) if issue.issue_type == "missing_working_dir")
    result = apply_health_fixes(Manager(data), [issue.id])

    assert result["applied"] == 1
    assert item.working_dir == ""


def test_apply_health_fixes_disables_missing_folder_sync(tmp_path):
    folder = Folder(
        id="f",
        name="Synced",
        linked_path=str(tmp_path / "missing-folder"),
        auto_sync=True,
    )
    data = AppData(folders=[folder])

    issue = next(issue for issue in check_shortcuts(data) if issue.issue_type == "missing_linked_folder")
    result = apply_health_fixes(Manager(data), [issue.id])

    assert result["applied"] == 1
    assert folder.auto_sync is False


def test_duplicate_name_is_debug_only():
    first = ShortcutItem(id="v1", name="Visual", type=ShortcutType.FILE)
    second = ShortcutItem(id="v2", name="Visual", type=ShortcutType.FILE)
    data = AppData(folders=[Folder(id="f", name="Folder", items=[first, second])])

    duplicate_issue = next(issue for issue in check_shortcuts(data) if issue.issue_type == "duplicate_name")

    assert duplicate_issue.severity == "debug"


def test_url_health_uses_executor_protocol_rules():
    mail = ShortcutItem(id="mail", name="Mail", type=ShortcutType.URL)
    mail.url = "mailto:support@example.com"
    settings = ShortcutItem(id="settings", name="Settings", type=ShortcutType.URL)
    settings.url = "ms-settings:display"
    blocked = ShortcutItem(id="bad", name="Bad", type=ShortcutType.URL)
    blocked.url = "javascript:alert(1)"
    data = AppData(folders=[Folder(id="f", name="Folder", items=[mail, settings, blocked])])

    issues = check_shortcuts(data)
    issues_by_id = {}
    for issue in issues:
        issues_by_id.setdefault(issue.shortcut_id, []).append(issue.issue_type)

    assert issues_by_id.get("mail", []) == []
    assert issues_by_id.get("settings", []) == []
    assert issues_by_id["bad"] == ["url_invalid"]


def test_health_reports_unresolved_environment_variable():
    item = ShortcutItem(id="env", name="Env", type=ShortcutType.FILE)
    item.target_path = r"%QL_TEST_MISSING_VAR%\app.exe"
    data = AppData(folders=[Folder(id="f", name="Folder", items=[item])])

    issue_types = {issue.issue_type for issue in check_shortcuts(data)}

    assert "unresolved_env_var" in issue_types
    assert "missing_target" not in issue_types


def test_health_reports_missing_lnk_target(tmp_path, monkeypatch):
    link_path = tmp_path / "app.lnk"
    link_path.write_text("", encoding="utf-8")
    item = ShortcutItem(id="link", name="Link", type=ShortcutType.FILE)
    item.target_path = str(link_path)
    data = AppData(folders=[Folder(id="f", name="Folder", items=[item])])

    monkeypatch.setattr("core.shortcut_health._resolve_lnk_target", lambda _path: str(tmp_path / "missing.exe"))

    issue_types = {issue.issue_type for issue in check_shortcuts(data)}

    assert "lnk_target_missing" in issue_types


def test_health_reports_chain_reference_problems():
    normal = ShortcutItem(id="normal", name="Normal", type=ShortcutType.FILE)
    nested = ShortcutItem(id="nested", name="Nested", type=ShortcutType.CHAIN)
    chain = ShortcutItem(id="chain", name="Chain", type=ShortcutType.CHAIN)
    chain.chain_steps = [
        {"shortcut_id": ""},
        {"shortcut_id": "missing"},
        {"shortcut_id": "chain"},
        {"shortcut_id": "nested"},
        {"shortcut_id": "normal"},
    ]
    data = AppData(folders=[Folder(id="f", name="Folder", items=[normal, nested, chain])])

    issue_types = {issue.issue_type for issue in check_shortcuts(data)}

    assert "chain_step_missing_id" in issue_types
    assert "chain_missing_reference" in issue_types
    assert "chain_self_reference" in issue_types
    assert "chain_nested" in issue_types
    assert "chain_empty" in issue_types
