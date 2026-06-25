"""Tests for persistent heavyweight-plugin workers."""

from __future__ import annotations

import textwrap
import time
from unittest.mock import MagicMock

from core.command_registry import CommandRegistry
from core.plugin_manager import PluginAPI
from core.plugin_worker_runtime import PersistentPluginWorker
from extensions.sdk.worker_protocol import CAP_HEARTBEAT

WORKER_SOURCE = """
def run_worker(channel, token):
    channel.send({"type": "ready", "token": token})
    while True:
        message = channel.receive()
        if message.get("type") == "shutdown":
            return 0
        if message.get("type") != "request":
            continue
        payload = message.get("payload") or {}
        channel.send({
            "type": "response",
            "id": message.get("id"),
            "payload": {"status": "ok", "value": payload.get("value")},
        })
"""

MISMATCHED_RESPONSE_WORKER_SOURCE = """
def run_worker(channel, token):
    channel.send({"type": "ready", "token": token})
    message = channel.receive()
    channel.send({
        "type": "response",
        "id": "wrong-request-id",
        "payload": {"status": "ok"},
    })
    channel.receive()
"""


def test_persistent_worker_reuses_one_process(tmp_path):
    script = tmp_path / "worker.py"
    script.write_text(textwrap.dedent(WORKER_SOURCE), encoding="utf-8")
    worker = PersistentPluginWorker(plugin_id="test", script_path=script, cwd=tmp_path)
    try:
        worker.start(timeout=10)
        pid = worker._process.pid
        assert worker.request({"value": "first"}, timeout=5)["value"] == "first"
        assert worker.request({"value": "second"}, timeout=5)["value"] == "second"
        assert worker._process.pid == pid
    finally:
        worker.close()
    assert worker.running is False


def test_plugin_api_owns_and_stops_persistent_worker(tmp_path):
    plugin_dir = tmp_path / "sample"
    plugin_dir.mkdir()
    script = plugin_dir / "worker.py"
    script.write_text(textwrap.dedent(WORKER_SOURCE), encoding="utf-8")
    api = PluginAPI("sample", str(plugin_dir), ["process.run"], CommandRegistry())

    assert api.prewarm_persistent_helper("worker.py", timeout=10)
    result = api.request_persistent_helper("worker.py", {"value": 42}, timeout=5)
    assert result == {"status": "ok", "value": 42}
    worker = next(iter(api._persistent_helpers.values()))

    api.close()

    assert worker.running is False
    assert api._persistent_helpers == {}


def test_worker_start_reports_early_child_exit_without_waiting_for_timeout(tmp_path):
    script = tmp_path / "broken_worker.py"
    script.write_text("raise RuntimeError('broken worker')\n", encoding="utf-8")
    worker = PersistentPluginWorker(plugin_id="broken", script_path=script, cwd=tmp_path)

    started = time.perf_counter()
    try:
        try:
            worker.start(timeout=10)
        except RuntimeError as exc:
            assert "exited during startup" in str(exc)
        else:
            raise AssertionError("broken worker unexpectedly started")
    finally:
        worker.close()

    assert time.perf_counter() - started < 2.0


def test_worker_closes_desynchronized_channel_after_mismatched_response(tmp_path):
    script = tmp_path / "mismatched_worker.py"
    script.write_text(textwrap.dedent(MISMATCHED_RESPONSE_WORKER_SOURCE), encoding="utf-8")
    worker = PersistentPluginWorker(plugin_id="mismatch", script_path=script, cwd=tmp_path)

    try:
        try:
            worker.request({"value": "test"}, timeout=5)
        except RuntimeError as exc:
            assert "mismatched response" in str(exc)
        else:
            raise AssertionError("mismatched response unexpectedly succeeded")

        assert worker.running is False
    finally:
        worker.close()


def test_health_check_clears_quarantined_after_successful_heartbeat():
    """Regression: a transient heartbeat failure used to permanently mark
    the worker as quarantined, even after a subsequent successful check.
    The flag must be cleared once the worker recovers."""

    worker = PersistentPluginWorker.__new__(PersistentPluginWorker)
    worker.plugin_id = "test"
    worker.negotiated_capabilities = frozenset({CAP_HEARTBEAT})
    worker.quarantined = True
    worker._request_lock = __import__("threading").Lock()

    # Build a fake channel that ACKs the next heartbeat.
    channel = MagicMock()
    sent_ids: list[str] = []

    def fake_send(payload):
        sent_ids.append(payload.get("id", ""))

    def fake_receive(timeout=None):
        return {"type": "heartbeat_ack", "id": sent_ids[-1]}

    channel.send.side_effect = fake_send
    channel.receive.side_effect = fake_receive
    worker._channel = channel
    # ``running`` is a property that checks both _process and _channel;
    # a process mock whose poll() returns None counts as "running".
    worker._process = MagicMock(poll=lambda: None)

    assert worker.running is True
    assert worker.health_check(timeout=1.0) is True
    assert worker.quarantined is False


def test_health_check_sets_quarantined_on_failure():
    """Counterpart: a heartbeat that times out must still set quarantined=True."""
    worker = PersistentPluginWorker.__new__(PersistentPluginWorker)
    worker.plugin_id = "test"
    worker.negotiated_capabilities = frozenset({CAP_HEARTBEAT})
    worker.quarantined = False
    worker._request_lock = __import__("threading").Lock()

    channel = MagicMock()
    channel.send.side_effect = None
    channel.receive.side_effect = TimeoutError("no response")
    worker._channel = channel
    worker._process = MagicMock(poll=lambda: None)

    assert worker.running is True
    assert worker.health_check(timeout=0.1) is False
    assert worker.quarantined is True
