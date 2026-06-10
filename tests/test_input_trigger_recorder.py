from qt_compat import QEvent
from ui.config_window.hotkey_capture_helpers import CAPTURE_MOD_WIN
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


def test_input_trigger_recorder_native_capture_failure_stops_recording(qapp, monkeypatch):
    recorder = InputTriggerRecorderWidget()
    monkeypatch.setattr(recorder, "_start_native_capture", lambda: False)

    recorder._toggle_recording()

    assert recorder.recording is False
    assert recorder._native_capture_active is False


def test_input_trigger_recorder_ignores_direct_qt_keypress_without_native_capture(qapp):
    class FakeKeyEvent:
        def type(self):
            return QEvent.KeyPress

    recorder = InputTriggerRecorderWidget()
    recorder.recording = True

    assert recorder.eventFilter(recorder.display, FakeKeyEvent()) is True
    assert recorder.get_keys() == []
    assert recorder.get_modifiers() == []
