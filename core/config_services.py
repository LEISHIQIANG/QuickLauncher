"""Internal configuration services used behind DataManager's public facade."""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

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
        payload = json.dumps(data_dict, ensure_ascii=False, separators=(",", ":"))
        json.loads(payload)
        return payload

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
        try:
            if had_original:
                shutil.copy2(self.data_file, fallback_backup)
            shutil.copyfile(temp_path, self.data_file)
            try:
                os.remove(temp_path)
            except Exception as cleanup_error:
                logger.debug("cleanup temp file after fallback copy failed: %s", cleanup_error)
        except Exception:
            if had_original and fallback_backup.exists():
                try:
                    shutil.copyfile(fallback_backup, self.data_file)
                except Exception as restore_error:
                    logger.error("restore data file after fallback failure failed: %s", restore_error)
            raise
        finally:
            if fallback_backup.exists():
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
        except Exception as exc:
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
