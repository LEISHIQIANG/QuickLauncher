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
