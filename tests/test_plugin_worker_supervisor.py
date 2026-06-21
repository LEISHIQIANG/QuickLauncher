from unittest.mock import Mock

import pytest

from core.plugin.worker_supervisor import PluginWorkerSupervisor
from core.plugin_worker_runtime import PluginWorkerBackpressure


def _worker(*, running=True, healthy=True, quarantined=False):
    worker = Mock()
    worker.running = running
    worker.quarantined = quarantined
    worker.negotiated_capabilities = frozenset({"request", "heartbeat"})
    worker.health_check.return_value = healthy
    return worker


def test_supervisor_owns_capacity_health_snapshot_and_idempotent_close():
    supervisor = PluginWorkerSupervisor("demo", max_workers=1)
    worker = _worker()

    assert supervisor.get_or_create("worker.py", lambda: worker) is worker
    assert supervisor.get_or_create("WORKER.py", lambda: Mock()) is worker
    assert supervisor.poll_health() == {"worker.py": True}
    assert supervisor.snapshot()["workers"]["worker.py"]["capabilities"] == ["heartbeat", "request"]
    with pytest.raises(PluginWorkerBackpressure):
        supervisor.get_or_create("second.py", Mock)

    supervisor.close()
    supervisor.close()
    worker.close.assert_called_once()
    assert supervisor.snapshot()["closed"] is True


def test_supervisor_stop_releases_worker_slot():
    supervisor = PluginWorkerSupervisor("demo", max_workers=1)
    first = _worker()
    second = _worker()
    supervisor.get_or_create("first.py", lambda: first)
    supervisor.stop("first.py")
    assert first.close.call_count == 1
    assert supervisor.get_or_create("second.py", lambda: second) is second
