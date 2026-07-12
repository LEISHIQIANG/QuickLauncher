from hooks.input_macro import InputMacroBackend


class FakeDLL:
    def __init__(self):
        self.capture_callback = None
        self.capture_kwargs = None
        self.played = None
        self.cancelled = False

    def start_input_capture(self, callback, **kwargs):
        self.capture_callback = callback
        self.capture_kwargs = kwargs
        return True

    def stop_input_capture(self, **kwargs):
        self.stop_kwargs = kwargs
        return None

    def is_input_capture_active(self):
        return self.capture_callback is not None

    def captured_events_to_macro(self, events, speed=1.0, preserve_initial_delay=False):
        return [{"type": event["type"], "delay_us": round(event["timestamp_us"] / speed)} for event in events]

    def play_macro(self, events, no_timing=False):
        self.played = (events, no_timing)
        return True

    def cancel_macro_playback(self):
        self.cancelled = True

    def wait_for_macro_playback(self, timeout_ms):
        return timeout_ms == 123

    def get_macro_status(self):
        return {"active": 0}

    def is_macro_playback_active(self):
        return False


def test_input_macro_backend_records_builds_and_plays():
    dll = FakeDLL()
    backend = InputMacroBackend(dll)

    assert backend.start_recording(mouse_move=False, mouse_wheel=False)
    dll.capture_callback({"type": 6, "timestamp_us": 100})
    dll.capture_callback({"type": 7, "timestamp_us": 300})

    assert backend.stop_recording() == [
        {"type": 6, "timestamp_us": 100},
        {"type": 7, "timestamp_us": 300},
    ]
    assert backend.play(speed=2.0)
    assert dll.played == (
        [{"type": 6, "delay_us": 50}, {"type": 7, "delay_us": 150}],
        False,
    )
    assert dll.capture_kwargs["filter_flags"] != 0
    assert dll.capture_kwargs["owner"] is backend
    assert dll.stop_kwargs["owner"] is backend


def test_input_macro_backend_scales_existing_playback_events():
    dll = FakeDLL()
    backend = InputMacroBackend(dll)

    assert backend.play(events=[{"type": 6, "delay_us": 200_000}], speed=2.0)

    assert dll.played == ([{"type": 6, "delay_us": 100_000}], False)


def test_input_macro_backend_cancel_wait_and_status():
    dll = FakeDLL()
    backend = InputMacroBackend(dll)

    backend.cancel()

    assert dll.cancelled is True
    assert backend.wait(123) is True
    assert backend.status() == {"active": 0}
    assert backend.is_playing is False


def test_input_macro_backend_bounds_recording_memory():
    dll = FakeDLL()
    backend = InputMacroBackend(dll, max_events=2)

    assert backend.start_recording()
    dll.capture_callback({"type": 6, "timestamp_us": 100})
    dll.capture_callback({"type": 7, "timestamp_us": 200})
    dll.capture_callback({"type": 6, "timestamp_us": 300})

    assert backend.recorded_events() == [
        {"type": 7, "timestamp_us": 200},
        {"type": 6, "timestamp_us": 300},
    ]
    assert backend.dropped_events == 1
