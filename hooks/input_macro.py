"""High-level keyboard/mouse macro recording and playback backend."""

import threading
from collections import deque
from collections.abc import Callable

from .hooks_wrapper import (
    CAPTURE_ALL_PHYSICAL,
    CAPTURE_KEYBOARD,
    CAPTURE_MOUSE_BUTTON,
    CAPTURE_MOUSE_MOVE,
    CAPTURE_MOUSE_WHEEL,
    HooksDLL,
)


class InputMacroBackend:
    """Thread-safe macro primitive built on the shared native hooks DLL.

    Mouse and keyboard hooks must already be installed by the application.
    This class intentionally owns no UI, persistence, trigger, or loop logic.
    """

    def __init__(self, dll: HooksDLL | None = None, *, max_events: int = 100_000):
        if max_events <= 0:
            raise ValueError("max_events must be greater than zero")
        self._dll = dll or HooksDLL.get_instance()
        self._events: deque[dict] = deque(maxlen=int(max_events))
        self._events_lock = threading.Lock()
        self._recording = False
        self._event_callback: Callable[[dict], None] | None = None
        self._dropped_events = 0

    def start_recording(
        self,
        *,
        mouse_move: bool = True,
        mouse_buttons: bool = True,
        mouse_wheel: bool = True,
        keyboard: bool = True,
        include_injected: bool = False,
        include_own_playback: bool = False,
        coalesce_mouse_moves: bool = False,
        event_filter: Callable[[dict], bool] | None = None,
        on_event: Callable[[dict], None] | None = None,
    ) -> bool:
        filters = 0
        if mouse_move:
            filters |= CAPTURE_MOUSE_MOVE
        if mouse_buttons:
            filters |= CAPTURE_MOUSE_BUTTON
        if mouse_wheel:
            filters |= CAPTURE_MOUSE_WHEEL
        if keyboard:
            filters |= CAPTURE_KEYBOARD
        if filters == 0:
            filters = CAPTURE_ALL_PHYSICAL

        with self._events_lock:
            self._events.clear()
            self._dropped_events = 0
        self._event_callback = on_event

        def _record(event: dict) -> None:
            snapshot = dict(event)
            if event_filter is not None and not event_filter(snapshot):
                return
            with self._events_lock:
                if len(self._events) == self._events.maxlen:
                    self._dropped_events += 1
                self._events.append(snapshot)
            callback = self._event_callback
            if callback:
                callback(snapshot)

        self._recording = self._dll.start_input_capture(
            _record,
            filter_flags=filters,
            include_injected=include_injected,
            include_own_playback=include_own_playback,
            coalesce_mouse_moves=coalesce_mouse_moves,
            owner=self,
        )
        return self._recording

    def stop_recording(self) -> list[dict]:
        self._dll.stop_input_capture(owner=self)
        self._recording = False
        self._event_callback = None
        return self.recorded_events()

    def inject_events(self, events: list[dict]) -> None:
        """Replace the in-memory event buffer with the provided list.

        Used by editors that need ``recorded_events()`` to reflect the events
        loaded from disk (e.g. opening a macro for editing without starting a
        new recording). The buffer is reset before the new entries are appended
        so that callers can rely on ``len(recorded_events()) == len(events)``
        for valid inputs. Excess entries that exceed ``max_events`` are
        silently dropped, matching the behaviour of the native capture path
        (``collections.deque(maxlen=...)`` discards from the oldest end).
        """
        normalized: list[dict] = [dict(event) for event in events if isinstance(event, dict)]
        with self._events_lock:
            self._events.clear()
            self._dropped_events = 0
            for event in normalized:
                if len(self._events) == self._events.maxlen:
                    self._dropped_events += 1
                self._events.append(event)

    def recorded_events(self) -> list[dict]:
        with self._events_lock:
            return [dict(event) for event in self._events]

    @property
    def dropped_events(self) -> int:
        with self._events_lock:
            return self._dropped_events

    def build_sequence(
        self,
        *,
        speed: float = 1.0,
        preserve_initial_delay: bool = False,
    ) -> list[dict]:
        return self._dll.captured_events_to_macro(
            self.recorded_events(),
            speed=speed,
            preserve_initial_delay=preserve_initial_delay,
        )

    def play(
        self,
        events: list[dict] | None = None,
        *,
        speed: float = 1.0,
        no_timing: bool = False,
    ) -> bool:
        if speed <= 0:
            raise ValueError("speed must be greater than zero")
        if events is None:
            sequence = self.build_sequence(speed=speed)
        else:
            sequence = [dict(event) for event in events]
            if speed != 1.0:
                for event in sequence:
                    event["delay_us"] = max(0, min(0xFFFFFFFF, round(int(event.get("delay_us", 0)) / speed)))
        return self._dll.play_macro(sequence, no_timing=no_timing)  # type: ignore[arg-type]

    def cancel(self) -> None:
        self._dll.cancel_macro_playback()

    def wait(self, timeout_ms: int = 0xFFFFFFFF) -> bool:
        return self._dll.wait_for_macro_playback(timeout_ms)

    def status(self) -> dict:
        return self._dll.get_macro_status()

    @property
    def is_recording(self) -> bool:
        return self._recording and self._dll.is_input_capture_active()

    @property
    def is_playing(self) -> bool:
        return self._dll.is_macro_playback_active()
