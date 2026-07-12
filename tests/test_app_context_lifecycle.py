from __future__ import annotations

from application.state import StateStore
from bootstrap.app_context import AppContext
from bootstrap.lifecycle import LifecycleManager, LifecycleState


class _UIActions:
    def execute(self, action):
        return True


def test_context_releases_resources_in_reverse_order_once():
    calls: list[str] = []
    lifecycle = LifecycleManager()
    lifecycle.register("first", lambda: calls.append("first"))
    lifecycle.register("second", lambda: calls.append("second"))
    context = AppContext(lifecycle, StateStore(), _UIActions(), object(), object())

    context.start()
    assert lifecycle.state == LifecycleState.RUNNING
    assert context.shutdown() == []
    assert context.shutdown() == []
    assert calls == ["second", "first"]
    assert lifecycle.state == LifecycleState.STOPPED


def test_lifecycle_continues_after_resource_failure():
    calls: list[str] = []
    lifecycle = LifecycleManager()
    lifecycle.register("last", lambda: calls.append("last"))

    def fail():
        raise RuntimeError("boom")

    lifecycle.register("broken", fail)
    lifecycle.register("first", lambda: calls.append("first"))

    assert lifecycle.shutdown() == ["broken"]
    assert calls == ["first", "last"]
