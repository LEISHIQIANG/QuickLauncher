from __future__ import annotations

import threading

import pytest

from core.executor_manager import COMMAND_EXECUTOR, ExecutorManager, ManagedExecutor


def test_manager_reuses_named_executor_and_shutdown_is_idempotent():
    manager = ExecutorManager()
    first = manager.get(COMMAND_EXECUTOR)
    second = manager.get(COMMAND_EXECUTOR)

    assert first is second
    assert first.submit(lambda: 42).result(timeout=1) == 42
    assert manager.shutdown_all(timeout=1.0) == {}
    assert manager.shutdown_all(timeout=1.0) == {}

    with pytest.raises(RuntimeError, match="shut down"):
        manager.get(COMMAND_EXECUTOR)
    with pytest.raises(RuntimeError, match="shut down"):
        first.submit(lambda: None)


def test_manager_cancels_cooperative_work_before_shutdown():
    manager = ExecutorManager()
    executor = manager.get(COMMAND_EXECUTOR)
    started = threading.Event()
    release = threading.Event()

    def worker():
        started.set()
        release.wait(1.0)

    future = executor.submit(worker)
    assert started.wait(1.0)
    release.set()

    assert manager.shutdown_all(timeout=1.0) == {}
    assert future.done()


def test_shutdown_with_queued_future_does_not_deadlock():
    executor = ManagedExecutor("single", 1, "single")
    started = threading.Event()
    release = threading.Event()

    def worker():
        started.set()
        release.wait(1.0)

    running = executor.submit(worker)
    queued = executor.submit(lambda: None)
    assert started.wait(1.0)

    shutdown_finished = threading.Event()

    def shutdown():
        executor.drain(timeout=0.05)
        shutdown_finished.set()

    thread = threading.Thread(target=shutdown, daemon=True)
    thread.start()
    assert shutdown_finished.wait(0.5), "queued-future cancellation deadlocked executor shutdown"
    assert queued.cancelled()
    release.set()
    assert running.result(timeout=1.0) is None
