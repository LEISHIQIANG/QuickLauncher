"""Comprehensive tests for core/config_history.py."""

import gzip
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.config_history import ConfigHistoryManager, ConfigSnapshot

# ── ConfigSnapshot.to_dict ──────────────────────────────────────────────────


def test_snapshot_to_dict_round_trip():
    snap = ConfigSnapshot(
        id="abc123",
        timestamp=1700000000.0,
        action="save",
        summary="test snapshot",
        version="2.5",
        path="/tmp/snap.json.gz",
        size_bytes=4096,
    )
    d = snap.to_dict()
    assert d["id"] == "abc123"
    assert d["timestamp"] == 1700000000.0
    assert d["action"] == "save"
    assert d["summary"] == "test snapshot"
    assert d["version"] == "2.5"
    assert d["path"] == "/tmp/snap.json.gz"
    assert d["size_bytes"] == 4096


def test_snapshot_to_dict_default_size_bytes():
    snap = ConfigSnapshot(id="x", timestamp=0.0, action="a", summary="s", version="1", path="/p")
    assert snap.to_dict()["size_bytes"] == 0


# ── record_snapshot ─────────────────────────────────────────────────────────


def test_record_snapshot_with_valid_data(tmp_path):
    mgr = ConfigHistoryManager(tmp_path, max_snapshots=5)
    data = {"version": "2.5", "folders": [{"id": "f1", "items": []}]}
    snap = mgr.record_snapshot(data, action="save", summary="manual save")
    assert snap is not None
    assert snap.action == "save"
    assert snap.summary == "manual save"
    assert snap.version == "2.5"
    assert snap.size_bytes > 0
    assert Path(snap.path).exists()


def test_record_snapshot_with_empty_data_returns_none(tmp_path):
    mgr = ConfigHistoryManager(tmp_path)
    assert mgr.record_snapshot({}, action="save") is None


def test_record_snapshot_with_non_dict_returns_none(tmp_path):
    mgr = ConfigHistoryManager(tmp_path)
    assert mgr.record_snapshot("not a dict") is None  # type: ignore[arg-type]
    assert mgr.record_snapshot(None) is None  # type: ignore[arg-type]
    assert mgr.record_snapshot([1, 2, 3]) is None  # type: ignore[arg-type]


def test_record_snapshot_default_action_and_summary(tmp_path):
    mgr = ConfigHistoryManager(tmp_path)
    snap = mgr.record_snapshot({"key": "val"})
    assert snap is not None
    assert snap.action == "change"
    assert snap.summary == ""


def test_record_snapshot_creates_directory(tmp_path):
    nested = tmp_path / "deep" / "nested" / "dir"
    mgr = ConfigHistoryManager(nested)
    snap = mgr.record_snapshot({"data": True})
    assert snap is not None
    assert nested.exists()


def test_record_snapshot_stores_compressed_data(tmp_path):
    mgr = ConfigHistoryManager(tmp_path)
    original_data = {"version": "1.0", "settings": {"theme": "dark", "lang": "zh"}}
    snap = mgr.record_snapshot(original_data)
    assert snap is not None
    with gzip.open(Path(snap.path), "rb") as f:
        payload = json.loads(f.read().decode("utf-8"))
    assert payload["data"] == original_data
    assert "metadata" in payload


# ── list_snapshots ──────────────────────────────────────────────────────────


def test_list_snapshots_empty_dir(tmp_path):
    mgr = ConfigHistoryManager(tmp_path / "nonexistent")
    assert mgr.list_snapshots() == []


def test_list_snapshots_returns_newest_first(tmp_path):
    mgr = ConfigHistoryManager(tmp_path, max_snapshots=10)
    for i in range(5):
        mgr.record_snapshot({"idx": i}, action=f"action_{i}")
        time.sleep(0.01)
    snaps = mgr.list_snapshots()
    assert len(snaps) == 5
    for i in range(len(snaps) - 1):
        assert snaps[i].timestamp >= snaps[i + 1].timestamp


def test_list_snapshots_metadata_fields(tmp_path):
    mgr = ConfigHistoryManager(tmp_path)
    mgr.record_snapshot({"version": "3.0"}, action="upgrade", summary="v2->v3")
    snaps = mgr.list_snapshots()
    assert len(snaps) == 1
    snap = snaps[0]
    assert snap.action == "upgrade"
    assert snap.summary == "v2->v3"
    assert snap.version == "3.0"
    assert snap.size_bytes > 0
    assert snap.id


# ── load_snapshot_data ──────────────────────────────────────────────────────


def test_load_snapshot_data_round_trip(tmp_path):
    mgr = ConfigHistoryManager(tmp_path)
    original = {"version": "2.5", "folders": [{"id": "dock", "items": []}]}
    snap = mgr.record_snapshot(original, action="save")
    assert snap is not None
    loaded = mgr.load_snapshot_data(snap.id)
    assert loaded == original


def test_load_snapshot_data_invalid_id_raises(tmp_path):
    mgr = ConfigHistoryManager(tmp_path)
    mgr.record_snapshot({"v": "1"}, action="save")
    with pytest.raises(FileNotFoundError):
        mgr.load_snapshot_data("nonexistent_id_12345")


def test_load_snapshot_data_empty_id_raises(tmp_path):
    mgr = ConfigHistoryManager(tmp_path)
    with pytest.raises(FileNotFoundError):
        mgr.load_snapshot_data("")


def test_load_snapshot_data_multiple_snapshots(tmp_path):
    mgr = ConfigHistoryManager(tmp_path, max_snapshots=10)
    ids = []
    for i in range(3):
        snap = mgr.record_snapshot({"idx": i, "data": f"value_{i}"})
        assert snap is not None
        ids.append(snap.id)
        time.sleep(0.01)
    for i, sid in enumerate(ids):
        loaded = mgr.load_snapshot_data(sid)
        assert loaded["idx"] == i


# ── prune ───────────────────────────────────────────────────────────────────


def test_prune_keeps_only_max_snapshots(tmp_path):
    mgr = ConfigHistoryManager(tmp_path, max_snapshots=3)
    for i in range(5):
        mgr.record_snapshot({"idx": i})
        time.sleep(0.01)
    snaps = mgr.list_snapshots()
    assert len(snaps) == 3
    loaded_indices = {mgr.load_snapshot_data(s.id)["idx"] for s in snaps}
    assert loaded_indices == {2, 3, 4}


def test_prune_with_max_one(tmp_path):
    mgr = ConfigHistoryManager(tmp_path, max_snapshots=1)
    for i in range(3):
        mgr.record_snapshot({"idx": i})
        time.sleep(0.01)
    snaps = mgr.list_snapshots()
    assert len(snaps) == 1
    assert mgr.load_snapshot_data(snaps[0].id)["idx"] == 2


def test_prune_does_not_delete_when_under_limit(tmp_path):
    mgr = ConfigHistoryManager(tmp_path, max_snapshots=10)
    for i in range(3):
        mgr.record_snapshot({"idx": i})
        time.sleep(0.005)
    assert len(mgr.list_snapshots()) == 3


def test_prune_called_automatically_on_record(tmp_path):
    mgr = ConfigHistoryManager(tmp_path, max_snapshots=2)
    for i in range(4):
        mgr.record_snapshot({"idx": i})
        time.sleep(0.01)
    assert len(mgr.list_snapshots()) == 2


# ── edge cases ──────────────────────────────────────────────────────────────


def test_max_snapshots_minimum_is_one():
    mgr = ConfigHistoryManager("/tmp/fake", max_snapshots=0)
    assert mgr.max_snapshots == 1

    mgr2 = ConfigHistoryManager("/tmp/fake", max_snapshots=-5)
    assert mgr2.max_snapshots == 1


def test_manager_accepts_str_path(tmp_path):
    mgr = ConfigHistoryManager(str(tmp_path))
    snap = mgr.record_snapshot({"k": "v"})
    assert snap is not None
    assert len(mgr.list_snapshots()) == 1
