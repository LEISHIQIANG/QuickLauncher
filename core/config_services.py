"""Internal configuration services used behind DataManager's public facade."""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .background_tasks import start_background_thread
from .config_recovery import (
    ConfigRecoveryReport,
    quarantine_bad_config,
    read_recovery_report,
    write_recovery_report,
)
from .config_validation import latest_valid_backup, load_valid_data_file, validate_app_data_dict
from .data_models import AppData
from .import_security import MAX_CONFIG_BYTES, has_zip_entry, read_zip_text

logger = logging.getLogger(__name__)


class ConfigDataStore:
    """Serialize and atomically replace the primary data.json file."""

    def __init__(self, data_file: Path | str):
        self.data_file = Path(data_file)

    def configure(self, data_file: Path | str) -> None:
        self.data_file = Path(data_file)

    def serialize_data(self, data_dict: dict) -> str:
        """Serialize AppData and reject fatal schema problems before writes."""
        issues = validate_app_data_dict(data_dict)
        fatal = {"root_not_object", "folders_not_list"}
        if any(issue in fatal for issue in issues):
            raise ValueError(f"fatal config schema issues: {issues}")
        if issues:
            logger.warning("data manager message: %s", issues)
        return json.dumps(data_dict, ensure_ascii=False, separators=(",", ":"))

    def replace_data_file(self, temp_file: Path | str) -> None:
        """Replace data.json, falling back when Windows denies atomic rename."""
        temp_path = Path(temp_file)
        try:
            os.replace(temp_path, self.data_file)
            return
        except OSError as replace_error:
            logger.debug("atomic data replace failed, using guarded copy fallback: %s", replace_error)

        fallback_backup = self.data_file.with_suffix(".write_backup")
        had_original = self.data_file.exists()
        data_file_intact = False
        try:
            if had_original:
                shutil.copy2(self.data_file, fallback_backup)
            shutil.copyfile(temp_path, self.data_file)
            data_file_intact = True
            try:
                os.remove(temp_path)
            except Exception as cleanup_error:
                logger.debug("cleanup temp file after fallback copy failed: %s", cleanup_error)
        except Exception:
            if had_original and fallback_backup.exists():
                try:
                    shutil.copyfile(fallback_backup, self.data_file)
                    data_file_intact = True
                except Exception as restore_error:
                    logger.error("restore data file after fallback failure failed: %s", restore_error)
            raise
        finally:
            if data_file_intact and fallback_backup.exists():
                try:
                    fallback_backup.unlink()
                except Exception as cleanup_error:
                    logger.debug("cleanup data write backup failed: %s", cleanup_error)


class ConfigBackupService:
    """Manage automatic data.json backups and retention."""

    def __init__(self, auto_backup_dir: Path | str, max_auto_backups: int = 5):
        self.auto_backup_dir = Path(auto_backup_dir)
        self.max_auto_backups = max(0, int(max_auto_backups or 0))

    def configure(self, auto_backup_dir: Path | str, max_auto_backups: int = 5) -> None:
        self.auto_backup_dir = Path(auto_backup_dir)
        self.max_auto_backups = max(0, int(max_auto_backups or 0))

    def create_auto_backup(self, data_file: Path | str) -> Path | None:
        data_file = Path(data_file)
        if not data_file.exists():
            return None

        try:
            self.auto_backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_path = self.auto_backup_dir / f"data_{timestamp}.json"
            shutil.copy2(data_file, backup_path)
            self.prune_auto_backups()
            return backup_path
        except Exception as exc:
            logger.debug("auto backup failed: %s", exc)
            return None

    def list_auto_backups(self) -> list[Path]:
        if not self.auto_backup_dir.exists():
            return []
        try:
            return sorted(
                self.auto_backup_dir.glob("data_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError as exc:
            logger.debug("list auto backups failed: %s", exc)
            return []

    def prune_auto_backups(self) -> None:
        backups = self.list_auto_backups()
        if self.max_auto_backups <= 0:
            stale = backups
        else:
            stale = backups[self.max_auto_backups :]
        for old_backup in stale:
            try:
                old_backup.unlink()
            except Exception as exc:
                logger.debug("delete old auto backup failed %s: %s", old_backup, exc)


@dataclass
class ConfigRecoveryResult:
    """Recovered AppData plus the status/report that should be surfaced."""

    data: AppData
    status: dict
    report: ConfigRecoveryReport


class ConfigRecoveryService:
    """Coordinate recovery reports, quarantine files, and auto-backup recovery."""

    def __init__(self, recovery_dir: Path | str, auto_backup_dir: Path | str, data_file: Path | str):
        self.recovery_dir = Path(recovery_dir)
        self.auto_backup_dir = Path(auto_backup_dir)
        self.data_file = Path(data_file)

    def configure(
        self,
        recovery_dir: Path | str,
        auto_backup_dir: Path | str,
        data_file: Path | str,
    ) -> None:
        self.recovery_dir = Path(recovery_dir)
        self.auto_backup_dir = Path(auto_backup_dir)
        self.data_file = Path(data_file)

    def write_report(self, report: ConfigRecoveryReport) -> None:
        write_recovery_report(self.recovery_dir, report)
        if report.status not in ("ok",):
            try:
                from .event_log import log_event

                log_event(
                    f"config.{report.status}",
                    f"Config {report.status}: {report.reason}",
                    {"source": report.source_path, "recovered_from": report.recovered_from},
                )
            except Exception:
                logger.debug("记录配置恢复事件失败", exc_info=True)

    def read_report(self) -> ConfigRecoveryReport | None:
        return read_recovery_report(self.recovery_dir)

    def report_dict(self) -> dict:
        report = self.read_report()
        return report.to_dict() if report else {}

    def quarantine_bad_config(self) -> Path | None:
        return quarantine_bad_config(self.data_file, self.recovery_dir)

    def recover_from_latest_backup(
        self, reason: str = "", quarantined_path: Path | str | None = None
    ) -> ConfigRecoveryResult | None:
        """Load the newest valid auto backup and try to persist it over data.json."""
        backup_path = latest_valid_backup(self.auto_backup_dir)
        if not backup_path:
            return None

        loaded, issues = load_valid_data_file(backup_path)
        status = "recovered"
        recovery_issues = ["recovered_from_auto_backup"] + issues
        try:
            shutil.copy2(backup_path, self.data_file)
        except Exception as copy_error:
            status = "recovered_memory_only"
            recovery_issues.append(f"persist_failed:{copy_error}")
            logger.warning("data manager message: %s", copy_error)

        report = ConfigRecoveryReport(
            status=status,
            reason=reason or "auto backup recovery",
            source_path=str(self.data_file),
            recovered_from=str(backup_path),
            quarantined_path=str(quarantined_path or ""),
            issues=recovery_issues,
        )
        return ConfigRecoveryResult(
            data=loaded,
            status={
                "status": "warn",
                "source": str(backup_path),
                "issues": recovery_issues,
            },
            report=report,
        )


class ConfigPackageService:
    """Handle shared full-backup import/export package details."""

    EXTRA_CONFIG_FILE_NAMES = ("custom_themes.json", "command_history.json")

    def __init__(self, app_dir: Path | str):
        self.app_dir = Path(app_dir)

    def configure(self, app_dir: Path | str) -> None:
        self.app_dir = Path(app_dir)

    def extra_config_files(self) -> dict[str, Path]:
        return {name: self.app_dir / name for name in self.EXTRA_CONFIG_FILE_NAMES}

    def write_extra_config_files(self, zf) -> None:
        for arc_name, file_path in self.extra_config_files().items():
            if not file_path.exists():
                continue
            try:
                zf.write(file_path, arc_name)
            except Exception as extra_err:
                logger.debug("backup extra config %s failed: %s", arc_name, extra_err)

    def restore_extra_config_files(self, zf, safe_index: dict, report: dict) -> None:
        for arc_name, target_path in self.extra_config_files().items():
            if not has_zip_entry(safe_index, arc_name):
                continue
            try:
                extra_text = read_zip_text(
                    zf,
                    safe_index,
                    arc_name,
                    max_bytes=MAX_CONFIG_BYTES,
                    report=report,
                )
                if extra_text is not None:
                    target_path.write_text(extra_text, encoding="utf-8")
            except Exception as extra_err:
                logger.debug("restore extra config %s failed: %s", arc_name, extra_err)


# ============================================================
# SaveScheduler — debounced delayed-save timer
# ============================================================


class SaveScheduler:
    """Debounce rapid consecutive save() calls into a single disk write.

    Instead of writing to disk on every ``save()`` call, the scheduler starts
    a short-lived registered background task. If another ``save()`` arrives
    before the task fires, the pending write is merged.

    This replaces the inline timer logic that used to live directly inside
    ``DataManager``.
    """

    def __init__(self, delay: float = 0.5, *, owner: str = "save-scheduler"):
        self._delay = max(0.0, float(delay))
        self._owner = owner
        self._timer: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None
        self._pending = False
        self._lock = threading.RLock()

    @property
    def delay(self) -> float:
        return self._delay

    @delay.setter
    def delay(self, value: float) -> None:
        self._delay = max(0.0, float(value))

    @property
    def pending(self) -> bool:
        with self._lock:
            return self._pending

    @property
    def current_timer(self) -> threading.Thread | None:
        with self._lock:
            return self._timer

    def schedule(self, callback) -> None:
        """Mark a save as pending and start (or restart) the debounce timer."""
        with self._lock:
            self._pending = True
            if self._timer is None:
                cancel_event = threading.Event()
                self._cancel_event = cancel_event
                self._timer = start_background_thread(
                    name=f"{self._owner}-debounce",
                    target=self._wait_and_fire,
                    args=(callback, cancel_event),
                    owner=self._owner,
                )

    def _wait_and_fire(self, callback, cancel_event: threading.Event) -> None:
        if cancel_event.wait(self._delay):
            return
        self._fire(callback, cancel_event)

    def _fire(self, callback, cancel_event: threading.Event) -> None:
        should_save = False
        with self._lock:
            if cancel_event is not self._cancel_event:
                return
            self._timer = None
            self._cancel_event = None
            if self._pending:
                self._pending = False
                should_save = True
        if should_save:
            try:
                callback()
            except Exception:
                logger.exception("SaveScheduler deferred callback failed")

    def flush(self, callback) -> bool:
        """Cancel any pending timer and execute the save immediately if dirty.

        Returns True if a save was performed.
        """
        cancel_event = None
        should_save = False
        with self._lock:
            cancel_event = self._cancel_event
            self._timer = None
            self._cancel_event = None
            if self._pending:
                self._pending = False
                should_save = True
        if cancel_event is not None:
            cancel_event.set()
        if should_save:
            callback()
            return True
        return False

    def cancel(self) -> None:
        """Cancel the pending timer without flushing."""
        cancel_event = None
        with self._lock:
            cancel_event = self._cancel_event
            self._timer = None
            self._cancel_event = None
            self._pending = False
        if cancel_event is not None:
            cancel_event.set()

    def reset_pending(self) -> None:
        """Clear the pending flag (used by batch_update exception path)."""
        with self._lock:
            self._pending = False


# ============================================================
# IconRepository — icon cache management
# ============================================================


class IconRepository:
    """Manage the on-disk icon cache directory.

    Extracted from ``DataManager`` to isolate the icon-cache concern (clean,
    stats, path enumeration) from the config-store concern.
    """

    def __init__(self, icons_dir: Path | str):
        self.icons_dir = Path(icons_dir)

    @property
    def exists(self) -> bool:
        return self.icons_dir.exists()

    def clean(
        self,
        used_icons: set[str],
        *,
        dry_run: bool = False,
    ) -> dict:
        """Remove orphan, duplicate, invalid-extension, and oversize cache files.

        *used_icons* is the set of normalised absolute paths currently
        referenced by ShortcutItems.  Files not in this set are candidates
        for removal.
        """
        import hashlib

        stats = {
            "exe_files_removed": 0,
            "exe_files_size_mb": 0,
            "large_files_removed": 0,
            "large_files_size_mb": 0,
            "orphan_files_removed": 0,
            "orphan_files_size_mb": 0,
            "duplicate_files_removed": 0,
            "duplicate_files_size_mb": 0,
            "total_removed": 0,
            "total_size_freed_mb": 0,
            "dry_run": dry_run,
        }

        if not self.icons_dir.exists():
            return stats

        seen_hashes: dict[str, str] = {}
        invalid_exts = {".exe", ".dll", ".sys", ".com", ".bat", ".cmd", ".msi", ".scr"}
        max_size = 10 * 1024 * 1024  # 10 MB

        for file_path in self.icons_dir.iterdir():
            if not file_path.is_file():
                continue

            file_path_normalized = os.path.normcase(os.path.abspath(str(file_path)))
            ext = file_path.suffix.lower()

            try:
                file_size = file_path.stat().st_size
                file_size_mb = file_size / (1024 * 1024)
            except OSError:
                continue

            is_in_use = file_path_normalized in used_icons
            should_delete = False
            reason = ""

            if ext in invalid_exts and not is_in_use:
                should_delete, reason = True, "executable"
                stats["exe_files_removed"] += 1
                stats["exe_files_size_mb"] += file_size_mb
            elif file_size > max_size and not is_in_use:
                should_delete, reason = True, "too_large"
                stats["large_files_removed"] += 1
                stats["large_files_size_mb"] += file_size_mb
            elif not is_in_use:
                should_delete, reason = True, "orphan"
                stats["orphan_files_removed"] += 1
                stats["orphan_files_size_mb"] += file_size_mb

            if not should_delete:
                try:
                    with open(file_path, "rb") as f:
                        content = f.read(65536)
                    file_hash = hashlib.md5(content + str(file_size).encode()).hexdigest()
                    if file_hash in seen_hashes:
                        if not is_in_use:
                            should_delete, reason = True, "duplicate"
                            stats["duplicate_files_removed"] += 1
                            stats["duplicate_files_size_mb"] += file_size_mb
                        else:
                            seen_hashes[file_hash] = str(file_path)
                    else:
                        seen_hashes[file_hash] = str(file_path)
                except OSError as exc:
                    logger.debug("hash icon cache file failed %s: %s", file_path, exc, exc_info=True)

            if should_delete:
                stats["total_removed"] += 1
                stats["total_size_freed_mb"] += file_size_mb
                if not dry_run:
                    try:
                        os.remove(file_path)
                        logger.info("removed icon cache file: %s (%s, %.2f MB)", file_path.name, reason, file_size_mb)
                    except OSError as e:
                        logger.warning("failed to remove icon cache file %s: %s", file_path, e)
                        stats["total_removed"] -= 1
                        stats["total_size_freed_mb"] -= file_size_mb

        for key in stats:
            if isinstance(stats[key], float):
                stats[key] = round(stats[key], 2)
        return stats

    def get_stats(self) -> dict:
        """Return aggregate statistics about the icon cache directory."""
        stats = {
            "total_files": 0,
            "total_size_mb": 0,
            "by_extension": {},
            "invalid_files": 0,
            "invalid_size_mb": 0,
        }
        if not self.icons_dir.exists():
            return stats

        invalid_exts = {".exe", ".dll", ".sys", ".com", ".bat", ".cmd", ".msi", ".scr"}
        for file_path in self.icons_dir.iterdir():
            if not file_path.is_file():
                continue
            try:
                file_size = file_path.stat().st_size
                file_size_mb = file_size / (1024 * 1024)
            except OSError:
                continue
            ext = file_path.suffix.lower() or ".unknown"
            stats["total_files"] += 1
            stats["total_size_mb"] += file_size_mb
            if ext not in stats["by_extension"]:
                stats["by_extension"][ext] = {"count": 0, "size_mb": 0}
            stats["by_extension"][ext]["count"] += 1
            stats["by_extension"][ext]["size_mb"] += file_size_mb
            if ext in invalid_exts or file_size > 10 * 1024 * 1024:
                stats["invalid_files"] += 1
                stats["invalid_size_mb"] += file_size_mb

        stats["total_size_mb"] = round(stats["total_size_mb"], 2)
        stats["invalid_size_mb"] = round(stats["invalid_size_mb"], 2)
        for ext_stats in stats["by_extension"].values():
            ext_stats["size_mb"] = round(ext_stats["size_mb"], 2)
        return stats
