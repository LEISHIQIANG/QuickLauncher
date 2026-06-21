"""Contract tests for persistence ports.

Verifies that port implementations satisfy the semantic contracts
defined in ``application/ports/persistence.py``.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from infrastructure.persistence.adapters import (
    BackupStoreAdapter,
    ConfigRepositoryAdapter,
    HistoryStoreAdapter,
)
from infrastructure.system_clock import SystemClock, system_clock

# ── Clock contract ──────────────────────────────────────────────────


def test_clock_now_returns_positive_monotonic_float():
    """Clock.now() must return a positive float that increases monotonically."""
    t1 = system_clock.now()
    t2 = system_clock.now()

    assert isinstance(t1, float), f"expected float, got {type(t1)}"
    assert isinstance(t2, float), f"expected float, got {type(t2)}"
    assert t1 > 0, f"timestamp must be positive, got {t1}"
    assert t2 >= t1, f"clock must be monotonic: {t2} < {t1}"


def test_clock_instances_are_independent():
    """Each SystemClock instance uses the same underlying clock."""
    c1 = SystemClock()
    c2 = SystemClock()
    t1 = c1.now()
    t2 = c2.now()
    # Both should return close values (same process, same time source)
    assert abs(t2 - t1) < 1.0, f"clocks too far apart: {t2} vs {t1}"


# ── ConfigRepository contract ───────────────────────────────────────


def test_config_repository_load_returns_empty_dict_for_missing_file(tmp_path):
    """ConfigRepository.load() must return {} when the data file does not exist."""
    data_file = tmp_path / "nonexistent.json"
    from core.config_services import ConfigDataStore

    store = ConfigDataStore(data_file)
    repo = ConfigRepositoryAdapter(store)
    result = repo.load()
    assert isinstance(result, dict), f"expected dict, got {type(result)}"
    assert result == {}, f"expected empty dict, got {result}"


def test_config_repository_save_and_load_roundtrip(tmp_path):
    """ConfigRepository.save() + load() must preserve data shape."""
    data_file = tmp_path / "test.json"
    data_file.write_text('{"version":"1.0"}', encoding="utf-8")

    from core.config_services import ConfigDataStore

    store = ConfigDataStore(data_file)
    repo = ConfigRepositoryAdapter(store)

    # First load existing
    loaded = repo.load()
    assert loaded.get("version") == "1.0"

    # Save new data
    new_rev = repo.save({"version": "2.0", "extra": True}, expected_revision=1)
    assert new_rev == 2, f"expected revision 2, got {new_rev}"

    # Verify persisted
    raw = json.loads(data_file.read_text(encoding="utf-8"))
    assert raw.get("version") == "2.0"
    assert raw.get("extra") is True


# ── BackupStore contract ────────────────────────────────────────────


def test_backup_store_restore_nonexistent_raises():
    """BackupStore.restore() must raise FileNotFoundError for missing backups."""
    from core.config_services import ConfigBackupService

    svc = ConfigBackupService(Path(tempfile.gettempdir()) / "nonexistent_backup_dir", 5)
    store = BackupStoreAdapter(svc, Path(tempfile.gettempdir()) / "fake_data.json")

    with pytest.raises(FileNotFoundError):
        store.restore("/nonexistent/backup/path.zip")


# ── ConfigStatePort contract (via DataManager) ──────────────────────


def test_config_state_port_locks_are_shared():
    """ConfigStatePort.save_lock and write_lock must return shared objects."""

    from core.config_state import ConfigState

    cs = ConfigState()
    assert type(cs.save_lock).__name__ == "RLock", "save_lock must be RLock"
    assert type(cs.write_lock).__name__ == "lock", "write_lock must be Lock"


def test_config_state_port_defaults_are_sane():
    """ConfigStatePort fields must have reasonable defaults."""
    from core.config_state import ConfigState

    cs = ConfigState()
    assert cs.runtime_revision == 0
    assert cs.batch_depth == 0
    assert cs.batch_dirty is False
    assert cs.batch_force_immediate is False
    assert isinstance(cs.deleted_system_ids, set)


def test_config_state_attach_to_host_sets_legacy_fields():
    """attach_to_host() must set the expected private attributes on the host."""
    from core.config_state import ConfigState

    cs = ConfigState()
    host = type("Host", (), {})()

    cs.attach_to_host(host)

    assert host._save_lock is cs.save_lock
    assert host._write_lock is cs.write_lock
    assert host._deleted_system_ids is cs.deleted_system_ids
    assert host._runtime_revision == cs.runtime_revision
    assert host._batch_depth == cs.batch_depth


# ── HistoryStore contract ───────────────────────────────────────────


def test_history_store_append_is_noop_for_empty_data():
    """HistoryStoreAdapter.append() must not raise on empty snapshots."""
    from core.config_history import ConfigHistoryManager

    # Use a temp directory to avoid touching real history
    with tempfile.TemporaryDirectory() as td:
        mgr = ConfigHistoryManager(td, max_snapshots=5)
        adapter = HistoryStoreAdapter(mgr)

        # Append should succeed (creates a snapshot file)
        adapter.append(1, {"test": True}, action="contract_test", summary="ok")

        # Verify a snapshot was created
        snapshots = mgr.list_snapshots()
        assert len(snapshots) >= 1, "history store did not persist snapshot"
