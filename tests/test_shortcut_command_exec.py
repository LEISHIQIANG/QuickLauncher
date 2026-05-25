import sys
import types

import core.shortcut_command_exec as command_exec
from core.data_models import ShortcutItem, ShortcutType


def test_python_visible_window_uses_wrapper_without_nested_quotes(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _python_launcher():
            return "python"

        @staticmethod
        def _write_temp_python_script(command):
            return r"C:\Users\Administrator\AppData\Local\Temp\tmp94kufm62.py"

        @staticmethod
        def _write_python_cmd_wrapper(script_path):
            return r"C:\Users\Administrator\AppData\Local\Temp\ql_py_wrapper.cmd"

        @staticmethod
        def _launch_with_privilege(target, parameters, directory, show_cmd=1, run_as_admin=False, admin_failure_message=""):
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
    assert captured["target"].endswith("cmd.exe")
    assert "/k" in captured["parameters"]
    assert "ql_py_wrapper.cmd" in captured["parameters"]
    assert r"\"C:\Users" not in captured["parameters"]
    assert "tmp94kufm62.py" not in captured["parameters"]


def test_config_window_alias_is_rerouted_even_when_saved_as_cmd(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _execute_builtin_command(command):
            captured["builtin"] = command
            return True

        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("show_config_window must not be executed as a shell command")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "show_config_window"

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["builtin"] == "show_config_window"


def test_system_builtin_alias_is_rerouted_even_when_saved_as_cmd(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _execute_builtin_command(command):
            captured["builtin"] = command
            return True

        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("system built-ins must not be executed as shell commands")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "open_control_panel"

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["builtin"] == "open_control_panel"


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


def test_test_command_reroutes_builtin_alias_saved_as_cmd(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _execute_builtin_command(command):
            captured["builtin"] = command
            return True

        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("test_command must not shell out known built-ins")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "open_this_pc"

    result = command_exec.CommandExecutionMixin.test_command(item)

    assert result["success"] is True
    assert result["exit_code"] == 0
    assert captured["builtin"] == "open_this_pc"


def test_config_window_builtin_uses_direct_fallback_when_callback_missing(monkeypatch):
    import core

    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _send_ipc_command_deferred(command):
            raise AssertionError("direct fallback should run before IPC")

    def direct_show():
        captured["direct"] = True
        return True

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(core, "has_callback", lambda name: False)
    monkeypatch.setattr(core, "call_callback", lambda name: None)
    monkeypatch.setitem(sys.modules, "main", types.SimpleNamespace(show_config_window_direct=direct_show))

    assert command_exec.CommandExecutionMixin._execute_builtin_command("show_config_window")
    assert captured["direct"] is True


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
    import core

    called = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        pass

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(FakeExecutor, "_is_qt_main_thread", staticmethod(lambda: False))
    monkeypatch.setattr(core, "has_callback", lambda name: name == "show_help")
    monkeypatch.setattr(core, "call_callback", lambda name: called.setdefault("name", name))

    assert command_exec.CommandExecutionMixin._execute_builtin_command("show_help")
    assert called == {}


def test_python_variables_are_disabled_by_default(monkeypatch):
    monkeypatch.setattr(command_exec, "ShortcutExecutor", command_exec.CommandExecutionMixin)
    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = 'print("{date}")'
    item.command_variables_enabled = False

    resolved = command_exec.CommandExecutionMixin._resolve_command_variables(item, item.command)

    assert resolved == item.command


def test_python_variables_can_be_enabled_explicitly(monkeypatch):
    monkeypatch.setattr(command_exec, "ShortcutExecutor", command_exec.CommandExecutionMixin)
    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = 'print("{date}")'
    item.command_variables_enabled = True

    resolved = command_exec.CommandExecutionMixin._resolve_command_variables(item, item.command)

    assert "{date}" not in resolved


def test_multiline_cmd_uses_wrapper_without_single_line_fallthrough(monkeypatch):
    captured = {}

    class FakeProcess:
        def wait(self):
            return 0

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _write_cmd_wrapper(command):
            captured["wrapped_command"] = command
            return r"C:\Temp\ql_user.cmd", r"C:\Temp\ql_wrapper.cmd"

        @staticmethod
        def _launch_with_privilege(target, parameters, directory, show_cmd=0, run_as_admin=False, admin_failure_message=""):
            captured["target"] = target
            captured["parameters"] = parameters
            captured["directory"] = directory
            return False, ""

        @staticmethod
        def _popen_silent(argv, cwd=None, env=None, shell=False):
            captured["popen"] = (argv, cwd, shell)
            return FakeProcess()

        @staticmethod
        def _sanitized_child_env():
            return {}

        @staticmethod
        def _safe_split_args(command):
            raise AssertionError("multiline CMD should not fall through to single-line parsing")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setenv("ComSpec", r"C:\Windows\System32\cmd.exe")

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = 'if exist "C:\\" (\n  echo ok\n)'
    item.command_variables_enabled = False

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["wrapped_command"] == item.command
    assert "ql_wrapper.cmd" in captured["parameters"]
    assert captured["popen"][0][-1].endswith("ql_wrapper.cmd")


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
    item.command = "{date}"
    item.command_variables_enabled = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert not success
    assert "值占位符" in error
    assert "echo {date}" in error


def test_value_only_variable_is_rejected_even_when_variables_disabled(monkeypatch):
    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("value-only variable must not be executed")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "{date}"
    item.command_variables_enabled = False

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert not success
    assert "解析变量" in error


def test_command_variable_inside_real_command_still_executes(monkeypatch):
    captured = {}

    class FakeProcess:
        def wait(self, timeout=None):
            return 0

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _launch_with_privilege(target, parameters, directory, show_cmd=0, run_as_admin=False, admin_failure_message=""):
            return False, ""

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
    item.command = "echo {date}"
    item.command_variables_enabled = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["shell"] is True
    assert captured["argv"].startswith("echo ")


def test_unquoted_external_variable_in_cmd_is_rejected(monkeypatch):
    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _popen_silent(*args, **kwargs):
            raise AssertionError("unsafe variable command must not execute")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "cmd"
    item.command = "echo {clipboard}"
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
    item.command = "echo {clipboard}"
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
    item.command = "{date}"
    item.command_variables_enabled = False

    result = command_exec.CommandExecutionMixin.test_command(item)

    assert result["success"] is False
    assert result["error"]


def test_quoted_external_variable_in_cmd_still_executes(monkeypatch):
    captured = {}

    class FakeProcess:
        def wait(self, timeout=None):
            return 0

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _launch_with_privilege(target, parameters, directory, show_cmd=0, run_as_admin=False, admin_failure_message=""):
            return False, ""

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
    item.command = "echo {clipboard:q}"
    item.command_variables_enabled = True

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["shell"] is True
    assert '"hello world"' in captured["argv"]


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
    item.python_execution_mode = "subprocess"

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert not success
    assert "系统 Python" in error
    assert "python312.dll" in error
    assert writes == []


def test_frozen_silent_python_without_launcher_does_not_fall_back_to_inline(monkeypatch):
    executed = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _python_launcher():
            return None

        @staticmethod
        def _python_inline_context():
            return executed

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(command_exec.sys, "frozen", True, raising=False)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = "value = 42"
    item.show_window = False
    item.python_execution_mode = "subprocess"

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert not success
    assert "系统 Python" in error
    assert executed == {}


def test_elevated_normal_python_uses_privilege_boundary_not_inline(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _is_launch_context_elevated():
            return True

        @staticmethod
        def _python_launcher():
            return r"C:\Python312\python.exe"

        @staticmethod
        def _write_temp_python_script(command):
            captured["script_command"] = command
            return r"C:\Temp\ql_script.py"

        @staticmethod
        def _launch_with_privilege(target, parameters, directory, show_cmd=0, run_as_admin=False, admin_failure_message=""):
            captured["target"] = target
            captured["run_as_admin"] = run_as_admin
            return True, ""

        @staticmethod
        def _python_inline_context():
            raise AssertionError("elevated launcher must not run normal python inline")

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.COMMAND)
    item.command_type = "python"
    item.command = "value = 42"
    item.show_window = False
    item.python_execution_mode = "legacy_inline"
    item.run_as_admin = False

    success, error = command_exec.CommandExecutionMixin._execute_command(item)

    assert success
    assert error == ""
    assert captured["target"] == r"C:\Python312\python.exe"
    assert captured["run_as_admin"] is False


def test_admin_cmd_success_after_standard_fallback_is_reported_success(monkeypatch):
    captured = {}

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _safe_split_args(command):
            return [r"C:\Tools\App.exe", "--flag"]

        @staticmethod
        def _launch_with_privilege(target, parameters, directory, show_cmd=0, run_as_admin=False, admin_failure_message=""):
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
        def _launch_with_privilege(target, parameters, directory, show_cmd=0, run_as_admin=False, admin_failure_message=""):
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
