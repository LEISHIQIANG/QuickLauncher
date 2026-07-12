"""Regression tests for ``core.save_coordinator.SaveCoordinator``.

These tests cover Bug #1 of the 1.6.3.7 audit:
``SaveCoordinator._do_save`` previously only caught ``OSError`` from the
atomic write path, which meant any non-``OSError`` exception (e.g.
``PermissionError`` from ``os.fsync``, a ``shutil.Error``, or an exception
from an extension / plugin hook) left the ``data.<uuid>.tmp`` file
leaked on disk and silently terminated the background save thread.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from core.data_models import AppData
from core.save_coordinator import SaveCoordinator


def _make_manager(tmp_path: Path) -> object:
    """Build a minimal ``DataManager``-shaped object for ``SaveCoordinator``."""
    manager = object.__new__(type("_DM", (), {}))
    manager.data = AppData()
    manager._save_lock = threading.RLock()
    manager._write_lock = threading.Lock()
    manager._batch_depth = 0
    manager._batch_dirty = False
    manager._batch_force_immediate = False
    manager._save_pending = False
    manager._save_timer = None
    manager._runtime_revision = 0
    manager._pending_history_action = "配置变更"
    manager._pending_history_summary = ""
    manager._suppress_next_history = False
    manager._last_saved_data_dict = None
    manager.history_manager = None
    manager.app_dir = tmp_path / "app"
    manager.data_file = manager.app_dir / "data.json"
    manager._config_status = {"status": "unknown", "source": "", "issues": []}
    manager.app_dir.mkdir(parents=True, exist_ok=True)
    manager.data_file.write_text("{}", encoding="utf-8")

    from core.config_services import ConfigDataStore

    def _get_config_store():
        service = getattr(manager, "config_store", None)
        if service is None:
            service = ConfigDataStore(manager.data_file)
            manager.config_store = service
        service.configure(manager.data_file)
        return service

    def _create_auto_backup():
        return None

    manager._get_config_store = _get_config_store  # type: ignore[attr-defined]
    manager._create_auto_backup = _create_auto_backup  # type: ignore[attr-defined]
    return manager


def test_do_save_cleans_temp_file_on_non_oserror_exception(tmp_path):
    """Non-``OSError`` exceptions must not leak the temp file on disk."""
    manager = _make_manager(tmp_path)
    coordinator = SaveCoordinator(manager)  # type: ignore[arg-type]

    def _explode(temp_path):
        raise RuntimeError("synthetic non-OSError failure from replace step")

    manager._replace_data_file = _explode  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError, match="synthetic"):
        coordinator._do_save()

    leftover = [p for p in manager.app_dir.iterdir() if p.suffix == ".tmp"]
    assert leftover == [], f"temp files leaked: {leftover}"


def test_do_save_marks_status_error_on_non_oserror_exception(tmp_path):
    """``_config_status`` must be updated to error on non-``OSError`` failures."""
    manager = _make_manager(tmp_path)
    coordinator = SaveCoordinator(manager)  # type: ignore[arg-type]

    def _explode(temp_path):
        raise RuntimeError("synthetic failure")

    manager._replace_data_file = _explode  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError):
        coordinator._do_save()

    status = manager._config_status
    assert status["status"] == "error"
    assert any("synthetic failure" in issue for issue in status["issues"])


def test_do_save_cleans_temp_file_on_oserror_exception(tmp_path):
    """``OSError`` path must still clean up the temp file (regression guard).

    Historically, ``OSError`` is swallowed (return ``False``) so that
    ``SaveCoordinator.save`` and the delayed-save retry loop can inspect
    the boolean result; the fix must keep that contract while making
    sure the temp file is still removed.
    """
    manager = _make_manager(tmp_path)
    coordinator = SaveCoordinator(manager)  # type: ignore[arg-type]

    def _explode_oserror(temp_path):
        raise OSError("synthetic OSError")

    manager._replace_data_file = _explode_oserror  # type: ignore[attr-defined]

    result = coordinator._do_save()
    assert result is False

    leftover = [p for p in manager.app_dir.iterdir() if p.suffix == ".tmp"]
    assert leftover == [], f"temp files leaked: {leftover}"
