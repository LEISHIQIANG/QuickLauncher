"""Guard tests for the W3.2 platform-executor functions.

The legacy :class:`CommandExecutionMixin` had five platform executors
(``_execute_powershell_command`` / ``_execute_bash_command`` /
``_execute_python_command`` / ``_execute_cmd_command``) that were
tightly coupled to the host class via private attribute lookups.
W3.2 splits the executor bodies into module-level functions in
:mod:`core.command_exec.platform_executors` so the call graph is
explicit and the mixin host can be refactored without rewriting each
executor.

These tests pin the contract: given a fake host (the function arguments
are the dependency surface), the executor returns the historical
``(success, error_message)`` tuple.  Behaviour drift is caught by
:file:`tests/test_shortcut_command_exec.py`'s 83 integration tests
which still call the legacy mixin methods.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

from core.command_exec import (
    execute_bash_command,
    execute_powershell_command,
    execute_silent_bash_command,
    execute_visible_bash_command,
)


class _FakeProcess:
    """Stand-in for ``Popen`` objects the platform executors may emit."""

    def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        return (b"", b"")


def _make_shortcut(**overrides: Any) -> SimpleNamespace:
    base = {
        "show_window": False,
        "run_as_admin": False,
        "working_dir": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _ExecutePowershellTest(unittest.TestCase):
    def test_returns_true_for_silent_launch(self) -> None:
        """Silent PowerShell: ``popen_silent`` is invoked, not ``popen``."""
        argv_holder: dict[str, Any] = {}

        def powershell_argv(command: str, no_exit: bool) -> list[str]:
            argv_holder["args"] = (command, no_exit)
            return ["pwsh.exe", "-NoProfile", "-Command", command]

        popen_calls: list[dict[str, Any]] = []

        def popen_silent(argv, **kwargs):
            popen_calls.append({"argv": argv, "kwargs": kwargs})
            return _FakeProcess()

        success, message = execute_powershell_command(
            _make_shortcut(),
            "Get-Date",
            powershell_argv=powershell_argv,
            direct_too_long=lambda argv: False,
            direct_length_error=lambda kind, argv: "too long",
            runtime_env=lambda shortcut: {},
            launch_with_privilege=lambda *args, **kwargs: (True, ""),
            popen_silent=popen_silent,
            powershell_launcher_error=lambda: "pwsh missing",
        )
        self.assertTrue(success)
        self.assertEqual(message, "")
        self.assertEqual(argv_holder["args"], ("Get-Date", False))
        self.assertEqual(len(popen_calls), 1)

    def test_returns_false_when_direct_command_too_long(self) -> None:
        success, message = execute_powershell_command(
            _make_shortcut(),
            "Get-Date",
            powershell_argv=lambda c, no_exit: ["pwsh"],
            direct_too_long=lambda argv: True,
            direct_length_error=lambda kind, argv: "powershell command is too long",
            runtime_env=lambda shortcut: {},
            launch_with_privilege=lambda *a, **k: (True, ""),
            popen_silent=lambda *a, **k: _FakeProcess(),
            powershell_launcher_error=lambda: "pwsh missing",
        )
        self.assertFalse(success)
        self.assertIn("too long", message)

    def test_returns_false_on_filenotfound(self) -> None:
        def raise_fnf(argv, **kwargs):
            raise FileNotFoundError("nope")

        success, message = execute_powershell_command(
            _make_shortcut(),
            "Get-Date",
            powershell_argv=lambda c, no_exit: ["pwsh"],
            direct_too_long=lambda argv: False,
            direct_length_error=lambda kind, argv: "x",
            runtime_env=lambda shortcut: {},
            launch_with_privilege=lambda *a, **k: (True, ""),
            popen_silent=raise_fnf,
            powershell_launcher_error=lambda: "pwsh missing",
        )
        self.assertFalse(success)
        self.assertEqual(message, "pwsh missing")


class _ExecuteBashTest(unittest.TestCase):
    def test_visible_launch_uses_bash_argv_with_login(self) -> None:
        argv_holder: dict[str, bool] = {}

        def bash_argv(command: str, login: bool) -> list[str]:
            argv_holder["login"] = login
            return ["bash", "--login", "-c", command]

        success, message = execute_visible_bash_command(
            "echo hi",
            cwd=None,
            bash_env={"PATH": "/bin"},
            run_as_admin=False,
            bash_launcher=lambda: "C:/Program Files/Git/bin/bash.exe",
            bash_argv=bash_argv,
            direct_too_long=lambda argv: False,
            direct_length_error=lambda kind, argv: "x",
            launch_with_privilege=lambda *a, **k: (True, ""),
            bash_launcher_error=lambda: "bash missing",
        )
        self.assertTrue(success)
        self.assertTrue(argv_holder["login"])

    def test_silent_launch_calls_popen_silent(self) -> None:
        seen: dict[str, Any] = {}

        def popen_silent(argv, **kwargs):
            seen["argv"] = argv
            return _FakeProcess()

        success, _ = execute_silent_bash_command(
            "echo hi",
            cwd=None,
            bash_env={"PATH": "/bin"},
            bash_launcher=lambda: "bash",
            bash_argv=lambda c, login: ["bash", "-c", c],
            direct_too_long=lambda argv: False,
            direct_length_error=lambda kind, argv: "x",
            popen_silent=popen_silent,
            bash_launcher_error=lambda: "bash missing",
        )
        self.assertTrue(success)
        self.assertEqual(seen["argv"], ["bash", "-c", "echo hi"])

    def test_bash_command_dispatch_with_show_window(self) -> None:
        # The ``execute_bash_command`` dispatcher still delegates to
        # the legacy ``ShortcutExecutor`` helpers for now (P2).  The
        # contract is that the function dispatches to the right
        # helper; verify by passing a unique bash path the legacy
        # helpers will not raise on.
        shortcut = _make_shortcut(show_window=True)
        calls = []

        def visible(command, cwd, env, run_as_admin):
            calls.append((command, cwd, env, run_as_admin))
            return True, ""

        success, message = execute_bash_command(
            shortcut,
            "echo hi",
            runtime_env=lambda sc: {},
            visible_executor=visible,
            silent_executor=lambda command, cwd, env: (True, ""),
        )
        self.assertTrue(success)
        self.assertEqual(message, "")
        self.assertEqual(calls[0][0], "echo hi")
        self.assertIsNone(calls[0][1])
        self.assertFalse(calls[0][3])
        self.assertEqual(calls[0][2]["LANG"], "en_US.UTF-8")


if __name__ == "__main__":
    unittest.main()
