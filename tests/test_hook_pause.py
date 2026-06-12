from hooks.hook_pause import mouse_hook_paused


class FakeHook:
    def __init__(self, paused=False):
        self.paused = paused
        self.calls = []

    def is_paused(self):
        return self.paused

    def set_paused(self, paused):
        self.paused = bool(paused)
        self.calls.append(self.paused)


def test_mouse_hook_pause_restores_previous_true_state():
    hook = FakeHook(paused=True)

    with mouse_hook_paused(hook, restore_previous=True):
        assert hook.paused is True

    assert hook.calls == [True, True]
    assert hook.paused is True


def test_mouse_hook_pause_restores_previous_false_state():
    hook = FakeHook(paused=False)

    with mouse_hook_paused(hook, restore_previous=True):
        assert hook.paused is True

    assert hook.calls == [True, False]
    assert hook.paused is False


def test_mouse_hook_pause_does_not_guess_state_when_read_fails():
    class ReadFailureHook(FakeHook):
        def is_paused(self):
            raise RuntimeError("unavailable")

    hook = ReadFailureHook()

    with mouse_hook_paused(hook, restore_previous=True):
        assert hook.paused is True

    assert hook.calls == [True]
