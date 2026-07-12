"""Tests for core/shortcut_executor.py"""

from unittest.mock import MagicMock

import core.shortcut_executor as se
from core.data_models import ShortcutItem, ShortcutType
from core.shortcut_executor import (
    STANDARD_USER_LAUNCH_FAILED_MESSAGE,
    ShortcutExecutor,
    _bind_shortcut_executor_mixins,
)


def test_module_constant():
    assert STANDARD_USER_LAUNCH_FAILED_MESSAGE
    assert isinstance(STANDARD_USER_LAUNCH_FAILED_MESSAGE, str)


def test_shortcut_executor_class_attrs():
    assert ShortcutExecutor._previous_hwnd is None
    assert hasattr(ShortcutExecutor, "_hotkey_lock")
    assert ShortcutExecutor._hotkey_lock_timeout == 2.0


def test_point_structure():
    pt = ShortcutExecutor.POINT(100, 200)
    assert pt.x == 100
    assert pt.y == 200
    pt2 = ShortcutExecutor.POINT()
    assert pt2.x == 0
    assert pt2.y == 0


def test_execute_exception_handling(monkeypatch):
    def raise_error(_):
        raise RuntimeError("boom")

    monkeypatch.setattr(ShortcutExecutor, "_execute_hotkey_safe", staticmethod(raise_error))
    shortcut = MagicMock(spec=ShortcutItem)
    shortcut.type = ShortcutType.HOTKEY
    shortcut.run_as_admin = False
    success, error = ShortcutExecutor.execute(shortcut)
    assert success is False
    assert "boom" in error


def test_execute_batch_launch_type(monkeypatch):
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.error = None
    import core.batch_launch_exec

    monkeypatch.setattr(core.batch_launch_exec, "execute_batch_launch", lambda shortcut, data_manager: mock_result)
    shortcut = MagicMock(spec=ShortcutItem)
    shortcut.type = ShortcutType.BATCH_LAUNCH
    shortcut.run_as_admin = False
    success, error = ShortcutExecutor.execute(shortcut)
    assert success is True
    assert error == ""


def test_execute_macro_uses_saved_speed(monkeypatch):
    import core.background_tasks as background_tasks
    import hooks.input_macro as input_macro

    calls = []

    class FakeBackend:
        def play(self, events=None, **kwargs):
            calls.append((list(events or []), kwargs))
            return True

    monkeypatch.setattr(input_macro, "InputMacroBackend", FakeBackend)
    monkeypatch.setattr(background_tasks, "start_background_thread", lambda **kwargs: kwargs["target"]())

    shortcut = ShortcutItem(
        type=ShortcutType.MACRO,
        macro_events=[{"type": 6, "delay_us": 200_000, "vk_code": 65}],
        macro_speed=2.0,
    )

    success, error = ShortcutExecutor._execute_macro(shortcut)

    assert success is True
    assert error == ""
    assert calls == [([{"type": 6, "delay_us": 200_000, "vk_code": 65}], {"speed": 2.0})]


def test_execute_macro_after_close_waits_for_restored_window(monkeypatch):
    import core.background_tasks as background_tasks
    import hooks.input_macro as input_macro

    calls = []

    class FakeBackend:
        def play(self, events=None, **kwargs):
            calls.append(("play", list(events or []), kwargs))
            return True

    monkeypatch.setattr(input_macro, "InputMacroBackend", FakeBackend)
    monkeypatch.setattr(background_tasks, "start_background_thread", lambda **kwargs: kwargs["target"]())
    monkeypatch.setattr(
        ShortcutExecutor, "restore_foreground_window_fast", lambda **_kwargs: calls.append(("restore",)) or True
    )
    monkeypatch.setattr(se.time, "sleep", lambda seconds: calls.append(("sleep", seconds)))
    monkeypatch.setattr(se.user32, "GetForegroundWindow", lambda: 456)

    ShortcutExecutor._previous_hwnd = 456
    shortcut = ShortcutItem(
        type=ShortcutType.MACRO,
        trigger_mode="after_close",
        macro_events=[{"type": 6, "delay_us": 200_000, "vk_code": 65}],
    )

    success, error = ShortcutExecutor._execute_macro(shortcut)

    assert success is True
    assert error == ""
    assert calls[:3] == [("sleep", 0.150), ("restore",), ("sleep", 0.250)]
    assert calls[-1] == ("play", [{"type": 6, "delay_us": 200_000, "vk_code": 65}], {"speed": 1.0})


def test_execute_with_files_empty():
    shortcut = MagicMock(spec=ShortcutItem)
    result = ShortcutExecutor.execute_with_files(shortcut, [])
    assert result is False


def test_execute_with_files_wrong_type():
    shortcut = MagicMock(spec=ShortcutItem)
    shortcut.type = ShortcutType.HOTKEY
    result = ShortcutExecutor.execute_with_files(shortcut, ["file.txt"])
    assert result is False


def test_execute_with_files_empty_target():
    shortcut = MagicMock(spec=ShortcutItem)
    shortcut.type = ShortcutType.FILE
    shortcut.target_path = ""
    result = ShortcutExecutor.execute_with_files(shortcut, ["file.txt"])
    assert result is False


def test_bind_shortcut_executor_mixins(monkeypatch):
    import core.shortcut_command_exec as sce
    import core.shortcut_file_exec as sfe
    import core.shortcut_hotkey as sh
    import core.shortcut_url_exec as sue
    import core.shortcut_window_control as swc

    for mod in (sce, sfe, sh, sue, swc):
        monkeypatch.delattr(mod, "ShortcutExecutor", raising=False)
        assert not hasattr(mod, "ShortcutExecutor")
    _bind_shortcut_executor_mixins()
    for mod in (sce, sfe, sh, sue, swc):
        assert mod.ShortcutExecutor is ShortcutExecutor
