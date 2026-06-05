import logging
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import MagicMock

import pytest

from core.folder_watcher import (
    WATCHDOG_AVAILABLE,
    FolderChangeHandler,
    FolderWatcherManager,
    get_watcher_manager,
    shutdown_watcher_manager,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FolderChangeHandler tests
# ---------------------------------------------------------------------------


class TestFolderChangeHandler:
    def test_init_stores_attributes(self):
        cb = MagicMock()
        handler = FolderChangeHandler("folder1", cb)
        assert handler.folder_id == "folder1"
        assert handler.callback is cb
        assert handler._last_trigger_time == 0.0
        assert handler._debounce_seconds == 2.0

    def test_first_trigger_calls_callback(self):
        cb = MagicMock()
        handler = FolderChangeHandler("f1", cb)
        handler._trigger_sync()
        cb.assert_called_once_with("f1")

    def test_debounce_prevents_second_trigger(self):
        cb = MagicMock()
        handler = FolderChangeHandler("f1", cb)
        handler._trigger_sync()
        assert cb.call_count == 1
        # Immediate second call should be debounced
        handler._trigger_sync()
        assert cb.call_count == 1

    def test_trigger_after_debounce_period(self):
        cb = MagicMock()
        handler = FolderChangeHandler("f1", cb)
        handler._debounce_seconds = 0.0  # disable debounce
        handler._trigger_sync()
        handler._trigger_sync()
        assert cb.call_count == 2

    def test_trigger_with_time_gap(self):
        cb = MagicMock()
        handler = FolderChangeHandler("f1", cb)
        handler._debounce_seconds = 0.05
        handler._trigger_sync()
        assert cb.call_count == 1
        time.sleep(0.07)
        handler._trigger_sync()
        assert cb.call_count == 2

    def test_callback_exception_does_not_propagate(self):
        cb = MagicMock(side_effect=RuntimeError("boom"))
        handler = FolderChangeHandler("f1", cb)
        # Should not raise
        handler._trigger_sync()
        cb.assert_called_once_with("f1")

    def test_on_created_triggers(self):
        cb = MagicMock()
        handler = FolderChangeHandler("f1", cb)
        event = MagicMock()
        handler.on_created(event)
        cb.assert_called_once_with("f1")

    def test_on_deleted_triggers(self):
        cb = MagicMock()
        handler = FolderChangeHandler("f1", cb)
        event = MagicMock()
        handler.on_deleted(event)
        cb.assert_called_once_with("f1")

    def test_on_modified_triggers_for_files(self):
        cb = MagicMock()
        handler = FolderChangeHandler("f1", cb)
        event = MagicMock()
        event.is_directory = False
        handler.on_modified(event)
        cb.assert_called_once_with("f1")

    def test_on_modified_skips_directories(self):
        cb = MagicMock()
        handler = FolderChangeHandler("f1", cb)
        event = MagicMock()
        event.is_directory = True
        handler.on_modified(event)
        cb.assert_not_called()

    def test_on_moved_triggers(self):
        cb = MagicMock()
        handler = FolderChangeHandler("f1", cb)
        event = MagicMock()
        handler.on_moved(event)
        cb.assert_called_once_with("f1")


# ---------------------------------------------------------------------------
# FolderWatcherManager tests
# ---------------------------------------------------------------------------


@pytest.fixture
def manager():
    """Create a real FolderWatcherManager and ensure cleanup."""
    mgr = FolderWatcherManager()
    yield mgr
    try:
        mgr.stop_all()
    except Exception as exc:
        logger.debug("停止监视器失败: %s", exc, exc_info=True)
        pass


class TestFolderWatcherManagerInit:
    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_init_creates_running_observer(self, manager):
        assert manager.observer is not None
        assert manager.observer.is_alive()

    def test_init_watches_empty(self, manager):
        assert manager.watches == {}


class TestFolderWatcherManagerStartWatch:
    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_start_watch_schedules_on_real_dir(self, manager, tmp_path):
        cb = MagicMock()
        manager.start_watch("f1", str(tmp_path), cb)
        assert "f1" in manager.watches

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_start_watch_nonexistent_path_skipped(self, manager, tmp_path):
        bogus = tmp_path / "does_not_exist_12345"
        cb = MagicMock()
        manager.start_watch("f1", str(bogus), cb)
        assert "f1" not in manager.watches

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_start_watch_file_path_skipped(self, manager, tmp_path):
        f = tmp_path / "afile.txt"
        f.write_text("hi")
        cb = MagicMock()
        manager.start_watch("f1", str(f), cb)
        assert "f1" not in manager.watches

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_start_watch_replaces_existing(self, manager, tmp_path):
        cb = MagicMock()
        manager.start_watch("f1", str(tmp_path), cb)
        manager.start_watch("f1", str(tmp_path), cb)
        assert "f1" in manager.watches
        # The old watch should have been unscheduled; the new one is different object
        # (we can at least verify it did not error and key exists)

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_start_watch_multiple_ids(self, manager, tmp_path):
        d1 = tmp_path / "d1"
        d1.mkdir()
        d2 = tmp_path / "d2"
        d2.mkdir()
        cb = MagicMock()
        manager.start_watch("f1", str(d1), cb)
        manager.start_watch("f2", str(d2), cb)
        assert "f1" in manager.watches
        assert "f2" in manager.watches


class TestFolderWatcherManagerStopWatch:
    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_stop_watch_existing(self, manager, tmp_path):
        cb = MagicMock()
        manager.start_watch("f1", str(tmp_path), cb)
        assert "f1" in manager.watches
        manager.stop_watch("f1")
        assert "f1" not in manager.watches

    def test_stop_watch_nonexistent_no_error(self, manager):
        manager.stop_watch("nonexistent_id")  # should not raise


class TestFolderWatcherManagerStopAll:
    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_stop_all_clears_state(self, tmp_path):
        mgr = FolderWatcherManager()
        cb = MagicMock()
        mgr.start_watch("f1", str(tmp_path), cb)
        mgr.stop_all()
        assert mgr.observer is None
        assert mgr.watches == {}

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_stop_all_is_idempotent(self):
        mgr = FolderWatcherManager()
        mgr.stop_all()
        mgr.stop_all()  # second call should not raise

    def test_stop_all_retries_stuck_observer(self):
        mgr = FolderWatcherManager()

        class StuckObserver:
            def __init__(self):
                self.join_timeouts = []
                self.unscheduled = False

            def stop(self):
                pass

            def join(self, timeout=None):
                self.join_timeouts.append(timeout)

            def is_alive(self):
                return True

            def unschedule_all(self):
                self.unscheduled = True

        observer = StuckObserver()
        mgr.observer = observer
        mgr.watches["f1"] = object()

        mgr.stop_all()

        assert observer.join_timeouts == [5.0, 2.0]
        assert observer.unscheduled is True
        assert mgr.observer is None
        assert mgr.watches == {}


def test_observer_is_daemon_when_watchdog_available(monkeypatch):
    import core.folder_watcher as folder_watcher

    class FakeObserver:
        def __init__(self):
            self.daemon = False
            self.started = False

        def start(self):
            self.started = True

    monkeypatch.setattr(folder_watcher, "WATCHDOG_AVAILABLE", True)
    monkeypatch.setattr(folder_watcher, "Observer", FakeObserver)

    mgr = folder_watcher.FolderWatcherManager()

    assert mgr.observer.daemon is True
    assert mgr.observer.started is True


# ---------------------------------------------------------------------------
# get_watcher_manager singleton tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=False)
def _reset_global():
    """Reset the module-level singleton around each test that needs it."""
    import core.folder_watcher as fwm

    original = fwm._watcher_manager
    fwm._watcher_manager = None
    yield
    # cleanup
    fwm._watcher_manager = None
    if original is not None:
        try:
            original.stop_all()
        except Exception as exc:
            logger.debug("停止原始监视器失败: %s", exc, exc_info=True)
            pass


class TestGetWatcherManager:
    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_returns_same_instance(self, _reset_global):
        a = get_watcher_manager()
        b = get_watcher_manager()
        assert a is b
        a.stop_all()

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_returns_folder_watcher_manager(self, _reset_global):
        mgr = get_watcher_manager()
        assert isinstance(mgr, FolderWatcherManager)
        mgr.stop_all()

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_thread_safety(self, _reset_global):
        """Multiple threads calling get_watcher_manager concurrently get the same instance."""
        results = [None] * 10

        def target(i):
            results[i] = get_watcher_manager()

        threads = [threading.Thread(target=target, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        first = results[0]
        assert first is not None
        for r in results[1:]:
            assert r is first
        first.stop_all()


# ---------------------------------------------------------------------------
# shutdown_watcher_manager tests
# ---------------------------------------------------------------------------


class TestShutdownWatcherManager:
    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_shutdown_clears_singleton(self, _reset_global):
        mgr = get_watcher_manager()
        assert mgr is not None
        shutdown_watcher_manager()
        import core.folder_watcher as fwm

        assert fwm._watcher_manager is None

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_shutdown_allows_new_singleton(self, _reset_global):
        first = get_watcher_manager()
        shutdown_watcher_manager()
        second = get_watcher_manager()
        assert second is not first
        second.stop_all()

    def test_shutdown_when_none_is_safe(self, _reset_global):
        # Should not raise even if no manager was created
        shutdown_watcher_manager()
