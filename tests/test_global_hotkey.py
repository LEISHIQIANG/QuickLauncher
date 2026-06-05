from PyQt5.QtCore import QAbstractNativeEventFilter

from ui.utils.global_hotkey import _HotkeyEventFilter


def test_hotkey_event_filter_is_qt_native_filter():
    event_filter = _HotkeyEventFilter({})

    assert isinstance(event_filter, QAbstractNativeEventFilter)
