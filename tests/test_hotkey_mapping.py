import pytest

import core.shortcut_hotkey as hotkey_mod
import hooks.hotkey_manager as manager_mod
from core.shortcut_hotkey import HotkeyExecutionMixin
from hooks.keyboard_hook_dll import KeyboardHook

pytestmark = pytest.mark.ui


def test_extended_function_keys_are_supported(monkeypatch):
    monkeypatch.setattr(hotkey_mod, "ShortcutExecutor", HotkeyExecutionMixin)

    assert HotkeyExecutionMixin._vk_from_key("f13") == 0x7C
    assert HotkeyExecutionMixin._vk_from_key("f24") == 0x87


def test_numpad_and_punctuation_keys_are_supported(monkeypatch):
    monkeypatch.setattr(hotkey_mod, "ShortcutExecutor", HotkeyExecutionMixin)

    assert HotkeyExecutionMixin._vk_from_key("num5") == 0x65
    assert HotkeyExecutionMixin._vk_from_key("/") == 0xBF
    assert HotkeyExecutionMixin._vk_from_key("\\") == 0xDC


def test_dll_unsupported_hotkey_returns_false(monkeypatch):
    """DLL设置热键失败时直接返回False，不再fallback到其它后端"""
    from qt_compat import QApplication

    QApplication.instance() or QApplication([])

    calls = []

    class FakeDll:
        def set_hotkey(self, hotkey, callback):
            calls.append(("dll", hotkey))
            return False

        def clear_hotkey(self):
            calls.append(("clear", None))

    manager = manager_mod.HotkeyManager()
    manager._dll = FakeDll()

    try:
        # DLL失败时应返回False，不再fallback
        assert not manager.set_hotkey("Win+Space")

        assert not manager._is_running
        assert ("dll", "<cmd>+<space>") in calls
        assert ("clear", None) in calls
    finally:
        manager.stop()


def test_hotkey_manager_normalizes_side_modifiers_and_fkeys():
    from qt_compat import QApplication

    QApplication.instance() or QApplication([])

    manager = manager_mod.HotkeyManager()

    assert manager._normalize_hotkey("LCtrl + RAlt + F1") == "<ctrl_l>+<alt_r>+<f1>"
    assert manager._normalize_hotkey("Win + Space") == "<cmd>+<space>"
    assert manager._normalize_hotkey("Ctrl + Shift + P") == "<ctrl>+<shift>+p"


def test_side_specific_hotkey_rejected():
    """带有左右区分修饰键的热键应直接被拒绝"""
    from qt_compat import QApplication

    QApplication.instance() or QApplication([])

    manager = manager_mod.HotkeyManager()
    # 不需要FakeDll，因为侧边修饰键应在DLL调用之前就被拒绝
    assert not manager.set_hotkey("LCtrl+P")
    assert not manager._is_running


def test_hotkey_manager_stop_resets_state(monkeypatch):
    from qt_compat import QApplication

    QApplication.instance() or QApplication([])

    class FakeDll:
        def clear_hotkey(self):
            pass

    manager = manager_mod.HotkeyManager()
    manager._dll = FakeDll()
    manager._is_running = True

    manager.stop()

    assert not manager._is_running


def test_hotkey_manager_reports_failure_without_dll(monkeypatch):
    """没有DLL实例时也应该优雅地失败"""
    from qt_compat import QApplication

    QApplication.instance() or QApplication([])

    manager = manager_mod.HotkeyManager()
    # _dll 为 None，模拟 DLL 不可用
    manager._dll = None

    # 由于没有 DLL，热键设置应失败
    # 但不应该崩溃（会尝试通过 HooksDLL.get_instance() 获取）
    # 如果 hooks.dll 文件也不存在，set_hotkey 应返回 False
    # 我们用 monkeypatch 模拟 HooksDLL.get_instance 返回一个假的
    class FakeDll:
        def set_hotkey(self, hotkey, callback):
            return False

        def clear_hotkey(self):
            pass

    from hooks.hooks_wrapper import HooksDLL

    monkeypatch.setattr(HooksDLL, "get_instance", classmethod(lambda cls, path=None: FakeDll()))

    assert not manager.set_hotkey("Ctrl+P")
    assert not manager._is_running


def test_keyboard_hook_clear_hotkey_calls_dll_clear():
    calls = []
    hook = object.__new__(KeyboardHook)
    hook._on_alt_double_tap = None
    hook._on_hotkey = object()

    class FakeDll:
        def clear_hotkey(self):
            calls.append("clear")

    hook._dll = FakeDll()

    assert not hook.set_hotkey("", None)
    assert hook._on_hotkey is None
    assert calls == ["clear"]


def test_keyboard_hook_set_hotkey_returns_dll_result():
    hook = object.__new__(KeyboardHook)
    hook._on_alt_double_tap = None

    class FakeDll:
        def set_hotkey(self, hotkey, callback):
            return hotkey == "Ctrl+P" and callback is not None

    hook._dll = FakeDll()

    assert hook.set_hotkey("Ctrl+P", lambda: None)
