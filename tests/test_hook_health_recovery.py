from types import SimpleNamespace

import pytest

from ui.tray_mixins.hooks_mixin import HooksMixin


def test_reinstall_hooks_can_recover_mouse_only(monkeypatch):
    calls = []
    tray = SimpleNamespace(
        _hook_reinstall_in_progress=False,
        _hook_reinstall_cooldown_until=0.0,
        _hook_reinstall_failures=0,
        _install_mouse_backend=lambda: calls.append("mouse") or True,
        _install_keyboard_hook=lambda: calls.append("keyboard"),
        keyboard_hook=None,
    )
    monkeypatch.setattr("ui.tray_mixins.hooks_mixin.time.monotonic", lambda: 100.0)

    assert HooksMixin._reinstall_hooks(tray, mouse=True, keyboard=False) is True
    assert calls == ["mouse"]
    assert tray._hook_reinstall_failures == 0
    assert tray._hook_reinstall_in_progress is False


def test_reinstall_hooks_uses_backoff_after_failure(monkeypatch):
    tray = SimpleNamespace(
        _hook_reinstall_in_progress=False,
        _hook_reinstall_cooldown_until=0.0,
        _hook_reinstall_failures=0,
        _install_mouse_backend=lambda: False,
        keyboard_hook=None,
    )
    monkeypatch.setattr("ui.tray_mixins.hooks_mixin.time.monotonic", lambda: 50.0)

    assert HooksMixin._reinstall_hooks(tray, mouse=True, keyboard=False) is False
    assert tray._hook_reinstall_failures == 1
    assert tray._hook_reinstall_cooldown_until == 52.0


def test_reinstall_hooks_backs_off_when_only_raw_input_recovers(monkeypatch):
    raw_only_hook = SimpleNamespace(is_installed=lambda: False)
    tray = SimpleNamespace(
        _hook_reinstall_in_progress=False,
        _hook_reinstall_cooldown_until=0.0,
        _hook_reinstall_failures=0,
        _install_mouse_backend=lambda: True,
        mouse_hook=raw_only_hook,
        keyboard_hook=None,
    )
    monkeypatch.setattr("ui.tray_mixins.hooks_mixin.time.monotonic", lambda: 75.0)

    assert HooksMixin._reinstall_hooks(tray, mouse=True, keyboard=False) is False
    assert tray._hook_reinstall_failures == 1
    assert tray._hook_reinstall_cooldown_until == 77.0


def test_reinstall_hooks_recovers_keyboard_without_duplicate_hotkey_channel(monkeypatch):
    keyboard_hook = SimpleNamespace(is_installed=lambda: True, _dll=object())
    tray = SimpleNamespace(
        _hook_reinstall_in_progress=False,
        _hook_reinstall_cooldown_until=0.0,
        _hook_reinstall_failures=0,
        _install_keyboard_hook=lambda: None,
        keyboard_hook=keyboard_hook,
    )
    monkeypatch.setattr("ui.tray_mixins.hooks_mixin.time.monotonic", lambda: 90.0)

    assert HooksMixin._reinstall_hooks(tray, mouse=False, keyboard=True) is True
    assert tray._hook_reinstall_failures == 0


def test_check_hook_health_logs_runtime_stat_increase(caplog):
    stats = [
        {"callback_queue_dropped": 2, "callback_exceptions": 1, "callback_queue_depth": 0},
        {"callback_queue_dropped": 5, "callback_exceptions": 2, "callback_queue_depth": 3},
    ]
    dll = SimpleNamespace(get_runtime_stats=lambda: stats.pop(0))
    hook = SimpleNamespace(is_installed=lambda: True, _dll=dll)
    tray = SimpleNamespace(
        _sleeping=False,
        mouse_hook=hook,
        keyboard_hook=hook,
        _last_hook_runtime_stats={},
    )

    HooksMixin._check_hook_health(tray)
    with caplog.at_level("WARNING"):
        HooksMixin._check_hook_health(tray)

    assert "dropped_delta=3 exception_delta=1 queue_depth=3" in caplog.text


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (["Foo"], ["foo", "foo.exe"]),
        (["Bar.EXE"], ["bar.exe", "bar"]),
        (["foo", "FOO.exe"], ["foo", "foo.exe"]),
    ],
)
def test_get_special_apps_for_hook_expands_and_deduplicates(configured, expected):
    tray = SimpleNamespace(_get_special_apps=lambda: configured)

    assert HooksMixin._get_special_apps_for_hook(tray) == expected


def test_process_check_executor_can_shutdown_and_restart():
    from ui.tray_mixins import hooks_mixin

    first = hooks_mixin._get_process_check_executor()
    hooks_mixin.shutdown_process_check_executor()
    second = hooks_mixin._get_process_check_executor()
    hooks_mixin.shutdown_process_check_executor()

    assert first is not second


def test_apply_keyboard_trigger_installs_missing_keyboard_hook():
    calls = []
    keyboard_hook = SimpleNamespace(is_installed=lambda: True)

    class MouseHook:
        def set_special_apps(self, apps):
            calls.append(("special_apps", apps))

        def set_keyboard_hook(self, hook):
            calls.append(("keyboard_hook", hook))

        def set_trigger_config_ex(self, *args):
            calls.append(("trigger", args))

    settings = SimpleNamespace(
        popup_trigger_mode="keyboard",
        popup_trigger_keys=["q"],
        popup_trigger_button="",
        popup_trigger_modifiers=["ctrl"],
        popup_special_trigger_mode="mouse",
        popup_special_trigger_keys=[],
        popup_special_trigger_button="middle",
        popup_special_trigger_modifiers=["ctrl"],
    )
    tray = SimpleNamespace(
        mouse_hook=MouseHook(),
        keyboard_hook=None,
        data_manager=SimpleNamespace(get_settings=lambda: settings),
        _get_special_apps_for_hook=lambda: [],
    )

    def install_keyboard_hook():
        calls.append(("install_keyboard",))
        tray.keyboard_hook = keyboard_hook

    tray._install_keyboard_hook = install_keyboard_hook

    HooksMixin._apply_mouse_hook_settings(tray)

    assert ("install_keyboard",) in calls
    assert ("keyboard_hook", keyboard_hook) in calls
    trigger_call = next(call for call in calls if call[0] == "trigger")
    assert trigger_call[1][:4] == ("keyboard", "", ["q"], ["ctrl"])


def test_apply_taskbar_trigger_disables_normal_mouse_trigger_and_uses_interval():
    calls = []

    class MouseHook:
        def set_special_apps(self, apps):
            calls.append(("special_apps", apps))

        def set_trigger_config_ex(self, *args):
            calls.append(("trigger", args))

        def set_taskbar_trigger(self, *args):
            calls.append(("taskbar", args))

    settings = SimpleNamespace(
        popup_trigger_source="taskbar",
        popup_trigger_mode="mouse",
        popup_trigger_keys=[],
        popup_trigger_button="",
        popup_trigger_modifiers=[],
        popup_taskbar_trigger_ctrl=False,
        popup_special_trigger_source="mouse",
        popup_special_trigger_mode="mouse",
        popup_special_trigger_keys=[],
        popup_special_trigger_button="middle",
        popup_special_trigger_modifiers=["ctrl"],
        popup_special_taskbar_trigger_ctrl=False,
        double_click_interval=285,
    )
    tray = SimpleNamespace(
        mouse_hook=MouseHook(),
        keyboard_hook=None,
        data_manager=SimpleNamespace(get_settings=lambda: settings),
        _get_special_apps_for_hook=lambda: [],
    )

    HooksMixin._apply_mouse_hook_settings(tray)

    assert ("trigger", ("mouse", "", [], [], "mouse", "middle", [], ["ctrl"])) in calls
    assert ("taskbar", (True, False, 285)) in calls
