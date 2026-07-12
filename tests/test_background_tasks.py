"""Tests for core.background_tasks — lightweight thread registry."""

from __future__ import annotations

import threading
import time

from core.background_tasks import (
    BackgroundTaskInfo,
    join_background_tasks,
    list_background_tasks,
    register_background_thread,
    start_background_thread,
)


def test_register_and_unregister():
    done = threading.Event()

    def worker():
        done.set()

    thread = threading.Thread(target=worker, daemon=True, name="test-register")
    register_background_thread(thread, owner="test")
    thread.start()
    assert done.wait(1.0)
    thread.join(timeout=1.0)

    tasks = list_background_tasks()
    matching = [t for t in tasks if t.name == "test-register"]
    assert len(matching) <= 1


def test_start_background_thread_basic():
    """A background thread runs and completes."""
    results = []

    def worker():
        results.append(42)

    thread = start_background_thread(name="test-basic", target=worker, owner="test")
    thread.join(timeout=1.0)
    assert results == [42]


def test_start_background_thread_with_args():
    results = []

    def worker(a, b, c=3):
        results.append(a + b + c)

    thread = start_background_thread(name="test-args", target=worker, args=(1, 2), kwargs={"c": 3}, owner="test")
    thread.join(timeout=1.0)
    assert results == [6]


def test_list_background_tasks():
    done = threading.Event()

    def worker():
        done.wait(0.5)

    thread = start_background_thread(name="test-list", target=worker, owner="test-list-owner")
    try:
        tasks = list_background_tasks()
        matching = [t for t in tasks if t.owner == "test-list-owner"]
        assert len(matching) >= 1
        task = matching[0]
        assert task.name == "test-list"
        assert task.owner == "test-list-owner"
        assert isinstance(task.alive, bool)
        assert isinstance(task.started_at, float)
        assert task.daemon is True
    finally:
        done.set()
        thread.join(timeout=1.0)


def test_list_cleans_stale_entries():
    """Stale (non-alive) threads are removed from the registry on list."""
    done = threading.Event()

    def worker():
        done.wait(0.1)

    thread = start_background_thread(name="test-stale", target=worker, owner="test")
    done.set()
    thread.join(timeout=1.0)

    # Give the thread time to fully terminate
    time.sleep(0.05)

    # List should clean the stale entry
    tasks = list_background_tasks()
    matching = [t for t in tasks if t.name == "test-stale"]
    assert len(matching) == 0


def test_join_background_tasks_by_owner():
    """join_background_tasks waits for tasks of a specific owner."""
    started = threading.Event()
    can_finish = threading.Event()

    def worker():
        started.set()
        can_finish.wait(1.0)

    thread = start_background_thread(name="test-join", target=worker, owner="join-owner")
    assert started.wait(1.0), "thread did not start"
    can_finish.set()
    remaining = join_background_tasks("join-owner", timeout=2.0)
    assert isinstance(remaining, list)
    # The task should have completed
    thread.join(timeout=0.5)
    assert not thread.is_alive()


def test_start_background_thread_daemon_default():
    """By default, threads are daemon threads."""
    results = []

    def worker():
        results.append(True)

    thread = start_background_thread(name="test-daemon", target=worker)
    assert thread.daemon is True
    thread.join(timeout=1.0)


def test_start_background_thread_non_daemon():
    results = []

    def worker():
        results.append(True)

    thread = start_background_thread(name="test-nondaemon", target=worker, daemon=False)
    assert thread.daemon is False
    thread.join(timeout=1.0)


def test_background_task_info_dataclass():
    info = BackgroundTaskInfo(
        name="test",
        owner="test-owner",
        started_at=100.0,
        daemon=True,
        alive=True,
    )
    assert info.name == "test"
    assert info.owner == "test-owner"
    assert info.started_at == 100.0
    assert info.daemon is True
    assert info.alive is True
