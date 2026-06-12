"""Tests for persistent heavyweight-plugin workers."""

from __future__ import annotations

import textwrap
import time

from core.command_registry import CommandRegistry
from core.plugin_manager import PluginAPI
from core.plugin_worker_runtime import PersistentPluginWorker

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
