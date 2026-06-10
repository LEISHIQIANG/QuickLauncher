from qt_compat import QEvent
from ui.config_window.hotkey_capture_helpers import (
    CAPTURE_MOD_ALT,
    CAPTURE_MOD_CTRL,
    CAPTURE_MOD_SHIFT,
    CAPTURE_MOD_WIN,
    SIDE_MODIFIER_BITS,
    key_name_from_vk,
)
from ui.config_window.hotkey_dialog import HotkeyRecorderWidget


def test_hotkey_recorder_native_capture_records_win_d(qapp):
    recorder = HotkeyRecorderWidget()

    recorder._handle_native_capture_result(0x44, CAPTURE_MOD_WIN, SIDE_MODIFIER_BITS["lwin"])

    assert recorder.get_modifiers() == ["win"]
    assert recorder.get_key() == "d"
    assert recorder.get_hotkey_string() == "Win + D"


def test_hotkey_recorder_native_capture_respects_left_right_modifiers(qapp):
    recorder = HotkeyRecorderWidget()
    recorder.set_advanced_sides(True)
    side_modifiers = (
        SIDE_MODIFIER_BITS["lctrl"]
        | SIDE_MODIFIER_BITS["ralt"]
        | SIDE_MODIFIER_BITS["lshift"]
        | SIDE_MODIFIER_BITS["rwin"]
    )

    recorder._handle_native_capture_result(
        0x7B,
        CAPTURE_MOD_CTRL | CAPTURE_MOD_ALT | CAPTURE_MOD_SHIFT | CAPTURE_MOD_WIN,
        side_modifiers,
    )

    assert recorder.get_modifiers() == ["lctrl", "ralt", "lshift", "rwin"]
    assert recorder.get_key() == "f12"
    assert recorder.get_hotkey_string() == "LCtrl + RAlt + LShift + RWin + F12"


def test_hotkey_recorder_native_capture_maps_symbol_and_numpad_keys(qapp):
    assert key_name_from_vk(0xBA) == ";"
    assert key_name_from_vk(0x61) == "num1"
    assert key_name_from_vk(0xAF) == "volumeup"


def test_hotkey_recorder_does_not_fallback_to_qt_recording_when_native_capture_fails(qapp, monkeypatch):
    recorder = HotkeyRecorderWidget()
    monkeypatch.setattr(recorder, "_start_native_capture", lambda: False)

    recorder.start_recording()

    assert recorder._recording is False
    assert recorder._native_capture_active is False


def test_hotkey_recorder_ignores_direct_qt_keypress_without_native_capture(qapp):
    class FakeKeyEvent:
        def type(self):
            return QEvent.KeyPress

    recorder = HotkeyRecorderWidget()

    assert recorder.eventFilter(recorder.display, FakeKeyEvent()) is True
    assert recorder.get_key() == ""
    assert recorder.get_modifiers() == []
