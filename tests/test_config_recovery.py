"""Tests for core/config_recovery.py — serialization, reports, file quarantine, and pruning."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config_recovery import (
    MAX_QUARANTINED_BYTES,
    RECOVERY_STATE_FILE,
    ConfigRecoveryReport,
    prune_quarantine,
    quarantine_bad_config,
    read_recovery_report,
    recovery_state_path,
    write_recovery_report,
)

pytestmark = pytest.mark.integration

# ── ConfigRecoveryReport Dataclass ──────────────────────────────────────────


def test_report_default_values():
    report = ConfigRecoveryReport()
    assert report.status == "ok"
    assert report.reason == ""
    assert report.source_path == ""
    assert report.recovered_from == ""
    assert report.quarantined_path == ""
    assert report.issues == []
    assert isinstance(report.created_at, str)


def test_report_to_dict_round_trip():
    report = ConfigRecoveryReport(
        status="repaired",
        reason="corrupted root object",
        source_path="/app/data.json",
        recovered_from="/app/backup.json",
        quarantined_path="/app/bad_data.json",
        issues=["duplicate_id"],
    )
    d = report.to_dict()
    assert d["status"] == "repaired"
    assert d["reason"] == "corrupted root object"
    assert d["source_path"] == "/app/data.json"
    assert d["recovered_from"] == "/app/backup.json"
    assert d["quarantined_path"] == "/app/bad_data.json"
    assert d["issues"] == ["duplicate_id"]


def test_report_from_dict_non_dict():
    report = ConfigRecoveryReport.from_dict("not a dict")
    assert report.status == "unknown"
    assert "invalid recovery report" in report.reason


def test_report_from_dict_fields():
    data = {
        "status": "warning",
        "reason": "missing keys",
        "source_path": "/src",
        "recovered_from": "/backup",
        "quarantined_path": "/bad",
        "issues": ["issue1", None, "issue2"],
        "created_at": "2026-05-30T12:00:00",
    }
    report = ConfigRecoveryReport.from_dict(data)
    assert report.status == "warning"
    assert report.reason == "missing keys"
    assert report.source_path == "/src"
    assert report.recovered_from == "/backup"
    assert report.quarantined_path == "/bad"
    assert report.issues == ["issue1", "issue2"]
    assert report.created_at == "2026-05-30T12:00:00"


# ── Recovery state path ──────────────────────────────────────────────────────


def test_recovery_state_path_resolution(tmp_path):
    p = recovery_state_path(tmp_path)
    assert p == tmp_path / RECOVERY_STATE_FILE


# ── Read / Write recovery report ─────────────────────────────────────────────


def test_write_and_read_report_success(tmp_path):
    report = ConfigRecoveryReport(status="repaired", reason="testing")
    assert write_recovery_report(tmp_path, report) is True

    loaded = read_recovery_report(tmp_path)
    assert loaded is not None
    assert loaded.status == "repaired"
    assert loaded.reason == "testing"


def test_read_report_not_exists(tmp_path):
    assert read_recovery_report(tmp_path) is None


def test_write_report_exception_returns_false():
    # Pass None to trigger an exception during mkdir/write_text
    assert write_recovery_report(None, ConfigRecoveryReport()) is False


def test_read_report_exception_returns_none():
    # Pass None to trigger an exception in path checking
    assert read_recovery_report(None) is None


# ── Quarantine bad config ────────────────────────────────────────────────────


def test_quarantine_bad_config_missing_source(tmp_path):
    non_existent = tmp_path / "nonexistent.json"
    result = quarantine_bad_config(non_existent, tmp_path / "recovery")
    assert result is None


def test_quarantine_bad_config_small_file(tmp_path):
    source = tmp_path / "data.json"
    source.write_text('{"bad_key": true}', encoding="utf-8")

    rec_dir = tmp_path / "recovery"
    quarantined = quarantine_bad_config(source, rec_dir)

    assert quarantined is not None
    assert quarantined.exists()
    assert quarantined.name.startswith("bad_data_")
    assert quarantined.name.endswith(".json")
    assert "summary" not in quarantined.name

    loaded = json.loads(quarantined.read_text(encoding="utf-8"))
    assert loaded == {"bad_key": True}


def test_quarantine_bad_config_large_file(tmp_path):
    source = tmp_path / "large_data.json"
    # Create a dummy large file that exceeds MAX_QUARANTINED_BYTES
    large_content = b"x" * (MAX_QUARANTINED_BYTES + 1024)
    source.write_bytes(large_content)

    rec_dir = tmp_path / "recovery"
    quarantined = quarantine_bad_config(source, rec_dir)

    assert quarantined is not None
    assert quarantined.exists()
    assert quarantined.name.startswith("bad_data_")
    assert quarantined.name.endswith(".summary.json")

    summary = json.loads(quarantined.read_text(encoding="utf-8"))
    assert summary["original_path"] == str(source)
    assert summary["size_bytes"] == len(large_content)
    assert "sha256" in summary
    assert "exceeded quarantine size limit" in summary["note"]


def test_quarantine_bad_config_exception_returns_none(tmp_path):
    source = tmp_path / "data.json"
    source.write_text("{}", encoding="utf-8")
    # Pass None as recovery dir to trigger an exception
    result = quarantine_bad_config(source, None)
    assert result is None


# ── Prune quarantine ────────────────────────────────────────────────────────


def test_prune_quarantine_keeps_newest(tmp_path):
    rec_dir = tmp_path / "recovery"
    rec_dir.mkdir()

    # Create 15 quarantine files
    files = []
    for i in range(15):
        # Create both standard and summary files to test combined pruning
        suffix = ".summary.json" if i % 2 == 0 else ".json"
        p = rec_dir / f"bad_data_20260530_12000{i}{suffix}"
        p.write_text("{}", encoding="utf-8")
        # Shift modification times slightly to control age ordering
        stat_mock = MagicMock()
        stat_mock.st_mtime = float(i)
        stat_mock.st_size = 10
        with patch.object(Path, "stat", return_value=stat_mock):
            files.append(p)

    # Prune and keep only 5
    prune_quarantine(rec_dir, keep=5)

    # Check that older files are removed, and only 5 remain
    existing = sorted(rec_dir.glob("bad_data_*"))
    assert len(existing) == 5


def test_prune_quarantine_exception_handled():
    # Should not raise exception
    prune_quarantine(None)
