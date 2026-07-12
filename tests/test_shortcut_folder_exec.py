import core.shortcut_executor as executor_mod
import core.shortcut_file_exec as file_exec
from core.shortcut_file_exec import FileExecutionMixin


def test_folder_launch_receives_admin_flag(monkeypatch):
    captured = {}

    class FakeExecutor(FileExecutionMixin):
        @staticmethod
        def _launch_with_privilege(
            target, parameters=None, directory=None, show_cmd=1, run_as_admin=False, admin_failure_message=""
        ):
            captured["target"] = target
            captured["run_as_admin"] = run_as_admin
            return True, ""

    monkeypatch.setattr(file_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(executor_mod, "ShortcutExecutor", FakeExecutor)

    success = FileExecutionMixin._open_folder_with_files(r"C:\Temp\Folder", [], run_as_admin=True)

    assert success is True
    assert captured["target"] == r"C:\Temp\Folder"
    assert captured["run_as_admin"] is True


def test_folder_launch_default_not_admin(monkeypatch):
    captured = {}

    class FakeExecutor(FileExecutionMixin):
        @staticmethod
        def _launch_with_privilege(
            target, parameters=None, directory=None, show_cmd=1, run_as_admin=False, admin_failure_message=""
        ):
            captured["run_as_admin"] = run_as_admin
            return True, ""

    monkeypatch.setattr(file_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(executor_mod, "ShortcutExecutor", FakeExecutor)

    success = FileExecutionMixin._open_folder_with_files(r"C:\Temp", [], run_as_admin=False)

    assert success is True
    assert captured["run_as_admin"] is False


def test_folder_launch_with_selected_files(monkeypatch):
    captured = {}

    class FakeExecutor(FileExecutionMixin):
        @staticmethod
        def _launch_with_privilege(
            target, parameters=None, directory=None, show_cmd=1, run_as_admin=False, admin_failure_message=""
        ):
            captured["target"] = target
            return True, ""

    monkeypatch.setattr(file_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(executor_mod, "ShortcutExecutor", FakeExecutor)

    files = [r"C:\Temp\a.txt", r"C:\Temp\b.txt"]
    success = FileExecutionMixin._open_folder_with_files(r"C:\Temp", files)

    assert success is True
    assert captured["target"] == r"C:\Temp"
