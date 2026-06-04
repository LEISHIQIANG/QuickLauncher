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
