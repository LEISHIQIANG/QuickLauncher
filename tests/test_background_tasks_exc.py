"""Tests for start_background_thread exception handling."""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from core.background_tasks import list_background_tasks, start_background_thread
from core.thread_errors import get_thread_error_log


@pytest.fixture
def isolated_log_path(monkeypatch):
    import core.thread_errors as te_mod

    tmpdir = tempfile.mkdtemp(prefix="ql_bg_exc_")
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


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_background_thread_error_recorded_start(isolated_log_path):
    """A crashing background thread records the error via thread_errors."""
    results = []

    def will_crash():
        results.append("started")
        raise RuntimeError("crash in bg thread")

    thread = start_background_thread(
        name="test-bg-crash",
        target=will_crash,
        owner="test-bg-error",
    )
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    records = get_thread_error_log(limit=10)
    found = [r for r in records if r.get("thread_name") == "test-bg-crash"]
    assert len(found) >= 1
    assert "crash in bg thread" in found[0]["exc_message"]
    assert found[0]["exc_type"] == "RuntimeError"
    assert results == ["started"]


def test_background_thread_normal_completion():
    """A normal background thread runs and is cleaned up from registry."""
    marker = []

    def worker():
        marker.append(1)

    thread = start_background_thread(name="test-bg-ok", target=worker, owner="test-bg-ok")
    thread.join(timeout=2.0)
    assert marker == [1]
    time.sleep(0.05)
    tasks = list_background_tasks()
    matching = [t for t in tasks if t.name == "test-bg-ok"]
    assert len(matching) == 0
