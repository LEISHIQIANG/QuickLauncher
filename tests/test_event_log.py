"""Comprehensive tests for core/event_log.py."""

import json
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import core.event_log as el


@pytest.fixture(autouse=True)
def _reset_event_log():
    """Reset global _event_dir before and after each test."""
    el._event_dir = None
    yield
    el._event_dir = None


# ── init_event_log ──────────────────────────────────────────────────────────


def test_init_sets_event_dir_from_str(tmp_path):
    el.init_event_log(str(tmp_path))
    assert el._event_dir == tmp_path


def test_init_sets_event_dir_from_path(tmp_path):
    el.init_event_log(tmp_path)
    assert el._event_dir == tmp_path


def test_init_overwrites_previous_dir(tmp_path):
    el.init_event_log(tmp_path / "a")
    el.init_event_log(tmp_path / "b")
    assert el._event_dir == tmp_path / "b"


# ── log_event: no-op when uninitialized ─────────────────────────────────────


def test_log_event_noop_when_uninitialized(tmp_path):
    el.log_event("test.action", "should be ignored")
    assert not (tmp_path / "events.jsonl").exists()


# ── log_event: basic round-trip ─────────────────────────────────────────────


def test_log_creates_file_and_entry(tmp_path):
    el.init_event_log(tmp_path)
    el.log_event("app.start", "Application started")
    path = tmp_path / "events.jsonl"
    assert path.exists()
    lines = [ln for ln in path.read_text("utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event"] == "app.start"
    assert entry["summary"] == "Application started"
    assert "time" in entry
    assert "details" not in entry


def test_log_multiple_events(tmp_path):
    el.init_event_log(tmp_path)
    for i in range(5):
        el.log_event(f"evt.{i}", f"summary {i}")
    lines = [ln for ln in (tmp_path / "events.jsonl").read_text("utf-8").splitlines() if ln.strip()]
    assert len(lines) == 5
    for i, ln in enumerate(lines):
        assert json.loads(ln)["event"] == f"evt.{i}"


def test_log_event_with_details(tmp_path):
    el.init_event_log(tmp_path)
    el.log_event("shortcut.add", "Added", details={"name": "notepad", "key": "Ctrl+N"})
    entry = json.loads((tmp_path / "events.jsonl").read_text("utf-8").splitlines()[0])
    assert entry["details"]["name"] == "notepad"
    assert entry["details"]["key"] == "Ctrl+N"


def test_details_truncation_over_200_chars(tmp_path):
    long_value = "x" * 300
    el.init_event_log(tmp_path)
    el.log_event("big", "data", details={"payload": long_value})
    entry = json.loads((tmp_path / "events.jsonl").read_text("utf-8").splitlines()[0])
    assert entry["details"]["payload"] == "x" * 200 + "..."


def test_details_exactly_200_chars_not_truncated(tmp_path):
    val = "a" * 200
    el.init_event_log(tmp_path)
    el.log_event("exact", "data", details={"v": val})
    entry = json.loads((tmp_path / "events.jsonl").read_text("utf-8").splitlines()[0])
    assert entry["details"]["v"] == val
    assert not entry["details"]["v"].endswith("...")


def test_details_values_coerced_to_str(tmp_path):
    el.init_event_log(tmp_path)
    el.log_event("types", "mixed", details={"count": 42, "flag": True, "ratio": 3.14})
    entry = json.loads((tmp_path / "events.jsonl").read_text("utf-8").splitlines()[0])
    assert entry["details"]["count"] == "42"
    assert entry["details"]["flag"] == "True"
    assert entry["details"]["ratio"] == "3.14"


def test_empty_details_dict_omitted(tmp_path):
    el.init_event_log(tmp_path)
    el.log_event("noop", "no details", details={})
    entry = json.loads((tmp_path / "events.jsonl").read_text("utf-8").splitlines()[0])
    assert "details" not in entry


def test_creates_nested_config_dir(tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    el.init_event_log(nested)
    el.log_event("mk", "dir")
    assert nested.exists()
    assert (nested / "events.jsonl").exists()


# ── _rotate_if_needed ───────────────────────────────────────────────────────


def test_no_rotation_under_limit(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("small\n", encoding="utf-8")
    original_max = el._MAX_BYTES
    try:
        el._MAX_BYTES = 1024
        el._rotate_if_needed(path)
        assert path.exists()
        assert not path.with_suffix(".jsonl.1").exists()
    finally:
        el._MAX_BYTES = original_max


def test_no_rotation_when_file_missing(tmp_path):
    path = tmp_path / "events.jsonl"
    el._rotate_if_needed(path)  # should not raise


def test_rotation_on_exceeding_limit(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("x" * 100, encoding="utf-8")
    original_max = el._MAX_BYTES
    original_backup = el._BACKUP_COUNT
    try:
        el._MAX_BYTES = 50
        el._BACKUP_COUNT = 2
        el._rotate_if_needed(path)
        assert not path.exists()
        assert path.with_suffix(".jsonl.1").exists()
        assert path.with_suffix(".jsonl.1").read_text("utf-8") == "x" * 100
    finally:
        el._MAX_BYTES = original_max
        el._BACKUP_COUNT = original_backup


def test_rotation_chain_shifts_backups(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("current", encoding="utf-8")
    (tmp_path / "events.jsonl.1").write_text("backup1", encoding="utf-8")
    original_max = el._MAX_BYTES
    original_backup = el._BACKUP_COUNT
    try:
        el._MAX_BYTES = 1
        el._BACKUP_COUNT = 2
        el._rotate_if_needed(path)
        assert path.with_suffix(".jsonl.2").read_text("utf-8") == "backup1"
        assert path.with_suffix(".jsonl.1").read_text("utf-8") == "current"
        assert not path.exists()
    finally:
        el._MAX_BYTES = original_max
        el._BACKUP_COUNT = original_backup


def test_oldest_backup_deleted_at_max(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("current", encoding="utf-8")
    (tmp_path / "events.jsonl.1").write_text("first", encoding="utf-8")
    (tmp_path / "events.jsonl.2").write_text("second", encoding="utf-8")
    original_max = el._MAX_BYTES
    original_backup = el._BACKUP_COUNT
    try:
        el._MAX_BYTES = 1
        el._BACKUP_COUNT = 2
        el._rotate_if_needed(path)
        assert not path.with_suffix(".jsonl.3").exists()
        assert path.with_suffix(".jsonl.2").read_text("utf-8") == "first"
        assert path.with_suffix(".jsonl.1").read_text("utf-8") == "current"
    finally:
        el._MAX_BYTES = original_max
        el._BACKUP_COUNT = original_backup


# ── read_recent_events ──────────────────────────────────────────────────────


def test_read_returns_empty_when_file_missing(tmp_path):
    assert el.read_recent_events(tmp_path) == []


def test_read_returns_empty_for_empty_file(tmp_path):
    (tmp_path / "events.jsonl").write_text("", encoding="utf-8")
    assert el.read_recent_events(tmp_path) == []


def test_read_returns_empty_for_nonexistent_dir(tmp_path):
    assert el.read_recent_events(tmp_path / "no_such_dir") == []


def test_read_valid_events(tmp_path):
    lines = [
        json.dumps({"time": "2025-01-01T00:00:00", "event": "a", "summary": "A"}),
        json.dumps({"time": "2025-01-01T00:00:01", "event": "b", "summary": "B"}),
    ]
    (tmp_path / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = el.read_recent_events(tmp_path)
    assert len(result) == 2
    assert result[0]["event"] == "a"
    assert result[1]["event"] == "b"


def test_read_max_lines_limits_returned_events(tmp_path):
    lines = [json.dumps({"time": f"t{i}", "event": f"e{i}", "summary": f"s{i}"}) for i in range(50)]
    (tmp_path / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = el.read_recent_events(tmp_path, max_lines=10)
    assert len(result) == 10
    assert result[0]["event"] == "e40"
    assert result[-1]["event"] == "e49"


def test_read_skips_malformed_json_lines(tmp_path):
    content = (
        '{"time":"t","event":"ok","summary":"OK"}\n'
        "NOT VALID JSON{{{ \n"
        '{"time":"t2","event":"ok2","summary":"OK2"}\n'
    )
    (tmp_path / "events.jsonl").write_text(content, encoding="utf-8")
    result = el.read_recent_events(tmp_path)
    assert len(result) == 2
    assert result[0]["event"] == "ok"
    assert result[1]["event"] == "ok2"


def test_read_skips_non_dict_json_lines(tmp_path):
    content = '[1, 2, 3]\n{"time":"t","event":"good","summary":"G"}\n"string"\n42\n'
    (tmp_path / "events.jsonl").write_text(content, encoding="utf-8")
    result = el.read_recent_events(tmp_path)
    assert len(result) == 1
    assert result[0]["event"] == "good"


def test_read_skips_blank_lines(tmp_path):
    content = '\n\n{"time":"t","event":"x","summary":"X"}\n\n\n'
    (tmp_path / "events.jsonl").write_text(content, encoding="utf-8")
    result = el.read_recent_events(tmp_path)
    assert len(result) == 1


def test_read_accepts_str_config_dir(tmp_path):
    (tmp_path / "events.jsonl").write_text('{"time":"t","event":"s","summary":"S"}\n', encoding="utf-8")
    result = el.read_recent_events(str(tmp_path))
    assert len(result) == 1


# ── End-to-end: init + log + read round-trip ────────────────────────────────


def test_init_log_read_round_trip(tmp_path):
    el.init_event_log(tmp_path)
    el.log_event("round.trip", "test event", details={"key": "value"})
    events = el.read_recent_events(tmp_path)
    assert len(events) == 1
    assert events[0]["event"] == "round.trip"
    assert events[0]["summary"] == "test event"
    assert events[0]["details"]["key"] == "value"


def test_init_log_read_multiple_round_trip(tmp_path):
    el.init_event_log(tmp_path)
    for i in range(20):
        el.log_event(f"action.{i}", f"desc {i}", details={"idx": i})
    events = el.read_recent_events(tmp_path, max_lines=5)
    assert len(events) == 5
    assert events[0]["event"] == "action.15"
    assert events[-1]["event"] == "action.19"


# ── Thread safety ───────────────────────────────────────────────────────────


def test_concurrent_log_events(tmp_path):
    el.init_event_log(tmp_path)
    original_max = el._MAX_BYTES
    try:
        el._MAX_BYTES = 10 * 1024 * 1024  # disable rotation
        num_threads = 10
        events_per_thread = 50
        barrier = threading.Barrier(num_threads)

        def worker(tid):
            barrier.wait()
            for j in range(events_per_thread):
                el.log_event(f"t{tid}", f"thread-{tid}-event-{j}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lines = [ln for ln in (tmp_path / "events.jsonl").read_text("utf-8").splitlines() if ln.strip()]
        assert len(lines) == num_threads * events_per_thread
        for ln in lines:
            entry = json.loads(ln)
            assert "event" in entry
            assert "summary" in entry
    finally:
        el._MAX_BYTES = original_max
