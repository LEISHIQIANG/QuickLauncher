from types import SimpleNamespace

import ui.config_window.window_lifecycle as lifecycle_mod
from qt_compat import QPoint
from ui.config_window.settings_commands_page import SettingsCommandsPageMixin
from ui.config_window.settings_panel import SettingsPanel
from ui.config_window.window_lifecycle import WindowLifecycleController
from ui.tray_mixins.windows_mixin import WindowsMixin


class _Timer:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class _Signal:
    def __init__(self):
        self.connected = []
        self.emitted = 0

    def connect(self, callback):
        self.connected.append(callback)

    def emit(self):
        self.emitted += 1


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


def test_settings_panel_change_does_not_reload_icon_grid_for_settings_only():
    from ui.config_window.main_window import ConfigWindow

    calls = []
    window = SimpleNamespace(
        data_manager=SimpleNamespace(get_settings=lambda: SimpleNamespace(theme="dark")),
        _theme="dark",
        settings_changed=_Signal(),
        _apply_theme=lambda: calls.append("theme"),
    )

    ConfigWindow._on_settings_panel_changed(window)

    assert calls == []
    assert window.settings_changed.emitted == 1


def test_settings_panel_change_only_rethemes_when_theme_changed():
    from ui.config_window.main_window import ConfigWindow

    calls = []
    window = SimpleNamespace(
        data_manager=SimpleNamespace(get_settings=lambda: SimpleNamespace(theme="light")),
        _theme="dark",
        settings_changed=_Signal(),
        _apply_theme=lambda: calls.append("theme"),
    )

    ConfigWindow._on_settings_panel_changed(window)

    assert calls == ["theme"]
    assert window.settings_changed.emitted == 1


def test_tray_settings_only_sync_uses_popup_settings_signal():
    from ui.tray_app import TrayApp

    settings = SimpleNamespace(
        hide_tray_icon=False,
        hardware_acceleration=True,
        special_apps=[],
        theme="dark",
        bg_mode="image",
        bg_alpha=80,
        bg_blur_radius=20,
        custom_bg_path="C:/wallpaper.png",
        bg_solid_color="#2b2b2b",
        corner_radius=8,
        dock_bg_alpha=90,
        icon_alpha=1.0,
        shadow_size=0,
        shadow_distance=0,
        edge_highlight_color="#ffffff",
        edge_highlight_opacity=0.0,
        double_click_interval=300,
        ui_scale_percent=100,
        cols=4,
        cell_size=72,
        icon_size=48,
    )
    item = SimpleNamespace(
        id="shortcut",
        name="Shortcut",
        type="file",
        order=0,
        enabled=True,
        icon_path="",
        target_path="C:/app.exe",
        target_args="",
        working_dir="",
        url="",
        command="",
        command_type="",
        trigger_mode="",
        alias="",
        tags=[],
    )
    folder = SimpleNamespace(
        id="default",
        name="常用",
        order=0,
        is_dock=False,
        is_icon_repo=False,
        linked_path="",
        items=[item],
    )

    class _Popup:
        def __init__(self):
            self.settings_updated = _Signal()
            self.refresh_calls = []
            self.preload_calls = []

        def width(self):
            return 240

        def refresh_data(self, *args, **kwargs):
            self.refresh_calls.append((args, kwargs))

        def preload_visible_icons(self, **kwargs):
            self.preload_calls.append(kwargs)

    tray = TrayApp.__new__(TrayApp)
    tray.data_manager = SimpleNamespace(get_settings=lambda: settings, data=SimpleNamespace(folders=[folder]))
    tray.popup_window = _Popup()
    tray.tray_icon = SimpleNamespace(show=lambda: None, hide=lambda: None)
    tray._sync_special_apps_to_hook = lambda: None
    tray._apply_hardware_acceleration = lambda _enabled: None
    tray._apply_double_click_interval = lambda _interval: None
    tray._create_menu = lambda: None
    tray._pending_settings_sync = True
    tray._last_synced_settings_snapshot = {**TrayApp._make_settings_snapshot(tray), "bg_mode": "theme"}
    tray._last_synced_popup_model_snapshot = TrayApp._make_popup_model_snapshot(tray)

    TrayApp._apply_pending_settings_changes(tray)

    assert tray.popup_window.settings_updated.emitted == 1
    assert tray.popup_window.refresh_calls == []

    TrayApp._refresh_popup_after_settings_change(tray, model_changed=False, preload_icons=True)

    assert tray.popup_window.settings_updated.emitted == 2
    assert tray.popup_window.preload_calls == [{"force": True, "all_pages": True}]


def test_tray_menu_disables_native_popup_effects(monkeypatch):
    import ui.tray_app as tray_app_mod
    from ui.tray_app import TrayApp

    created = []

    class _Menu:
        def __init__(self, **kwargs):
            created.append(kwargs)

        def add_action(self, *args, **kwargs):
            pass

        def add_separator(self):
            pass

    monkeypatch.setattr(tray_app_mod, "PopupMenu", _Menu)
    tray = TrayApp.__new__(TrayApp)
    tray.data_manager = SimpleNamespace(get_settings=lambda: SimpleNamespace(theme="dark"))
    tray._show_config = lambda: None
    tray._restart = lambda: None
    tray._show_log = lambda: None
    tray._show_diagnostics = lambda: None
    tray._quit = lambda: None

    TrayApp._create_menu(tray)

    assert created[0]["native_effects"] is False


def test_ui_scale_reopen_keeps_new_config_window_centered_on_old_window(monkeypatch):
    import ui.config_window as config_window_pkg
    import ui.utils.font_manager as font_manager
    import ui.utils.ui_scale as ui_scale

    old_center = QPoint(420, 260)
    applied_scale = []

    class FakeSignal:
        def __init__(self):
            self.connected = []

        def connect(self, callback):
            self.connected.append(callback)

    class FakeRect:
        def __init__(self, width=240, height=160, center=None):
            self._width = width
            self._height = height
            self._center = center or QPoint(0, 0)
            self._top_left = QPoint(0, 0)

        def center(self):
            return self._center

        def moveCenter(self, center):
            self._center = center
            self._top_left = QPoint(center.x() - self._width // 2, center.y() - self._height // 2)

        def topLeft(self):
            return self._top_left

    class FakeOldWindow:
        def __init__(self):
            self.closed_with_animation = False

        def frameGeometry(self):
            return FakeRect(center=old_center)

        def animate_close_then(self, callback):
            self.closed_with_animation = True
            callback()

    class FakeConfigWindow:
        last_instance = None

        def __init__(self, data_manager, tray_app=None):
            self.data_manager = data_manager
            self.tray_app = tray_app
            self.settings_changed = FakeSignal()
            self.moved_to = None
            self.shown = False
            self._centered_show_animation = False
            FakeConfigWindow.last_instance = self

        def frameGeometry(self):
            return FakeRect()

        def move(self, pos):
            self.moved_to = pos

        def show(self):
            self.shown = True

        def winId(self):
            raise RuntimeError("no native window in unit test")

        def raise_(self):
            return None

        def activateWindow(self):
            return None

    class FakeDataManager:
        def __init__(self):
            self.reloaded = False

        def reload(self):
            self.reloaded = True

    class Tray(WindowsMixin):
        def __init__(self):
            self.data_manager = FakeDataManager()
            self.config_window = FakeOldWindow()
            self.settings_changed_calls = 0
            self.popup_refresh_calls = []

        def _wake_from_sleep(self, source):
            self.wake_source = source

        def _on_settings_changed(self):
            self.settings_changed_calls += 1

        def _refresh_popup_after_settings_change(self, **kwargs):
            self.popup_refresh_calls.append(kwargs)

    monkeypatch.setattr(config_window_pkg, "ConfigWindow", FakeConfigWindow, raising=False)
    monkeypatch.setattr(ui_scale, "set_scale", lambda percent: applied_scale.append(percent))
    monkeypatch.setattr(font_manager, "apply_app_font", lambda _base_size=13: None)

    tray = Tray()
    old_window = tray.config_window
    tray.apply_ui_scale_and_reopen_config(125)

    new_window = FakeConfigWindow.last_instance
    assert old_window.closed_with_animation is True
    assert tray.data_manager.reloaded is True
    assert new_window.shown is True
    assert new_window._centered_show_animation is True
    assert new_window.moved_to == QPoint(300, 180)
    settings_connected = new_window.settings_changed.connected
    assert settings_connected
    assert settings_connected[0] == tray._on_settings_changed
    assert applied_scale == [125]
    assert tray.settings_changed_calls == 1
    assert tray.popup_refresh_calls == [{"model_changed": False, "preload_icons": True}]


def test_ui_scale_reopen_waits_for_old_window_close_animation(monkeypatch):
    import ui.config_window as config_window_pkg
    import ui.utils.font_manager as font_manager
    import ui.utils.ui_scale as ui_scale

    class FakeSignal:
        def connect(self, _callback):
            return None

    class FakeRect:
        def center(self):
            return QPoint(200, 160)

        def moveCenter(self, _center):
            return None

        def topLeft(self):
            return QPoint(0, 0)

    class FakeOldWindow:
        def __init__(self):
            self.close_callback = None

        def frameGeometry(self):
            return FakeRect()

        def animate_close_then(self, callback):
            self.close_callback = callback

    class FakeConfigWindow:
        created = 0

        def __init__(self, *_args, **_kwargs):
            FakeConfigWindow.created += 1
            self.settings_changed = FakeSignal()
            self._centered_show_animation = False

        def frameGeometry(self):
            return FakeRect()

        def move(self, _pos):
            return None

        def show(self):
            return None

        def winId(self):
            raise RuntimeError("no native window in unit test")

        def raise_(self):
            return None

        def activateWindow(self):
            return None

    class FakeDataManager:
        def reload(self):
            return None

    class Tray(WindowsMixin):
        def __init__(self):
            self.data_manager = FakeDataManager()
            self.config_window = FakeOldWindow()

        def _wake_from_sleep(self, _source):
            return None

        def _on_settings_changed(self):
            return None

    monkeypatch.setattr(config_window_pkg, "ConfigWindow", FakeConfigWindow, raising=False)
    monkeypatch.setattr(ui_scale, "set_scale", lambda _percent: None)
    monkeypatch.setattr(font_manager, "apply_app_font", lambda _base_size=13: None)

    tray = Tray()
    old_window = tray.config_window

    tray.apply_ui_scale_and_reopen_config(125)

    assert old_window.close_callback is not None
    assert FakeConfigWindow.created == 0

    old_window.close_callback()

    assert FakeConfigWindow.created == 1
