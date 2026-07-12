from hooks import hooks_wrapper
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


def test_hotkey_recorder_auto_completes_alt_q_after_release(qapp):
    recorder = HotkeyRecorderWidget()
    recorder._recording = True

    recorder._handle_native_capture_result(0x51, CAPTURE_MOD_ALT, SIDE_MODIFIER_BITS["lalt"])
    assert recorder._recording is True
    recorder._handle_native_capture_result(0, CAPTURE_MOD_ALT, SIDE_MODIFIER_BITS["lalt"])

    assert recorder._recording is False
    assert recorder.get_modifiers() == ["alt"]
    assert recorder.get_keys() == ["q"]
    assert recorder.get_hotkey_string() == "Alt + Q"


def test_hotkey_recorder_record_button_stops_active_capture(qapp, monkeypatch):
    recorder = HotkeyRecorderWidget()
    calls = []
    recorder._recording = True
    monkeypatch.setattr(recorder, "stop_recording", lambda: calls.append("stop"))

    recorder._toggle_recording()

    assert calls == ["stop"]


def test_hotkey_recorder_auto_completes_plain_keyboard_key(qapp):
    recorder = HotkeyRecorderWidget()
    recorder._recording = True

    recorder._handle_native_capture_result(0x51, 0, 0)
    recorder._handle_native_capture_result(0, 0, 0)

    assert recorder._recording is False
    assert recorder.get_modifiers() == []
    assert recorder.get_keys() == ["q"]
    assert recorder.get_hotkey_string() == "Q"


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


def test_hotkey_recorder_native_capture_records_multiple_main_keys(qapp):
    recorder = HotkeyRecorderWidget()

    recorder._handle_native_capture_result(0x41, CAPTURE_MOD_CTRL, 0)
    recorder._handle_native_capture_result(0x42, CAPTURE_MOD_CTRL, 0)
    recorder._handle_native_capture_result(0, CAPTURE_MOD_CTRL, 0)

    assert recorder.get_keys() == ["a", "b"]
    assert recorder.get_hotkey_string() == "Ctrl + A + B"


def test_hotkey_recorder_does_not_fallback_to_qt_recording_when_native_capture_fails(qapp, monkeypatch):
    recorder = HotkeyRecorderWidget()
    monkeypatch.setattr(recorder, "_start_native_capture", lambda: False)

    recorder.start_recording()

    assert recorder._recording is False
    assert recorder._native_capture_active is False
    assert recorder._keyboard_state_poller.is_active() is False


def test_hotkey_recorder_ignores_callback_from_previous_capture_session(qapp):
    recorder = HotkeyRecorderWidget()
    recorder._recording = True
    recorder._capture_session = 2

    recorder._handle_native_capture_result(
        0x51,
        CAPTURE_MOD_CTRL,
        SIDE_MODIFIER_BITS["lctrl"],
        capture_session=1,
    )

    assert recorder.get_keys() == []
    assert recorder.get_modifiers() == []


def test_hotkey_recorder_ignores_direct_qt_keypress_without_native_capture(qapp):
    class FakeKeyEvent:
        def type(self):
            return QEvent.KeyPress

    recorder = HotkeyRecorderWidget()

    assert recorder.eventFilter(recorder.display, FakeKeyEvent()) is True
    assert recorder.get_key() == ""
    assert recorder.get_modifiers() == []


def test_hotkey_recorder_rearms_keyboard_hook_before_capture(qapp, monkeypatch):
    calls = []

    class FakeDLL:
        loaded = True
        compatible = True
        _has_protected_chord_capture = True

        def rearm_keyboard_hook_for_capture(self):
            calls.append("rearm_keyboard")
            return True, False

        def start_protected_chord_capture(self, callback, **kwargs):
            calls.append(("start_capture", kwargs))
            return True

    monkeypatch.setattr(hooks_wrapper.HooksDLL, "get_instance", lambda: FakeDLL())
    recorder = HotkeyRecorderWidget()

    assert recorder._start_native_capture() is True
    assert calls[-1][1]["include_injected"] is True
    recorder._finish_native_capture(stop_native=False)

    assert calls[0] == "rearm_keyboard"
    assert calls[1][0] == "start_capture"
    assert calls[1][1]["keyboard"] is True
    assert calls[1][1]["mouse_buttons"] is False
