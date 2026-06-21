"""Tests for the shared popup execution service lifecycle.

These tests cover the P0-02 / P0-03 follow-ups:

* The launcher popup reuses one ``CommandExecutionService`` per popup
  instance (instead of allocating a new service on every click).
* ``closeEvent`` on the popup drains the cached service's tracked
  futures so a closing popup does not leak work.
* The cached service still participates in the process-wide executor
  pool exposed by :class:`CommandExecutionService`.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.command_execution_service import CommandExecutionService
from core.command_results import CommandResultStore
from ui.launcher_popup.popup_item_execution import PopupItemExecutionMixin

pytestmark = pytest.mark.ui


class _FakePopup(PopupItemExecutionMixin):
    """Lightweight harness that exercises the mixin's service cache helpers."""

    def __init__(self, tray_app=None):
        self.tray_app = tray_app
        self.shutdown_calls: list[float] = []
        self._popup_execution_service = None
        self._exec_service = MagicMock(spec=CommandExecutionService)
        self._exec_service.shutdown = self._record_shutdown

    def _record_shutdown(self, timeout: float = 0.2) -> None:  # type: ignore[override]
        self.shutdown_calls.append(float(timeout))
        # Track shutdown for assertions on active futures.
        self._popup_execution_service = None

    def _provide_service(self, service: CommandExecutionService) -> CommandExecutionService:
        self._popup_execution_service = service
        return service


def test_popup_caches_command_execution_service(monkeypatch):
    """P0-02 follow-up: the popup must reuse one service per popup instance."""

    popup = _FakePopup()
    created: list[CommandExecutionService] = []

    def fake_ctor(_store, **_kwargs):
        service = CommandExecutionService(CommandResultStore())
        created.append(service)
        return service

    monkeypatch.setattr(
        "core.command_execution_service.CommandExecutionService",
        fake_ctor,
    )

    first = popup._get_popup_execution_service()
    second = popup._get_popup_execution_service()

    assert first is second
    assert len(created) == 1
    assert first._pool is CommandExecutionService._get_shared_pool()


def test_popup_close_shuts_down_cached_service(monkeypatch):
    """P0-03 follow-up: closing the popup must drain the cached service."""

    popup = _FakePopup()
    monkeypatch.setattr(
        "core.command_execution_service.CommandExecutionService",
        lambda _store, **_kwargs: popup._exec_service,
    )

    service = popup._get_popup_execution_service()
    assert service is popup._exec_service

    popup._shutdown_popup_execution_service(timeout=0.3)

    assert popup.shutdown_calls == [0.3]
    assert popup._popup_execution_service is None

    # A second call after shutdown is a safe no-op.
    popup._shutdown_popup_execution_service(timeout=0.5)
    assert popup.shutdown_calls == [0.3]


def test_popup_execution_service_uses_tray_app_result_store(monkeypatch):
    """If the tray app already has a result store, the cached service reuses it."""

    tray_app = SimpleNamespace(command_result_store=CommandResultStore())
    popup = _FakePopup(tray_app=tray_app)
    captured: list[CommandResultStore | None] = []

    def fake_ctor(store, **_kwargs):
        captured.append(store)
        return CommandExecutionService(store)

    monkeypatch.setattr(
        "core.command_execution_service.CommandExecutionService",
        fake_ctor,
    )

    popup._get_popup_execution_service()

    assert captured == [tray_app.command_result_store]


def test_popup_creates_result_store_when_tray_app_missing(monkeypatch):
    """If the tray app has no result store yet, the popup initializes one."""

    tray_app = SimpleNamespace()
    popup = _FakePopup(tray_app=tray_app)
    captured: list[CommandResultStore | None] = []

    def fake_ctor(store, **_kwargs):
        captured.append(store)
        return CommandExecutionService(store)

    monkeypatch.setattr(
        "core.command_execution_service.CommandExecutionService",
        fake_ctor,
    )

    popup._get_popup_execution_service()

    assert len(captured) == 1
    assert isinstance(captured[0], CommandResultStore)
    assert tray_app.command_result_store is captured[0]
