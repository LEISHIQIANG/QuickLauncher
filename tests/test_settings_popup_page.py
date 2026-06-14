from ui.config_window.settings_popup_page import SettingsPopupPageMixin


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
