"""Tests for core/shortcut_executor.py"""

from unittest.mock import MagicMock

import core.shortcut_executor as se
from core.data_models import ShortcutItem, ShortcutType
from core.shortcut_executor import (
    STANDARD_USER_LAUNCH_FAILED_MESSAGE,
    Key,
    ShortcutExecutor,
    _bind_shortcut_executor_mixins,
    _import_pynput,
)


def test_module_constant():
    assert STANDARD_USER_LAUNCH_FAILED_MESSAGE
    assert isinstance(STANDARD_USER_LAUNCH_FAILED_MESSAGE, str)


def test_import_pynput_success(monkeypatch):
    monkeypatch.setattr(se, "HAS_PYNPUT", False)
    monkeypatch.setattr(se, "_pynput_Key", None)
    _import_pynput()
    assert se.HAS_PYNPUT is True
    assert se._pynput_Key is not None


def test_import_pynput_idempotent(monkeypatch):
    sentinel = MagicMock()
    monkeypatch.setattr(se, "_pynput_Key", sentinel)
    monkeypatch.setattr(se, "HAS_PYNPUT", False)
    _import_pynput()
    assert se._pynput_Key is sentinel


def test_import_pynput_failure_graceful(monkeypatch):
    monkeypatch.setattr(se, "HAS_PYNPUT", False)
    monkeypatch.setattr(se, "_pynput_Key", None)
    import sys

    monkeypatch.setitem(sys.modules, "pynput.keyboard", None)
    monkeypatch.setitem(sys.modules, "pynput", None)
    _import_pynput()
    assert se.HAS_PYNPUT is False
    assert se._pynput_Key is None


def test_key_function(monkeypatch):
    monkeypatch.setattr(se, "HAS_PYNPUT", False)
    monkeypatch.setattr(se, "_pynput_Key", None)
    result = Key()
    assert se.HAS_PYNPUT is True
    assert result is se._pynput_Key


def test_shortcut_executor_class_attrs():
    assert ShortcutExecutor._previous_hwnd is None
    assert hasattr(ShortcutExecutor, "_hotkey_lock")
    assert ShortcutExecutor._hotkey_lock_timeout == 2.0
    assert ShortcutExecutor._last_cleanup_time == 0
    assert ShortcutExecutor.PYNPUT_SPECIAL_KEYS == {}
    assert ShortcutExecutor._PYNPUT_KEYS_LOADED is False


def test_ensure_pynput_keys(monkeypatch):
    monkeypatch.setattr(ShortcutExecutor, "_PYNPUT_KEYS_LOADED", False)
    monkeypatch.setattr(ShortcutExecutor, "PYNPUT_SPECIAL_KEYS", {})
    ShortcutExecutor._ensure_pynput_keys()
    assert ShortcutExecutor._PYNPUT_KEYS_LOADED is True
    assert "ctrl" in ShortcutExecutor.PYNPUT_SPECIAL_KEYS
    assert ShortcutExecutor.PYNPUT_SPECIAL_KEYS["ctrl"] is not None


def test_ensure_pynput_keys_idempotent(monkeypatch):
    monkeypatch.setattr(ShortcutExecutor, "_PYNPUT_KEYS_LOADED", True)
    monkeypatch.setattr(ShortcutExecutor, "PYNPUT_SPECIAL_KEYS", {"ctrl": "fake"})
    ShortcutExecutor._ensure_pynput_keys()
    assert ShortcutExecutor.PYNPUT_SPECIAL_KEYS == {"ctrl": "fake"}


def test_ensure_pynput_keys_graceful_when_pynput_none(monkeypatch):
    monkeypatch.setattr(ShortcutExecutor, "_PYNPUT_KEYS_LOADED", False)
    monkeypatch.setattr(ShortcutExecutor, "PYNPUT_SPECIAL_KEYS", {})
    monkeypatch.setattr(se, "Key", lambda: None)
    ShortcutExecutor._ensure_pynput_keys()
    assert ShortcutExecutor._PYNPUT_KEYS_LOADED is True
    assert ShortcutExecutor.PYNPUT_SPECIAL_KEYS == {}


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


def test_execute_chain_type(monkeypatch):
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.error = None
    import core.shortcut_chain_exec

    monkeypatch.setattr(core.shortcut_chain_exec, "execute_shortcut_chain", lambda s: mock_result)
    shortcut = MagicMock(spec=ShortcutItem)
    shortcut.type = ShortcutType.CHAIN
    shortcut.run_as_admin = False
    success, error = ShortcutExecutor.execute(shortcut)
    assert success is True
    assert error == ""


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
