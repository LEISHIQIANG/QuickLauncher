from ui.config_window.settings_popup_page import SettingsPopupPageMixin


class FakeSignal:
    def __init__(self):
        self.emitted = 0

    def emit(self):
        self.emitted += 1


class FakeRecorder:
    def __init__(
        self,
        *,
        mode="mouse",
        keys=None,
        button="middle",
        modifiers=None,
        taskbar=False,
        taskbar_ctrl=False,
    ):
        self.mode = mode
        self.keys = list(keys or [])
        self.button = button
        self.modifiers = list(modifiers or [])
        self.taskbar = taskbar
        self.taskbar_ctrl = taskbar_ctrl
        self.set_calls = []
        self.clear_calls = 0

    def get_mode(self):
        return self.mode

    def get_keys(self):
        return list(self.keys)

    def get_button(self):
        return self.button

    def get_modifiers(self):
        return list(self.modifiers)

    def is_taskbar_trigger(self):
        return self.taskbar

    def get_taskbar_ctrl(self):
        return self.taskbar_ctrl

    def set_trigger(self, mode, keys, button, modifiers):
        self.set_calls.append((mode, list(keys), button, list(modifiers)))

    def clear(self):
        self.clear_calls += 1
        self.mode = "mouse"
        self.keys = []
        self.button = ""
        self.modifiers = []
        self.taskbar = False
        self.taskbar_ctrl = False


def test_trigger_apply_button_shows_success_toast():
    calls = []

    class Panel(SettingsPopupPageMixin):
        def _try_apply_trigger_config(self):
            return True

        def _show_trigger_apply_toast(self, applied):
            calls.append(applied)

    Panel()._on_trigger_config_changed()

    assert calls == [True]


def test_trigger_apply_button_shows_failure_toast_on_exception():
    calls = []

    class Panel(SettingsPopupPageMixin):
        def _try_apply_trigger_config(self):
            raise RuntimeError("save failed")

        def _show_trigger_apply_toast(self, applied):
            calls.append(applied)

    Panel()._on_trigger_config_changed()

    assert calls == [False]


def test_taskbar_preset_waits_for_apply_button():
    calls = []

    class Panel(SettingsPopupPageMixin):
        def _try_apply_trigger_config(self):
            calls.append("apply")

        def _show_trigger_apply_toast(self, applied):
            calls.append(("toast", applied))

    Panel()._on_taskbar_preset_selected("normal", False)

    assert calls == []


def test_clear_trigger_waits_for_apply_button():
    normal = FakeRecorder(button="middle")
    special = FakeRecorder(button="middle", modifiers=["ctrl"])
    calls = []

    panel = type(
        "Panel",
        (SettingsPopupPageMixin,),
        {
            "normal_trigger_recorder": normal,
            "special_trigger_recorder": special,
            "_try_apply_trigger_config": lambda self: calls.append("apply"),
        },
    )()

    panel._on_clear_trigger("normal")

    assert normal.clear_calls == 1
    assert calls == []


def test_try_apply_trigger_config_returns_false_when_runtime_hook_apply_fails():
    updates = []

    class DataManager:
        data = None

        def update_settings(self, **kwargs):
            updates.append(kwargs)

    class TrayApp:
        def _apply_mouse_hook_settings(self):
            return False

    panel = type(
        "Panel",
        (SettingsPopupPageMixin,),
        {
            "_updating": False,
            "data_manager": DataManager(),
            "tray_app": TrayApp(),
            "normal_trigger_recorder": FakeRecorder(taskbar=True),
            "special_trigger_recorder": FakeRecorder(button="middle", modifiers=["ctrl"]),
            "trigger_config_changed": FakeSignal(),
        },
    )()

    assert panel._try_apply_trigger_config() is False
    assert updates
    assert updates[0]["popup_trigger_source"] == "mouse"
    assert updates[0]["popup_trigger_button"] == "middle"
    assert panel.trigger_config_changed.emitted == 0


def test_trigger_apply_toast_reuses_alt_double_tap_style(monkeypatch):
    created = []

    class FakeToast:
        def __init__(self):
            self.calls = []
            created.append(self)

        def show_toast(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    monkeypatch.setattr("ui.toast_notification.ToastNotification", FakeToast)

    panel = type("Panel", (), {"current_theme": "light"})()
    SettingsPopupPageMixin._show_trigger_apply_toast(panel, True)
    SettingsPopupPageMixin._show_trigger_apply_toast(panel, False)

    assert len(created) == 1
    assert created[0].calls == [
        (
            ("应用成功",),
            {
                "theme": "light",
                "duration_ms": 800,
                "target_widget": panel,
                "center_on_target": True,
            },
        ),
        (
            ("应用失败",),
            {
                "theme": "light",
                "duration_ms": 800,
                "target_widget": panel,
                "center_on_target": True,
            },
        ),
    ]
