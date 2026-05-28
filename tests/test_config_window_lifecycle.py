from types import SimpleNamespace

import ui.config_window.window_lifecycle as lifecycle_mod
from ui.config_window.settings_commands_page import SettingsCommandsPageMixin
from ui.config_window.settings_panel import SettingsPanel
from ui.config_window.window_lifecycle import WindowLifecycleController


class _Timer:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_window_lifecycle_drops_stale_and_closed_callbacks():
    calls = []
    controller = WindowLifecycleController(SimpleNamespace())

    generation = controller.open_generation()
    assert controller.run_if_current(generation, calls.append, "current") is True

    controller.next_generation()
    assert controller.run_if_current(generation, calls.append, "stale") is False

    current_generation = controller.generation
    controller.close_generation()
    assert controller.run_if_current(current_generation, calls.append, "closed") is False
    assert calls == ["current"]


def test_window_lifecycle_defer_without_generation_only_checks_close(monkeypatch):
    scheduled = []
    monkeypatch.setattr(lifecycle_mod.QTimer, "singleShot", lambda _delay, callback: scheduled.append(callback))
    calls = []
    controller = WindowLifecycleController(SimpleNamespace())

    controller.defer(0, calls.append, "later")
    controller.next_generation()
    scheduled.pop()()
    assert calls == ["later"]

    controller.defer(0, calls.append, "closed")
    controller.close_generation()
    scheduled.pop()()
    assert calls == ["later"]


def test_window_lifecycle_stop_timers_is_best_effort():
    owner = SimpleNamespace(anim=_Timer(), refresh=_Timer(), missing=None)
    controller = WindowLifecycleController(owner, ("anim", "missing"))

    controller.stop_timers("refresh")

    assert owner.anim.stopped is True
    assert owner.refresh.stopped is True


def test_settings_command_page_stops_debounce_timers():
    panel = SimpleNamespace(_builtin_filter_timer=_Timer(), _refresh_timer=_Timer())

    SettingsCommandsPageMixin._stop_command_page_timers(panel)

    assert panel._builtin_filter_timer.stopped is True
    assert panel._refresh_timer.stopped is True


def test_settings_panel_stop_background_timers_stops_slider_and_command_timers():
    calls = []
    panel = SimpleNamespace(
        _slider_debounce_timer=_Timer(),
        _stop_command_page_timers=lambda: calls.append("commands"),
    )

    SettingsPanel.stop_background_timers(panel)

    assert panel._slider_debounce_timer.stopped is True
    assert calls == ["commands"]
