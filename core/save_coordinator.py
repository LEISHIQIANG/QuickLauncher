"""Save coordination service.

Extracted from :class:`core.data_manager.DataManager` in 1.6.3.8 to
isolate the save-scheduling / debouncing / history-annotation pipeline.
The class takes a reference to the owning DataManager and reads/writes
the save-related private attributes:

* ``_save_lock`` / ``_write_lock`` — threading primitives
* ``_save_timer`` / ``_save_pending`` / ``_save_delay`` — debounce state
* ``_batch_depth`` / ``_batch_dirty`` / ``_batch_force_immediate`` —
  batched-write state
* ``_runtime_revision`` / ``_last_saved_data_dict`` —
  ``_config_status`` / ``_pending_history_action`` /
  ``_pending_history_summary`` / ``_suppress_next_history`` — history
* ``data_file`` / ``data`` — payload source

Public API stays on :class:`DataManager`; this class is internal and may be
called directly by tests.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config_validation import validate_app_data
from .import_security import has_report_warnings, new_import_report

if TYPE_CHECKING:
    from .data_manager import DataManager

logger = logging.getLogger(__name__)

_HISTORY_DEFAULT = "\u914d\u7f6e\u53d8\u66f4"


class SaveCoordinator:
    """Coordinate debounced / batched / atomic writes to ``data.json``."""

    def __init__(self, dm: DataManager) -> None:
        self._dm = dm

    # ── public save lifecycle ──────────────────────────────────────

    def save(self, immediate: bool = False) -> bool:
        """Schedule or perform a save depending on batch state and ``immediate``."""
        dm = self._dm
        with dm._save_lock:
            dm._runtime_revision += 1
            if dm._batch_depth > 0:
                dm._save_pending = True
                dm._batch_dirty = True
                if immediate:
                    dm._batch_force_immediate = True
                return True

        if immediate:
            return self._do_save()

        with dm._save_lock:
            dm._save_pending = True
            if dm._save_timer is None:
                scheduler = dm._get_save_scheduler()
                scheduler.schedule(self._delayed_save)
                dm._save_timer = scheduler.current_timer  # type: ignore[assignment]
        return True

    def shutdown(self, timeout: float = 3.0) -> None:
        """Flush pending saves and cancel timers before application exit.

        Call this once during application teardown to ensure no data is lost
        from the delayed-save debounce window.
        """
        dm = self._dm
        should_save = False
        with dm._save_lock:
            if dm._save_pending:
                dm._save_pending = False
                should_save = True
            self._cancel_scheduled_save_locked()
        if should_save:
            try:
                self._do_save()
            except Exception as exc:
                logger.error("shutdown flush save failed: %s", exc, exc_info=True)

    def flush_pending_save(self) -> None:
        dm = self._dm
        should_save = False
        with dm._save_lock:
            self._cancel_scheduled_save_locked()
            if dm._save_pending:
                dm._save_pending = False
                should_save = True
        if should_save:
            # Forward via dm so test mocks on ``dm._do_save`` still work.
            dm._do_save()

    @contextmanager
    def batch_update(self, immediate: bool = False):
        """Batch multiple writes into a single save at context exit."""
        dm = self._dm
        with dm._save_lock:
            dm._batch_depth += 1
            if immediate:
                dm._batch_force_immediate = True

        try:
            yield dm
        except Exception:
            # Don't save partial changes on exception — reset all dirty flags
            with dm._save_lock:
                dm._batch_dirty = False
                dm._batch_force_immediate = False
                dm._save_pending = False
                self._cancel_scheduled_save_locked()
            raise
        finally:
            should_flush = False
            flush_immediately = False
            with dm._save_lock:
                if dm._batch_depth > 0:
                    dm._batch_depth -= 1
                assert dm._batch_depth >= 0, "batch_update depth underflow"

                if dm._batch_depth == 0:
                    if dm._save_pending or dm._batch_dirty:
                        should_flush = True
                        flush_immediately = dm._batch_force_immediate
                        self._cancel_scheduled_save_locked()
                        dm._save_pending = False

                    dm._batch_dirty = False
                    dm._batch_force_immediate = False

            if should_flush:
                if flush_immediately:
                    # Forward via dm so test mocks on ``dm._do_save`` still work.
                    dm._do_save()
                else:
                    # Forward via dm so test mocks on ``dm.save`` still work.
                    dm.save(immediate=False)

    # ── history / status helpers ───────────────────────────────────

    def mark_history(self, action: str, summary: str = "") -> None:
        dm = self._dm
        dm._pending_history_action = action or _HISTORY_DEFAULT
        dm._pending_history_summary = summary or ""

    def get_config_status(self) -> dict:
        """Return latest configuration load/save validation status."""
        dm = self._dm
        with dm._save_lock:
            status: dict[str, Any] = dict(getattr(dm, "_config_status", {}) or {})
            report = dm.get_recovery_report()
            if report:
                status["recovery"] = report
            try:
                status["current_issues"] = validate_app_data(dm.data)
            except Exception as exc:
                status["current_issues"] = [str(exc)]
                status["status"] = "error"
            return status

    def reset_import_report(self) -> dict:
        dm = self._dm
        dm._last_import_report = new_import_report()
        return dm._last_import_report

    def get_last_import_report(self) -> dict:
        dm = self._dm
        report = getattr(dm, "_last_import_report", None) or new_import_report()
        return {
            "dry_run": bool(report.get("dry_run", False)),
            "mode": str(report.get("mode", "") or ""),
            "skipped_files": list(report.get("skipped_files", [])),
            "skipped_settings": list(report.get("skipped_settings", [])),
            "warnings": list(report.get("warnings", [])),
            "imported_items": int(report.get("imported_items", 0) or 0),
            "has_warnings": has_report_warnings(report),
        }

    # ── private helpers ────────────────────────────────────────────

    def _delayed_save(self) -> None:
        dm = self._dm
        should_save = False
        with dm._save_lock:
            dm._save_timer = None
            if dm._save_pending:
                dm._save_pending = False
                should_save = True

        if should_save:
            self._do_save()

    def _cancel_scheduled_save_locked(self) -> None:
        dm = self._dm
        scheduler = getattr(dm, "save_scheduler", None)
        scheduler_timer = scheduler.current_timer if scheduler is not None else None
        timer = getattr(dm, "_save_timer", None)
        dm._save_timer = None
        if scheduler is not None:
            scheduler.cancel()
        if timer is not None and timer is not scheduler_timer:
            timer.cancel()

    def _do_save(self) -> bool:
        """Save data to disk atomically with lock splitting."""
        dm = self._dm
        with dm._save_lock:
            try:
                payload = self._serialize_data()
                next_data_dict = json.loads(payload)
                previous_data_dict = dm._last_saved_data_dict
                suppress_history = bool(dm._suppress_next_history)
                history_action = dm._pending_history_action
                history_summary = dm._pending_history_summary
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.error("serialize data failed: %s", e)
                return False

        write_success = False
        with dm._write_lock:
            temp_file = dm.data_file.with_name(f"{dm.data_file.stem}.{uuid.uuid4().hex}.tmp")
            try:
                self._create_auto_backup()

                with open(temp_file, "w", encoding="utf-8") as f:
                    f.write(payload)

                dm._replace_data_file(temp_file)
                write_success = True

            except OSError as e:
                logger.error("save data failed: %s", e)
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except OSError as cleanup_error:
                        logger.debug("cleanup temp file failed: %s", cleanup_error)

        if write_success:
            with dm._save_lock:
                if suppress_history:
                    dm._suppress_next_history = False
                elif previous_data_dict and previous_data_dict != next_data_dict:
                    history = getattr(dm, "history_manager", None)
                    if history is not None:
                        history.record_snapshot(
                            previous_data_dict,
                            action=history_action,
                            summary=history_summary,
                        )
                    dm._pending_history_action = _HISTORY_DEFAULT
                    dm._pending_history_summary = ""
                dm._last_saved_data_dict = next_data_dict
                dm._config_status = {"status": "ok", "source": str(dm.data_file), "issues": []}
        return write_success

    def _replace_data_file(self, temp_file: Path) -> None:
        # Forward via dm so tests can patch ``dm._replace_data_file``.
        self._dm._replace_data_file(temp_file)

    def _create_auto_backup(self) -> None:
        # Forward via dm so tests can patch ``dm._create_auto_backup``.
        self._dm._create_auto_backup()

    def _serialize_data(self) -> str:
        return self._dm._get_config_store().serialize_data(self._main_data_dict())

    def _main_data_dict(self) -> dict:
        dm = self._dm
        data_dict = dm.data.to_dict()
        folders = data_dict.get("folders", [])
        if isinstance(folders, list):
            data_dict["folders"] = [
                folder
                for folder in folders
                if not bool(folder.get("is_icon_repo", False)) and folder.get("id") != "icon_repo"
            ]
        return data_dict


__all__ = ["SaveCoordinator"]
