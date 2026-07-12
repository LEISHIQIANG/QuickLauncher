import base64
import threading
import types

import pytest

import core.shortcut_command_exec as command_exec
from core.command_registry import CommandDefinition, CommandResult, take_pending_command_result
from core.data_models import ShortcutItem, ShortcutType

pytestmark = pytest.mark.ui


@pytest.fixture(autouse=True)
def _default_shortcut_executor(monkeypatch):
    if command_exec.ShortcutExecutor is None:
        from core import ShortcutExecutor

        monkeypatch.setattr(command_exec, "ShortcutExecutor", ShortcutExecutor)


@pytest.mark.parametrize("capture_output", [False, True])
def test_command_preparation_rejects_unquoted_external_variables(monkeypatch, capture_output):
    class FakeExecutor(command_exec.CommandExecutionMixin):
        pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo {{input}}"
    item.command_variables_enabled = True
    item.capture_output = capture_output

    if capture_output:
        result = command_exec.CommandExecutionMixin.run_command_capture(item)
        assert result.success is False
        assert "必须使用 :q 引用" in result.message
        assert result.payload["window_size"]
    else:
        success, error = command_exec.CommandExecutionMixin._execute_command(item)
        assert success is False
        assert "必须使用 :q 引用" in error


@pytest.mark.parametrize("capture_output", [False, True])
def test_command_preparation_rejects_value_only_variables(monkeypatch, capture_output):
    class FakeExecutor(command_exec.CommandExecutionMixin):
        pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "{{clipboard}}"
    item.command_variables_enabled = True
    item.capture_output = capture_output

    if capture_output:
        result = command_exec.CommandExecutionMixin.run_command_capture(item)
        assert result.success is False
        assert "命令只包含值占位符" in result.message
        assert result.error == "命令无效"
    else:
        success, error = command_exec.CommandExecutionMixin._execute_command(item)
        assert success is False
        assert "命令只包含值占位符" in error


def test_python_visible_window_runs_python_directly(monkeypatch):
    """Show-window Python runs python.exe script.py, not a cmd.exe wrapper."""
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _python_launcher():
            return "python"

        @staticmethod
        def _write_temp_python_script(command):
            return r"C:\Users\Administrator\AppData\Local\Temp\tmp94kufm62.py"

        @staticmethod
        def _launch_with_privilege(
            target, parameters, directory, show_cmd=1, run_as_admin=False, admin_failure_message=""
        ):
            captured["target"] = target
            captured["parameters"] = parameters
            captured["directory"] = directory
            captured["show_cmd"] = show_cmd
            captured["run_as_admin"] = run_as_admin
            return True, ""

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setenv("ComSpec", r"C:\Windows\System32\cmd.exe")

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = "print('hello')"
    item.show_window = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["target"] == "python"
    assert "tmp94kufm62.py" in captured["parameters"]
    # cmd.exe wrapper is no longer used
    assert captured["show_cmd"] == 1
    assert "/k" not in captured.get("parameters", "")


def test_config_window_alias_saved_as_cmd_runs_as_cmd(monkeypatch):
    captured = {}

    class FakeProcess:
        def wait(self, timeout=None):
            return 0

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _execute_builtin_command(command):
            raise AssertionError("cmd commands must not be silently rewritten to builtin")

        @staticmethod
        def _cmd_launcher():
            return "cmd.exe"

        @staticmethod
        def _safe_split_args(command):
            return command.split()

        @staticmethod
        def _launch_with_privilege(target, parameters, directory, show_cmd=0, run_as_admin=False, **kwargs):
            raise AssertionError("silent cmd commands must not use ShellExecute")

        @staticmethod
        def _popen_silent(argv, cwd=None, env=None, shell=False):
            captured["argv"] = argv
            captured["cwd"] = cwd
            captured["shell"] = shell
            return FakeProcess()

        @staticmethod
        def _runtime_env(shortcut):
            return {}

        @staticmethod
        def restore_foreground_window():
            pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "show_config_window"

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["argv"] == ["cmd.exe", "/d", "/s", "/c", "show_config_window"]
    assert captured["shell"] is False


def test_system_builtin_alias_saved_as_cmd_runs_as_cmd(monkeypatch):
    captured = {}

    class FakeProcess:
        def wait(self, timeout=None):
            return 0

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _execute_builtin_command(command):
            raise AssertionError("cmd commands must not be silently rewritten to builtin")

        @staticmethod
        def _cmd_launcher():
            return "cmd.exe"

        @staticmethod
        def _safe_split_args(command):
            return command.split()

        @staticmethod
        def _launch_with_privilege(target, parameters, directory, show_cmd=0, run_as_admin=False, **kwargs):
            raise AssertionError("silent cmd commands must not use ShellExecute")

        @staticmethod
        def _popen_silent(argv, cwd=None, env=None, shell=False):
            captured["argv"] = argv
            captured["cwd"] = cwd
            captured["shell"] = shell
            return FakeProcess()

        @staticmethod
        def _runtime_env(shortcut):
            return {}

        @staticmethod
        def restore_foreground_window():
            pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "open_control_panel"

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["argv"] == ["cmd.exe", "/d", "/s", "/c", "open_control_panel"]
    assert captured["shell"] is False


def test_windows_system_builtin_alias_launches_task_manager(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _shell_execute_open(target, parameters=None, directory=None, show_cmd=1, run_as_admin=False):
            captured["target"] = target
            captured["parameters"] = parameters
            return True

        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("successful ShellExecute must not fall through to Popen")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    assert command_exec.CommandExecutionMixin._execute_builtin_command("taskmgr")
    assert captured == {"target": "taskmgr.exe", "parameters": None}


def test_internal_builtin_opens_config_parent_when_file_is_missing(monkeypatch, tmp_path):
    opened = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _app_install_dir():
            return str(tmp_path)

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.os, "startfile", lambda path: opened.setdefault("path", path), raising=False)

    assert command_exec.CommandExecutionMixin._execute_builtin_command("config-file")
    assert opened["path"] == str(tmp_path / "config")


def test_internal_text_file_builtin_uses_notepad_instead_of_file_association(monkeypatch, tmp_path):
    captured = {}
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "data.json").write_text("{}", encoding="utf-8")

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _app_install_dir():
            return str(tmp_path)

        @staticmethod
        def _shell_execute_open(target, parameters=None, directory=None, show_cmd=1, run_as_admin=False):
            captured["target"] = target
            captured["parameters"] = parameters
            return True

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(
        command_exec.os,
        "startfile",
        lambda path: (_ for _ in ()).throw(AssertionError("must not use file association")),
        raising=False,
    )
    monkeypatch.setattr(command_exec.os, "name", "nt", raising=False)

    assert command_exec.CommandExecutionMixin._execute_builtin_command("open_config_file")
    assert captured["target"] == "notepad.exe"
    assert str(config_dir / "data.json") in captured["parameters"]


def test_error_log_builtin_uses_same_fast_text_file_path(monkeypatch, tmp_path):
    captured = {}
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "error.log").write_text("boom", encoding="utf-8")

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _app_install_dir():
            return str(tmp_path)

        @staticmethod
        def _shell_execute_open(target, parameters=None, directory=None, show_cmd=1, run_as_admin=False):
            captured["target"] = target
            captured["parameters"] = parameters
            return True

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.os, "name", "nt", raising=False)

    assert command_exec.CommandExecutionMixin._execute_builtin_command("open_error_log")
    assert captured["target"] == "notepad.exe"
    assert str(config_dir / "error.log") in captured["parameters"]


def test_test_command_keeps_cmd_alias_as_shell_command(monkeypatch):
    captured = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return b"cmd ok", b""

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    class FakeExecutor(command_exec.CommandExecutionMixin):
        pass

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_cmd_launcher", staticmethod(lambda: "cmd.exe"))
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}), raising=False)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "open_this_pc"

    result = command_exec.CommandExecutionMixin.test_command(item)

    assert result["success"] is True
    assert result["exit_code"] == 0
    assert captured["args"][0] == ["cmd.exe", "/d", "/s", "/c", "open_this_pc"]
    assert captured["kwargs"]["shell"] is False


def test_config_window_builtin_dispatches_through_ui_actions_port(monkeypatch):
    """W1 收尾后,show_config_window 走 UIActions 端口而非 IPC 直连回退。"""
    from application.ports.ui_actions import UIAction
    from core.shortcut_executor import ShortcutExecutor

    captured = {}

    class FakeActions:
        def execute(self, action):
            captured["action"] = action
            return True

    monkeypatch.setattr(ShortcutExecutor, "_ui_actions", FakeActions(), raising=False)
    monkeypatch.setattr(ShortcutExecutor, "_is_qt_main_thread", classmethod(lambda cls: True), raising=False)

    assert command_exec.CommandExecutionMixin._execute_builtin_command("show_config_window")
    assert captured["action"] == UIAction.SHOW_CONFIG_WINDOW


def test_open_install_dir_builtin_works_without_ui_callback(monkeypatch, tmp_path):
    opened = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.os.path, "isdir", lambda path: True)
    monkeypatch.setattr(command_exec.os, "startfile", lambda path: opened.setdefault("path", path), raising=False)
    monkeypatch.setattr(command_exec.sys, "frozen", True, raising=False)
    monkeypatch.setattr(command_exec.sys, "executable", str(tmp_path / "QuickLauncher.exe"))

    assert command_exec.CommandExecutionMixin._execute_builtin_command("open_install_dir")
    assert opened["path"] == str(tmp_path)


def test_open_install_dir_builtin_uses_project_root_in_source_mode(monkeypatch):
    opened = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.os.path, "isdir", lambda path: True)
    monkeypatch.setattr(command_exec.os, "startfile", lambda path: opened.setdefault("path", path), raising=False)
    monkeypatch.delattr(command_exec.sys, "frozen", raising=False)

    assert command_exec.CommandExecutionMixin._execute_builtin_command("open_install_dir")
    assert opened["path"] == command_exec.CommandExecutionMixin._app_install_dir()


def test_ui_builtin_defers_callback_outside_qt_main_thread(monkeypatch):
    from application.ports.ui_actions import UIAction
    from core.shortcut_executor import ShortcutExecutor

    called = {}

    class FakeActions:
        def execute(self, action):
            called.setdefault("action", action)
            return True

    class FakeInvoker:
        execute_signal = type("S", (), {"emit": staticmethod(lambda fn: called.setdefault("emitted", fn))})()

    monkeypatch.setattr(ShortcutExecutor, "_ui_actions", FakeActions(), raising=False)
    monkeypatch.setattr(ShortcutExecutor, "_is_qt_main_thread", classmethod(lambda cls: False), raising=False)
    monkeypatch.setattr(command_exec, "_main_thread_invoker", FakeInvoker())

    assert command_exec.CommandExecutionMixin._execute_builtin_command("show_help")
    assert callable(called.get("emitted"))
    assert called.get("action") is None
    called["emitted"]()
    assert called.get("action") == UIAction.SHOW_HELP


def test_builtin_command_can_suppress_result_panel(monkeypatch):
    import core

    take_pending_command_result()

    cmd = CommandDefinition(
        id="suppress",
        title="Suppress",
        aliases=[],
        description="",
        category="",
        handler=lambda ctx: CommandResult(success=True, message="cancelled", payload={"_suppress_result_panel": True}),
    )

    class FakeRegistry:
        def count(self):
            return 1

        def get(self, command_id):
            return cmd if command_id == "suppress" else None

        def get_canonical(self, command_id):
            return ""

    monkeypatch.setattr(core, "registry", FakeRegistry())

    assert command_exec.CommandExecutionMixin._execute_builtin_command("suppress") is True
    assert take_pending_command_result() is None


def test_python_variables_are_disabled_by_default(monkeypatch):
    monkeypatch.setattr(command_exec, "ShortcutExecutor", command_exec.CommandExecutionMixin)
    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = 'print("{{date}}")'
    item.command_variables_enabled = False

    resolved = command_exec.CommandExecutionMixin._resolve_command_variables(item, item.command)

    assert resolved == item.command


def test_python_variables_can_be_enabled_explicitly(monkeypatch):
    monkeypatch.setattr(command_exec, "ShortcutExecutor", command_exec.CommandExecutionMixin)
    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = 'print("{{date}}")'
    item.command_variables_enabled = True

    resolved = command_exec.CommandExecutionMixin._resolve_command_variables(item, item.command)

    assert "{{date}}" not in resolved


def test_multiline_cmd_runs_direct_without_temp_wrapper(monkeypatch):
    captured = {}

    class FakeStdin:
        def write(self, data):
            captured["stdin"] = data

        def close(self):
            captured["stdin_closed"] = True

    class FakeProcess:
        stdin = FakeStdin()

    def fake_popen(argv, **kwargs):
        captured["popen"] = (argv, kwargs)
        return FakeProcess()

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _cmd_launcher():
            return r"C:\Windows\System32\cmd.exe"

        @staticmethod
        def _sanitized_child_env():
            return {}

        @staticmethod
        def _get_silent_startupinfo():
            return None

        @staticmethod
        def _get_silent_creationflags():
            return 0

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setenv("ComSpec", r"C:\Windows\System32\cmd.exe")

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = 'if exist "C:\\" (\n  echo ok\n)'
    item.command_variables_enabled = False

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["popen"][0] == [r"C:\Windows\System32\cmd.exe", "/d", "/q", "/k", "prompt $H"]
    assert captured["popen"][1]["shell"] is False
    assert b"echo ok" in captured["stdin"]
    assert b"ql_wrapper.cmd" not in captured["stdin"]
    assert captured["stdin_closed"] is True


def test_value_only_variable_is_not_executed_as_cmd(monkeypatch):
    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("value-only variable must not be executed")

        @staticmethod
        def _launch_with_privilege(*args, **kwargs):
            raise AssertionError("value-only variable must not be launched")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "{{date}}"
    item.command_variables_enabled = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert not success
    assert "值占位符" in error
    assert "echo {{date}}" in error


def test_value_only_variable_is_rejected_even_when_variables_disabled(monkeypatch):
    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("value-only variable must not be executed")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "{{date}}"
    item.command_variables_enabled = False

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert not success
    assert "解析变量" in error


def test_value_only_param_variable_is_not_executed(monkeypatch):
    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("value-only param variable must not execute")

        @staticmethod
        def _launch_with_privilege(*args, **kwargs):
            raise AssertionError("value-only param variable must not launch")

        @staticmethod
        def _command_param_defs(shortcut):
            return [{"name": "cmd", "required": True}]

        @staticmethod
        def _command_param_values(shortcut):
            return {"cmd": "calc.exe"}

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "{{param:cmd:q}}"

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert not success
    assert "值占位符" in error


def test_raw_mode_does_not_expand_or_reject_variable_text(monkeypatch):
    captured = {}

    class FakeProcess:
        def wait(self, timeout=None):
            return 0

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _launch_with_privilege(*args, **kwargs):
            return False, ""

        @staticmethod
        def _cmd_launcher():
            return "cmd.exe"

        @staticmethod
        def _popen_silent(argv, cwd=None, env=None, shell=False):
            captured["argv"] = argv
            return FakeProcess()

        @staticmethod
        def _runtime_env(shortcut):
            return {}

        @staticmethod
        def _safe_split_args(command):
            return command.split()

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo {{clipboard}}"
    item.command_variables_enabled = True
    item.raw_mode = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["argv"][-1] == "echo {{clipboard}}"


def test_command_variable_inside_real_command_still_executes(monkeypatch):
    captured = {}

    class FakeProcess:
        def wait(self, timeout=None):
            return 0

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _launch_with_privilege(
            target, parameters, directory, show_cmd=0, run_as_admin=False, admin_failure_message=""
        ):
            return False, ""

        @staticmethod
        def _cmd_launcher():
            return "cmd.exe"

        @staticmethod
        def _popen_silent(argv, cwd=None, env=None, shell=False):
            captured["argv"] = argv
            captured["cwd"] = cwd
            captured["shell"] = shell
            return FakeProcess()

        @staticmethod
        def _sanitized_child_env():
            return {}

        @staticmethod
        def _safe_split_args(command):
            return command.split()

        @staticmethod
        def restore_foreground_window():
            captured["restored"] = True

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo {{date}}"
    item.command_variables_enabled = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["shell"] is False
    assert captured["argv"][:4] == ["cmd.exe", "/d", "/s", "/c"]
    assert captured["argv"][4].startswith("echo ")


def test_unquoted_external_variable_in_cmd_is_rejected(monkeypatch):
    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("unsafe variable command must not execute")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo {{clipboard}}"
    item.command_variables_enabled = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert not success
    assert ":q" in error


def test_test_command_rejects_unquoted_external_variable(monkeypatch):
    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("unsafe variable command must not execute")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo {{clipboard}}"
    item.command_variables_enabled = True

    result = command_exec.CommandExecutionMixin.test_command(item)

    assert result["success"] is False
    assert ":q" in result["error"]


def test_test_command_rejects_value_only_variable(monkeypatch):
    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("value-only variable must not execute")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "{{date}}"
    item.command_variables_enabled = False

    result = command_exec.CommandExecutionMixin.test_command(item)

    assert result["success"] is False
    assert result["error"]


def test_test_command_forwards_cancel_event(monkeypatch):
    cancel_event = threading.Event()
    seen = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def run_command_capture(shortcut, timeout=None, cancel_event=None, on_update=None):
            seen["timeout"] = timeout
            seen["cancel_event"] = cancel_event
            return CommandResult(
                success=False,
                message="cancelled",
                display_type="log",
                error="已取消",
                payload={"duration": 0.0},
            )

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "ping -n 10 127.0.0.1"

    result = command_exec.CommandExecutionMixin.test_command(item, timeout=1.5, cancel_event=cancel_event)

    assert result["success"] is False
    assert result["error"] == "已取消"
    assert seen == {"timeout": 1.5, "cancel_event": cancel_event}


def test_quoted_external_variable_in_cmd_still_executes(monkeypatch):
    captured = {}

    class FakeProcess:
        def wait(self, timeout=None):
            return 0

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _launch_with_privilege(
            target, parameters, directory, show_cmd=0, run_as_admin=False, admin_failure_message=""
        ):
            return False, ""

        @staticmethod
        def _cmd_launcher():
            return "cmd.exe"

        @staticmethod
        def _popen_silent(argv, cwd=None, env=None, shell=False):
            captured["argv"] = argv
            captured["shell"] = shell
            return FakeProcess()

        @staticmethod
        def _sanitized_child_env():
            return {}

        @staticmethod
        def _safe_split_args(command):
            return command.split()

        @staticmethod
        def restore_foreground_window():
            pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec, "read_clipboard_text", lambda: "hello world")

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo {{clipboard:q}}"
    item.command_variables_enabled = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["shell"] is False
    assert captured["argv"][:4] == ["cmd.exe", "/d", "/s", "/c"]
    assert '"hello world"' in captured["argv"][4]


def test_frozen_python_launcher_rejects_app_directory_candidate(monkeypatch, tmp_path):
    app_dir = tmp_path / "QuickLauncher"
    app_dir.mkdir()
    app_python = app_dir / "python.exe"
    app_python.write_text("", encoding="utf-8")

    class FakeExecutor(command_exec.CommandExecutionMixin):
        pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.sys, "frozen", True, raising=False)
    monkeypatch.setattr(command_exec.sys, "executable", str(app_dir / "QuickLauncher.exe"))
    monkeypatch.setattr(command_exec.shutil, "which", lambda name: str(app_python) if name == "python" else None)

    def fail_probe(candidate):
        raise AssertionError("app directory python.exe must be rejected before probing")

    monkeypatch.setattr(FakeExecutor, "_probe_python_launcher", staticmethod(fail_probe))

    assert command_exec.CommandExecutionMixin._find_system_python_launcher() is None


def test_nuitka_packaged_runtime_rejects_app_directory_candidate_without_sys_frozen(monkeypatch, tmp_path):
    app_dir = tmp_path / "QuickLauncher"
    app_dir.mkdir()
    app_python = app_dir / "python.exe"
    app_python.write_text("", encoding="utf-8")

    class FakeExecutor(command_exec.CommandExecutionMixin):
        pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.delattr(command_exec.sys, "frozen", raising=False)
    monkeypatch.setattr(command_exec.sys, "executable", str(app_dir / "QuickLauncher.exe"))
    monkeypatch.setattr(command_exec.shutil, "which", lambda name: str(app_python) if name == "python" else None)

    def fail_probe(candidate):
        raise AssertionError("Nuitka app directory python.exe must be rejected before probing")

    monkeypatch.setattr(FakeExecutor, "_probe_python_launcher", staticmethod(fail_probe))

    assert command_exec.CommandExecutionMixin._is_packaged_runtime()
    assert command_exec.CommandExecutionMixin._find_system_python_launcher() is None


def test_frozen_python_launcher_requires_successful_probe(monkeypatch, tmp_path):
    python_exe = tmp_path / "Python312" / "python.exe"
    python_exe.parent.mkdir()
    python_exe.write_text("", encoding="utf-8")
    probed = []

    class FakeExecutor(command_exec.CommandExecutionMixin):
        pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.sys, "frozen", True, raising=False)
    monkeypatch.setattr(command_exec.sys, "executable", str(tmp_path / "QuickLauncher" / "QuickLauncher.exe"))
    monkeypatch.setattr(command_exec.shutil, "which", lambda name: str(python_exe) if name == "python" else None)

    def probe(candidate):
        probed.append(candidate)
        return True

    monkeypatch.setattr(FakeExecutor, "_probe_python_launcher", staticmethod(probe))

    assert command_exec.CommandExecutionMixin._find_system_python_launcher() == str(python_exe)
    assert probed == [str(python_exe)]


def test_python_launcher_probe_uses_hidden_process_options(monkeypatch):
    captured = {}
    hidden_options = {"creationflags": 0x08000000, "startupinfo": object()}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _capture_popen_platform_kwargs():
            return hidden_options

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.subprocess, "run", fake_run)

    assert command_exec.CommandExecutionMixin._probe_python_launcher("python.exe") is True
    assert captured["argv"][0] == "python.exe"
    assert captured["kwargs"]["creationflags"] == hidden_options["creationflags"]
    assert captured["kwargs"]["startupinfo"] is hidden_options["startupinfo"]


def test_frozen_visible_python_without_system_launcher_returns_clear_error(monkeypatch):
    writes = []

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _python_launcher():
            return None

        @staticmethod
        def _write_temp_python_script(command):
            writes.append(command)
            return r"C:\Temp\ql_script.py"

        @staticmethod
        def _write_python_cmd_wrapper(script_path):
            raise AssertionError("wrapper must not be written without a working Python launcher")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = "print('hello')"
    item.show_window = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert not success
    assert "系统 Python" in error
    assert "python312.dll" in error
    assert writes == []


def test_frozen_silent_python_without_launcher_does_not_fall_back_to_inline(monkeypatch):
    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _python_launcher():
            return None

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.sys, "frozen", True, raising=False)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = "value = 42"
    item.show_window = False

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert not success
    assert "系统 Python" in error


def test_python_silent_uses_stdin_in_elevated_context(monkeypatch):
    thread_target = []

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _is_launch_context_elevated():
            return True

        @staticmethod
        def _python_launcher():
            return r"C:\Python312\python.exe"

        @staticmethod
        def _get_silent_startupinfo():
            return None

        @staticmethod
        def _get_silent_creationflags(shell=False):
            return 0x00000008  # DETACHED_PROCESS

        @staticmethod
        def _runtime_env(shortcut):
            return {}

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    real_thread = command_exec.threading.Thread

    def fake_thread(*args, **kwargs):
        thread_target.append(kwargs.get("target"))
        return real_thread(*args, **kwargs)

    monkeypatch.setattr(command_exec.threading, "Thread", fake_thread)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = "value = 42"
    item.show_window = False
    item.run_as_admin = False

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    # Should use stdin pipe in a thread, not _popen_silent with temp file
    assert len(thread_target) == 1


def test_admin_cmd_success_after_standard_fallback_is_reported_success(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _safe_split_args(command):
            return [r"C:\Tools\App.exe", "--flag"]

        @staticmethod
        def _launch_with_privilege(
            target, parameters, directory, show_cmd=0, run_as_admin=False, admin_failure_message=""
        ):
            captured["target"] = target
            captured["parameters"] = parameters
            captured["run_as_admin"] = run_as_admin
            return True, ""

        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("successful ShellExecute fallback must not fall through to Popen")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.os.path, "exists", lambda path: path == r"C:\Tools\App.exe")

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = r"C:\Tools\App.exe --flag"
    item.run_as_admin = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["target"] == r"C:\Tools\App.exe"
    assert captured["parameters"] == "--flag"
    assert captured["run_as_admin"] is True


def test_admin_cmd_in_elevated_context_uses_unified_privilege_route(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _safe_split_args(command):
            return [r"C:\Tools\App.exe", "--flag"]

        @staticmethod
        def _is_launch_context_elevated():
            return True

        @staticmethod
        def _launch_with_privilege(
            target, parameters, directory, show_cmd=0, run_as_admin=False, admin_failure_message=""
        ):
            captured["target"] = target
            captured["parameters"] = parameters
            captured["directory"] = directory
            captured["show_cmd"] = show_cmd
            captured["run_as_admin"] = run_as_admin
            return True, ""

        @staticmethod
        def _popen_silent(argv, cwd=None, env=None, shell=False):
            raise AssertionError("admin commands should use the unified privilege route")

        @staticmethod
        def _sanitized_child_env():
            return {}

        @staticmethod
        def restore_foreground_window():
            pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.os.path, "exists", lambda path: path == r"C:\Tools\App.exe")

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = r"C:\Tools\App.exe --flag"
    item.run_as_admin = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["target"] == r"C:\Tools\App.exe"
    assert captured["parameters"] == "--flag"
    assert captured["run_as_admin"] is True


def test_shortcut_item_persists_capture_output_fields():
    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.capture_output = True
    item.command_timeout_seconds = 3.5
    item.command_output_max_chars = 12345
    item.command_panel_size = "small"

    restored = ShortcutItem.from_dict(item.to_dict())

    assert restored.capture_output is True
    assert restored.command_timeout_seconds == 3.5
    assert restored.command_output_max_chars == 12345
    assert restored.command_panel_size == "small"


def test_shortcut_item_persists_command_profile_fields():
    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_params = [{"name": "host", "type": "text", "required": True}]
    item.command_env = {"QL_TEST": "1"}
    item.command_encoding = "gbk"

    restored = ShortcutItem.from_dict(item.to_dict())

    assert restored.command_params[0]["name"] == "host"
    assert restored.command_env == {"QL_TEST": "1"}
    assert restored.command_encoding == "gbk"


def test_run_command_capture_resolves_param_and_env_and_decodes_gbk(monkeypatch):
    import core.shortcut_command_exec as command_exec

    captured = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return "中文".encode("gbk"), b""

        def poll(self):
            return 0

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {"BASE": "1"}))

    item = ShortcutItem(
        type=ShortcutType.COMMAND,
        command_type="cmd",
        command="echo {{param:host:q}}",
        command_params=[{"name": "host", "required": True}],
        command_env={"QL_TEST": "yes"},
        command_encoding="gbk",
    )
    item._runtime_param_values = {"host": "example.com"}

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert captured["args"][0] == [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
        "echo example.com",
    ]
    assert captured["kwargs"]["env"]["QL_TEST"] == "yes"
    assert result.payload["stdout"] == "中文"
    assert result.payload["stdout_encoding"].lower() in ("cp936", "gbk")


def test_run_command_capture_preflight_rejects_missing_workdir(tmp_path):
    item = ShortcutItem(
        type=ShortcutType.COMMAND,
        command_type="cmd",
        command="echo ok",
        working_dir=str(tmp_path / "missing"),
    )

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is False
    assert result.display_type == "list"
    assert "工作目录" in result.message


def test_run_command_capture_cmd_stdout_stderr_and_exit(monkeypatch):
    class FakeProcess:
        returncode = 7

        def communicate(self, timeout=None):
            return "out", "err"

    captured = {}

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_cmd_launcher", staticmethod(lambda: "cmd.exe"))
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo test"
    item.capture_output = True
    item.command_panel_size = "small"

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is False
    assert result.display_type == "log"
    assert result.payload["window_size"] == "small"
    assert result.payload["stdout"] == "out"
    assert result.payload["stderr"] == "err"
    assert result.payload["exit_code"] == 7
    assert captured["kwargs"]["stdout"] == command_exec.subprocess.PIPE
    assert captured["kwargs"]["stdin"] == command_exec.subprocess.DEVNULL
    assert captured["args"][0] == ["cmd.exe", "/d", "/s", "/c", "echo test"]
    assert captured["kwargs"]["shell"] is False


def test_run_command_capture_cmd_hides_console_on_windows(monkeypatch):
    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return b"out", b""

    captured = {}
    no_window = 0x08000000

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(command_exec.os, "name", "nt", raising=False)
    monkeypatch.setattr(command_exec.subprocess, "CREATE_NO_WINDOW", no_window, raising=False)
    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_cmd_launcher", staticmethod(lambda: "cmd.exe"))
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "curl ipinfo.io"
    item.capture_output = True

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is True
    assert captured["args"][0] == ["cmd.exe", "/d", "/s", "/c", "curl ipinfo.io"]
    assert captured["kwargs"]["creationflags"] & no_window
    assert captured["kwargs"]["shell"] is False


def test_run_command_capture_cmd_multiline_uses_stdin_without_wrapper(monkeypatch):
    class FakeProcess:
        returncode = 0

        def communicate(self, input=None, timeout=None):
            captured["stdin"] = input
            return b"\n\x08 \x08line1\r\nline2\r\n", b""

    captured = {}

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_cmd_launcher", staticmethod(lambda: "cmd.exe"))
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo line1\necho line2"
    item.capture_output = True

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is True
    assert captured["args"][0] == ["cmd.exe", "/d", "/q", "/k", "prompt $H"]
    assert captured["kwargs"]["stdin"] == command_exec.subprocess.PIPE
    assert b"echo line2" in captured["stdin"]
    assert b".cmd" not in captured["stdin"]
    assert result.payload["stdout"] == "line1\r\nline2\r\n"


def test_run_command_capture_rejects_unsupported_command_type(monkeypatch):
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_cmd_launcher", staticmethod(lambda: "cmd.exe"))

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "wscript"
    item.command = "echo test"

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is False
    assert "Unsupported command type" in result.message


def test_preprocessing_default_allows_shell_pipe_for_cmd(monkeypatch):
    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return "ok", ""

    captured = {}

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_cmd_launcher", staticmethod(lambda: "cmd.exe"))
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo ok | findstr ok"

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is True
    assert captured["args"][0] == ["cmd.exe", "/d", "/s", "/c", "echo ok | findstr ok"]
    assert captured["kwargs"]["shell"] is False


def test_preprocessing_strict_mode_blocks_shell_chaining(monkeypatch):
    from core.preprocessing.pipeline import PreprocessingContext, PreprocessingPipeline

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo ok & echo bad"

    monkeypatch.setattr(command_exec.ShortcutExecutor, "_cmd_launcher", staticmethod(lambda: "cmd.exe"))
    monkeypatch.setattr(
        command_exec.ShortcutExecutor,
        "_command_preprocessing_result",
        staticmethod(
            lambda shortcut, command, command_type: PreprocessingPipeline(
                strict_mode=True,
                rate_limiting=False,
            ).process(
                PreprocessingContext(
                    command=command,
                    command_type=command_type,
                    raw_mode=False,
                )
            )
        ),
    )

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is False
    assert "Command preprocessing failed" in result.error


def test_preprocessing_pipeline_exception_fails_closed(monkeypatch):
    """P0-04: If the preprocessing pipeline itself raises, execution must be blocked."""

    import core.preprocessing.pipeline as pipeline_mod
    from core.preprocessing.pipeline import PreprocessingPipeline

    class BoomPipeline(PreprocessingPipeline):
        def process(self, context):  # noqa: D401 - test stub
            raise RuntimeError("pipeline boom")

    def fake_factory(*_args, **_kwargs):
        return BoomPipeline(rate_limiting=False)

    monkeypatch.setattr(command_exec.ShortcutExecutor, "_cmd_launcher", staticmethod(lambda: "cmd.exe"))
    monkeypatch.setattr(
        command_exec.ShortcutExecutor,
        "_command_param_values",
        staticmethod(lambda shortcut: {}),
        raising=False,
    )
    monkeypatch.setattr(
        command_exec.ShortcutExecutor,
        "_command_panel_size",
        staticmethod(lambda shortcut: "medium"),
        raising=False,
    )
    monkeypatch.setattr(pipeline_mod, "create_pipeline_from_settings", fake_factory)
    monkeypatch.setattr(PreprocessingPipeline, "process", BoomPipeline.process)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo ok"

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is False
    assert result.error is not None
    assert "preprocessing" in result.error.lower() or "预处理" in result.error


def test_preprocessing_settings_failure_blocks_direct_execution(monkeypatch):
    """Configuration read failures must not fall back to permissive execution."""

    from types import SimpleNamespace

    monkeypatch.setattr(
        "core.data_manager",
        SimpleNamespace(get_settings=lambda: (_ for _ in ()).throw(RuntimeError("settings broken"))),
    )
    launched = []
    monkeypatch.setattr(command_exec.process_runtime, "popen", lambda *a, **kw: launched.append((a, kw)))

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo should-not-run"

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success is False
    assert "预处理" in error or "preprocessing" in error.lower()
    assert launched == []


def test_run_command_capture_timeout_kills_process(monkeypatch):
    class FakeProcess:
        returncode = -9

        def __init__(self):
            self.calls = 0
            self.killed = False

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise command_exec.subprocess.TimeoutExpired("cmd", timeout)
            return "partial", ""

        def kill(self):
            self.killed = True

    proc = FakeProcess()
    monkeypatch.setattr(command_exec.subprocess, "Popen", lambda *args, **kwargs: proc)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "slow"
    item.command_timeout_seconds = 0.1

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is False
    assert result.payload["timed_out"] is True
    assert proc.killed is True
    assert "partial" in result.message


def test_run_command_capture_timeout_uses_process_tree_termination(monkeypatch):
    class FakeProcess:
        pid = 12345
        returncode = -9

        def __init__(self):
            self.calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise command_exec.subprocess.TimeoutExpired("cmd", timeout)
            return b"partial", b""

    proc = FakeProcess()
    terminated = []
    monkeypatch.setattr(command_exec.subprocess, "Popen", lambda *args, **kwargs: proc)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))
    monkeypatch.setattr(
        command_exec.ShortcutExecutor,
        "_terminate_process_tree",
        staticmethod(lambda process: terminated.append(process)),
    )

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "slow"
    item.command_timeout_seconds = 0.1

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is False
    assert result.payload["timed_out"] is True
    assert terminated == [proc]


def test_run_command_capture_truncates_output(monkeypatch):
    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return "x" * 1100, ""

    monkeypatch.setattr(command_exec.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "long"
    item.command_output_max_chars = 1000

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is True
    assert result.payload["stdout_truncated"] is True
    assert len(result.payload["stdout"]) < 1100


def test_run_command_capture_python_subprocess(monkeypatch):
    class FakeProcess:
        returncode = 0

        def communicate(self, input=None, timeout=None):
            captured["stdin_data"] = input
            return "py out", "py err"

    captured = {}

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_python_launcher", staticmethod(lambda: "python"))
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))

    # Ensure no temp file is written
    monkeypatch.setattr(
        command_exec.ShortcutExecutor,
        "_write_temp_python_script",
        staticmethod(lambda script: (_ for _ in ()).throw(AssertionError("temp file should not be written"))),
    )

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = "print('x')"

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is True
    assert result.payload["stdout"] == "py out"
    assert result.payload["stderr"] == "py err"
    # Python capture uses stdin pipe (not temp file), so popen_args is [python, -u]
    assert captured["args"][0] == ["python", "-u"]
    assert captured["kwargs"]["stdin"] == command_exec.subprocess.PIPE
    assert captured["stdin_data"] == b"print('x')"


def test_run_command_capture_powershell_subprocess(monkeypatch):
    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return "ps out", ""

    captured = {}
    powershell_exe = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_powershell_launcher", staticmethod(lambda: powershell_exe))
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "powershell"
    item.command = 'Write-Output "ok"'

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is True
    assert result.payload["stdout"] == "ps out"
    argv = captured["args"][0]
    assert argv[:5] == [
        powershell_exe,
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
    ]
    assert argv[5] == "-EncodedCommand"
    assert base64.b64decode(argv[6]).decode("utf-16le") == 'Write-Output "ok"'
    assert captured["kwargs"]["shell"] is False


def test_powershell_argv_encodes_multiline_unicode_without_script_file(monkeypatch):
    powershell_exe = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    monkeypatch.setattr(command_exec, "ShortcutExecutor", command_exec.CommandExecutionMixin)
    monkeypatch.setattr(
        command_exec.CommandExecutionMixin, "_powershell_launcher", staticmethod(lambda: powershell_exe)
    )

    command = 'Write-Output "中文"\nWrite-Output "quote: \'"'
    argv = command_exec.CommandExecutionMixin._powershell_argv(command, no_exit=True)

    assert argv[:6] == [powershell_exe, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit"]
    assert argv[6] == "-EncodedCommand"
    assert base64.b64decode(argv[7]).decode("utf-16le") == command


def test_run_command_capture_powershell_variables_use_literal_quoting(monkeypatch):
    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return b"literal\r\n", b""

    captured = {}
    powershell_exe = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_powershell_launcher", staticmethod(lambda: powershell_exe))
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "powershell"
    item.command = "Write-Output {{input:q}}"
    item.command_variables_enabled = True
    item._runtime_input_values = {"input": '"; Write-Output PWNED; #'}

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is True
    argv = captured["args"][0]
    assert argv[5] == "-EncodedCommand"
    assert base64.b64decode(argv[6]).decode("utf-16le") == "Write-Output '\"; Write-Output PWNED; #'"


def test_run_command_capture_powershell_subexpression_input_is_literal(monkeypatch):
    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return b"literal\r\n", b""

    captured = {}
    powershell_exe = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_powershell_launcher", staticmethod(lambda: powershell_exe))
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "powershell"
    item.command = "Write-Output {{input:q}}"
    item.command_variables_enabled = True
    item._runtime_input_values = {"input": "$(Write-Output PWNED)"}

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is True
    argv = captured["args"][0]
    assert argv[5] == "-EncodedCommand"
    assert base64.b64decode(argv[6]).decode("utf-16le") == "Write-Output '$(Write-Output PWNED)'"


def test_execute_command_capture_false_keeps_silent_launch(monkeypatch):
    captured = {}

    class FakeProcess:
        def wait(self, timeout=None):
            return 0

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def run_command_capture(shortcut, timeout=None):
            raise AssertionError("capture branch should not run")

        @staticmethod
        def _launch_with_privilege(*args, **kwargs):
            return False, ""

        @staticmethod
        def _cmd_launcher():
            return "cmd.exe"

        @staticmethod
        def _popen_silent(argv, cwd=None, env=None, shell=False):
            captured["argv"] = argv
            captured["shell"] = shell
            return FakeProcess()

        @staticmethod
        def _safe_split_args(command):
            return command.split()

        @staticmethod
        def _sanitized_child_env():
            return {}

        @staticmethod
        def restore_foreground_window():
            pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo ok"
    item.capture_output = False

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success is True
    assert error == ""
    assert captured["argv"] == ["cmd.exe", "/d", "/s", "/c", "echo ok"]
    assert captured["shell"] is False


def test_execute_command_capture_disabled_for_admin(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def run_command_capture(shortcut, timeout=None):
            raise AssertionError("admin command should not use capture branch")

        @staticmethod
        def _launch_with_privilege(
            target, parameters, directory, show_cmd=0, run_as_admin=False, admin_failure_message=""
        ):
            captured["run_as_admin"] = run_as_admin
            return True, ""

        @staticmethod
        def _safe_split_args(command):
            return command.split()

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo ok"
    item.capture_output = True
    item.run_as_admin = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success is True
    assert error == ""
    assert captured["run_as_admin"] is True


def test_command_dialog_insert_menu_exposes_ip_variables(qapp):
    from qt_compat import QPushButton
    from ui.config_window.command_dialog import CommandDialog

    dialog = CommandDialog(shortcut=ShortcutItem(type=ShortcutType.COMMAND))
    try:
        dialog._show_insert_popup()
        buttons = {button.text(): button for button in dialog._insert_menu.findChildren(QPushButton)}
        assert "内网 IP" in buttons
        assert "公网 IP" in buttons

        buttons["内网 IP"].click()
        qapp.processEvents()
        assert "{{LAN_IP}}" in dialog.command_edit.toPlainText()

        # Re-show popup since clicking an action closes it and may delete child widgets
        dialog._show_insert_popup()
        buttons = {button.text(): button for button in dialog._insert_menu.findChildren(QPushButton)}
        buttons["公网 IP"].click()
        qapp.processEvents()
        assert "{{WAN_IP}}" in dialog.command_edit.toPlainText()
    finally:
        if getattr(dialog, "_insert_menu", None):
            try:
                dialog._insert_menu.close()
                dialog._insert_menu.deleteLater()
            except RuntimeError:
                pass
        dialog.deleteLater()


def test_command_dialog_builtin_disables_insert_and_test(qapp):
    from ui.config_window.command_dialog import CommandDialog

    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.command_type = "builtin"
    shortcut.command = "open_task_manager"
    dialog = CommandDialog(shortcut=shortcut)
    try:
        dialog.type_combo.setCurrentIndex(4)

        assert dialog.insert_var_btn.isEnabled() is False
        assert dialog._test_btn.isEnabled() is False
        dialog._show_insert_popup()
        assert getattr(dialog, "_insert_menu", None) is None
    finally:
        dialog.deleteLater()


# ── Bash (Git Bash) 支持测试 ──────────────────────────────────────────────


def test_normalize_command_type_bash_aliases():
    from core.shortcut_command_exec import CommandExecutionMixin

    assert CommandExecutionMixin._normalize_command_type("bash") == "bash"
    assert CommandExecutionMixin._normalize_command_type("git-bash") == "bash"
    assert CommandExecutionMixin._normalize_command_type("gitbash") == "bash"
    assert CommandExecutionMixin._normalize_command_type("sh") == "bash"
    assert CommandExecutionMixin._normalize_command_type("Bash") == "bash"
    assert CommandExecutionMixin._normalize_command_type("BASH") == "bash"


def test_bash_in_supported_command_types():
    from core.shortcut_command_exec import CommandExecutionMixin

    assert "bash" in CommandExecutionMixin._SUPPORTED_COMMAND_TYPES


def test_bash_launcher_finds_via_shutil(monkeypatch):
    monkeypatch.setattr(
        "core.shortcut_command_exec.shutil.which",
        lambda x: r"C:\Program Files\Git\bin\bash.exe" if x == "bash" else None,
    )
    monkeypatch.setattr("os.path.isfile", lambda p: p.endswith("bash.exe"))

    from core.shortcut_command_exec import CommandExecutionMixin

    result = CommandExecutionMixin._bash_launcher()
    assert result is not None
    assert result.endswith("bash.exe")


def test_bash_launcher_returns_none_when_not_found(monkeypatch):
    monkeypatch.setattr("core.shortcut_command_exec.shutil.which", lambda x: None)
    monkeypatch.setattr("os.path.isfile", lambda p: False)

    from core.shortcut_command_exec import CommandExecutionMixin

    assert CommandExecutionMixin._bash_launcher() is None


def test_bash_argv_constructs_correct_args():
    from core.shortcut_command_exec import CommandExecutionMixin

    class FakeExecutor(CommandExecutionMixin):
        pass

    import core.shortcut_command_exec as ce

    orig = ce.ShortcutExecutor
    ce.ShortcutExecutor = FakeExecutor
    try:
        FakeExecutor._bash_launcher = staticmethod(lambda: r"C:\Git\bin\bash.exe")
        argv = FakeExecutor._bash_argv("echo hello")
        assert argv == [r"C:\Git\bin\bash.exe", "-c", "echo hello"]

        argv_login = FakeExecutor._bash_argv("echo hello", login=True)
        assert argv_login == [r"C:\Git\bin\bash.exe", "--login", "-c", "echo hello"]
    finally:
        ce.ShortcutExecutor = orig


def test_bash_execute_command_silent(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _bash_launcher():
            return r"C:\Program Files\Git\bin\bash.exe"

        @staticmethod
        def _bash_argv(command, login=False):
            return [r"C:\Program Files\Git\bin\bash.exe", "-c", command]

        @staticmethod
        def _popen_silent(argv, cwd=None, env=None, shell=False):
            captured["argv"] = argv
            captured["cwd"] = cwd
            captured["env"] = env
            captured["shell"] = shell

        @staticmethod
        def _runtime_env(shortcut):
            return {"PATH": "C:\\Windows\\System32", "LANG": "en_US.UTF-8"}

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "bash"
    item.command = "ls -la"
    item.show_window = False

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["argv"] == [r"C:\Program Files\Git\bin\bash.exe", "-c", "ls -la"]
    assert captured["shell"] is False
    assert "--login" not in captured["argv"][1:]


def test_bash_execute_command_show_window(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _bash_launcher():
            return r"C:\Program Files\Git\bin\bash.exe"

        @staticmethod
        def _bash_argv(command, login=False):
            argv = [r"C:\Program Files\Git\bin\bash.exe"]
            if login:
                argv.append("--login")
            argv.extend(["-c", command])
            return argv

        @staticmethod
        def _launch_with_privilege(
            target, parameters, directory, show_cmd=1, run_as_admin=False, admin_failure_message=""
        ):
            captured["target"] = target
            captured["parameters"] = parameters
            captured["show_cmd"] = show_cmd
            return True, ""

        @staticmethod
        def _resolve_long_path(p):
            return p

        @staticmethod
        def _cleanup_file_later(*args):
            pass

        @staticmethod
        def _runtime_env(shortcut):
            return {"PATH": "C:\\Windows\\System32", "LANG": "en_US.UTF-8"}

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "bash"
    item.command = "echo hello"
    item.show_window = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["target"].endswith("bash.exe")
    assert "--login" in captured["parameters"]


def test_bash_multiline_command_runs_direct_without_temp_script(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _bash_launcher():
            return r"C:\Program Files\Git\bin\bash.exe"

        @staticmethod
        def _bash_argv(command, login=False):
            argv = [r"C:\Program Files\Git\bin\bash.exe"]
            if login:
                argv.append("--login")
            argv.extend(["-c", command])
            return argv

        @staticmethod
        def _popen_silent(argv, cwd=None, env=None, shell=False):
            captured["argv"] = argv
            captured["cwd"] = cwd
            captured["shell"] = shell

        @staticmethod
        def _runtime_env(shortcut):
            return {"PATH": "C:\\Windows\\System32", "LANG": "en_US.UTF-8"}

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "bash"
    item.command = "echo line1\necho line2"
    item.show_window = False

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert "echo line1\necho line2" in captured["argv"][-1]
    assert ".sh" not in captured["argv"][-1]


def test_bash_capture_output(monkeypatch):
    captured = {}

    class FakePopen:
        def __init__(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            self.returncode = 0

        def communicate(self, timeout=None):
            return b"hello output\n", b""

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(command_exec.subprocess, "Popen", FakePopen)

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _bash_launcher():
            return r"C:\Program Files\Git\bin\bash.exe"

        @staticmethod
        def _bash_argv(command, login=False):
            return [r"C:\Program Files\Git\bin\bash.exe", "-c", command]

        @staticmethod
        def _resolve_long_path(p):
            return p

        @staticmethod
        def _runtime_env(shortcut):
            return {"PATH": "C:\\Windows\\System32"}

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "bash"
    item.command = "echo hello\necho done"
    item.capture_output = True
    item.show_window = False

    result = command_exec.CommandExecutionMixin.run_command_capture(item, timeout=5.0)

    assert result.success
    assert "hello output" in result.payload.get("stdout", "")
    assert captured["args"][0] == [r"C:\Program Files\Git\bin\bash.exe", "-c", item.command]
    assert captured["kwargs"]["shell"] is False


def test_bash_capture_oserror_both_fail_returns_denied_message(monkeypatch):
    """When both direct bash -c and script fallback fail, show combined error."""
    call_count = [0]

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _bash_launcher():
            return r"C:\Program Files\Git\bin\bash.exe"

        @staticmethod
        def _bash_argv(command, login=False):
            return [r"C:\Program Files\Git\bin\bash.exe", "-c", command]

        @staticmethod
        def _runtime_env(shortcut):
            return {"PATH": "C:\\Windows\\System32"}

        @staticmethod
        def _bash_capture_via_script(
            command, cwd, env, timeout_value, start, max_chars, panel_size, command_type, shortcut
        ):
            return None  # fallback also fails

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    def fake_popen(*args, **kwargs):
        call_count[0] += 1
        raise OSError("couldn't create signal pipe, Win32 error 5")

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "bash"
    item.command = "echo hello"
    item.capture_output = True

    result = command_exec.CommandExecutionMixin.run_command_capture(item, timeout=5.0)

    assert result.success is False
    assert call_count == [1]
    assert "Win32 error 5" in result.error


def test_bash_capture_signal_pipe_stderr_returns_clear_failure(monkeypatch):
    class FakePopen:
        returncode = 3221225794

        def communicate(self, input=None, timeout=None):
            return b"", b"0 [main] bash.exe: *** fatal error - couldn't create signal pipe, Win32 error 5"

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(command_exec.subprocess, "Popen", lambda *args, **kwargs: FakePopen())

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _bash_launcher():
            return r"C:\Program Files\Git\bin\bash.exe"

        @staticmethod
        def _bash_argv(command, login=False):
            return [r"C:\Program Files\Git\bin\bash.exe", "-c", command]

        @staticmethod
        def _runtime_env(shortcut):
            return {"PATH": "C:\\Windows\\System32"}

        @staticmethod
        def _bash_capture_via_script(
            command, cwd, env, timeout_value, start, max_chars, panel_size, command_type, shortcut
        ):
            return None  # fallback also fails

        @staticmethod
        def _bash_direct_capture_denied_message(detail):
            return "Git Bash 直接捕获启动失败且在回退模式下也失败了。\n\n" + detail

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "bash"
    item.command = "echo hello"
    item.capture_output = True

    result = command_exec.CommandExecutionMixin.run_command_capture(item, timeout=5.0)

    assert result.success is False
    assert "Win32 error 5" in result.error
    assert result.payload["exit_code"] == 3221225794


def test_bash_capture_direct_timeout(monkeypatch):
    class FakePopen:
        def __init__(self, *args, **kwargs):
            self.returncode = -15
            self.killed = False

        def communicate(self, timeout=None):
            if not self.killed:
                raise command_exec.subprocess.TimeoutExpired("bash", timeout)
            return b"", b""

        def kill(self):
            self.killed = True

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    proc = FakePopen()
    monkeypatch.setattr(command_exec.subprocess, "Popen", FakePopen)

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _bash_launcher():
            return r"C:\Program Files\Git\bin\bash.exe"

        @staticmethod
        def _bash_argv(command, login=False):
            return [r"C:\Program Files\Git\bin\bash.exe", "-c", command]

        @staticmethod
        def _resolve_long_path(p):
            return p

        @staticmethod
        def _runtime_env(shortcut):
            return {"PATH": "C:\\Windows\\System32"}

        @staticmethod
        def _terminate_process_tree(process):
            process.kill()

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.subprocess, "Popen", lambda *args, **kwargs: proc)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "bash"
    item.command = "sleep 999"
    item.capture_output = True
    item.show_window = False

    result = command_exec.CommandExecutionMixin.run_command_capture(item, timeout=0.3)

    assert not result.success
    assert result.payload.get("timed_out") is True
    assert proc.killed is True
    assert "超时" in result.message


def test_bash_capture_direct_cancel(monkeypatch):
    terminated = []

    class FakePopen:
        def __init__(self, *args, **kwargs):
            self.returncode = -15

        def communicate(self, timeout=None):
            return b"", b""

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(command_exec.subprocess, "Popen", FakePopen)

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _bash_launcher():
            return r"C:\Program Files\Git\bin\bash.exe"

        @staticmethod
        def _bash_argv(command, login=False):
            return [r"C:\Program Files\Git\bin\bash.exe", "-c", command]

        @staticmethod
        def _resolve_long_path(p):
            return p

        @staticmethod
        def _runtime_env(shortcut):
            return {"PATH": "C:\\Windows\\System32"}

        @staticmethod
        def _terminate_process_tree(process):
            terminated.append(process)

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "bash"
    item.command = "sleep 999"
    item.capture_output = True
    item.show_window = False

    cancel_event = threading.Event()
    cancel_event.set()
    result = command_exec.CommandExecutionMixin.run_command_capture(item, timeout=5.0, cancel_event=cancel_event)

    assert not result.success
    assert result.payload.get("cancelled") is True
    assert result.payload.get("timed_out") is False
    assert terminated


def test_run_command_capture_validates_runtime_command_params():
    item = ShortcutItem(
        id="port",
        name="Port",
        type=ShortcutType.COMMAND,
        command="echo ok",
        command_type="cmd",
        capture_output=True,
        command_params=[{"name": "port", "validator": "port", "default": "0"}],
    )

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is False
    assert result.display_type == "list"
    assert "端口范围" in result.message


# ── Python capture via stdin (no temp file) ─────────────────


def test_python_capture_uses_stdin_no_temp_file(monkeypatch):
    """Python capture should pipe code via stdin, not a temp .py file."""
    captured = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, input=None, timeout=None):
            captured["stdin_data"] = input
            return "py output", ""

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_python_launcher", staticmethod(lambda: "python"))
    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))

    # Ensure no temp file is written
    writes = []

    def fake_write_temp(*args):
        writes.append(args)
        raise AssertionError("temp file should not be written for capture")

    monkeypatch.setattr(command_exec.ShortcutExecutor, "_write_temp_python_script", staticmethod(fake_write_temp))

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = "print('capture me')"
    item.capture_output = True

    result = command_exec.CommandExecutionMixin.run_command_capture(item)

    assert result.success is True
    assert result.payload["stdout"] == "py output"
    # Verify stdin pipe (not DEVNULL), no script path in args
    assert captured["args"][0] == ["python", "-u"]
    assert captured["kwargs"]["stdin"] == command_exec.subprocess.PIPE
    assert captured["stdin_data"] == b"print('capture me')"
    assert writes == []


# ── Bash capture fallback tests ─────────────────────────────


def test_bash_capture_oserror_fallback_succeeds(monkeypatch):
    """When bash -c raises OSError 'signal pipe', fallback to script should work."""
    popen_calls = []
    fallback_called = []

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _bash_launcher():
            return r"C:\Program Files\Git\bin\bash.exe"

        @staticmethod
        def _bash_argv(command, login=False):
            return [r"C:\Program Files\Git\bin\bash.exe", "-c", command]

        @staticmethod
        def _popen_silent(argv, cwd=None, env=None, shell=False):
            return True, ""

        @staticmethod
        def _runtime_env(shortcut):
            return {"PATH": "C:\\Windows\\System32"}

        @staticmethod
        def _bash_write_script(command):
            return r"C:\Users\Test\AppData\Local\Temp\ql_script.sh"

        @staticmethod
        def _bash_capture_via_script(
            command, cwd, env, timeout_value, start, max_chars, panel_size, command_type, shortcut
        ):
            fallback_called.append((command, command_type))
            return command_exec.CommandResult(
                success=True,
                message="fallback ok",
                display_type="log",
                payload={"stdout": "fallback output", "window_size": panel_size},
            )

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    # First Popen raises OSError (signal pipe)
    original_popen = command_exec.subprocess.Popen

    def fake_popen_first_fail(*args, **kwargs):
        if not popen_calls:
            popen_calls.append(("first", args, kwargs))
            raise OSError("couldn't create signal pipe, Win32 error 5")
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen_first_fail)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "bash"
    item.command = "echo hello"
    item.capture_output = True

    result = command_exec.CommandExecutionMixin.run_command_capture(item, timeout=5.0)

    assert result.success is True
    assert "fallback" in result.message
    assert fallback_called == [("echo hello", "bash")]


def test_bash_capture_stderr_denied_fallback_succeeds(monkeypatch):
    """When bash -c returns stderr with 'signal pipe', fallback to script should work."""
    popen_calls = []
    fallback_called = []

    class FakePopen:
        returncode = 3221225794

        def __init__(self, *args, **kwargs):
            popen_calls.append(args)
            self.returncode = 3221225794

        def communicate(self, input=None, timeout=None):
            return b"", b"couldn't create signal pipe, Win32 error 5"

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(command_exec.subprocess, "Popen", FakePopen)

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _bash_launcher():
            return r"C:\Program Files\Git\bin\bash.exe"

        @staticmethod
        def _bash_argv(command, login=False):
            return [r"C:\Program Files\Git\bin\bash.exe", "-c", command]

        @staticmethod
        def _runtime_env(shortcut):
            return {"PATH": "C:\\Windows\\System32"}

        @staticmethod
        def _bash_capture_via_script(
            command, cwd, env, timeout_value, start, max_chars, panel_size, command_type, shortcut
        ):
            fallback_called.append((command, command_type))
            return command_exec.CommandResult(
                success=True,
                message="fallback ok",
                display_type="log",
                payload={"stdout": "script output", "window_size": panel_size},
            )

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "bash"
    item.command = "echo hello"
    item.capture_output = True

    result = command_exec.CommandExecutionMixin.run_command_capture(item, timeout=5.0)

    assert result.success is True
    assert "fallback" in result.message
    assert fallback_called == [("echo hello", "bash")]


def test_bash_capture_oserror_fallback_returns_denied(monkeypatch):
    """When both direct and fallback bash capture fail, show clear error."""

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _bash_launcher():
            return r"C:\Program Files\Git\bin\bash.exe"

        @staticmethod
        def _bash_argv(command, login=False):
            return [r"C:\Program Files\Git\bin\bash.exe", "-c", command]

        @staticmethod
        def _runtime_env(shortcut):
            return {"PATH": "C:\\Windows\\System32"}

        @staticmethod
        def _bash_capture_via_script(
            command, cwd, env, timeout_value, start, max_chars, panel_size, command_type, shortcut
        ):
            return None  # fallback also fails

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    def fake_popen_fail(*args, **kwargs):
        raise OSError("couldn't create signal pipe, Win32 error 5")

    monkeypatch.setattr(command_exec.subprocess, "Popen", fake_popen_fail)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "bash"
    item.command = "echo hello"
    item.capture_output = True

    result = command_exec.CommandExecutionMixin.run_command_capture(item, timeout=5.0)

    assert result.success is False
    assert "Win32 error 5" in result.error


# ── Python show_window admin launch test ────────────────────


def test_python_visible_window_admin_launch(monkeypatch):
    """Admin + show_window Python should use _launch_with_privilege."""
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _python_launcher():
            return r"C:\Python312\python.exe"

        @staticmethod
        def _write_temp_python_script(command):
            return r"C:\Temp\ql_script.py"

        @staticmethod
        def _launch_with_privilege(
            target, parameters, directory, show_cmd=1, run_as_admin=False, admin_failure_message=""
        ):
            captured["target"] = target
            captured["parameters"] = parameters
            captured["run_as_admin"] = run_as_admin
            return True, ""

        @staticmethod
        def _runtime_env(shortcut):
            return {}

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.os, "name", "nt", raising=False)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = 'print("admin")'
    item.show_window = True
    item.run_as_admin = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["target"] == r"C:\Python312\python.exe"
    assert captured["run_as_admin"] is True


# ── _decode_bytes forwards command_type ─────────────────────


def test_decode_bytes_forwards_command_type(monkeypatch):
    """_decode_bytes should pass command_type to decode_command_output."""
    seen = []

    from core.command_exec import capture as capture_mod

    original_decode = capture_mod._decode_command_output

    def tracking_decode(data, preferred="auto", command_type=""):
        seen.append(command_type)
        return original_decode(data, preferred, command_type=command_type)

    monkeypatch.setattr(capture_mod, "_decode_command_output", tracking_decode)

    monkeypatch.setattr(command_exec.ShortcutExecutor, "_sanitized_child_env", staticmethod(lambda: {}))

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return b"hello", b""

    monkeypatch.setattr(command_exec.subprocess, "Popen", lambda *a, **kw: FakeProcess())

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo ok"
    item.capture_output = True

    command_exec.CommandExecutionMixin.run_command_capture(item)

    # Should have command_type="cmd" in at least one decode call
    assert "cmd" in seen
