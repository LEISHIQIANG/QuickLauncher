"""
Data manager
"""

import copy
import json
import logging
import os
import shutil
import tempfile
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config_history import ConfigHistoryManager
from .config_recovery import ConfigRecoveryReport
from .config_repairs import apply_config_repairs
from .config_services import (
    ConfigBackupService,
    ConfigDataStore,
    ConfigPackageService,
    ConfigRecoveryService,
    IconRepository,
    SaveScheduler,
)
from .config_validation import (
    load_valid_data_file,
    sanitize_app_data_dict,
    validate_app_data,
    validate_app_data_dict,
)
from .data_models import (
    AppData,
    AppSettings,
    Folder,
    ShortcutItem,
)
from .i18n import normalize_language, set_language
from .import_security import (
    MAX_BACKGROUND_BYTES,
    MAX_CONFIG_BYTES,
    MAX_ICON_BYTES,
    UnsafeZipError,
    build_safe_zip_index,
    has_report_warnings,
    has_zip_entry,
    is_allowed_background_path,
    is_allowed_icon_path,
    new_import_report,
    normalize_zip_name,
    read_zip_bytes,
    read_zip_text,
    set_imported_items,
    skip_file,
)
from .path_security import resolve_under, safe_rmtree_child
from .trigger_config import normalize_trigger_settings

logger = logging.getLogger(__name__)


class DataManager:
    """Data manager."""

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        import sys

        if getattr(sys, "frozen", False):
            install_dir = Path(sys.executable).parent
        else:
            install_dir = Path(__file__).parent.parent

        self.install_dir = install_dir
        self.app_dir = install_dir / "config"
        self.data_file = self.app_dir / "data.json"
        self.icon_repo_file = self.app_dir / "icon_repo.json"
        self.system_icons_file = install_dir / "assets" / "system_icons" / "config.json"
        self.icons_dir = install_dir / "icons"
        self.auto_backup_dir = self.app_dir / "auto_backups"
        self.history_dir = self.app_dir / "history"
        self.recovery_dir = self.app_dir / "recovery"
        self.config_dir = self.app_dir
        self._max_auto_backups = 5

        # Initialize event log
        try:
            from .event_log import init_event_log

            init_event_log(self.app_dir)
        except Exception as exc:
            logger.debug("初始化事件日志失败: %s", exc, exc_info=True)
        # Initialize search history with data directory for persistence
        try:
            from .search_history import set_search_history_data_dir

            set_search_history_data_dir(self.app_dir)
        except Exception as exc:
            logger.debug("初始化搜索历史数据目录失败: %s", exc, exc_info=True)
        self._max_history_snapshots = 20

        from .config_migrator import ConfigMigrator

        # 先检测上次迁移中断的残留，再判断是否需要完整迁移
        if ConfigMigrator.needs_partial_recovery():
            ConfigMigrator.recover_partial()
        if ConfigMigrator.needs_migration():
            ConfigMigrator.migrate()

        self._save_timer = None
        self._save_pending = False
        self._save_lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._save_delay = 0.5  # Merge rapid consecutive saves within 500 ms.
        self._batch_depth = 0
        self._batch_dirty = False
        self._batch_force_immediate = False
        self._runtime_revision = 0
        self._pending_history_action = "\u914d\u7f6e\u53d8\u66f4"
        self._pending_history_summary = ""
        self._suppress_next_history = False
        self._last_saved_data_dict = None
        self._config_status = {"status": "unknown", "source": "", "issues": []}
        self._last_import_report = new_import_report()

        self._ensure_dirs()
        self.config_store = ConfigDataStore(self.data_file)
        self.backup_service = ConfigBackupService(self.auto_backup_dir, self._max_auto_backups)
        self.package_service = ConfigPackageService(self.app_dir)
        self.recovery_service = ConfigRecoveryService(self.recovery_dir, self.auto_backup_dir, self.data_file)
        self.history_manager = ConfigHistoryManager(self.history_dir, self._max_history_snapshots)
        self.save_scheduler = SaveScheduler(delay=self._save_delay, owner="data-manager-save")
        self.icon_repository = IconRepository(self.icons_dir)
        self._detect_stale_transaction_journal()
        self.data = self._load()
        repair_report = self._apply_config_repairs_to_current()
        self._icon_repo_folder = self._load_icon_repo_folder()
        self._attach_icon_repo_folder()
        set_language(getattr(self.data.settings, "language", "zh_CN"))
        self._last_saved_data_dict = self._main_data_dict()
        if repair_report.changed and self.data_file.exists():
            logger.info("Repaired config/data.json: %s", repair_report.to_dict())
            self._suppress_next_history = True
            self.save(immediate=True)

    def get_runtime_revision(self) -> int:
        """Data manager."""
        return int(self._runtime_revision)

    def _ensure_dirs(self):
        """Data manager."""
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.icons_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.recovery_dir.mkdir(parents=True, exist_ok=True)

    def _get_config_store(self) -> ConfigDataStore:
        service = getattr(self, "config_store", None)
        if service is None:
            service = ConfigDataStore(self.data_file)
            self.config_store = service
        service.configure(self.data_file)
        return service

    def _get_backup_service(self) -> ConfigBackupService:
        service = getattr(self, "backup_service", None)
        if service is None:
            service = ConfigBackupService(self.auto_backup_dir, self._max_auto_backups)
            self.backup_service = service
        service.configure(self.auto_backup_dir, self._max_auto_backups)
        return service

    def _get_recovery_service(self) -> ConfigRecoveryService:
        service = getattr(self, "recovery_service", None)
        if service is None:
            service = ConfigRecoveryService(self.recovery_dir, self.auto_backup_dir, self.data_file)
            self.recovery_service = service
        service.configure(self.recovery_dir, self.auto_backup_dir, self.data_file)
        return service

    def _get_package_service(self) -> ConfigPackageService:
        service = getattr(self, "package_service", None)
        if service is None:
            service = ConfigPackageService(self.app_dir)
            self.package_service = service
        service.configure(self.app_dir)
        return service

    def _get_save_scheduler(self) -> SaveScheduler:
        service = getattr(self, "save_scheduler", None)
        if service is None:
            service = SaveScheduler(delay=getattr(self, "_save_delay", 0.5), owner="data-manager-save")
            self.save_scheduler = service
        service.delay = getattr(self, "_save_delay", service.delay)
        return service

    def _get_icon_repository(self) -> IconRepository:
        service = getattr(self, "icon_repository", None)
        if service is None:
            service = IconRepository(self.icons_dir)
            self.icon_repository = service
        service.icons_dir = Path(self.icons_dir)
        return service

    def _cancel_scheduled_save_locked(self) -> None:
        scheduler = getattr(self, "save_scheduler", None)
        scheduler_timer = scheduler.current_timer if scheduler is not None else None
        timer = getattr(self, "_save_timer", None)
        self._save_timer = None
        if scheduler is not None:
            scheduler.cancel()
        if timer is not None and timer is not scheduler_timer:
            timer.cancel()

    def _detach_icon_repo_folder(self) -> Folder | None:
        """Remove and return the runtime icon repository folder from AppData."""
        for folder in list(self.data.folders):
            if getattr(folder, "is_icon_repo", False) or folder.id == "icon_repo":
                self.data.folders.remove(folder)
                folder.id = "icon_repo"
                folder.name = "\u56fe\u6807\u4ed3\u5e93"
                folder.is_system = True
                folder.is_dock = False
                folder.is_icon_repo = True
                return folder
        return None

    def _attach_icon_repo_folder(self) -> None:
        """Attach the icon repository as a runtime-only folder for existing UI code."""
        self.data.folders = [
            f for f in self.data.folders if not getattr(f, "is_icon_repo", False) and f.id != "icon_repo"
        ]
        max_order = max((f.order for f in self.data.folders), default=0)
        self._icon_repo_folder.id = "icon_repo"
        self._icon_repo_folder.name = "\u56fe\u6807\u4ed3\u5e93"
        self._icon_repo_folder.order = max_order + 1
        self._icon_repo_folder.is_system = True
        self._icon_repo_folder.is_dock = False
        self._icon_repo_folder.is_icon_repo = True
        self.data.folders.append(self._icon_repo_folder)

    def _load_icon_repo_folder(self) -> Folder:
        """Load the combined runtime icon repository from system and user sources."""
        legacy_folder = self._detach_icon_repo_folder()
        system_items = self._load_system_icon_items()
        user_folder = self._read_icon_repo_file() if self.icon_repo_file.exists() else None
        user_items = list(getattr(user_folder, "items", []) or [])

        if not user_items and legacy_folder is not None:
            user_items = list(getattr(legacy_folder, "items", []) or [])

        user_items = self._filter_user_icon_items(user_items, system_items)
        self._write_icon_repo_items(user_items)

        for item in system_items:
            item._icon_repo_source = "system"
        for item in user_items:
            item._icon_repo_source = "user"

        items = sorted(system_items, key=lambda item: int(getattr(item, "order", 0) or 0)) + sorted(
            user_items, key=lambda item: int(getattr(item, "order", 0) or 0)
        )
        return Folder(id="icon_repo", name="\u56fe\u6807\u4ed3\u5e93", is_system=True, is_icon_repo=True, items=items)

    def _read_icon_repo_file(self) -> Folder | None:
        try:
            raw = json.loads(self.icon_repo_file.read_text(encoding="utf-8"))
            items = raw.get("items", []) if isinstance(raw, dict) else []
            if not isinstance(items, list):
                items = []
            return Folder(
                id="icon_repo",
                name="\u56fe\u6807\u4ed3\u5e93",
                is_system=True,
                is_icon_repo=True,
                items=[ShortcutItem.from_dict(item) for item in items if isinstance(item, dict)],
            )
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            logger.warning("load icon repository failed: %s", exc)
            return None

    def _load_system_icon_items(self) -> list[ShortcutItem]:
        seed_file = Path(
            getattr(self, "system_icons_file", self.install_dir / "assets" / "system_icons" / "config.json")
        )
        seed_dir = seed_file.parent
        if not seed_file.exists():
            return []
        try:
            raw = json.loads(seed_file.read_text(encoding="utf-8"))
            items = raw.get("items", []) if isinstance(raw, dict) else []
            result = []
            for item_data in items:
                if not isinstance(item_data, dict):
                    continue
                item_copy = dict(item_data)
                icon_path = str(item_copy.get("icon_path", "") or "")
                if icon_path and not os.path.isabs(icon_path):
                    icon_path = icon_path.replace("/", os.sep).replace("\\", os.sep)
                    item_copy["icon_path"] = str(seed_dir / icon_path)
                result.append(ShortcutItem.from_dict(item_copy))
            return result
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            logger.warning("load system icons failed: %s", exc)
            return []

    def _filter_user_icon_items(
        self, user_items: list[ShortcutItem], system_items: list[ShortcutItem]
    ) -> list[ShortcutItem]:
        system_ids = {item.id for item in system_items}
        system_names = {item.name for item in system_items}
        filtered = []
        for item in user_items:
            if item.id in system_ids or item.name in system_names:
                continue
            item._icon_repo_source = "user"
            filtered.append(item)
        return filtered

    @staticmethod
    def _is_system_icon_repo_item(item: ShortcutItem | None) -> bool:
        return getattr(item, "_icon_repo_source", "") == "system"

    @staticmethod
    def _is_user_icon_repo_item(item: ShortcutItem | None) -> bool:
        return getattr(item, "_icon_repo_source", "") == "user"

    @staticmethod
    def _strip_icon_repo_runtime_source(item: ShortcutItem) -> ShortcutItem:
        try:
            delattr(item, "_icon_repo_source")
        except AttributeError as exc:
            logger.debug("删除运行时属性失败: %s", exc, exc_info=True)
        return item

    def _write_icon_repo_items(self, items: list[ShortcutItem]) -> bool:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": "1.0", "items": [item.to_dict() for item in items]},
            ensure_ascii=False,
            indent=2,
        )
        temp_file = self.icon_repo_file.with_name(f"{self.icon_repo_file.stem}.{uuid.uuid4().hex}.tmp")
        try:
            temp_file.write_text(payload, encoding="utf-8")
            icon_repo_store = ConfigDataStore(self.icon_repo_file)
            icon_repo_store.replace_data_file(temp_file)
            return True
        except (OSError, TypeError, ValueError) as exc:
            logger.error("save icon repository failed: %s", exc)
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except OSError as exc:
                logger.debug("清理临时文件失败: %s", exc, exc_info=True)
            return False

    def save_icon_repo(self) -> bool:
        with self._save_lock:
            self._runtime_revision += 1
            folder = self.data.get_folder_by_id("icon_repo") or getattr(self, "_icon_repo_folder", None)
            if folder is None:
                return False
            self._icon_repo_folder = folder
            items = [item for item in list(folder.items) if not self._is_system_icon_repo_item(item)]
        return self._write_icon_repo_items(items)

    def _load(self) -> AppData:
        """Data manager."""
        if self.data_file.exists():
            try:
                loaded, issues = load_valid_data_file(self.data_file)
                self._config_status = {
                    "status": "warn" if issues else "ok",
                    "source": str(self.data_file),
                    "issues": issues,
                }
                if issues:
                    logger.warning("data manager message: %s", issues)
                self._write_recovery_report(
                    ConfigRecoveryReport(
                        status="ok",
                        reason="loaded",
                        source_path=str(self.data_file),
                        issues=issues,
                    )
                )
                return loaded
            except Exception as e:
                logger.warning("data manager message: %s", e)
                quarantined = self._get_recovery_service().quarantine_bad_config()
                recovered = self._recover_from_latest_backup(str(e), quarantined)
                if recovered is not None:
                    return recovered
                self._config_status = {
                    "status": "warn",
                    "source": str(self.data_file),
                    "issues": ["fallback_default", str(e)],
                }
                self._write_recovery_report(
                    ConfigRecoveryReport(
                        status="fallback_default",
                        reason=str(e),
                        source_path=str(self.data_file),
                        quarantined_path=str(quarantined or ""),
                        issues=[str(e)],
                    )
                )
        else:
            self._config_status = {"status": "ok", "source": "default", "issues": []}
            self._write_recovery_report(
                ConfigRecoveryReport(status="ok", reason="default config", source_path="default")
            )
        return AppData()

    def _apply_config_repairs_to_current(self):
        """Apply config repairs to the current in-memory data."""
        try:
            report = apply_config_repairs(self.data)
            if report.issues:
                self._config_status.setdefault("issues", [])
                self._config_status["issues"].extend(
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
        self, reason: str = "", quarantined_path: Path | str | None = None
    ) -> AppData | None:
        """Recover data.json from the newest valid auto backup."""
        try:
            result = self._get_recovery_service().recover_from_latest_backup(reason, quarantined_path)
            if result is None:
                return None
            self._config_status = result.status
            self._write_recovery_report(result.report)
            logger.warning("data manager message: %s", result.report.recovered_from)
            return result.data
        except Exception as exc:
            logger.error("data manager message: %s", exc)
            return None

    def save(self, immediate: bool = False) -> bool:
        """Data manager."""
        with self._save_lock:
            self._runtime_revision += 1
            if self._batch_depth > 0:
                self._save_pending = True
                self._batch_dirty = True
                if immediate:
                    self._batch_force_immediate = True
                return True

        if immediate:
            return self._do_save()

        with self._save_lock:
            self._save_pending = True
            if self._save_timer is None:
                scheduler = self._get_save_scheduler()
                scheduler.schedule(self._delayed_save)
                self._save_timer = scheduler.current_timer
        return True

    def _delayed_save(self):
        """Data manager."""
        should_save = False
        with self._save_lock:
            self._save_timer = None
            if self._save_pending:
                self._save_pending = False
                should_save = True

        if should_save:
            self._do_save()

    def shutdown(self, timeout: float = 3.0) -> None:
        """Flush pending saves and cancel timers before application exit.

        Call this once during application teardown to ensure no data is lost
        from the delayed-save debounce window.
        """
        should_save = False
        with self._save_lock:
            if self._save_pending:
                self._save_pending = False
                should_save = True
            self._cancel_scheduled_save_locked()
        if should_save:
            try:
                self._do_save()
            except Exception as exc:
                logger.error("shutdown flush save failed: %s", exc, exc_info=True)

    @contextmanager
    def batch_update(self, immediate: bool = False):
        """Data manager."""
        with self._save_lock:
            self._batch_depth += 1
            if immediate:
                self._batch_force_immediate = True

        try:
            yield self
        except Exception:
            # Don't save partial changes on exception — reset all dirty flags
            with self._save_lock:
                self._batch_dirty = False
                self._batch_force_immediate = False
                self._save_pending = False
                self._cancel_scheduled_save_locked()
            raise
        finally:
            should_flush = False
            flush_immediately = False
            with self._save_lock:
                if self._batch_depth > 0:
                    self._batch_depth -= 1
                assert self._batch_depth >= 0, "batch_update depth underflow"

                if self._batch_depth == 0:
                    if self._save_pending or self._batch_dirty:
                        should_flush = True
                        flush_immediately = self._batch_force_immediate
                        self._cancel_scheduled_save_locked()
                        self._save_pending = False

                    self._batch_dirty = False
                    self._batch_force_immediate = False

            if should_flush:
                if flush_immediately:
                    self._do_save()
                else:
                    self.save(immediate=True)

    def _do_save(self) -> bool:
        """Save data to disk atomically with lock splitting."""

        with self._save_lock:
            try:
                payload = self._serialize_data()
                next_data_dict = json.loads(payload)
                previous_data_dict = self._last_saved_data_dict
                suppress_history = bool(self._suppress_next_history)
                history_action = self._pending_history_action
                history_summary = self._pending_history_summary
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.error("serialize data failed: %s", e)
                return False

        write_success = False
        with self._write_lock:
            temp_file = self.data_file.with_name(f"{self.data_file.stem}.{uuid.uuid4().hex}.tmp")
            try:
                self._create_auto_backup()

                with open(temp_file, "w", encoding="utf-8") as f:
                    f.write(payload)

                self._replace_data_file(temp_file)
                write_success = True

            except OSError as e:
                logger.error("save data failed: %s", e)
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except OSError as cleanup_error:
                        logger.debug("cleanup temp file failed: %s", cleanup_error)

        if write_success:
            with self._save_lock:
                if suppress_history:
                    self._suppress_next_history = False
                elif previous_data_dict and previous_data_dict != next_data_dict:
                    history = getattr(self, "history_manager", None)
                    if history is not None:
                        history.record_snapshot(previous_data_dict, action=history_action, summary=history_summary)
                    self._pending_history_action = "\u914d\u7f6e\u53d8\u66f4"
                    self._pending_history_summary = ""
                self._last_saved_data_dict = next_data_dict
                self._config_status = {"status": "ok", "source": str(self.data_file), "issues": []}
        return write_success

    def _serialize_data(self) -> str:
        """Serialize data and validate the JSON before writing it to disk."""
        return self._get_config_store().serialize_data(self._main_data_dict())

    def _main_data_dict(self) -> dict:
        """Return AppData without the runtime-only icon repository folder."""
        data_dict = self.data.to_dict()
        folders = data_dict.get("folders", [])
        if isinstance(folders, list):
            data_dict["folders"] = [
                folder
                for folder in folders
                if not bool(folder.get("is_icon_repo", False)) and folder.get("id") != "icon_repo"
            ]
        return data_dict

    def _mark_history(self, action: str, summary: str = ""):
        self._pending_history_action = action or "\u914d\u7f6e\u53d8\u66f4"
        self._pending_history_summary = summary or ""

    def _write_recovery_report(self, report: ConfigRecoveryReport) -> None:
        self._get_recovery_service().write_report(report)

    def get_recovery_report(self) -> dict:
        return self._get_recovery_service().report_dict()

    def get_config_status(self) -> dict:
        """Return latest configuration load/save validation status."""
        with self._save_lock:
            status = dict(getattr(self, "_config_status", {}) or {})
            report = self.get_recovery_report()
            if report:
                status["recovery"] = report
            try:
                status["current_issues"] = validate_app_data(self.data)
            except Exception as exc:
                status["current_issues"] = [str(exc)]
                status["status"] = "error"
            return status

    def _reset_import_report(self) -> dict:
        self._last_import_report = new_import_report()
        return self._last_import_report

    def get_last_import_report(self) -> dict:
        report = getattr(self, "_last_import_report", None) or new_import_report()
        return {
            "dry_run": bool(report.get("dry_run", False)),
            "mode": str(report.get("mode", "") or ""),
            "skipped_files": list(report.get("skipped_files", [])),
            "skipped_settings": list(report.get("skipped_settings", [])),
            "warnings": list(report.get("warnings", [])),
            "imported_items": int(report.get("imported_items", 0) or 0),
            "has_warnings": has_report_warnings(report),
        }

    def list_config_history(self) -> list:
        history = getattr(self, "history_manager", None)
        return history.list_snapshots() if history else []

    def restore_config_history(self, snapshot_id: str) -> bool:
        """Restore AppData from a persisted history snapshot."""
        with self._save_lock:
            try:
                history = getattr(self, "history_manager", None)
                if history is None:
                    return False
                data_dict = history.load_snapshot_data(snapshot_id)
                issues = validate_app_data_dict(data_dict)
                if "root_not_object" in issues or "folders_not_list" in issues:
                    logger.warning("data manager message: %s", issues)
                    return False
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                old_data = self.data
                old_saved = getattr(self, "_last_saved_data_dict", None)
                old_config_status = dict(getattr(self, "_config_status", {}) or {})
                self.data = AppData.from_dict(data_dict)
                self._apply_config_repairs_to_current()
                if not self.save(immediate=True):
                    self.data = old_data
                    self._last_saved_data_dict = old_saved
                    self._config_status = old_config_status
                    return False
                return True
            except Exception as exc:
                logger.exception("restore config history failed: %s", exc)
                return False

    def _replace_data_file(self, temp_file: Path):
        """Replace data.json, falling back when Windows denies atomic rename."""
        self._get_config_store().replace_data_file(temp_file)

    def _create_auto_backup(self):
        """Create a timestamped backup of the current data file before replacing it."""
        self._get_backup_service().create_auto_backup(self.data_file)

    def flush_pending_save(self):
        """Data manager."""
        should_save = False
        with self._save_lock:
            self._cancel_scheduled_save_locked()
            if self._save_pending:
                self._save_pending = False
                should_save = True

        if should_save:
            self._do_save()

    def reload(self):
        """Data manager."""
        with self._save_lock:
            self.flush_pending_save()
            self.data = self._load()
            repair_report = self._apply_config_repairs_to_current()
            self._icon_repo_folder = self._load_icon_repo_folder()
            self._attach_icon_repo_folder()
            if repair_report.changed and self.data_file.exists():
                self._suppress_next_history = True
                self.save(immediate=True)
            set_language(getattr(self.data.settings, "language", "zh_CN"))
            self._runtime_revision += 1

    def record_shortcut_used(self, shortcut_id: str) -> bool:
        """Data manager."""
        if not shortcut_id:
            return False

        with self._save_lock:
            try:
                for folder in getattr(self.data, "folders", []) or []:
                    for item in getattr(folder, "items", []) or []:
                        if getattr(item, "id", "") == shortcut_id:
                            item.mark_used()
                            self._suppress_next_history = True
                            settings = getattr(self.data, "settings", None)
                            smart_sort_enabled = getattr(settings, "sort_mode", "custom") == "smart"
                            if smart_sort_enabled and not getattr(folder, "is_dock", False):
                                self._apply_smart_order(folder)
                                self._persist_folder_changes(folder, immediate=True)
                            else:
                                self._persist_folder_changes(folder, immediate=False)
                            logger.debug(
                                "recorded shortcut usage: id=%s count=%s",
                                shortcut_id,
                                getattr(item, "use_count", 0),
                            )
                            return True
            except Exception as e:
                logger.warning("record shortcut usage failed for %s: %s", shortcut_id, e)
                return False

            logger.debug("shortcut not found when recording usage: %s", shortcut_id)
            return False

    def _apply_smart_order(self, folder) -> int:
        """Update smart_order for one folder without changing custom order."""
        if not folder or getattr(folder, "is_dock", False):
            return 0

        ranked = sorted(
            getattr(folder, "items", []) or [],
            key=lambda item: (
                -max(0, int(getattr(item, "use_count", 0) or 0)),
                -max(0.0, float(getattr(item, "last_used_at", 0.0) or 0.0)),
                int(getattr(item, "order", 0) or 0),
            ),
        )
        updated = 0
        for index, item in enumerate(ranked):
            if getattr(item, "smart_order", None) != index:
                item.smart_order = index
                updated += 1
        return updated

    def add_folder(self, name: str) -> Folder:
        """Data manager."""
        with self._save_lock:
            self._mark_history("\u914d\u7f6e\u53d8\u66f4")
            max_order = max((f.order for f in self.data.folders), default=0)
            folder = Folder(name=name, order=max_order + 1)
            self.data.folders.append(folder)
            self.save()
            return folder

    def rename_folder(self, folder_id: str, new_name: str) -> bool:
        """Data manager."""
        with self._save_lock:
            folder = self.data.get_folder_by_id(folder_id)
            if folder and folder.is_icon_repo:
                return False
            if folder:
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                folder.name = new_name
                self.save()
                return True
            return False

    def delete_folder(self, folder_id: str) -> bool:
        """Data manager."""
        with self._save_lock:
            folder = self.data.get_folder_by_id(folder_id)
            if folder and not folder.is_system:
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                self.data.folders.remove(folder)
                self.save()
                return True
            return False

    def reorder_folders(self, folder_ids: list[str]):
        """Data manager."""
        with self._save_lock:
            self._mark_history("\u914d\u7f6e\u53d8\u66f4")
            order_map = {fid: i for i, fid in enumerate(folder_ids)}
            for folder in self.data.folders:
                if folder.id in order_map:
                    folder.order = order_map[folder.id]
            self.data.folders.sort(key=lambda f: f.order)
            self.save()

    def add_shortcut(self, folder_id: str, shortcut: ShortcutItem) -> bool:
        """Data manager."""
        with self._save_lock:
            folder = self.data.get_folder_by_id(folder_id)
            if folder:
                if getattr(folder, "is_icon_repo", False):
                    shortcut._icon_repo_source = "user"
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                max_order = max((s.order for s in folder.items), default=-1)
                shortcut.order = max_order + 1
                folder.items.append(shortcut)
                self._persist_folder_changes(folder, immediate=True)
                return True
            return False

    def add_shortcuts(self, folder_id: str, shortcuts: list[ShortcutItem]) -> int:
        """Data manager."""
        with self._save_lock:
            folder = self.data.get_folder_by_id(folder_id)
            if folder and shortcuts:
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                max_order = max((s.order for s in folder.items), default=-1)
                count = 0
                for shortcut in shortcuts:
                    if getattr(folder, "is_icon_repo", False):
                        shortcut._icon_repo_source = "user"
                    shortcut.order = max_order + 1 + count
                    folder.items.append(shortcut)
                    count += 1
                self._persist_folder_changes(folder, immediate=True)
                return count
            return 0

    def _find_shortcut_with_folder(self, shortcut_id: str):
        with self._save_lock:
            for folder in self.data.folders:
                for item in folder.items:
                    if item.id == shortcut_id:
                        return folder, item
            return None, None

    def get_shortcut_by_id(self, shortcut_id: str):
        """Data manager."""
        _, item = self._find_shortcut_with_folder(shortcut_id)
        return item

    def _persist_folder_changes(self, *folders, immediate: bool = True) -> bool:
        icon_changed = any(getattr(folder, "is_icon_repo", False) for folder in folders if folder is not None)
        main_changed = any(not getattr(folder, "is_icon_repo", False) for folder in folders if folder is not None)
        ok = True
        if icon_changed:
            ok = self.save_icon_repo() and ok
        if main_changed:
            ok = self.save(immediate=immediate) and ok
        return ok

    def recalculate_smart_order(self, folder_id: str | None = None) -> dict:
        """Data manager."""
        with self._save_lock:
            self._mark_history("\u914d\u7f6e\u53d8\u66f4")
            target_folders = []
            if folder_id:
                folder = self.data.get_folder_by_id(folder_id)
                if folder and not folder.is_dock:
                    target_folders = [folder]
            else:
                target_folders = list(self.data.get_pages())

            updated = 0
            with self.batch_update(immediate=True):
                for folder in target_folders:
                    updated += self._apply_smart_order(folder)
                if updated:
                    self._batch_dirty = True

            return {"folders": len(target_folders), "updated": updated}

    def move_shortcut_to_folder(self, shortcut_id: str, target_folder_id: str) -> bool:
        """Data manager."""
        with self._save_lock:
            source_folder = None
            target_shortcut = None

            for folder in self.data.folders:
                for item in folder.items:
                    if item.id == shortcut_id:
                        source_folder = folder
                        target_shortcut = item
                        break
                if source_folder:
                    break

            if not source_folder or not target_shortcut:
                return False
            if self._is_system_icon_repo_item(target_shortcut):
                return False

            target_folder = self.data.get_folder_by_id(target_folder_id)
            if not target_folder:
                return False

            if source_folder.id == target_folder.id:
                return False

            self._mark_history("\u914d\u7f6e\u53d8\u66f4")

            source_folder.items.remove(target_shortcut)

            max_order = max((s.order for s in target_folder.items), default=-1)
            target_shortcut.order = max_order + 1
            target_folder.items.append(target_shortcut)

            self._persist_folder_changes(source_folder, target_folder, immediate=True)
            return True

    def delete_shortcuts_batch(self, shortcut_ids: list[str]) -> dict:
        """Data manager."""
        with self._save_lock:
            wanted = [sid for sid in shortcut_ids or [] if sid]
            wanted_set = set(wanted)
            removed_ids = []
            if not wanted_set:
                return {"requested": 0, "success": 0, "failed": 0, "affected_ids": []}

            icon_touched = False
            with self.batch_update(immediate=True):
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                for folder in self.data.folders:
                    kept = []
                    for item in folder.items:
                        if item.id in wanted_set:
                            if self._is_system_icon_repo_item(item):
                                kept.append(item)
                                continue
                            removed_ids.append(item.id)
                            icon_touched = icon_touched or getattr(folder, "is_icon_repo", False)
                        else:
                            kept.append(item)
                    if len(kept) != len(folder.items):
                        folder.items = kept
                if removed_ids:
                    self._batch_dirty = True
            if icon_touched:
                self.save_icon_repo()

            return {
                "requested": len(wanted),
                "success": len(removed_ids),
                "failed": len(wanted_set - set(removed_ids)),
                "affected_ids": removed_ids,
            }

    def move_shortcuts_batch(self, shortcut_ids: list[str], target_folder_id: str) -> dict:
        """Data manager."""
        with self._save_lock:
            target_folder = self.data.get_folder_by_id(target_folder_id)
            wanted = [sid for sid in shortcut_ids or [] if sid]
            if not target_folder or not wanted:
                return {"requested": len(wanted), "success": 0, "failed": len(wanted), "affected_ids": []}

            moved = []
            icon_touched = getattr(target_folder, "is_icon_repo", False)
            with self.batch_update(immediate=True):
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                for shortcut_id in wanted:
                    source_folder, item = self._find_shortcut_with_folder(shortcut_id)
                    if not source_folder or not item or source_folder.id == target_folder.id:
                        continue
                    if self._is_system_icon_repo_item(item):
                        continue
                    icon_touched = icon_touched or getattr(source_folder, "is_icon_repo", False)
                    source_folder.items.remove(item)
                    if getattr(target_folder, "is_icon_repo", False):
                        item._icon_repo_source = "user"
                    elif getattr(source_folder, "is_icon_repo", False):
                        self._strip_icon_repo_runtime_source(item)
                    max_order = max((s.order for s in target_folder.items), default=-1)
                    item.order = max_order + 1
                    target_folder.items.append(item)
                    moved.append(item.id)
                if moved:
                    self._batch_dirty = True
            if moved and icon_touched:
                self.save_icon_repo()

            return {
                "requested": len(wanted),
                "success": len(moved),
                "failed": len(set(wanted) - set(moved)),
                "affected_ids": moved,
            }

    def copy_shortcuts_batch(self, shortcut_ids: list[str], target_folder_id: str) -> dict:
        """Copy shortcuts to a folder, assigning fresh ids and preserving the sources."""
        with self._save_lock:
            target_folder = self.data.get_folder_by_id(target_folder_id)
            wanted = [sid for sid in shortcut_ids or [] if sid]
            if not target_folder or not wanted:
                return {"requested": len(wanted), "success": 0, "failed": len(wanted), "affected_ids": []}

            copied = []
            max_order = max((s.order for s in target_folder.items), default=-1)
            for shortcut_id in wanted:
                source_folder, item = self._find_shortcut_with_folder(shortcut_id)
                if not source_folder or not item:
                    continue
                new_item = copy.deepcopy(item)
                new_item.id = str(uuid.uuid4())
                if getattr(target_folder, "is_icon_repo", False):
                    new_item._icon_repo_source = "user"
                else:
                    self._strip_icon_repo_runtime_source(new_item)
                max_order += 1
                new_item.order = max_order
                target_folder.items.append(new_item)
                copied.append(new_item.id)

            if copied:
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                self._persist_folder_changes(target_folder, immediate=True)

            return {
                "requested": len(wanted),
                "success": len(copied),
                "failed": max(0, len(wanted) - len(copied)),
                "affected_ids": copied,
            }

    def set_shortcuts_enabled_batch(self, shortcut_ids: list[str], enabled: bool) -> dict:
        """set_shortcuts_enabled_batch"""
        with self._save_lock:
            wanted = [sid for sid in shortcut_ids or [] if sid]
            wanted_set = set(wanted)
            changed = []
            if not wanted_set:
                return {"requested": 0, "success": 0, "failed": 0, "affected_ids": []}

            icon_touched = False
            with self.batch_update(immediate=True):
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                for folder in self.data.folders:
                    for item in folder.items:
                        if item.id in wanted_set:
                            if self._is_system_icon_repo_item(item):
                                continue
                            item.enabled = bool(enabled)
                            changed.append(item.id)
                            icon_touched = icon_touched or getattr(folder, "is_icon_repo", False)
                if changed:
                    self._batch_dirty = True
            if icon_touched:
                self.save_icon_repo()

            return {
                "requested": len(wanted),
                "success": len(changed),
                "failed": len(wanted_set - set(changed)),
                "affected_ids": changed,
            }

    def update_shortcut(self, folder_id: str, shortcut: ShortcutItem) -> bool:
        """update_shortcut"""
        with self._save_lock:
            folder = self.data.get_folder_by_id(folder_id)
            if folder:
                for i, item in enumerate(folder.items):
                    if item.id == shortcut.id:
                        if self._is_system_icon_repo_item(item):
                            return False
                        if getattr(folder, "is_icon_repo", False):
                            shortcut._icon_repo_source = "user"
                        self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                        folder.items[i] = shortcut
                        self._persist_folder_changes(folder, immediate=True)
                        return True
            return False

    def delete_shortcut(self, folder_id: str, shortcut_id: str) -> bool:
        """delete_shortcut"""
        with self._save_lock:
            folder = self.data.get_folder_by_id(folder_id)
            if folder:
                for i, item in enumerate(folder.items):
                    if item.id == shortcut_id:
                        if self._is_system_icon_repo_item(item):
                            return False
                        self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                        folder.items.pop(i)
                        self._persist_folder_changes(folder, immediate=True)
                        return True
            return False

    def reorder_shortcuts(self, folder_id: str, shortcut_ids: list[str]):
        """reorder_shortcuts"""
        with self._save_lock:
            folder = self.data.get_folder_by_id(folder_id)
            if folder:
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                if getattr(folder, "is_icon_repo", False):
                    user_items = [item for item in folder.items if not self._is_system_icon_repo_item(item)]
                    user_id_set = {item.id for item in user_items}
                    user_ids = [sid for sid in shortcut_ids if sid in user_id_set]
                    order_map = {sid: i for i, sid in enumerate(user_ids)}
                    for item in user_items:
                        if item.id in order_map:
                            item.order = order_map[item.id]
                    system_items = [item for item in folder.items if self._is_system_icon_repo_item(item)]
                    folder.items = sorted(system_items, key=lambda x: x.order) + sorted(
                        user_items, key=lambda x: x.order
                    )
                else:
                    order_map = {sid: i for i, sid in enumerate(shortcut_ids)}
                    for item in folder.items:
                        if item.id in order_map:
                            item.order = order_map[item.id]
                    folder.items.sort(key=lambda x: x.order)
                self._persist_folder_changes(folder, immediate=False)

    def update_settings(self, **kwargs):
        """update_settings"""
        with self._save_lock:
            changed = False

            if any(key.startswith("popup_trigger_") or key.startswith("popup_special_trigger_") for key in kwargs):
                preview = copy.copy(self.data.settings)
                for key, value in kwargs.items():
                    if hasattr(preview, key):
                        setattr(preview, key, value)
                kwargs = {**kwargs, **normalize_trigger_settings(preview)}

            for key, value in kwargs.items():
                if hasattr(self.data.settings, key):
                    current_value = getattr(self.data.settings, key)

                    if current_value is value:
                        if isinstance(value, list | dict | set):
                            changed = True
                        continue

                    if current_value == value:
                        continue

                    setattr(self.data.settings, key, value)
                    changed = True

            if changed:
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                self.save(immediate=True)

    def get_settings(self) -> AppSettings:
        """get_settings"""
        with self._save_lock:
            set_language(getattr(self.data.settings, "language", "zh_CN"))
            snapshot = copy.copy(self.data.settings)
            # 深拷贝可变列表字段，防止调用者修改列表污染原始数据
            snapshot.enabled_plugins = list(snapshot.enabled_plugins)
            snapshot.favorite_commands = list(snapshot.favorite_commands)
            snapshot.disabled_builtin_commands = list(snapshot.disabled_builtin_commands)
            return snapshot

    def set_language(self, language: str, immediate: bool = True) -> str:
        """Set the application language without requiring a UI switch control."""
        normalized = normalize_language(language)
        with self._save_lock:
            if getattr(self.data.settings, "language", "zh_CN") != normalized:
                self.data.settings.language = normalized
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                self.save(immediate=immediate)
        set_language(normalized)
        return normalized

    def clean_icon_cache(self, dry_run: bool = False) -> dict:
        """清理图标缓存中的无用、重复和非法文件。

        Delegates to ``self.icon_repository.clean()`` for the actual file
        iteration and removal logic.
        """
        if not self.icons_dir.exists():
            return {
                "exe_files_removed": 0, "exe_files_size_mb": 0,
                "large_files_removed": 0, "large_files_size_mb": 0,
                "orphan_files_removed": 0, "orphan_files_size_mb": 0,
                "duplicate_files_removed": 0, "duplicate_files_size_mb": 0,
                "total_removed": 0, "total_size_freed_mb": 0,
                "dry_run": dry_run,
            }

        with self._save_lock:
            used_icons = set()
            for folder in self.data.folders:
                for item in folder.items:
                    if item.icon_path:
                        used_icons.add(os.path.normcase(os.path.abspath(item.icon_path)))

        return self._get_icon_repository().clean(used_icons, dry_run=dry_run)

    def get_icon_cache_stats(self) -> dict:
        """get_icon_cache_stats — delegates to ``self.icon_repository.get_stats()``."""
        return self._get_icon_repository().get_stats()

    def get_all_cache_paths(self) -> dict:
        """get_all_cache_paths"""
        import winreg

        cache_info = {
            "app_data_dir": str(self.app_dir),
            "icons_dir": str(self.icons_dir),
            "files": [],
            "directories": [],
            "registry_keys": [],
        }

        if self.app_dir.exists():
            cache_info["directories"].append(str(self.app_dir))
            for item in self.app_dir.iterdir():
                cache_info["files"].append(str(item))

        if self.icons_dir.exists():
            cache_info["directories"].append(str(self.icons_dir))

        registry_keys = [
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ]

        for key_path in registry_keys:
            try:
                handle = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
                winreg.CloseKey(handle)
                cache_info["registry_keys"].append(key_path)
            except OSError:
                logger.debug("打开注册表键失败: %s", key_path, exc_info=True)

        return cache_info

    def factory_reset(self, callback=None) -> dict:
        """factory_reset"""
        import winreg

        with self._save_lock:
            stats = {"files_removed": 0, "dirs_removed": 0, "registry_keys_removed": 0, "errors": []}

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
                    winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS
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
                remove_children_safely(self.icons_dir, "icons")
            except Exception as e:
                stats["errors"].append(f"Factory reset step failed: {e}")

            report("Removing app data...", 0.6)
            try:
                remove_children_safely(self.app_dir, "app data")
            except Exception as e:
                stats["errors"].append(f"Factory reset step failed: {e}")

            report("Resetting in-memory configuration...", 0.9)
            try:
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                self.data = AppData()
                self._last_saved_data_dict = None
            except Exception as e:
                stats["errors"].append(f"Factory reset step failed: {e}")

            # Persist the clean state to disk directly
            data_file = self.app_dir / "data.json"
            try:
                data_file.parent.mkdir(parents=True, exist_ok=True)
                default_data = AppData().to_dict()
                with open(data_file, "w", encoding="utf-8") as f:
                    json.dump(default_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                stats["errors"].append(f"Factory reset persist failed: {e}")

            return stats

    def backup_full_config(self, save_path: str) -> bool:
        """backup_full_config"""
        with self._save_lock:
            try:
                if not self.save(immediate=True):
                    return False

                with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    data_dict = self._main_data_dict()

                    bg_path = getattr(self.data.settings, "custom_bg_path", "")
                    if bg_path and os.path.exists(bg_path):
                        ext = os.path.splitext(bg_path)[1]
                        arc_bg_name = f"background{ext}"
                        zf.write(bg_path, arc_bg_name)
                        data_dict["settings"]["custom_bg_path"] = arc_bg_name

                    zf.writestr("data.json", json.dumps(data_dict, ensure_ascii=False, indent=2))
                    icon_repo_folder = self.data.get_folder_by_id("icon_repo")
                    icon_repo_items = [
                        item
                        for item in getattr(icon_repo_folder, "items", [])
                        if not self._is_system_icon_repo_item(item)
                    ]
                    icon_repo_dict = {
                        "version": "1.0",
                        "items": [item.to_dict() for item in icon_repo_items],
                    }
                    zf.writestr("icon_repo.json", json.dumps(icon_repo_dict, ensure_ascii=False, indent=2))

                    self._get_package_service().write_extra_config_files(zf)

                    if self.icons_dir.exists():
                        for file_path in self.icons_dir.iterdir():
                            if file_path.is_file():
                                zf.write(file_path, f"icons/{file_path.name}")

                return True
            except Exception as e:
                logger.error("backup_full_config failed: %s", e)
                return False

    # ── Transaction journal helpers ────────────────────────────────

    def _detect_stale_transaction_journal(self) -> None:
        """Check for a stale transaction journal from a previous crash.

        If a journal file exists at startup, the previous session likely
        crashed mid-transaction.  We log a warning and attempt to restore
        from the most recent automatic backup if data.json is corrupted
        or missing.
        """
        journal_path = self.recovery_dir / "transaction_journal.json"
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
            data_ok = self.data_file.exists()
            if data_ok:
                try:
                    json.loads(self.data_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    data_ok = False
            if not data_ok:
                logger.warning("data.json 损坏或缺失，尝试从最近备份恢复...")
                self._attempt_restore_from_latest_backup()
            else:
                logger.info("data.json 完整性正常，清除遗留事务日志")
            try:
                journal_path.unlink()
            except OSError as exc:
                logger.debug("清除遗留事务日志失败: %s", exc)
        except Exception as exc:
            logger.warning("处理遗留事务日志失败: %s", exc, exc_info=True)

    def _attempt_restore_from_latest_backup(self) -> None:
        """Try to restore data.json from the most recent automatic backup."""
        if not self.auto_backup_dir.is_dir():
            logger.warning("无自动备份目录，无法恢复")
            return
        backups = sorted(self.auto_backup_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not backups:
            logger.warning("自动备份目录为空，无法恢复")
            return
        latest = backups[0]
        try:
            backup_data = json.loads(latest.read_text(encoding="utf-8"))
            if not isinstance(backup_data, dict):
                logger.warning("最新备份 %s 格式无效", latest.name)
                return
            import shutil
            shutil.copy2(str(latest), str(self.data_file))
            logger.info("已从备份 %s 恢复 data.json", latest.name)
        except Exception as exc:
            logger.error("从备份恢复 data.json 失败: %s", exc, exc_info=True)

    def _write_transaction_journal(self, operation: str, extra: dict | None = None) -> None:
        """Write a pre-transaction state snapshot to the recovery directory.

        The journal records the current data.json hash, icon directory file
        count, and timestamp.  If the application crashes mid-transaction,
        the journal can be used to detect an inconsistent state on next
        startup.
        """
        journal_path = self.recovery_dir / "transaction_journal.json"
        try:
            self.recovery_dir.mkdir(parents=True, exist_ok=True)
            data_hash = ""
            if self.data_file.exists():
                import hashlib

                data_hash = hashlib.sha256(self.data_file.read_bytes()).hexdigest()
            icon_count = 0
            if self.icons_dir.exists():
                icon_count = sum(1 for p in self.icons_dir.iterdir() if p.is_file())
            journal = {
                "operation": operation,
                "timestamp": datetime.now().isoformat(),
                "data_file_hash": data_hash,
                "icon_file_count": icon_count,
                "data_file_exists": self.data_file.exists(),
                "icons_dir_exists": self.icons_dir.exists(),
            }
            if extra:
                journal.update(extra)
            journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("write transaction journal failed: %s", exc, exc_info=True)

    def _clear_transaction_journal(self) -> None:
        """Remove the transaction journal after successful completion."""
        journal_path = self.recovery_dir / "transaction_journal.json"
        try:
            if journal_path.exists():
                journal_path.unlink()
        except Exception as exc:
            logger.debug("clear transaction journal failed: %s", exc, exc_info=True)

    def _verify_transaction_consistency(self) -> dict:
        """Post-transaction verification: compare in-memory state with disk.

        Returns a dict with ``consistent`` (bool) and ``issues`` (list).
        """
        issues: list[str] = []
        # Check that data.json on disk matches in-memory state.
        if self.data_file.exists():
            try:
                disk_data = json.loads(self.data_file.read_text(encoding="utf-8"))
                mem_data = self.data.to_dict() if hasattr(self.data, "to_dict") else {}
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

    def restore_full_config(self, backup_path: str) -> bool:
        """Data manager."""
        return self._restore_full_config_safe(backup_path)

    def _restore_full_config_safe(self, backup_path: str) -> bool:
        with self._save_lock:
            # Write pre-transaction journal for crash recovery.
            self._write_transaction_journal("restore_full_config", {"source": backup_path})
            report = self._reset_import_report()
            restored_bg_path = None
            try:
                if not os.path.exists(backup_path):
                    return False

                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                with zipfile.ZipFile(backup_path, "r") as zf:
                    safe_index = build_safe_zip_index(zf, report)
                    if not has_zip_entry(safe_index, "data.json"):
                        logger.warning("invalid backup file: missing data.json")
                        return False

                    data_json = read_zip_text(
                        zf,
                        safe_index,
                        "data.json",
                        max_bytes=MAX_CONFIG_BYTES,
                        report=report,
                        required=True,
                    )
                    if data_json is None:
                        return False
                    data_dict = sanitize_app_data_dict(json.loads(data_json), report)
                    restored_icon_repo_items = None
                    if has_zip_entry(safe_index, "icon_repo.json"):
                        icon_repo_json = read_zip_text(
                            zf,
                            safe_index,
                            "icon_repo.json",
                            max_bytes=MAX_CONFIG_BYTES,
                            report=report,
                            required=False,
                        )
                        if icon_repo_json is not None:
                            icon_repo_dict = json.loads(icon_repo_json)
                            icon_items = icon_repo_dict.get("items", []) if isinstance(icon_repo_dict, dict) else []
                            if isinstance(icon_items, list):
                                restored_icon_repo_items = [
                                    ShortcutItem.from_dict(item) for item in icon_items if isinstance(item, dict)
                                ]

                    install_root = Path(self.install_dir).resolve(strict=False)
                    app_root = Path(self.app_dir).resolve(strict=False)
                    icons_root = Path(self.icons_dir).resolve(strict=False)
                    temp_icons_dir = resolve_under(
                        install_root,
                        tempfile.mkdtemp(prefix="ql_restore_icons_", dir=str(install_root)),
                    )
                    bg_rel_path = data_dict.get("settings", {}).get("custom_bg_path", "")
                    if bg_rel_path and not os.path.isabs(bg_rel_path):
                        normalized_bg = normalize_zip_name(bg_rel_path)
                        if (
                            normalized_bg
                            and has_zip_entry(safe_index, normalized_bg)
                            and is_allowed_background_path(normalized_bg)
                        ):
                            bg_bytes = read_zip_bytes(
                                zf,
                                safe_index,
                                normalized_bg,
                                max_bytes=MAX_BACKGROUND_BYTES,
                                report=report,
                            )
                            if bg_bytes is None:
                                data_dict["settings"]["custom_bg_path"] = ""
                            else:
                                target_bg_path = resolve_under(
                                    app_root,
                                    app_root / f"restored_bg_{os.path.basename(bg_rel_path)}",
                                )
                                with open(target_bg_path, "wb") as f:
                                    f.write(bg_bytes)
                                restored_bg_path = target_bg_path
                                data_dict["settings"]["custom_bg_path"] = str(target_bg_path)
                        else:
                            if normalized_bg:
                                skip_file(report, normalized_bg, "missing or unsupported background image")
                            data_dict["settings"]["custom_bg_path"] = ""

                    for name in list(safe_index.keys()):
                        if name.startswith("icons/") and not name.endswith("/"):
                            if not is_allowed_icon_path(name):
                                skip_file(report, name, "unsupported icon extension")
                                continue
                            icon_bytes = read_zip_bytes(
                                zf,
                                safe_index,
                                name,
                                max_bytes=MAX_ICON_BYTES,
                                report=report,
                            )
                            if icon_bytes is None:
                                continue
                            filename = os.path.basename(name)
                            if filename:
                                target_path = resolve_under(temp_icons_dir, temp_icons_dir / filename)
                                with open(target_path, "wb") as f:
                                    f.write(icon_bytes)

                    restored_data = AppData.from_dict(data_dict)
                    legacy_icon_repo = None
                    for folder in list(restored_data.folders):
                        if getattr(folder, "is_icon_repo", False) or folder.id == "icon_repo":
                            restored_data.folders.remove(folder)
                            legacy_icon_repo = folder
                            break
                    if restored_icon_repo_items is None:
                        restored_icon_repo_items = list(getattr(legacy_icon_repo, "items", []) or [])
                    apply_config_repairs(restored_data)

                    old_data = self.data
                    old_saved = getattr(self, "_last_saved_data_dict", None)
                    old_config_status = dict(getattr(self, "_config_status", {}) or {})
                    backup_icons_dir = None
                    try:
                        if self.icons_dir.exists():
                            backup_icons_dir = resolve_under(
                                icons_root.parent,
                                icons_root.with_name(f"{icons_root.name}_backup_restore"),
                            )
                            if backup_icons_dir.exists():
                                safe_rmtree_child(icons_root.parent, backup_icons_dir)
                            icons_root.replace(backup_icons_dir)

                        icons_root.mkdir(parents=True, exist_ok=True)
                        for item in temp_icons_dir.iterdir():
                            target_icon = resolve_under(icons_root, icons_root / item.name)
                            shutil.move(str(resolve_under(temp_icons_dir, item)), str(target_icon))

                        self.data = restored_data
                        self._write_icon_repo_items(restored_icon_repo_items or [])
                        self._icon_repo_folder = self._load_icon_repo_folder()
                        self._attach_icon_repo_folder()
                        if not self.save(immediate=True):
                            raise RuntimeError("save restored config failed")
                        set_imported_items(report, sum(len(f.items) for f in self.data.folders))

                        self._get_package_service().restore_extra_config_files(zf, safe_index, report)
                    except Exception:
                        self.data = old_data
                        self._last_saved_data_dict = old_saved
                        self._config_status = old_config_status
                        if icons_root.exists():
                            safe_rmtree_child(icons_root.parent, icons_root)
                        if backup_icons_dir and backup_icons_dir.exists():
                            backup_icons_dir.replace(icons_root)
                        if restored_bg_path and restored_bg_path.exists():
                            try:
                                restored_bg_path.unlink()
                            except Exception as cleanup_error:
                                logger.debug(
                                    "cleanup restored background failed %s: %s", restored_bg_path, cleanup_error
                                )
                            restored_bg_path = None
                        raise
                    finally:
                        if temp_icons_dir.exists():
                            safe_rmtree_child(install_root, temp_icons_dir)

                    if backup_icons_dir and backup_icons_dir.exists():
                        safe_rmtree_child(backup_icons_dir.parent, backup_icons_dir)

                    # Post-transaction: clear journal and verify consistency.
                    consistency = self._verify_transaction_consistency()
                    if not consistency["consistent"]:
                        logger.warning("post-restore consistency issues: %s", consistency["issues"])
                    self._clear_transaction_journal()
                    return True

            except (UnsafeZipError, ValueError, json.JSONDecodeError) as e:
                if restored_bg_path and restored_bg_path.exists():
                    try:
                        restored_bg_path.unlink()
                    except Exception as cleanup_error:
                        logger.debug("cleanup restored background failed %s: %s", restored_bg_path, cleanup_error)
                logger.warning("restore_full_config rejected unsafe backup: %s", e)
                return False
            except Exception as e:
                if restored_bg_path and restored_bg_path.exists():
                    try:
                        restored_bg_path.unlink()
                    except Exception as cleanup_error:
                        logger.debug("cleanup restored background failed %s: %s", restored_bg_path, cleanup_error)
                logger.exception("restore_full_config failed: %s", e)
                return False

    def export_shareable_config(self, save_path: str) -> bool:
        """Data manager."""
        with self._save_lock:
            try:
                self.save(immediate=True)

                data_dict = self.data.to_dict()

                shareable_dict = {"version": data_dict.get("version", "1.0"), "items": []}

                icon_entries = []  # [(source_path, mode, archive_name)]

                folders = data_dict.get("folders", [])
                for folder in folders:
                    items = folder.get("items", folder.get("shortcuts", []))
                    for shortcut in items:
                        shortcut_type = shortcut.get("type", "file")
                        if shortcut_type in ["hotkey", "command", "url"]:
                            original_id = shortcut.get("id") or str(uuid.uuid4())
                            item_copy = {
                                "id": original_id,
                                "name": shortcut.get("name", ""),
                                "type": shortcut.get("type", ""),
                                "order": shortcut.get("order", 0),
                                "enabled": shortcut.get("enabled", True),
                                "tags": shortcut.get("tags", []),
                                "last_used_at": shortcut.get("last_used_at", 0.0),
                                "use_count": shortcut.get("use_count", 0),
                                "alias": shortcut.get("alias", ""),
                                "target_path": shortcut.get("target_path", ""),
                                "target_args": shortcut.get("target_args", ""),
                                "working_dir": shortcut.get("working_dir", ""),
                                "hotkey": shortcut.get("hotkey", ""),
                                "hotkey_modifiers": shortcut.get("hotkey_modifiers", []),
                                "hotkey_key": shortcut.get("hotkey_key", ""),
                                "url": shortcut.get("url", ""),
                                "preferred_browser_path": shortcut.get("preferred_browser_path", ""),
                                "preferred_browser_args": shortcut.get("preferred_browser_args", ""),
                                "command": shortcut.get("command", ""),
                                "command_type": shortcut.get("command_type", "cmd"),
                                "trigger_mode": shortcut.get("trigger_mode", "immediate"),
                                "show_window": shortcut.get("show_window", False),
                                "run_as_admin": shortcut.get("run_as_admin", False),
                                "command_variables_enabled": shortcut.get("command_variables_enabled", False),
                                "icon_data": shortcut.get("icon_data", ""),
                                "icon_invert_light": shortcut.get("icon_invert_light", False),
                                "icon_invert_dark": shortcut.get("icon_invert_dark", False),
                                "icon_invert_with_theme": shortcut.get("icon_invert_with_theme", False),
                                "icon_invert_current": shortcut.get("icon_invert_current", False),
                                "icon_invert_theme_when_set": shortcut.get("icon_invert_theme_when_set", ""),
                            }

                            icon_path = shortcut.get("icon_path", "")
                            if icon_path:
                                actual_path = icon_path.split(",")[0] if "," in icon_path else icon_path

                                if os.path.exists(actual_path):
                                    ext = os.path.splitext(actual_path)[1].lower()
                                    if ext in [".exe", ".dll"]:
                                        new_icon_name = f"{original_id}.png"
                                        icon_entries.append((actual_path, "extract", new_icon_name))
                                    else:
                                        original_ext = os.path.splitext(actual_path)[1] or ".png"
                                        new_icon_name = f"{original_id}{original_ext}"
                                        icon_entries.append((actual_path, "copy", new_icon_name))

                                    item_copy["icon_path"] = f"icons/{new_icon_name}"
                                else:
                                    item_copy["icon_path"] = ""
                            else:
                                item_copy["icon_path"] = ""

                            shareable_dict["items"].append(item_copy)

                with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr("config.json", json.dumps(shareable_dict, ensure_ascii=False, indent=2))

                    for orig_path, mode, new_name in icon_entries:
                        try:
                            if mode == "extract":
                                from core.icon_extractor import IconExtractor

                                pixmap = IconExtractor.from_file(orig_path, size=256, return_image=False)
                                if pixmap and not pixmap.isNull():
                                    ext = os.path.splitext(new_name)[1].lower() or ".png"
                                    with tempfile.NamedTemporaryFile(
                                        suffix=ext, prefix="ql_icon_", delete=False
                                    ) as tmp:
                                        tmp_path = tmp.name
                                    try:
                                        success = pixmap.save(tmp_path, "PNG")
                                        if success:
                                            zf.write(tmp_path, f"icons/{new_name}")
                                    finally:
                                        try:
                                            os.remove(tmp_path)
                                        except OSError:
                                            logger.debug("删除临时图标文件失败: %s", tmp_path, exc_info=True)
                            else:
                                zf.write(orig_path, f"icons/{new_name}")
                        except Exception as e:
                            logger.warning("failed to add icon %s: %s", orig_path, e)

                return True

            except Exception as e:
                logger.exception("export_shareable_config failed: %s", e)
                return False

    def import_shareable_config(self, import_path: str, merge: bool = True) -> bool:
        """Data manager."""
        return self._import_shareable_config_safe(import_path, merge=merge)

    def _import_shareable_config_transactional(self, import_path: str, merge: bool, report: dict) -> bool:
        temp_icons_dir = None
        moved_icons: list[Path] = []
        original_data_dict: dict | None = None
        install_root = Path(self.install_dir).resolve(strict=False)
        try:
            if not os.path.exists(import_path):
                return False
            if not zipfile.is_zipfile(import_path):
                return False

            # Write pre-transaction journal for crash recovery.
            self._write_transaction_journal("import_shareable_config", {"source": import_path, "merge": merge})

            with self._save_lock:
                self._mark_history("\u914d\u7f6e\u53d8\u66f4")
                original_data_dict = self.data.to_dict()
                icons_root = Path(self.icons_dir).resolve(strict=False)
                temp_icons_dir = resolve_under(
                    install_root,
                    tempfile.mkdtemp(prefix="ql_import_icons_", dir=str(install_root)),
                )
                with zipfile.ZipFile(import_path, "r") as zf:
                    safe_index = build_safe_zip_index(zf, report)
                    config_text = read_zip_text(
                        zf,
                        safe_index,
                        "config.json",
                        max_bytes=MAX_CONFIG_BYTES,
                        report=report,
                        required=True,
                    )
                    if config_text is None:
                        return False
                    import_dict = json.loads(config_text)
                    import_items = import_dict.get("items", []) if isinstance(import_dict, dict) else []
                    if not isinstance(import_items, list) or not import_items:
                        return False

                    staged_shortcuts = []
                    staged_icons: list[tuple[Path, Path]] = []
                    for item_dict in import_items[:2048]:
                        if not isinstance(item_dict, dict):
                            continue
                        item_type = item_dict.get("type", "file")
                        if item_type not in ["hotkey", "command", "url"]:
                            continue
                        item_dict = dict(item_dict)
                        item_dict["id"] = str(uuid.uuid4())
                        item_dict["run_as_admin"] = False
                        icon_path = item_dict.get("icon_path", "")
                        if icon_path and icon_path.startswith("icons/"):
                            if has_zip_entry(safe_index, icon_path) and is_allowed_icon_path(icon_path):
                                icon_ext = os.path.splitext(icon_path)[1] or ".png"
                                icon_filename = f"{item_dict['id']}{icon_ext}"
                                temp_icon_path = resolve_under(temp_icons_dir, temp_icons_dir / icon_filename)
                                local_icon_path = resolve_under(icons_root, icons_root / icon_filename)
                                icon_bytes = read_zip_bytes(
                                    zf,
                                    safe_index,
                                    icon_path,
                                    max_bytes=MAX_ICON_BYTES,
                                    report=report,
                                )
                                if icon_bytes is not None:
                                    with open(temp_icon_path, "wb") as f:
                                        f.write(icon_bytes)
                                    item_dict["icon_path"] = str(local_icon_path)
                                    staged_icons.append((temp_icon_path, local_icon_path))
                                else:
                                    item_dict["icon_path"] = ""
                            else:
                                skip_file(report, icon_path, "missing or unsupported icon")
                                item_dict["icon_path"] = ""
                        else:
                            item_dict["icon_path"] = ""

                        staged_shortcuts.append(ShortcutItem.from_dict(item_dict))

                    imported_count = len(staged_shortcuts)
                    if imported_count <= 0:
                        return False

                    import_folder_name = "\u5bfc\u5165\u56fe\u6807"
                    legacy_import_folder_names = {import_folder_name, "Imported Icons"}
                    target_folder = None
                    for folder in self.data.folders:
                        if folder.name in legacy_import_folder_names:
                            target_folder = folder
                            folder.name = import_folder_name
                            break

                    if not target_folder:
                        max_folder_order = max((f.order for f in self.data.folders), default=0)
                        target_folder = Folder(name=import_folder_name, order=max_folder_order + 1)
                        append_target_folder = True
                    else:
                        append_target_folder = False

                    self.icons_dir.mkdir(parents=True, exist_ok=True)
                    for temp_icon_path, local_icon_path in staged_icons:
                        shutil.move(str(temp_icon_path), str(local_icon_path))
                        moved_icons.append(local_icon_path)

                    if append_target_folder:
                        self.data.folders.append(target_folder)
                    if not merge:
                        target_folder.items.clear()
                    max_order = max((s.order for s in target_folder.items), default=-1)
                    for shortcut in staged_shortcuts:
                        max_order += 1
                        shortcut.order = max_order
                        target_folder.items.append(shortcut)

                self._apply_config_repairs_to_current()
                if not self.save(immediate=True):
                    raise RuntimeError("failed to save imported shareable config")
                set_imported_items(report, imported_count)

                # Post-transaction: clear journal and verify consistency.
                consistency = self._verify_transaction_consistency()
                if not consistency["consistent"]:
                    logger.warning("post-import consistency issues: %s", consistency["issues"])
                self._clear_transaction_journal()
                return imported_count > 0

        except Exception as e:
            if original_data_dict is not None:
                self.data = AppData.from_dict(original_data_dict)
                self._pending_history_action = "\u914d\u7f6e\u53d8\u66f4"
                self._pending_history_summary = ""
            for icon_path in moved_icons:
                try:
                    if icon_path.exists():
                        icon_path.unlink()
                except Exception as cleanup_error:
                    logger.debug("cleanup imported icon failed %s: %s", icon_path, cleanup_error)
            if isinstance(e, UnsafeZipError | ValueError | json.JSONDecodeError):
                logger.warning("import_shareable_config rejected unsafe package: %s", e)
            else:
                logger.exception("import_shareable_config failed: %s", e)
            return False
        finally:
            if temp_icons_dir and temp_icons_dir.exists():
                try:
                    safe_rmtree_child(install_root, temp_icons_dir)
                except Exception as cleanup_error:
                    logger.debug("cleanup import temp icons failed %s: %s", temp_icons_dir, cleanup_error)

    def _import_shareable_config_safe(self, import_path: str, merge: bool = True) -> bool:
        report = self._reset_import_report()
        return self._import_shareable_config_transactional(import_path, merge, report)

    def redirect_missing_icon_paths(self, new_icon_path: str) -> int:
        """Redirect missing icon paths to files found beside a newly fixed icon."""
        if not new_icon_path:
            return 0

        with self._save_lock:

            def _split_icon_location(path: str):
                raw = (path or "").strip()
                if not raw:
                    return "", ""
                if "," in raw:
                    file_part, suffix = raw.rsplit(",", 1)
                    suffix = suffix.strip()
                    if suffix.lstrip("-").isdigit():
                        return file_part.strip(), f",{suffix}"
                return raw, ""

            def _normalize_icon_file(path: str) -> str:
                return os.path.abspath(os.path.expanduser(os.path.expandvars(path or "")))

            def _supports_icon_index(path: str) -> bool:
                return os.path.splitext(path)[1].lower() in {".exe", ".dll", ".ico"}

            def _case_insensitive_child(directory: str, filename: str) -> str:
                try:
                    wanted = os.path.normcase(filename)
                    for entry in os.scandir(directory):
                        if entry.is_file() and os.path.normcase(entry.name) == wanted:
                            return entry.path
                except OSError:
                    return ""
                direct = os.path.join(directory, filename)
                if os.path.isfile(direct):
                    return direct
                return ""

            def _stem_match_child(directory: str, missing_file: str) -> str:
                missing_stem = os.path.splitext(os.path.basename(missing_file))[0]
                if not missing_stem:
                    return ""
                wanted_stem = os.path.normcase(missing_stem)
                preferred_exts = (".ico", ".png", ".jpg", ".jpeg", ".bmp", ".exe", ".dll")
                matches = []
                try:
                    for entry in os.scandir(directory):
                        if not entry.is_file():
                            continue
                        stem, ext = os.path.splitext(entry.name)
                        ext = ext.lower()
                        if ext not in preferred_exts or os.path.normcase(stem) != wanted_stem:
                            continue
                        matches.append(entry.path)
                except OSError:
                    return ""
                if not matches:
                    return ""
                priority = {ext: index for index, ext in enumerate(preferred_exts)}
                matches.sort(key=lambda path: priority.get(os.path.splitext(path)[1].lower(), 99))
                return matches[0]

            def _candidate_for_missing_icon(missing_file: str, search_dir: str) -> tuple[str, str]:
                filename = os.path.basename(missing_file)
                if not filename:
                    return "", ""
                exact = _case_insensitive_child(search_dir, filename)
                if exact:
                    return exact, "exact"
                stem_match = _stem_match_child(search_dir, missing_file)
                if stem_match:
                    return stem_match, "stem"
                return "", ""

            new_icon_file, _ = _split_icon_location(new_icon_path)
            new_icon_file = _normalize_icon_file(new_icon_file)
            if not new_icon_file or not os.path.isfile(new_icon_file):
                return 0

            new_dir = os.path.dirname(new_icon_file)
            count = 0

            for folder in self.data.folders:
                for item in folder.items:
                    if not item.icon_path:
                        continue
                    raw_icon_path = (item.icon_path or "").strip()
                    if os.path.normcase(raw_icon_path) == os.path.normcase(new_icon_path):
                        continue
                    item_icon_file, item_icon_suffix = _split_icon_location(raw_icon_path)
                    item_icon_file = _normalize_icon_file(item_icon_file)
                    if not item_icon_file or os.path.isfile(item_icon_file):
                        continue
                    candidate_file, match_kind = _candidate_for_missing_icon(item_icon_file, new_dir)
                    if not candidate_file:
                        continue
                    suffix = item_icon_suffix if _supports_icon_index(candidate_file) else ""
                    item.icon_path = f"{candidate_file}{suffix}"
                    count += 1
                    logger.debug(
                        "redirected missing icon path item=%s match=%s old=%r new=%r",
                        item.id,
                        match_kind,
                        raw_icon_path,
                        item.icon_path,
                    )

            if count:
                self.save(immediate=True)

            return count
