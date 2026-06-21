from __future__ import annotations

from types import SimpleNamespace

from ui.tray_controllers import TrayController, TrayControllerSet


def test_controller_delegates_state_to_owner():
    owner = SimpleNamespace(value=1)
    controller = TrayController(owner)

    controller.value = 2

    assert owner.value == 2
    assert controller.value == 2


def test_controller_set_resolves_behavior_and_stops_once():
    calls = []
    owner = SimpleNamespace(_runtime_shutdown_started=False)
    controllers = TrayControllerSet(owner)
    shutdown = controllers.resolve("_shutdown_runtime_components")

    assert callable(shutdown)

    class FakeController:
        def stop(self):
            calls.append("stop")

    controllers._controllers = (FakeController(), FakeController())
    controllers.stop()
    controllers.stop()

    assert calls == ["stop", "stop"]
