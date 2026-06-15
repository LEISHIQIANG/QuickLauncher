"""Tests for the verified topmost toggle implementation."""

import json
import os
import threading
from pathlib import Path

import core.shortcut_command_exec as command_exec
import core.shortcut_hotkey as hotkey
import core.shortcut_window_control as window_control
from core.data_models import ShortcutItem, ShortcutType


def _handle_value(value) -> int:
    raw = getattr(value, "value", value)
    return int(raw or 0)


class FakeKernel32:
    def __init__(self, process_id: int = 999):
        self.process_id = process_id

    def GetCurrentProcessId(self):
        return self.process_id


class FakeUser32:
    def __init__(self):
        self.valid = {100, 110, 200}
        self.root_owner = {110: 100}
        self.process_ids = {100: 42, 110: 42, 200: 84}
        self.class_names = {100: "Notepad", 110: "Dialog", 200: "CabinetWClass"}
        self.topmost = {100: True, 110: True, 200: False}
        self.cursor_hwnd = 200
        self.foreground_hwnd = 100
        self.ignore_state_changes = 0
        self.reuse_after_set = False
        self.set_calls = []

    def IsWindow(self, hwnd):
        return _handle_value(hwnd) in self.valid

    def GetForegroundWindow(self):
        return self.foreground_hwnd

    def GetAncestor(self, hwnd, flag):
        handle = _handle_value(hwnd)
        return self.root_owner.get(handle, handle)

    def GetDesktopWindow(self):
        return 1

    def GetShellWindow(self):
        return 2

    def GetWindowThreadProcessId(self, hwnd, process_id_ref):
        process_id_ref._obj.value = self.process_ids.get(_handle_value(hwnd), 0)
        return 1 if process_id_ref._obj.value else 0

    def GetClassNameW(self, hwnd, buffer, length):
        buffer.value = self.class_names.get(_handle_value(hwnd), "")[: max(0, length - 1)]
        return len(buffer.value)

    def GetWindowLongW(self, hwnd, index):
        assert index == window_control.GWL_EXSTYLE
        return window_control.WS_EX_TOPMOST if self.topmost.get(_handle_value(hwnd), False) else 0

    def SetWindowPos(self, hwnd, insert_after, x, y, cx, cy, flags):
        handle = _handle_value(hwnd)
        self.set_calls.append((handle, _handle_value(insert_after), flags))
        if self.ignore_state_changes:
            self.ignore_state_changes -= 1
        else:
            self.topmost[handle] = _handle_value(insert_after) == _handle_value(window_control.HWND_TOPMOST)
        if self.reuse_after_set:
            self.process_ids[handle] = 777
        return 1

    def GetWindowTextW(self, hwnd, buffer, length):
        buffer.value = f"Window {_handle_value(hwnd)}"
        return len(buffer.value)


def _make_executor(
    monkeypatch,
    user32: FakeUser32,
    previous_hwnd=110,
    previous_process_id=42,
    current_process_id=999,
):
    class FakeExecutor(window_control.WindowControlMixin):
        _previous_hwnd = previous_hwnd
        _previous_hwnd_process_id = previous_process_id

        @staticmethod
        def _get_window_at_cursor():
            return user32.cursor_hwnd

    monkeypatch.setattr(window_control, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(window_control, "user32", user32)
    monkeypatch.setattr(window_control, "kernel32", FakeKernel32(current_process_id))
    monkeypatch.setattr(window_control.time, "sleep", lambda _seconds: None)
    return FakeExecutor


def test_toggle_changes_root_owner_and_consumes_saved_window(monkeypatch):
    user32 = FakeUser32()
    executor = _make_executor(monkeypatch, user32)

    assert executor._toggle_topmost() is True
    assert user32.topmost[100] is False
    assert executor._previous_hwnd is None
    assert user32.set_calls == [
        (
            100,
            _handle_value(window_control.HWND_NOTOPMOST),
            window_control.SWP_NOMOVE | window_control.SWP_NOSIZE | window_control.SWP_NOACTIVATE,
        )
    ]


def test_toggle_retries_until_requested_state_is_verified(monkeypatch):
    user32 = FakeUser32()
    user32.ignore_state_changes = 1
    executor = _make_executor(monkeypatch, user32)

    assert executor._toggle_topmost() is True
    assert user32.topmost[100] is False
    assert len(user32.set_calls) == 2


def test_toggle_rejects_reused_window_handle(monkeypatch):
    user32 = FakeUser32()
    user32.reuse_after_set = True
    executor = _make_executor(monkeypatch, user32)

    assert executor._toggle_topmost() is False


def test_toggle_rejects_handle_reused_before_target_capture(monkeypatch):
    user32 = FakeUser32()
    user32.process_ids[110] = 777
    user32.process_ids[200] = 0
    executor = _make_executor(monkeypatch, user32, previous_process_id=42)

    assert executor._toggle_topmost() is False
    assert user32.set_calls == []


def test_toggle_skips_quicklauncher_window_and_uses_cursor_target(monkeypatch):
    user32 = FakeUser32()
    user32.process_ids[100] = 999
    executor = _make_executor(monkeypatch, user32, current_process_id=999)

    assert executor._toggle_topmost() is True
    assert user32.topmost[200] is True
    assert user32.set_calls[0][0] == 200


def test_foreground_capture_does_not_overwrite_external_target_with_own_popup(monkeypatch):
    user32 = FakeUser32()
    user32.process_ids[200] = os.getpid()

    class FakeExecutor(hotkey.HotkeyExecutionMixin, window_control.WindowControlMixin):
        _previous_hwnd = None
        _previous_hwnd_process_id = None
        _foreground_window_lock = threading.RLock()

    monkeypatch.setattr(hotkey, "user32", user32)
    monkeypatch.setattr(window_control, "user32", user32)

    user32.foreground_hwnd = 100
    assert FakeExecutor.save_foreground_window() is True
    assert (FakeExecutor._previous_hwnd, FakeExecutor._previous_hwnd_process_id) == (100, 42)

    user32.foreground_hwnd = 200
    assert FakeExecutor.save_foreground_window() is False
    assert (FakeExecutor._previous_hwnd, FakeExecutor._previous_hwnd_process_id) == (100, 42)


def test_toggle_rejects_desktop_shell_surfaces(monkeypatch):
    user32 = FakeUser32()
    user32.class_names[100] = "WorkerW"
    user32.class_names[200] = "Shell_TrayWnd"
    executor = _make_executor(monkeypatch, user32)

    assert executor._toggle_topmost() is False
    assert user32.set_calls == []


def test_force_topmost_is_idempotent(monkeypatch):
    user32 = FakeUser32()
    executor = _make_executor(monkeypatch, user32)

    assert executor._set_topmost(True) is True
    assert user32.topmost[100] is True
    assert user32.set_calls == []


def test_legacy_force_topmost_commands_remain_compatible_but_not_advertised():
    from core.builtin_commands import BUILTIN_COMMAND_ALIASES
    from core.command_registry import CommandRegistry
    from core.slash_commands import SLASH_COMMANDS

    force_on_aliases = {"topmost_on", "置顶开", "pin_on", "pin-on"}
    force_off_aliases = {"topmost_off", "置顶关", "unpin", "pin_off", "pin-off"}
    assert all(BUILTIN_COMMAND_ALIASES[alias] == "pin_on" for alias in force_on_aliases)
    assert all(BUILTIN_COMMAND_ALIASES[alias] == "pin_off" for alias in force_off_aliases)
    assert {"pin-on", "pin-off"}.isdisjoint(command.canonical for command in SLASH_COMMANDS)

    topmost = next(command for command in SLASH_COMMANDS if command.canonical == "topmost")
    assert "toggle_topmost" in topmost.aliases

    registry = CommandRegistry()
    registry.migrate_slash_commands()
    registry.migrate_builtin_aliases()
    assert registry.get_canonical("pin-on") == "pin_on"
    assert registry.get_canonical("pin-off") == "pin_off"


def test_builtin_dispatch_supports_toggle_and_legacy_force_commands(monkeypatch):
    calls = []

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _toggle_topmost(target=window_control._TOPMOST_TARGET_UNSET):
            calls.append(("toggle", target))
            return True

        @staticmethod
        def _set_topmost(topmost, target=window_control._TOPMOST_TARGET_UNSET):
            calls.append(("set", topmost, target))
            return True

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)

    assert command_exec.CommandExecutionMixin._execute_builtin_command("topmost") is True
    assert command_exec.CommandExecutionMixin._execute_builtin_command("pin_on") is True
    assert command_exec.CommandExecutionMixin._execute_builtin_command("pin_off") is True
    assert calls == [
        ("toggle", window_control._TOPMOST_TARGET_UNSET),
        ("set", True, window_control._TOPMOST_TARGET_UNSET),
        ("set", False, window_control._TOPMOST_TARGET_UNSET),
    ]


def test_captured_missing_target_does_not_fall_back_late(monkeypatch):
    calls = []

    class FakeExecutor(command_exec.CommandExecutionMixin):
        @staticmethod
        def _toggle_topmost(target=window_control._TOPMOST_TARGET_UNSET):
            calls.append(target)
            return target is not None

    monkeypatch.setattr(command_exec, "ShortcutExecutor", FakeExecutor)
    shortcut = ShortcutItem(type=ShortcutType.COMMAND, command="topmost", command_type="builtin")
    shortcut._topmost_target_captured = True
    shortcut._topmost_target = None

    assert FakeExecutor._execute_builtin_for_shortcut(shortcut, shortcut.command) is False
    assert calls == [None]


def test_system_topmost_shortcut_uses_builtin_command_type():
    config_path = Path(__file__).parents[1] / "assets" / "system_icons" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    topmost = next(item for item in config["items"] if item.get("command") == "topmost")
    assert topmost["command_type"] == "builtin"
