from PyQt5.QtCore import QAbstractNativeEventFilter

from ui.utils.global_hotkey import Win32GlobalHotkey, _HotkeyEventFilter


def test_hotkey_event_filter_is_qt_native_filter():
    event_filter = _HotkeyEventFilter({})

    assert isinstance(event_filter, QAbstractNativeEventFilter)


def test_register_aborts_when_native_event_filter_is_unavailable(monkeypatch):
    hotkeys = Win32GlobalHotkey()
    monkeypatch.setattr(hotkeys, "_ensure_filter", lambda: False)

    assert hotkeys.register("Ctrl+Shift+L", lambda: None) == 0
    assert hotkeys._hotkeys == {}


def test_parse_hotkey_rejects_multiple_main_keys():
    assert Win32GlobalHotkey._parse_hotkey("Ctrl+A+B") == (0, 0)


def test_unregister_keeps_entry_when_win32_call_fails(monkeypatch):
    hotkeys = Win32GlobalHotkey()
    hotkeys._hotkeys[7] = {"hotkey_str": "Ctrl+Shift+L"}

    class User32:
        @staticmethod
        def UnregisterHotKey(_hwnd, _hotkey_id):
            return 0

    monkeypatch.setattr("ctypes.windll.user32", User32())

    assert hotkeys.unregister(7) is False
    assert 7 in hotkeys._hotkeys
