from __future__ import annotations

import json
from types import SimpleNamespace

from core.plugin.state_store import PluginStateStore


def _info(plugin_id: str = "demo"):
    return SimpleNamespace(
        manifest=SimpleNamespace(id=plugin_id),
        status="disabled",
        quarantined=False,
        failure_count=2,
        last_error_stage="command",
        last_error_at=123.0,
        disabled_reason="",
        error="",
    )


def test_state_store_round_trips_plugin_lifecycle(tmp_path):
    store = PluginStateStore(tmp_path)
    info = _info()
    info.status = "quarantined"
    info.quarantined = True
    info.disabled_reason = "repeated failure"

    store.persist(info)
    restored = PluginStateStore(tmp_path).apply(_info())

    assert restored.status == "quarantined"
    assert restored.quarantined is True
    assert restored.failure_count == 2
    assert restored.disabled_reason == "repeated failure"
    assert not (tmp_path / "plugin_state.json.tmp").exists()


def test_state_store_fails_closed_on_invalid_json(tmp_path):
    (tmp_path / "plugin_state.json").write_text("{broken", encoding="utf-8")

    store = PluginStateStore(tmp_path)
    restored = store.apply(_info())

    assert restored.status == "disabled"
    assert restored.failure_count == 2


def test_error_log_is_structured_and_privacy_bounded(tmp_path):
    store = PluginStateStore(tmp_path)
    store.append_error("demo", "load", "operation-1", RuntimeError("boom"), "trace", "recorded")

    payload = json.loads((tmp_path / "plugin_errors.jsonl").read_text(encoding="utf-8"))
    assert payload["plugin_id"] == "demo"
    assert payload["operation_id"] == "operation-1"
    assert payload["error"] == "boom"
