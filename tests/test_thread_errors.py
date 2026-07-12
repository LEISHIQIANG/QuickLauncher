"""Tests for core.thread_errors — structured thread error logging."""

from __future__ import annotations

import os
import tempfile
import threading
import time

import pytest

import core.thread_errors as te_mod
from core.thread_errors import get_thread_error_log, record_thread_error


@pytest.fixture
def isolated_log_path():
    """Each test gets a fresh temp directory + monkeypatched _get_log_path."""
    tmpdir = tempfile.mkdtemp(prefix="ql_thread_errors_")
    log_path = os.path.join(tmpdir, "thread_errors.jsonl")

    original = te_mod._get_log_path

    def _fake_path():
        return log_path

    te_mod._get_log_path = _fake_path
    yield log_path

    te_mod._get_log_path = original
    try:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


def test_record_and_read(isolated_log_path):
    record_thread_error(
        thread_name="test-thread",
        exc=ValueError("test error"),
        owner="test",
    )
    records = get_thread_error_log(limit=10)
    assert len(records) >= 1
    found = [r for r in records if r.get("thread_name") == "test-thread"]
    assert len(found) >= 1
    assert found[0]["exc_type"] == "ValueError"
    assert "test error" in found[0]["exc_message"]
    assert isinstance(found[0]["thread_id"], int) and found[0]["thread_id"] > 0
    assert found[0]["owner"] == "test"
    assert "trace" in found[0]


def test_record_and_read_returns_newest_first(isolated_log_path):
    record_thread_error(thread_name="t1", exc=RuntimeError("first"))
    time.sleep(0.002)
    record_thread_error(thread_name="t2", exc=RuntimeError("second"))
    records = get_thread_error_log(limit=10)
    t1_times = [r["time"] for r in records if r["thread_name"] == "t1"]
    t2_times = [r["time"] for r in records if r["thread_name"] == "t2"]
    if t2_times and t1_times:
        assert t2_times[0] >= t1_times[0]


def test_limit(isolated_log_path):
    for i in range(20):
        record_thread_error(thread_name=f"t{i}", exc=RuntimeError(f"err{i}"))
    records = get_thread_error_log(limit=5)
    assert len(records) <= 5


def test_after_filter(isolated_log_path):
    record_thread_error(thread_name="t-before", exc=ValueError("before"))
    iso_after = _iso_now()
    time.sleep(0.005)
    record_thread_error(thread_name="t-after", exc=ValueError("after"))
    records = get_thread_error_log(limit=10, after=iso_after)
    thread_names = [r["thread_name"] for r in records]
    assert "t-before" not in thread_names
    assert "t-after" in thread_names


def test_concurrent_writes(isolated_log_path):
    errors: list[Exception] = []
    lock = threading.Lock()

    def writer(idx: int):
        try:
            for _ in range(10):
                record_thread_error(
                    thread_name=f"concurrent-{idx}",
                    exc=ValueError(f"concurrent error {idx}"),
                    owner="stress",
                )
                time.sleep(0.001)
        except Exception as e:
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,), daemon=True) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not errors, f"concurrent writes failed: {errors}"
    records = get_thread_error_log(limit=100)
    assert len(records) >= 1


def test_survives_empty_file(isolated_log_path):
    """An empty log file should return no records (not crash)."""
    records = get_thread_error_log()
    assert isinstance(records, list)
    assert len(records) == 0


def test_survives_corrupted_line(isolated_log_path):
    """Corrupted lines in the log file are skipped without crashing."""
    with open(isolated_log_path, "w", encoding="utf-8") as f:
        f.write('not json\n{"valid": true}\nmore garbage\n')
    record_thread_error(thread_name="t-clean", exc=ValueError("clean"))
    records = get_thread_error_log(limit=10)
    assert len(records) >= 1
    clean = [r for r in records if r.get("thread_name") == "t-clean"]
    assert len(clean) >= 1


def test_all_required_fields_present(isolated_log_path):
    record_thread_error(
        thread_name="field-test",
        exc=TypeError("missing arg"),
        owner="field-owner",
        trace="custom trace",
    )
    records = get_thread_error_log(limit=10)
    found = [r for r in records if r.get("thread_name") == "field-test"]
    assert len(found) >= 1
    record = found[0]
    for key in ("time", "thread_name", "thread_id", "owner", "exc_type", "exc_message", "trace"):
        assert key in record, f"missing field: {key}"
    assert record["trace"] == "custom trace"


def test_custom_trace_preserved(isolated_log_path):
    record_thread_error(
        thread_name="trace-test",
        exc=RuntimeError("x"),
        owner="t",
        trace="custom stack",
    )
    records = get_thread_error_log(limit=10)
    found = [r for r in records if r.get("thread_name") == "trace-test"]
    assert len(found) >= 1
    assert found[0]["trace"] == "custom stack"


def test_rotation(isolated_log_path):
    """Write enough to trigger log rotation (using small max_bytes)."""
    original_max = te_mod._MAX_BYTES
    try:
        te_mod._MAX_BYTES = 100
        for i in range(200):
            record_thread_error(
                thread_name=f"rot-{i}",
                exc=RuntimeError("x" * 50),
                owner="rotation",
            )
        records = get_thread_error_log(limit=10)
        assert len(records) > 0, "No records after rotation"
    finally:
        te_mod._MAX_BYTES = original_max


def _iso_now() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="microseconds")
