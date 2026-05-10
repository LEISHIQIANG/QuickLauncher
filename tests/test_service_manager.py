import sys
import types

from core import service_manager


def install_fake_autostart(monkeypatch, **overrides):
    fake = types.SimpleNamespace(
        is_auto_start_enabled=lambda: True,
        get_auto_start_method=lambda: "task_scheduler",
        is_task_scheduler_enabled=lambda: True,
        _read_registry_value=lambda: None,
        enable_auto_start=lambda *args, **kwargs: (True, "task_scheduler"),
        disable_auto_start=lambda: (True, "disabled"),
    )
    for name, value in overrides.items():
        setattr(fake, name, value)
    monkeypatch.setitem(sys.modules, "core.auto_start_manager", fake)
    return fake


def install_fake_windows_service(monkeypatch, **overrides):
    fake = types.SimpleNamespace(
        is_service_installed=lambda: False,
        is_service_running=lambda: False,
        stop_service=lambda: None,
        uninstall_service=lambda: None,
    )
    for name, value in overrides.items():
        setattr(fake, name, value)
    monkeypatch.setitem(sys.modules, "core.windows_service", fake)
    return fake


def test_get_autostart_status_normalized(monkeypatch):
    install_fake_autostart(monkeypatch, _read_registry_value=lambda: "value")
    install_fake_windows_service(
        monkeypatch,
        is_service_installed=lambda: True,
        is_service_running=lambda: False,
    )

    status = service_manager.get_autostart_status()

    assert status == {
        "enabled": True,
        "method": "task_scheduler",
        "task_scheduler_enabled": True,
        "registry_enabled": True,
        "service_installed": True,
        "service_running": False,
    }


def test_get_autostart_status_survives_manager_failure(monkeypatch):
    def fail():
        raise RuntimeError("boom")

    install_fake_autostart(monkeypatch, is_auto_start_enabled=fail)
    install_fake_windows_service(monkeypatch, is_service_installed=lambda: True)

    status = service_manager.get_autostart_status()

    assert status["enabled"] is False
    assert status["method"] == "none"
    assert status["service_installed"] is True


def test_disable_service_autostart_cleans_legacy_service(monkeypatch):
    install_fake_autostart(monkeypatch)
    calls = []
    install_fake_windows_service(
        monkeypatch,
        is_service_installed=lambda: True,
        stop_service=lambda: calls.append("stop"),
        uninstall_service=lambda: calls.append("uninstall"),
    )

    success, _ = service_manager.disable_service_autostart()

    assert success is True
    assert calls == ["stop", "uninstall"]
