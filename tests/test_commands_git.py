import subprocess

from core.command_registry import CommandContext
from core.commands import cmd_git as facade_cmd_git
from core.commands_git import cmd_git


def test_cmd_git_facade_identity():
    assert facade_cmd_git is cmd_git


def test_cmd_git_rejects_unknown_subcommand():
    result = cmd_git(CommandContext(args_text="reset"))

    assert result.success is False
    assert result.error == "未知 Git 子命令"
    assert result.payload["window_size"] == "large"


def test_cmd_git_checkout_requires_branch():
    result = cmd_git(CommandContext(args_text="checkout"))

    assert result.success is False
    assert result.error == "缺少分支名"


def test_cmd_git_rejects_missing_repo(tmp_path):
    missing = tmp_path / "missing"

    result = cmd_git(CommandContext(args_text=f"status {missing}"))

    assert result.success is False
    assert result.error == "目录不存在"
    assert result.payload["repo"] == str(missing)


def test_cmd_git_rejects_non_git_directory(monkeypatch, tmp_path):
    class Proc:
        def __init__(self, argv, cwd=None, **kwargs):
            self.argv = argv
            self.cwd = cwd
            self.returncode = 128

        def communicate(self, timeout=None):
            return "", "fatal: not a git repository\n"

    monkeypatch.setattr("subprocess.Popen", Proc)

    result = cmd_git(CommandContext(args_text=f"status {tmp_path}"))

    assert result.success is False
    assert result.error == "不是 Git 仓库"
    assert result.payload["exit_code"] == 128


def test_cmd_git_branch_table(monkeypatch, tmp_path):
    class Proc:
        def __init__(self, argv, cwd=None, **kwargs):
            self.argv = argv
            self.cwd = cwd
            self.returncode = 0

        def communicate(self, timeout=None):
            if self.argv[1:3] == ["rev-parse", "--is-inside-work-tree"]:
                return "true\n", ""
            return "* main abc123\n  remotes/origin/main abc123\n", ""

    monkeypatch.setattr("subprocess.Popen", Proc)

    result = cmd_git(CommandContext(args_text=f"branch {tmp_path}"))

    assert result.success is True
    assert result.display_type == "table"
    assert result.payload["columns"] == ["Current", "Branch"]
    assert result.payload["rows"][0] == ["*", "main abc123"]


def test_cmd_git_timeout_kills_process(monkeypatch, tmp_path):
    processes = []

    class Proc:
        def __init__(self, argv, cwd=None, **kwargs):
            self.argv = argv
            self.cwd = cwd
            self.returncode = 0
            self.killed = False
            processes.append(self)

        def communicate(self, timeout=None):
            if self.argv[1:3] == ["rev-parse", "--is-inside-work-tree"]:
                return "true\n", ""
            if not self.killed:
                raise subprocess.TimeoutExpired(self.argv, timeout)
            return "", ""

        def kill(self):
            self.killed = True

    monkeypatch.setattr("subprocess.Popen", Proc)

    result = cmd_git(CommandContext(args_text=f"pull {tmp_path}"))

    assert result.success is False
    assert result.error == "执行超时"
    assert result.payload["timed_out"] is True
    assert processes[-1].killed is True
