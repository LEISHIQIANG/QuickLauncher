from __future__ import annotations

import threading

import pytest

from application.errors import RevisionConflict
from application.state import StateStore


def test_snapshot_is_deeply_immutable_and_detached():
    source = {"settings": {"theme": "dark"}, "items": [1, 2]}
    store = StateStore(source)
    snapshot = store.snapshot()
    source["settings"]["theme"] = "light"

    assert snapshot.state["settings"]["theme"] == "dark"
    assert snapshot.state["items"] == (1, 2)
    with pytest.raises(TypeError):
        snapshot.state["new"] = True


def test_submit_requires_expected_revision_and_rolls_forward_once():
    store = StateStore({"count": 1})

    updated = store.submit(lambda state: {**state, "count": state["count"] + 1}, expected_revision=0)

    assert updated.revision == 1
    assert updated.state["count"] == 2
    with pytest.raises(RevisionConflict) as exc_info:
        store.submit(lambda state: state, expected_revision=0)
    assert exc_info.value.actual == 1


def test_failed_command_does_not_change_state_or_revision():
    store = StateStore({"value": "before"})

    def fail(state):
        state["value"] = "partial"
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        store.submit(fail, expected_revision=0)
    assert store.snapshot().revision == 0
    assert store.snapshot().state["value"] == "before"


def test_concurrent_writers_cannot_commit_same_revision_twice():
    store = StateStore({"wins": 0})
    barrier = threading.Barrier(3)
    outcomes: list[str] = []

    def write():
        barrier.wait()
        try:
            store.submit(lambda state: {"wins": state["wins"] + 1}, expected_revision=0)
            outcomes.append("committed")
        except RevisionConflict:
            outcomes.append("conflict")

    threads = [threading.Thread(target=write) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["committed", "conflict"]
    assert store.snapshot().state["wins"] == 1
