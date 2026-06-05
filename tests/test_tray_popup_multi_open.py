from types import SimpleNamespace

import pytest

from ui.tray_app import TrayApp

pytestmark = pytest.mark.ui


class FakePopup:
    def __init__(self, pinned=True, visible=True):
        self.is_pinned = pinned
        self._visible = visible
        self.closed = False

    def isVisible(self):
        return self._visible

    def width(self):
        if self.closed:
            raise RuntimeError("deleted")
        return 100

    def close(self):
        self.closed = True
        self._visible = False

    def hide(self):
        self._visible = False


class FakeTimer:
    def __init__(self):
        self.stopped = False
        self.started = False
        self.start_count = 0

    def isActive(self):
        return True

    def stop(self):
        self.stopped = True

    def start(self, *_args):
        self.started = True
        self.start_count += 1


class FakeRuntimeComponent:
    def __init__(self):
        self.stopped = False
        self.hidden = False
        self.uninstalled = False

    def stop(self):
        self.stopped = True

    def hide(self):
        self.hidden = True

    def uninstall(self):
        self.uninstalled = True


def _tray_like(multi_open=True):
    tray = TrayApp.__new__(TrayApp)
    tray._extra_popup_windows = []
    tray._max_extra_popup_windows = 2
    tray.data_manager = SimpleNamespace(get_settings=lambda: SimpleNamespace(popup_multi_open_when_pinned=multi_open))
    tray.popup_window = None
    tray.config_window = None
    tray.log_window = None
    return tray


def test_should_multi_open_only_for_visible_pinned_popup():
    tray = _tray_like(multi_open=True)

    assert tray._should_multi_open_pinned_popup(FakePopup(pinned=True, visible=True)) is True
    assert tray._should_multi_open_pinned_popup(FakePopup(pinned=False, visible=True)) is False
    assert tray._should_multi_open_pinned_popup(FakePopup(pinned=True, visible=False)) is False

    tray_disabled = _tray_like(multi_open=False)
    assert tray_disabled._should_multi_open_pinned_popup(FakePopup(pinned=True, visible=True)) is False


def test_extra_popup_pool_keeps_at_most_two_old_windows():
    tray = _tray_like(multi_open=True)
    first = FakePopup()
    second = FakePopup()
    third = FakePopup()

    tray._keep_as_extra_popup(first)
    tray._keep_as_extra_popup(second)
    tray._keep_as_extra_popup(third)

    assert first.closed is True
    assert second.closed is False
    assert third.closed is False
    assert tray._extra_popup_windows == [second, third]


def test_extra_popup_pool_ignores_duplicates():
    tray = _tray_like(multi_open=True)
    popup = FakePopup()

    tray._keep_as_extra_popup(popup)
    tray._keep_as_extra_popup(popup)

    assert tray._extra_popup_windows == [popup]


def test_prune_extra_popup_windows_handles_closed_popups():
    tray = _tray_like(multi_open=True)
    first = FakePopup()
    second = FakePopup()
    first.close()
    tray._extra_popup_windows = [first, second]

    tray._prune_extra_popup_windows()

    assert tray._extra_popup_windows == [second]


def test_shutdown_runtime_components_stops_timers_hooks_and_windows(monkeypatch):
    tray = _tray_like(multi_open=True)
    tray._settings_sync_timer = FakeTimer()
    tray._sleep_timer = FakeTimer()
    tray._deferred_startup_timer = FakeTimer()
    tray._memory_check_timer = FakeTimer()
    tray._process_check_timer = FakeTimer()
    tray._update_checker = FakeRuntimeComponent()
    tray.hotkey_manager = FakeRuntimeComponent()
    tray.mouse_hook = FakeRuntimeComponent()
    tray.keyboard_hook = FakeRuntimeComponent()
    tray.tray_icon = FakeRuntimeComponent()
    tray.config_window = FakePopup()
    tray.diagnostics_window = FakePopup()
    tray.log_window = None
    tray.shortcut_health_window = None
    tray.config_history_window = None
    tray.slash_help_window = None
    tray._toast = None

    monkeypatch.setattr("core.folder_watcher.shutdown_watcher_manager", lambda: None)

    tray._shutdown_runtime_components()

    assert tray._settings_sync_timer.stopped is True
    assert tray._update_checker.stopped is True
    assert tray.hotkey_manager.stopped is True
    assert tray.mouse_hook is None
    assert tray.keyboard_hook is None
    assert tray.tray_icon.hidden is True
    assert tray.config_window is None
    assert tray.diagnostics_window is None


def test_start_defers_runtime_components_until_called(monkeypatch):
    tray = _tray_like(multi_open=True)
    tray._started = False
    tray._safe_mode = False
    tray._deferred_startup_timer = FakeTimer()
    tray._memory_check_timer = FakeTimer()
    tray._process_check_timer = FakeTimer()
    tray._hook_health_timer = FakeTimer()
    tray._sleep_timer = FakeTimer()
    tray._special_app_monitors_active = False
    tray._known_processes = {"old.exe"}
    tray.data_manager = SimpleNamespace(
        get_settings=lambda: SimpleNamespace(
            auto_update_enabled=True,
            sleep_mode_enabled=False,
            special_apps=[],
        )
    )
    scheduled = []
    activity = []
    monkeypatch.setattr("ui.tray_app.QTimer.singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    tray._install_hook = lambda: None
    tray._install_keyboard_hook_and_hotkey = lambda: None
    tray._init_update_system = lambda: None
    tray._mark_activity = lambda source="": activity.append(source)

    tray.start()
    tray.start()

    assert tray._deferred_startup_timer.start_count == 1
    assert tray._memory_check_timer.start_count == 1
    assert tray._hook_health_timer.start_count == 1
    assert [delay for delay, _callback in scheduled] == [0, 0, 5000]
    assert activity == ["startup"]
