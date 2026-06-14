from hooks import hooks_wrapper
from qt_compat import QEvent
from ui.config_window.hotkey_capture_helpers import CAPTURE_MOD_ALT, CAPTURE_MOD_CTRL, CAPTURE_MOD_WIN
from ui.config_window.input_trigger_recorder import InputTriggerRecorderWidget


class _FakeMouseHook:
    def __init__(self, paused):
        self.paused = paused
        self.calls = []

    def is_paused(self):
        return self.paused

    def set_paused(self, paused):
        self.paused = paused
        self.calls.append(paused)


class _UnreadableMouseHook:
    def __init__(self):
        self.calls = []

    def is_paused(self):
        raise RuntimeError("state unavailable")

    def set_paused(self, paused):
        self.calls.append(paused)


def test_input_trigger_recorder_restores_previous_mouse_hook_pause_state(qapp):
    recorder = InputTriggerRecorderWidget()
    hook = _FakeMouseHook(paused=True)
    recorder.set_mouse_hook(hook)

    recorder._toggle_recording()
    recorder._end_recording()

    assert hook.calls == [True, True]
    assert hook.paused is True


def test_input_trigger_recorder_restores_unpaused_mouse_hook_state(qapp):
    recorder = InputTriggerRecorderWidget()
    hook = _FakeMouseHook(paused=False)
    recorder.set_mouse_hook(hook)

    recorder._toggle_recording()
    recorder._end_recording()

    assert hook.calls == [True, False]
    assert hook.paused is False


def test_input_trigger_recorder_does_not_restore_unknown_pause_state(qapp):
    recorder = InputTriggerRecorderWidget()
    hook = _UnreadableMouseHook()
    recorder.set_mouse_hook(hook)

    recorder._toggle_recording()
    recorder._end_recording()

    assert hook.calls == [True]


def test_input_trigger_recorder_native_capture_records_keyboard_trigger(qapp):
    recorder = InputTriggerRecorderWidget()

    recorder._handle_native_capture_result(0x44, CAPTURE_MOD_WIN, 0)

    assert recorder.get_mode() == "keyboard"
    assert recorder.get_keys() == ["d"]
    assert recorder.get_modifiers() == ["win"]
    assert recorder.display.text() == "Win + D"


def test_input_trigger_recorder_keeps_alt_q_recording_until_manual_confirmation(qapp):
    recorder = InputTriggerRecorderWidget()
    recorder.recording = True

    recorder._handle_native_capture_result(0x51, CAPTURE_MOD_ALT, 0)
    assert recorder.recording is True
    recorder._handle_native_capture_result(0, CAPTURE_MOD_ALT, 0)

    assert recorder.recording is False
    assert recorder.get_mode() == "keyboard"
    assert recorder.get_keys() == ["q"]
    assert recorder.get_modifiers() == ["alt"]
    assert recorder.display.text() == "Alt + Q"


def test_input_trigger_recorder_record_button_stops_active_capture(qapp, monkeypatch):
    recorder = InputTriggerRecorderWidget()
    calls = []
    recorder.recording = True
    monkeypatch.setattr(recorder, "_end_recording", lambda: calls.append("stop"))

    recorder._toggle_recording()

    assert calls == ["stop"]


def test_input_trigger_recorder_native_capture_records_keyboard_mouse_hybrid(qapp):
    recorder = InputTriggerRecorderWidget()

    recorder._handle_native_capture_result(0x41, CAPTURE_MOD_CTRL, 0)
    recorder._handle_native_capture_result(-8, CAPTURE_MOD_CTRL, 0)
    recorder._handle_native_capture_result(0, CAPTURE_MOD_CTRL, 0)

    assert recorder.get_mode() == "hybrid"
    assert recorder.get_keys() == ["a"]
    assert recorder.get_button() == "x1"
    assert recorder.get_modifiers() == ["ctrl"]
    assert recorder.display.text() == "Ctrl + A + 侧键后"


def test_input_trigger_recorder_native_capture_records_plain_keyboard_key(qapp):
    recorder = InputTriggerRecorderWidget()
    recorder.recording = True

    recorder._handle_native_capture_result(0x51, 0, 0)
    recorder._handle_native_capture_result(0, 0, 0)

    assert recorder.recording is False
    assert recorder.get_mode() == "keyboard"
    assert recorder.get_keys() == ["q"]
    assert recorder.get_modifiers() == []
    assert recorder.display.text() == "Q"


def test_input_trigger_recorder_native_capture_records_plain_and_modified_mouse(qapp):
    plain = InputTriggerRecorderWidget()
    plain.recording = True
    plain._handle_native_capture_result(-4, 0, 0)
    plain._handle_native_capture_result(0, 0, 0)

    modified = InputTriggerRecorderWidget()
    modified.recording = True
    modified._handle_native_capture_result(-8, CAPTURE_MOD_ALT, 0)
    modified._handle_native_capture_result(0, CAPTURE_MOD_ALT, 0)

    assert plain.get_mode() == "mouse"
    assert plain.get_button() == "middle"
    assert plain.get_modifiers() == []
    assert plain.display.text() == "中键"
    assert modified.get_mode() == "mouse"
    assert modified.get_button() == "x1"
    assert modified.get_modifiers() == ["alt"]
    assert modified.display.text() == "Alt + 侧键后"


def test_input_trigger_recorder_native_capture_failure_stops_recording(qapp, monkeypatch):
    recorder = InputTriggerRecorderWidget()
    monkeypatch.setattr(recorder, "_start_native_capture", lambda: False)

    recorder._toggle_recording()

    assert recorder.recording is False
    assert recorder._native_capture_active is False
    assert recorder._keyboard_state_poller.is_active() is False


def test_input_trigger_recorder_ignores_callback_from_previous_capture_session(qapp):
    recorder = InputTriggerRecorderWidget()
    recorder.recording = True
    recorder._capture_session = 2

    recorder._handle_native_capture_result(
        0x51,
        CAPTURE_MOD_CTRL,
        0,
        capture_session=1,
    )

    assert recorder.get_keys() == []
    assert recorder.get_modifiers() == []


def test_input_trigger_recorder_ignores_direct_qt_keypress_without_native_capture(qapp):
    class FakeKeyEvent:
        def type(self):
            return QEvent.KeyPress

    recorder = InputTriggerRecorderWidget()
    recorder.recording = True

    assert recorder.eventFilter(recorder.display, FakeKeyEvent()) is True
    assert recorder.get_keys() == []
    assert recorder.get_modifiers() == []


def test_input_trigger_recorder_rearms_keyboard_hook_before_capture(qapp, monkeypatch):
    calls = []

    class FakeDLL:
        loaded = True
        compatible = True
        _has_protected_chord_capture = True

        def rearm_keyboard_hook_for_capture(self):
            calls.append("rearm_keyboard")
            return True, False

        def is_mouse_hook_installed(self):
            return True

        def start_protected_chord_capture(self, callback, **kwargs):
            calls.append(("start_capture", kwargs))
            return True

    monkeypatch.setattr(hooks_wrapper.HooksDLL, "get_instance", lambda: FakeDLL())
    recorder = InputTriggerRecorderWidget()

    assert recorder._start_native_capture() is True
    assert calls[-1][1]["include_injected"] is True
    recorder._finish_native_capture(stop_native=False)

    assert calls[0] == "rearm_keyboard"
    assert calls[1][0] == "start_capture"
    assert calls[1][1]["keyboard"] is True
    assert calls[1][1]["mouse_buttons"] is True
