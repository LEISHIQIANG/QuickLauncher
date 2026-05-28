from core.command_registry import CommandContext
from core.commands import cmd_env as facade_cmd_env
from core.commands import cmd_god as facade_cmd_god
from core.commands_windows import cmd_env, cmd_god


def test_cmd_env_launches_environment_editor(monkeypatch):
    calls = []
    monkeypatch.setattr("subprocess.Popen", lambda argv: calls.append(argv))

    result = cmd_env(CommandContext())

    assert result.success is True
    assert calls == [["rundll32.exe", "sysdm.cpl,EditEnvironmentVariables"]]
    assert facade_cmd_env is cmd_env


def test_cmd_env_reports_launch_failure(monkeypatch):
    def fail(argv):
        raise OSError("blocked")

    monkeypatch.setattr("subprocess.Popen", fail)

    result = cmd_env(CommandContext())

    assert result.success is False
    assert result.error == "启动失败"


def test_cmd_god_uses_startfile_first(monkeypatch):
    calls = []
    monkeypatch.setattr("os.startfile", lambda target: calls.append(target), raising=False)

    result = cmd_god(CommandContext())

    assert result.success is True
    assert calls == ["shell:::{ED7BA470-8E54-465E-825C-99712043E01C}"]
    assert facade_cmd_god is cmd_god


def test_cmd_god_falls_back_to_explorer(monkeypatch):
    popen_calls = []

    def fail_startfile(target):
        raise OSError("no startfile")

    monkeypatch.setattr("os.startfile", fail_startfile, raising=False)
    monkeypatch.setattr("subprocess.Popen", lambda argv: popen_calls.append(argv))

    result = cmd_god(CommandContext())

    assert result.success is True
    assert popen_calls == [["explorer.exe", "shell:::{ED7BA470-8E54-465E-825C-99712043E01C}"]]


def test_cmd_god_reports_failure_when_all_launchers_fail(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("blocked")

    monkeypatch.setattr("os.startfile", fail, raising=False)
    monkeypatch.setattr("subprocess.Popen", fail)

    result = cmd_god(CommandContext())

    assert result.success is False
    assert result.error == "打开失败"
