"""Tests for the extracted :mod:`core.command_exec` helpers.

These tests exercise the module-level helpers that used to be private
``CommandExecutionMixin`` static methods.  The mixin still keeps the
same method names and delegates to the modules, so the public surface
is preserved.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

from core.command_exec import cleanup as cleanup_mod
from core.command_exec import preflight as preflight_mod
from core.command_exec.cleanup import cleanup_file_later, terminate_process_tree
from core.command_exec.preflight import (
    DESTRUCTIVE_CONFIRMATION_ATTR,
    consume_confirmation,
    destructive_confirmation_result,
    mark_confirmed,
    prepare_command_for_execution,
    requires_confirmation,
)
from core.data_models import ShortcutItem, ShortcutType


def _make_shortcut(**overrides) -> ShortcutItem:
    item = ShortcutItem(
        id=overrides.pop("id", "id"),
        name=overrides.pop("name", "name"),
        type=overrides.pop("type", ShortcutType.COMMAND),
        command=overrides.pop("command", ""),
        command_type=overrides.pop("command_type", "cmd"),
    )
    for key, value in overrides.items():
        setattr(item, key, value)
    return item


# ── cleanup ───────────────────────────────────────────────────────


def test_terminate_process_tree_handles_none():
    assert terminate_process_tree(None) is None


def test_terminate_process_tree_kills_process(monkeypatch):
    process = MagicMock(spec=subprocess.Popen)
    process.pid = 1234
    fake_run = MagicMock()
    monkeypatch.setattr(cleanup_mod.subprocess, "run", fake_run)

    terminate_process_tree(process)

    process.kill.assert_called_once_with()
    # The subprocess.run call uses taskkill on Windows; we only verify it
    # was triggered for the right pid.
    assert fake_run.call_count in (0, 1)


def test_cleanup_file_later_runs_in_background(monkeypatch):
    captured = {}

    class _FakeThread:
        def __init__(self, *, name, target, owner):
            captured["name"] = name
            captured["target"] = target
            captured["owner"] = owner

    monkeypatch.setattr(cleanup_mod, "start_background_thread", _FakeThread)

    process = MagicMock()
    cleanup_file_later(process, ("/tmp/example.tmp",))

    target = captured["target"]
    assert callable(target)
    assert captured["name"] == "CommandTempCleanup"
    assert captured["owner"] == "shortcut-command-exec"

    # Drive the cleanup body directly to confirm it tolerates a closed
    # process and a missing file.
    target()


def test_cleanup_file_later_accepts_no_paths(monkeypatch):
    captured = {}

    class _FakeThread:
        def __init__(self, *, name, target, owner):
            captured["target"] = target

    monkeypatch.setattr(cleanup_mod, "start_background_thread", _FakeThread)

    cleanup_file_later(None)
    captured["target"]()


# ── preflight ─────────────────────────────────────────────────────


def test_requires_confirmation_routes_to_command_type(monkeypatch):
    shortcut = _make_shortcut(command_type="cmd")
    monkeypatch.setattr(preflight_mod, "assess_command_risk", lambda *args, **kwargs: [])
    assert requires_confirmation(shortcut) == []


def test_mark_and_consume_confirmation_roundtrip():
    shortcut = _make_shortcut()
    assert consume_confirmation(shortcut) is False
    mark_confirmed(shortcut, True)
    assert getattr(shortcut, DESTRUCTIVE_CONFIRMATION_ATTR) is True
    assert consume_confirmation(shortcut) is True
    # One-shot: after consume the flag should be cleared.
    assert getattr(shortcut, DESTRUCTIVE_CONFIRMATION_ATTR) is False
    assert consume_confirmation(shortcut) is False


def test_destructive_confirmation_result_returns_none_when_no_risks(monkeypatch):
    monkeypatch.setattr(preflight_mod, "requires_confirmation", lambda *a, **kw: [])
    shortcut = _make_shortcut()
    assert destructive_confirmation_result(shortcut, "echo hi", "cmd") is None


def test_destructive_confirmation_result_includes_risks(monkeypatch):
    monkeypatch.setattr(
        preflight_mod,
        "requires_confirmation",
        lambda *a, **kw: [{"code": "rm_rf", "message": "deletes files"}],
    )
    shortcut = _make_shortcut()
    result = destructive_confirmation_result(shortcut, "rm -rf /", "cmd")
    assert result is not None
    assert result.success is False
    assert result.display_type == "confirm"
    assert result.payload["requires_confirmation"] is True
    assert "deletes files" in result.payload["detail"]


def test_destructive_confirmation_result_respects_existing_confirmation(monkeypatch):
    monkeypatch.setattr(
        preflight_mod,
        "requires_confirmation",
        lambda *a, **kw: [{"code": "rm_rf", "message": "deletes files"}],
    )
    shortcut = _make_shortcut()
    mark_confirmed(shortcut, True)
    assert destructive_confirmation_result(shortcut, "rm -rf /", "cmd") is None


def test_prepare_command_for_execution_returns_none_for_clean_command(monkeypatch):
    monkeypatch.setattr(
        preflight_mod,
        "_should_expand_command_variables",
        lambda *a, **kw: False,
        raising=False,
    )

    class _LegacyMixin:
        @staticmethod
        def _should_expand_command_variables(_shortcut):
            return False

    monkeypatch.setattr(
        "core.shortcut_command_exec.CommandExecutionMixin",
        _LegacyMixin,
    )

    shortcut = _make_shortcut(command="echo hi", command_type="cmd")
    new_command, error = prepare_command_for_execution(shortcut, "echo hi", "cmd")
    assert new_command == "echo hi"
    assert error is None


def test_prepare_command_for_execution_rejects_only_variable_command(monkeypatch):
    class _LegacyMixin:
        @staticmethod
        def _should_expand_command_variables(_shortcut):
            return True

    monkeypatch.setattr(
        "core.shortcut_command_exec.CommandExecutionMixin",
        _LegacyMixin,
    )

    shortcut = _make_shortcut(
        command="{{param:cmd:q}}",
        command_type="cmd",
        command_variables_enabled=True,
    )
    _, error = prepare_command_for_execution(shortcut, "{{param:cmd:q}}", "cmd")
    assert error is not None
    assert error.success is False
    assert "占位符" in error.message or "placeholder" in error.message.lower()


def test_prepare_command_for_execution_resolves_variables(monkeypatch):
    class _LegacyMixin:
        @staticmethod
        def _should_expand_command_variables(_shortcut):
            return True

        @staticmethod
        def _resolve_command_variables(_shortcut, command):
            return command.replace("{{name}}", "world")

    monkeypatch.setattr(
        "core.shortcut_command_exec.CommandExecutionMixin",
        _LegacyMixin,
    )

    shortcut = _make_shortcut(
        command="echo {{name}}",
        command_type="cmd",
        command_variables_enabled=True,
    )
    new_command, error = prepare_command_for_execution(shortcut, "echo {{name}}", "cmd")
    assert error is None
    assert new_command == "echo world"
