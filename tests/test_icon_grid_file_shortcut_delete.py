"""Regression tests for the file-shortcut delete freeze/crash.

Background
----------
When a FILE/FOLDER shortcut is deleted from the configuration panel, the
icon loader worker is on the slow ``_extract_win32`` path (``SHGetFileInfo``).
If the user deletes again before the previous worker has finished, the
old code's ``self._icon_thread.finished.connect(self._icon_thread.deleteLater)``
combined with rapid ``load_folder`` re-creation could deadlock or
segfault. The tests below pin down:

1. ``_start_async_icon_load`` no longer schedules the QThread to
   ``deleteLater`` itself from its own ``finished`` signal.
2. Same guard for ``_start_favicon_fetch_worker``.
3. Rapid back-to-back ``_start_async_icon_load`` calls (the operation
   that happens on every delete -> ``load_folder`` -> icon reload) leave
   the connection state consistent.
4. ``_safe_reload_folder`` does not call ``load_folder`` once the user
   has switched folders.
"""

from __future__ import annotations

import pytest

import ui.config_window.icon_grid as grid_mod
from core import ShortcutItem, ShortcutType

pytestmark = pytest.mark.ui


class _ScriptedStatusDialog:
    """Stub for SimpleStatusDialog used by _batch_fetch_icons."""

    def __init__(self, title="", parent=None):
        self.texts: list[str] = []

    def update_text(self, text):
        self.texts.append(text)

    def show(self):
        return None

    def close(self):
        return None

    def isVisible(self):
        return True


def _make_file_shortcut(sid: str, target: str = "C:/dummy.exe") -> ShortcutItem:
    return ShortcutItem(
        id=sid,
        name=sid,
        type=ShortcutType.FILE,
        target_path=target,
        icon_path="",
        order=0,
        enabled=True,
    )


def _stop_grid_thread(grid, thread_attr: str, worker_attr: str) -> None:
    worker = getattr(grid, worker_attr, None)
    thread = getattr(grid, thread_attr, None)
    if worker is not None and callable(getattr(worker, "cancel", None)):
        worker.cancel()
    if thread is not None:
        thread.quit()
        thread.wait(1000)
        try:
            if worker is not None:
                worker.deleteLater()
            thread.deleteLater()
        except RuntimeError:
            pass
    setattr(grid, thread_attr, None)
    setattr(grid, worker_attr, None)


def _new_icon_grid_for_thread_tests() -> grid_mod.IconGrid:
    grid = grid_mod.IconGrid.__new__(grid_mod.IconGrid)
    grid._icon_load_generation = 0
    grid._icon_worker = None
    grid._icon_thread = None
    grid._stop_icon_thread = lambda: _stop_grid_thread(grid, "_icon_thread", "_icon_worker")
    grid._favicon_fetch_generation = 0
    grid._favicon_fetch_worker = None
    grid._favicon_fetch_thread = None
    grid._favicon_fetch_shortcuts = {}
    grid._favicon_fetch_success_count = 0
    grid._favicon_fetch_status_dialog = None
    grid._stop_favicon_fetch_thread = lambda: _stop_grid_thread(grid, "_favicon_fetch_thread", "_favicon_fetch_worker")
    return grid


def test_start_async_icon_load_connection_count_is_two(qapp, monkeypatch):
    """``_start_async_icon_load`` must connect only 2 slots to
    ``thread.finished`` (the cleanup lambda + worker.deleteLater).

    The old code connected 3 slots (also ``thread.deleteLater``), which
    is the regression we are guarding against.
    """
    grid = _new_icon_grid_for_thread_tests()
    monkeypatch.setattr(grid_mod._IconLoadWorker, "run", lambda self: None)
    grid._start_async_icon_load([("s1", "", "C:/prog.exe", 24, ShortcutType.FILE)])

    try:
        thread = grid._icon_thread
        assert thread is not None
        receiver_count = thread.receivers(thread.finished)
        assert receiver_count == 2, (
            f"expected 2 receivers on thread.finished (cleanup lambda + worker.deleteLater), "
            f"got {receiver_count}. The dangerous thread.deleteLater self-connection is back."
        )
    finally:
        grid._stop_icon_thread()


def test_start_favicon_fetch_worker_connection_count_is_two(qapp, monkeypatch):
    """Same regression guard for the favicon fetch worker."""
    grid = _new_icon_grid_for_thread_tests()
    monkeypatch.setattr(grid_mod, "SimpleStatusDialog", _ScriptedStatusDialog)
    monkeypatch.setattr(grid_mod._BatchFaviconFetchWorker, "run", lambda self: None)

    grid._start_favicon_fetch_worker(
        tasks=[("s1", "S1", "https://example.com")],
        status_dialog=_ScriptedStatusDialog(),
        shortcuts={"s1": _make_file_shortcut("s1")},
    )

    try:
        thread = grid._favicon_fetch_thread
        assert thread is not None
        receiver_count = thread.receivers(thread.finished)
        assert receiver_count == 2, f"expected 2 receivers on thread.finished, got {receiver_count}"
    finally:
        try:
            if grid._favicon_fetch_thread is not None:
                grid._favicon_fetch_thread.quit()
                grid._favicon_fetch_thread.wait(1000)
        except Exception:
            pass
        grid._stop_favicon_fetch_thread()


def test_rapid_reload_leaves_connection_state_consistent(qapp, monkeypatch):
    """Simulate the exact delete -> load_folder -> _start_async_icon_load
    sequence 5 times in a row. The dangerous self-deleteLater connection
    must NEVER appear on any of the created threads, and the live thread
    (if any) must have at most 2 receivers on ``finished``.
    """
    grid = _new_icon_grid_for_thread_tests()
    monkeypatch.setattr(grid_mod._IconLoadWorker, "run", lambda self: None)
    try:
        for i in range(5):
            grid._start_async_icon_load([(f"s{i}", "", f"C:/prog{i}.exe", 24, ShortcutType.FILE)])
            # The new code's contract: every freshly-created thread has
            # exactly 2 finished-receivers (cleanup lambda + worker
            # deleteLater), and 0 self-references.
            current = grid._icon_thread
            assert current is not None
            assert current.receivers(current.finished) == 2, (
                f"iteration {i}: expected 2 finished-receivers, got " f"{current.receivers(current.finished)}"
            )
    finally:
        grid._stop_icon_thread()


def test_safe_reload_folder_guards_against_orphaned_load(qapp):
    """``_safe_reload_folder`` must not call ``load_folder`` if the user
    has already switched to another folder by the time the deferred
    timer fires (the popup's ``deleteLater`` may have changed state).
    """
    from ui.config_window.main_window import ConfigWindow

    cfg = ConfigWindow.__new__(ConfigWindow)
    loads = []

    class _Grid:
        def __init__(self):
            self.current_folder_id = "f1"

        def load_folder(self, fid):
            loads.append((id(self), fid))

    cfg.icon_grid = _Grid()

    cfg._safe_reload_folder("f1")
    assert loads == [(id(cfg.icon_grid), "f1")]

    cfg.icon_grid.current_folder_id = "f2"
    cfg._safe_reload_folder("f1")
    assert loads == [(id(cfg.icon_grid), "f1")]
