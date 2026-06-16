"""Data loader, recovery and transaction journal service.

Extracted from :class:`core.data_manager.DataManager` in 1.6.3.3 to isolate:

* **Load** — :py:meth:`DataLoader.load` from ``data.json`` with quarantine +
  fallback to the most recent auto-backup.
* **Repair** — :py:meth:`DataLoader.apply_repairs` runs :func:`apply_config_repairs`
  against the current in-memory data.
* **Recovery** — :py:meth:`DataLoader.reload` and
  :py:meth:`DataLoader.restore_history` re-read the on-disk state.
* **Transaction journal** — :py:meth:`DataLoader.detect_stale_journal`,
  :py:meth:`DataLoader.write_journal`, :py:meth:`DataLoader.clear_journal`,
  :py:meth:`DataLoader.verify_consistency` track crash-safety on the
  ``restore_full_config`` / ``import_shareable_config`` paths.
* **Factory reset** — :py:meth:`DataLoader.factory_reset` removes app data,
  icon cache, and the registry auto-start entry.

Public API stays on :class:`DataManager`; this class is internal and may be
called directly by tests.
"""

from __future__ import annotations

import json
import logging
import shutil
import winreg  # noqa: F401  # used inside factory_reset, imported lazily in caller paths
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config_recovery import ConfigRecoveryReport
from .config_repairs import apply_config_repairs
from .config_validation import load_valid_data_file, validate_app_data_dict
from .data_models import AppData
from .i18n import set_language
from .path_security import resolve_under, safe_rmtree_child

if TYPE_CHECKING:
    from .data_manager import DataManager

logger = logging.getLogger(__name__)

_HISTORY_DEFAULT = "\u914d\u7f6e\u53d8\u66f4"


class DataLoader:
    """Coordinate data.json load/recovery/transaction lifecycle.

    The class is the entry point for everything that needs to read the
    persisted config back into memory, restore from a snapshot, or
    guarantee crash-safety around risky multi-file transactions.
    """

    def __init__(self, dm: DataManager) -> None:
        self._dm = dm

    # ── load ──────────────────────────────────────────────────────────

    def load(self) -> AppData:
        """Load ``data.json`` with quarantine + auto-backup fallback."""
        dm = self._dm
        if dm.data_file.exists():
            try:
                loaded, issues = load_valid_data_file(dm.data_file)
                dm._config_status = {
                    "status": "warn" if issues else "ok",
                    "source": str(dm.data_file),
                    "issues": issues,
                }
                if issues:
                    logger.warning("data manager message: %s", issues)
                dm._write_recovery_report(
                    ConfigRecoveryReport(
                        status="ok",
                        reason="loaded",
                        source_path=str(dm.data_file),
                        issues=issues,
                    )
                )
                return loaded
            except Exception as e:
                logger.warning("data manager message: %s", e)
                quarantined = dm._get_recovery_service().quarantine_bad_config()
                recovered = self._recover_from_latest_backup(str(e), quarantined)
                if recovered is not None:
                    return recovered
                dm._config_status = {
                    "status": "warn",
                    "source": str(dm.data_file),
                    "issues": ["fallback_default", str(e)],
                }
                dm._write_recovery_report(
                    ConfigRecoveryReport(
                        status="fallback_default",
                        reason=str(e),
                        source_path=str(dm.data_file),
                        quarantined_path=str(quarantined or ""),
                        issues=[str(e)],
                    )
                )
        else:
            dm._config_status = {"status": "ok", "source": "default", "issues": []}
            dm._write_recovery_report(ConfigRecoveryReport(status="ok", reason="default config", source_path="default"))
        return AppData()

    def apply_repairs(self):
        """Apply :func:`apply_config_repairs` to the current in-memory data."""
        dm = self._dm
        try:
            report = apply_config_repairs(dm.data)
            if report.issues:
                dm._config_status.setdefault("issues", [])
                dm._config_status["issues"].extend(
                    f"config_repair:{issue.code}:{issue.path}" for issue in report.issues
                )
            return report
        except Exception as exc:
            logger.warning("config repair failed: %s", exc)

            class _EmptyReport:
                changed = False
                issues = []

                def to_dict(self):
                    return {"changed": False, "repaired": 0, "problem_count": 0, "issues": []}

            return _EmptyReport()

    def _recover_from_latest_backup(
        self,
        reason: str = "",
        quarantined_path: Path | str | None = None,
    ) -> AppData | None:
        """Recover data.json from the newest valid auto backup."""
        dm = self._dm
        try:
            result = dm._get_recovery_service().recover_from_latest_backup(reason, quarantined_path)
            if result is None:
                return None
            dm._config_status = result.status
            dm._write_recovery_report(result.report)
            logger.warning("data manager message: %s", result.report.recovered_from)
            return result.data
        except Exception as exc:
            logger.error("data manager message: %s", exc)
            return None

    # ── reload / history restore ──────────────────────────────────────

    def reload(self) -> None:
        """Flush pending writes and re-read everything from disk."""
        dm = self._dm
        with dm._save_lock:
            dm.flush_pending_save()
            dm.data = self.load()
            repair_report = self.apply_repairs()
            dm._icon_repo_folder = dm._get_icon_repository_service().load_folder()
            dm._get_icon_repository_service().attach_folder()
            if repair_report.changed and dm.data_file.exists():
                dm._suppress_next_history = True
                dm.save(immediate=True)
            set_language(getattr(dm.data.settings, "language", "zh_CN"))
            dm._runtime_revision += 1

    def list_history(self) -> list:
        dm = self._dm
        history = getattr(dm, "history_manager", None)
        return history.list_snapshots() if history else []

    def restore_history(self, snapshot_id: str) -> bool:
        """Restore AppData from a persisted history snapshot."""
        dm = self._dm
        with dm._save_lock:
            try:
                history = getattr(dm, "history_manager", None)
                if history is None:
                    return False
                data_dict = history.load_snapshot_data(snapshot_id)
                issues = validate_app_data_dict(data_dict)
                if "root_not_object" in issues or "folders_not_list" in issues:
                    logger.warning("data manager message: %s", issues)
                    return False
                dm._mark_history(_HISTORY_DEFAULT)
                old_data = dm.data
                old_saved = getattr(dm, "_last_saved_data_dict", None)
                old_config_status = dict(getattr(dm, "_config_status", {}) or {})
                dm.data = AppData.from_dict(data_dict)
                self.apply_repairs()
                if not dm.save(immediate=True):
                    dm.data = old_data
                    dm._last_saved_data_dict = old_saved
                    dm._config_status = old_config_status
                    return False
                return True
            except Exception as exc:
                logger.exception("restore config history failed: %s", exc)
                return False

    # ── transaction journal ───────────────────────────────────────────

    def detect_stale_journal(self) -> None:
        """Check for a stale transaction journal from a previous crash.

        If a journal file exists at startup, the previous session likely
        crashed mid-transaction.  We log a warning and attempt to restore
        from the most recent automatic backup if data.json is corrupted
        or missing.
        """
        dm = self._dm
        journal_path = dm.recovery_dir / "transaction_journal.json"
        if not journal_path.exists():
            return
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            operation = journal.get("operation", "unknown")
            timestamp = journal.get("timestamp", "unknown")
            logger.warning(
                "检测到上次会话遗留的事务日志 (operation=%s, timestamp=%s), "
                "可能表明上次事务未完成。正在检查数据完整性...",
                operation,
                timestamp,
            )
            data_ok = dm.data_file.exists()
            if data_ok:
                try:
                    json.loads(dm.data_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    data_ok = False
            if not data_ok:
                logger.warning("data.json 损坏或缺失，尝试从最近备份恢复...")
                self.attempt_restore_from_latest_backup()
            else:
                logger.info("data.json 完整性正常，清除遗留事务日志")
            try:
                journal_path.unlink()
            except OSError as exc:
                logger.debug("清除遗留事务日志失败: %s", exc)
        except Exception as exc:
            logger.warning("处理遗留事务日志失败: %s", exc, exc_info=True)

    def attempt_restore_from_latest_backup(self) -> None:
        """Try to restore data.json from the most recent automatic backup."""
        dm = self._dm
        if not dm.auto_backup_dir.is_dir():
            logger.warning("无自动备份目录，无法恢复")
            return
        backups = sorted(dm.auto_backup_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not backups:
            logger.warning("自动备份目录为空，无法恢复")
            return
        latest = backups[0]
        try:
            backup_data = json.loads(latest.read_text(encoding="utf-8"))
            if not isinstance(backup_data, dict):
                logger.warning("最新备份 %s 格式无效", latest.name)
                return
            shutil.copy2(str(latest), str(dm.data_file))
            logger.info("已从备份 %s 恢复 data.json", latest.name)
        except Exception as exc:
            logger.error("从备份恢复 data.json 失败: %s", exc, exc_info=True)

    def write_journal(self, operation: str, extra: dict | None = None) -> None:
        """Write a pre-transaction state snapshot to the recovery directory.

        The journal records the current data.json hash, icon directory file
        count, and timestamp.  If the application crashes mid-transaction,
        the journal can be used to detect an inconsistent state on next
        startup.
        """
        dm = self._dm
        journal_path = dm.recovery_dir / "transaction_journal.json"
        try:
            dm.recovery_dir.mkdir(parents=True, exist_ok=True)
            data_hash = ""
            if dm.data_file.exists():
                import hashlib

                data_hash = hashlib.sha256(dm.data_file.read_bytes()).hexdigest()
            icon_count = 0
            if dm.icons_dir.exists():
                icon_count = sum(1 for p in dm.icons_dir.iterdir() if p.is_file())
            journal = {
                "operation": operation,
                "timestamp": datetime.now().isoformat(),
                "data_file_hash": data_hash,
                "icon_file_count": icon_count,
                "data_file_exists": dm.data_file.exists(),
                "icons_dir_exists": dm.icons_dir.exists(),
            }
            if extra:
                journal.update(extra)
            journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("write transaction journal failed: %s", exc, exc_info=True)

    def clear_journal(self) -> None:
        """Remove the transaction journal after successful completion."""
        dm = self._dm
        journal_path = dm.recovery_dir / "transaction_journal.json"
        try:
            if journal_path.exists():
                journal_path.unlink()
        except Exception as exc:
            logger.debug("clear transaction journal failed: %s", exc, exc_info=True)

    def verify_consistency(self) -> dict:
        """Post-transaction verification: compare in-memory state with disk.

        Returns a dict with ``consistent`` (bool) and ``issues`` (list).
        """
        dm = self._dm
        issues: list[str] = []
        if dm.data_file.exists():
            try:
                disk_data = json.loads(dm.data_file.read_text(encoding="utf-8"))
                mem_data = dm.data.to_dict() if hasattr(dm.data, "to_dict") else {}
                if disk_data.get("version") != mem_data.get("version"):
                    issues.append("version mismatch between memory and disk")
                disk_folders = len(disk_data.get("folders", []))
                mem_folders = len(mem_data.get("folders", []))
                if disk_folders != mem_folders:
                    issues.append(f"folder count mismatch: disk={disk_folders}, mem={mem_folders}")
            except Exception as exc:
                issues.append(f"data.json verification failed: {exc}")
        else:
            issues.append("data.json does not exist after transaction")

        return {"consistent": len(issues) == 0, "issues": issues}

    # ── factory reset ─────────────────────────────────────────────────

    def factory_reset(self, callback=None) -> dict:
        """Reset registry auto-start, icon cache, and app data directory."""

        dm = self._dm
        with dm._save_lock:
            stats: dict[str, Any] = {
                "files_removed": 0,
                "dirs_removed": 0,
                "registry_keys_removed": 0,
                "errors": [],
            }

            def remove_children_safely(root: Path, label: str):
                root_path = Path(root).resolve(strict=False)
                if not root_path.exists() or root_path.is_symlink():
                    return
                for item in root_path.iterdir():
                    try:
                        target = resolve_under(root_path, item)
                        if target.is_symlink() or target.is_file():
                            target.unlink()
                            stats["files_removed"] += 1
                        elif target.is_dir():
                            safe_rmtree_child(root_path, target)
                            stats["dirs_removed"] += 1
                    except Exception as e:
                        stats["errors"].append(f"Failed to remove {label} item {item}: {e}")

            def report(msg, progress):
                if callback:
                    try:
                        callback(msg, progress)
                    except Exception as exc:
                        logger.debug("回调函数执行失败: %s", exc, exc_info=True)
                logger.info(msg)

            report("Resetting startup registry entry...", 0.1)
            try:
                reg_key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0,
                    winreg.KEY_ALL_ACCESS,
                )
                try:
                    winreg.DeleteValue(reg_key, "QuickLauncher")
                    stats["registry_keys_removed"] += 1
                except OSError:
                    logger.debug("删除注册表启动项失败", exc_info=True)
                winreg.CloseKey(reg_key)
            except Exception as e:
                stats["errors"].append(f"Factory reset step failed: {e}")

            report("Removing icon cache...", 0.3)
            try:
                remove_children_safely(dm.icons_dir, "icons")
            except Exception as e:
                stats["errors"].append(f"Factory reset step failed: {e}")

            report("Removing app data...", 0.6)
            try:
                remove_children_safely(dm.app_dir, "app data")
            except Exception as e:
                stats["errors"].append(f"Factory reset step failed: {e}")

            report("Resetting in-memory configuration...", 0.9)
            try:
                dm._mark_history(_HISTORY_DEFAULT)
                dm.data = AppData()
                dm._last_saved_data_dict = None
            except Exception as e:
                stats["errors"].append(f"Factory reset step failed: {e}")

            # Persist the clean state to disk directly
            data_file = dm.app_dir / "data.json"
            try:
                data_file.parent.mkdir(parents=True, exist_ok=True)
                default_data = AppData().to_dict()
                with open(data_file, "w", encoding="utf-8") as f:
                    json.dump(default_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                stats["errors"].append(f"Factory reset persist failed: {e}")

            return stats


__all__ = ["DataLoader"]
