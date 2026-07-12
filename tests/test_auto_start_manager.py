"""Auto-start manager regression tests."""

from pathlib import Path

import core.auto_start_manager as auto_start


class _FakeCollection:
    def __init__(self, items):
        self._items = items
        self.Count = len(items)

    def Item(self, index):
        return self._items[index - 1]


class _FakeAction:
    def __init__(self, path, arguments, cwd):
        self.Path = path
        self.Arguments = arguments
        self.WorkingDirectory = cwd


class _FakeTrigger:
    def __init__(self, delay):
        self.Delay = delay


class _FakePrincipal:
    RunLevel = 0
    UserId = ""


class _FakeDefinition:
    def __init__(self, action, trigger):
        self.Principal = _FakePrincipal()
        self.Actions = _FakeCollection([action])
        self.Triggers = _FakeCollection([trigger])


class _FakeTask:
    Enabled = True

    def __init__(self, action, trigger):
        self.Definition = _FakeDefinition(action, trigger)


def _patch_frozen_app(monkeypatch):
    app_path = r"C:\QuickLauncher\QuickLauncher.exe"
    app_cwd = r"C:\QuickLauncher"
    monkeypatch.setattr(auto_start, "_is_frozen", lambda: True)
    monkeypatch.setattr(auto_start, "_get_exe_path", lambda: app_path)
    monkeypatch.setattr(auto_start, "_get_current_user_identity_variants", lambda: set())
    return app_path, app_cwd


def test_admin_task_uses_launcher_and_short_delay(monkeypatch):
    app_path, app_cwd = _patch_frozen_app(monkeypatch)
    monkeypatch.setattr(auto_start, "_is_current_account_admin", lambda: True)

    task_path, task_args, task_cwd, task_mode = auto_start._build_task_action_launch(app_path, "", app_cwd)

    assert task_mode == "admin_launcher"
    assert task_path == app_path
    assert "--autostart-launch" in task_args
    assert "--target-exe" in task_args
    assert task_cwd == app_cwd
    assert auto_start._get_task_trigger_delay(task_mode) == "PT2S"


def test_standard_task_direct_launch_has_no_delay(monkeypatch):
    app_path, app_cwd = _patch_frozen_app(monkeypatch)
    monkeypatch.setattr(auto_start, "_is_current_account_admin", lambda: False)

    task_path, task_args, task_cwd, task_mode = auto_start._build_task_action_launch(app_path, "", app_cwd)

    assert (task_path, task_args, task_cwd, task_mode) == (app_path, "", app_cwd, "standard_direct")
    assert auto_start._get_task_trigger_delay(task_mode) == ""


def test_admin_task_without_delay_is_stale(monkeypatch):
    app_path, app_cwd = _patch_frozen_app(monkeypatch)
    monkeypatch.setattr(auto_start, "_is_current_account_admin", lambda: True)
    task_path, task_args, task_cwd, _ = auto_start._build_task_action_launch(app_path, "", app_cwd)
    action = _FakeAction(task_path, task_args, task_cwd)

    stale_task = _FakeTask(action, _FakeTrigger(""))
    current_task = _FakeTask(action, _FakeTrigger("PT2S"))

    assert not auto_start._task_matches_launch_spec(stale_task, app_path, "", app_cwd)
    assert auto_start._task_matches_launch_spec(current_task, app_path, "", app_cwd)

    valid, reason = auto_start._validate_task_launch_spec(stale_task, app_path, "", app_cwd)
    assert not valid
    assert "trigger_delay_mismatch" in reason
    assert "mode=admin_launcher" in reason


def test_repair_needed_detects_stale_or_missing_task(monkeypatch):
    monkeypatch.setattr(auto_start, "get_auto_start_check_result", lambda: (False, "task_missing_or_inaccessible"))

    assert auto_start.is_auto_start_repair_needed(True)
    assert not auto_start.is_auto_start_repair_needed(False)


def test_legacy_task_scheduler_module_removed():
    legacy_module = Path(auto_start.__file__).with_name("task_scheduler_manager.py")

    assert not legacy_module.exists()
