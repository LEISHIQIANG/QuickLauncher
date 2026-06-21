"""
Data manager
"""

import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from runtime_paths import app_root
from runtime_paths import config_dir as runtime_config_dir

from .backup_service import BackupService
from .config_history import ConfigHistoryManager
from .config_recovery import ConfigRecoveryReport
from .config_services import (
    ConfigBackupService,
    ConfigDataStore,
    ConfigPackageService,
    ConfigRecoveryService,
    IconRepository,
    SaveScheduler,
)
from .config_state import ConfigState
from .data_loader import DataLoader
from .data_models import (
    AppData,
    AppSettings,
    Folder,
    ShortcutItem,
)
from .folder_service import FolderService
from .i18n import set_language
from .icon_repository import IconRepositoryService
from .import_security import (
    new_import_report,
)
from .save_coordinator import SaveCoordinator
from .settings_service import SettingsService
from .shortcut_service import ShortcutService

if TYPE_CHECKING:
    from qt_compat import QTimer

logger = logging.getLogger(__name__)


class DataManager:
    """Data manager."""

    _instance: "DataManager | None" = None
    _instance_lock = threading.Lock()

    # Public paths (set in __init__).
    install_dir: Path
    app_dir: Path
    data_file: Path
    icon_repo_file: Path
    system_icons_file: Path
    icons_dir: Path
    auto_backup_dir: Path
    history_dir: Path
    recovery_dir: Path

    # Core state.
    data: AppData
    _initialized: bool
    _save_lock: threading.RLock
    _write_lock: threading.Lock
    _save_timer: "QTimer | None"
    _save_pending: bool
    _save_delay: float
    _batch_depth: int
    _batch_dirty: bool
    _batch_force_immediate: bool
    _runtime_revision: int
    _pending_history_action: str
    _pending_history_summary: str
    _suppress_next_history: bool
    _last_saved_data_dict: "dict | None"
    _config_status: "dict[str, Any]"
    _last_import_report: "dict[str, Any]"
    _icon_repo_folder: Folder
    _deleted_system_ids: "set[str]"
    _max_auto_backups: int
    _max_history_snapshots: int

    # Lazily-instantiated sub-services.
    config_store: "ConfigDataStore | None"
    backup_service: "ConfigBackupService | None"
    package_service: "ConfigPackageService | None"
    recovery_service: "ConfigRecoveryService | None"
    save_scheduler: "SaveScheduler | None"
    icon_repository: "IconRepository | None"
    folder_service: "FolderService | None"
    icon_repository_service: "IconRepositoryService | None"
    shortcut_service: "ShortcutService | None"
    data_loader: "DataLoader | None"
    history_manager: "ConfigHistoryManager | None"

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

        install_dir = app_root()

        self.install_dir = install_dir
        self.app_dir = runtime_config_dir()
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
        self._save_delay = 0.5  # Merge rapid consecutive saves within 500 ms.

        # W2 stage A: shared coordination state owned by ConfigState.
        self._config_state = ConfigState()
        self._config_state.attach_to_host(self)

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
        self._get_folder_service()
        self._get_icon_repository_service()
        self._get_shortcut_service()
        self._get_data_loader()
        self._get_settings_service()
        self._get_save_coordinator()
        self._get_backup_service_runner()
        self._detect_stale_transaction_journal()
        self.data = self._load()
        repair_report = self._apply_config_repairs_to_current()
        self._icon_repo_folder = self._load_icon_repo_folder()
        self._attach_icon_repo_folder()
        set_language(getattr(self.data.settings, "language", "zh_CN"))
        self._last_saved_data_dict = self._main_data_dict()
        # Publish ConfigLoaded event for downstream consumers.
        try:
            from application.events import ConfigLoaded, event_bus

            event_bus.publish(
                ConfigLoaded(
                    version=self.data.version,
                    schema_version=self.data.config_schema_version,
                )
            )
        except Exception as exc:
            logger.debug("ConfigLoaded event publish failed: %s", exc, exc_info=True)
        if repair_report.changed and self.data_file.exists():
            logger.info("Repaired config/data.json: %s", repair_report.to_dict())
            self._suppress_next_history = True
            self.save(immediate=True)

    def get_runtime_revision(self) -> int:
        """Data manager."""
        return int(self._runtime_revision)

    @property
    def clock(self):
        """Clock port adapter (lazy singleton)."""
        clock = getattr(self, "_clock", None)
        if clock is None:
            from infrastructure.system_clock import system_clock

            self._clock = system_clock
            clock = system_clock
        return clock

    # ── ConfigState port properties (W2 stage B: read-only routing) ──

    @property
    def save_lock(self):
        """Shared re-entrant lock for save coordination (ConfigStatePort)."""
        return self._save_lock

    @property
    def write_lock(self):
        """Shared exclusive lock for write serialization (ConfigStatePort)."""
        return self._write_lock

    @property
    def runtime_revision(self) -> int:
        """Monotonic revision counter incremented on each save (ConfigStatePort)."""
        return int(self._runtime_revision)

    @property
    def batch_depth(self) -> int:
        """Nesting depth of the batch-write context (ConfigStatePort)."""
        return int(self._batch_depth)

    @property
    def batch_dirty(self) -> bool:
        """Whether the batch has pending modifications (ConfigStatePort)."""
        return bool(self._batch_dirty)

    @property
    def batch_force_immediate(self) -> bool:
        """Whether to force the next save immediately (ConfigStatePort)."""
        return bool(self._batch_force_immediate)

    @property
    def pending_history_action(self) -> str:
        """Pending history annotation for the next save (ConfigStatePort)."""
        return str(self._pending_history_action)

    @property
    def pending_history_summary(self) -> str:
        """Pending history summary for the next save (ConfigStatePort)."""
        return str(self._pending_history_summary)

    @property
    def suppress_next_history(self) -> bool:
        """Whether to skip history recording on next save (ConfigStatePort)."""
        return bool(self._suppress_next_history)

    @property
    def deleted_system_ids(self) -> set[str]:
        """Set of icon-repo system IDs deleted in this session (ConfigStatePort)."""
        return self._deleted_system_ids

    @property
    def state_store(self):
        """StateStore backed by loaded AppData (lazy singleton).

        Provides revision-gated atomic state updates via
        :class:`application.state.store.StateStore`.
        """
        store = getattr(self, "_state_store", None)
        if store is None:
            from application.state.store import StateStore

            store = StateStore(
                self._main_data_dict() if self.data is not None else {},
                revision=self._runtime_revision,
            )
            self._state_store = store
        return store

    @property
    def config_repository(self):
        """ConfigRepository port adapter (lazy singleton)."""
        repo = getattr(self, "_config_repo", None)
        if repo is None:
            from infrastructure.persistence.adapters import ConfigRepositoryAdapter

            repo = ConfigRepositoryAdapter(self._get_config_store())
            self._config_repo = repo
        return repo

    @property
    def backup_store(self):
        """BackupStore port adapter (lazy singleton)."""
        store = getattr(self, "_backup_store", None)
        if store is None:
            from infrastructure.persistence.adapters import BackupStoreAdapter

            store = BackupStoreAdapter(self._get_backup_service(), self.data_file)
            self._backup_store = store
        return store

    @property
    def history_store(self):
        """HistoryStore port adapter (lazy singleton)."""
        store = getattr(self, "_history_store", None)
        if store is None:
            from infrastructure.persistence.adapters import HistoryStoreAdapter

            history_manager = getattr(self, "history_manager", None)
            if history_manager is None:
                history_manager = ConfigHistoryManager(self.history_dir, self._max_history_snapshots)
                self.history_manager = history_manager
            store = HistoryStoreAdapter(history_manager)
            self._history_store = store
        return store

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

    def _get_icon_repository_service(self) -> IconRepositoryService:
        service = getattr(self, "icon_repository_service", None)
        if service is None:
            service = IconRepositoryService(self)
            self.icon_repository_service = service
        return service

    def _get_folder_service(self) -> FolderService:
        service = getattr(self, "folder_service", None)
        if service is None:
            service = FolderService(self)
            self.folder_service = service
        return service

    def _get_shortcut_service(self) -> ShortcutService:
        service = getattr(self, "shortcut_service", None)
        if service is None:
            service = ShortcutService(self)
            self.shortcut_service = service
        return service

    def _get_settings_service(self) -> SettingsService:
        service = getattr(self, "settings_service", None)
        if service is None:
            service = SettingsService(self)
            self.settings_service = service
        return service

    def _get_save_coordinator(self) -> SaveCoordinator:
        service = getattr(self, "save_coordinator", None)
        if service is None:
            state = getattr(self, "_config_state", None)
            if state is None:
                state = ConfigState(
                    save_lock=getattr(self, "_save_lock", threading.RLock()),
                    write_lock=getattr(self, "_write_lock", threading.Lock()),
                    runtime_revision=int(getattr(self, "_runtime_revision", 0)),
                    batch_depth=int(getattr(self, "_batch_depth", 0)),
                    batch_dirty=bool(getattr(self, "_batch_dirty", False)),
                    batch_force_immediate=bool(getattr(self, "_batch_force_immediate", False)),
                    pending_history_action=str(getattr(self, "_pending_history_action", "配置变更")),
                    pending_history_summary=str(getattr(self, "_pending_history_summary", "")),
                    suppress_next_history=bool(getattr(self, "_suppress_next_history", False)),
                    deleted_system_ids=set(getattr(self, "_deleted_system_ids", set())),
                )
                self._config_state = state
                state.attach_to_host(self)
            service = SaveCoordinator(self, state=state)
            self.save_coordinator = service
        return service

    def _get_backup_service_runner(self) -> BackupService:
        service = getattr(self, "backup_service_runner", None)
        if service is None:
            service = BackupService(self)
            self.backup_service_runner = service
        return service

    def _get_data_loader(self) -> DataLoader:
        service = getattr(self, "data_loader", None)
        if service is None:
            service = DataLoader(self)
            self.data_loader = service
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
        return self._get_icon_repository_service().detach_folder()

    def _attach_icon_repo_folder(self) -> None:
        """Attach the icon repository as a runtime-only folder for existing UI code."""
        self._get_icon_repository_service().attach_folder()

    def _load_icon_repo_folder(self) -> Folder:
        """Load the combined runtime icon repository from system and user sources."""
        return self._get_icon_repository_service().load_folder()

    def _read_icon_repo_file(self) -> Folder | None:
        return self._get_icon_repository_service()._read_user_file()

    def _load_system_icon_items(self) -> list[ShortcutItem]:
        return self._get_icon_repository_service()._load_system_items()

    def _filter_user_icon_items(
        self, user_items: list[ShortcutItem], system_items: list[ShortcutItem]
    ) -> list[ShortcutItem]:
        return self._get_icon_repository_service()._filter_user_items(user_items, system_items)

    @staticmethod
    def _is_system_icon_repo_item(item: ShortcutItem | None) -> bool:
        return IconRepositoryService.is_system_item(item)

    @staticmethod
    def _is_user_icon_repo_item(item: ShortcutItem | None) -> bool:
        return IconRepositoryService.is_user_item(item)

    @staticmethod
    def _strip_icon_repo_runtime_source(item: ShortcutItem) -> ShortcutItem:
        return IconRepositoryService.strip_runtime_source(item)

    def _write_icon_repo_items(self, items: list[ShortcutItem]) -> bool:
        return self._get_icon_repository_service()._write_user_items(items)

    def save_icon_repo(self) -> bool:
        return self._get_icon_repository_service().save()

    def _load(self) -> AppData:
        """Data manager."""
        return self._get_data_loader().load()

    def _apply_config_repairs_to_current(self):
        """Apply config repairs to the current in-memory data."""
        return self._get_data_loader().apply_repairs()

    def _recover_from_latest_backup(
        self, reason: str = "", quarantined_path: Path | str | None = None
    ) -> AppData | None:
        """Recover data.json from the newest valid auto backup."""
        return self._get_data_loader()._recover_from_latest_backup(reason, quarantined_path)

    def save(self, immediate: bool = False) -> bool:
        """Data manager."""
        return self._get_save_coordinator().save(immediate=immediate)

    def _delayed_save(self):
        """Data manager."""
        self._get_save_coordinator()._delayed_save()

    def shutdown(self, timeout: float = 3.0) -> None:
        """Flush pending saves and cancel timers before application exit.

        Call this once during application teardown to ensure no data is lost
        from the delayed-save debounce window.
        """
        self._get_save_coordinator().shutdown(timeout=timeout)

    @contextmanager
    def batch_update(self, immediate: bool = False):
        """Data manager."""
        with self._get_save_coordinator().batch_update(immediate=immediate) as dm:
            yield dm

    def _do_save(self) -> bool:
        """Save data to disk atomically with lock splitting."""
        return self._get_save_coordinator()._do_save()

    def _serialize_data(self) -> str:
        """Serialize data and validate the JSON before writing it to disk."""
        return self._get_save_coordinator()._serialize_data()

    def _main_data_dict(self) -> dict:
        """Return AppData without the runtime-only icon repository folder."""
        return self._get_save_coordinator()._main_data_dict()

    def _mark_history(self, action: str, summary: str = ""):
        self._get_save_coordinator().mark_history(action, summary)

    def _write_recovery_report(self, report: ConfigRecoveryReport) -> None:
        self._get_recovery_service().write_report(report)

    def get_recovery_report(self) -> dict:
        return self._get_recovery_service().report_dict()

    def get_config_status(self) -> dict:
        """Return latest configuration load/save validation status."""
        return self._get_save_coordinator().get_config_status()

    def _reset_import_report(self) -> dict:
        return self._get_save_coordinator().reset_import_report()

    def get_last_import_report(self) -> dict:
        return self._get_save_coordinator().get_last_import_report()

    def list_config_history(self) -> list:
        return self._get_data_loader().list_history()

    def restore_config_history(self, snapshot_id: str) -> bool:
        """Restore AppData from a persisted history snapshot."""
        return self._get_data_loader().restore_history(snapshot_id)

    def _replace_data_file(self, temp_file: Path):
        """Replace data.json, falling back when Windows denies atomic rename."""
        self._get_config_store().replace_data_file(temp_file)

    def _create_auto_backup(self):
        """Create a timestamped backup of the current data file before replacing it."""
        self._get_backup_service().create_auto_backup(self.data_file)

    def flush_pending_save(self):
        """Data manager."""
        self._get_save_coordinator().flush_pending_save()

    def reload(self):
        """Data manager."""
        self._get_data_loader().reload()

    def record_shortcut_used(self, shortcut_id: str) -> bool:
        """Data manager."""
        return self._get_shortcut_service().record_used(shortcut_id)

    def _apply_smart_order(self, folder) -> int:
        """Update smart_order for one folder without changing custom order."""
        return self._get_shortcut_service()._apply_smart_order(folder)

    def add_folder(self, name: str) -> Folder:
        """Data manager."""
        return self._get_folder_service().add(name)

    def rename_folder(self, folder_id: str, new_name: str) -> bool:
        """Data manager."""
        return self._get_folder_service().rename(folder_id, new_name)

    def delete_folder(self, folder_id: str) -> bool:
        """Data manager."""
        return self._get_folder_service().delete(folder_id)

    def reorder_folders(self, folder_ids: list[str]):
        """Data manager."""
        self._get_folder_service().reorder(folder_ids)

    def add_shortcut(self, folder_id: str, shortcut: ShortcutItem) -> bool:
        """Data manager."""
        return self._get_shortcut_service().add(folder_id, shortcut)

    def add_shortcuts(self, folder_id: str, shortcuts: list[ShortcutItem]) -> int:
        """Data manager."""
        return self._get_shortcut_service().add_many(folder_id, shortcuts)

    def _find_shortcut_with_folder(self, shortcut_id: str):
        return self._get_shortcut_service().find_with_folder(shortcut_id)

    def get_shortcut_by_id(self, shortcut_id: str):
        """Data manager."""
        return self._get_shortcut_service().get_by_id(shortcut_id)

    def _persist_folder_changes(self, *folders, immediate: bool = True) -> bool:
        return self._get_shortcut_service()._persist_folder_changes(*folders, immediate=immediate)

    def recalculate_smart_order(self, folder_id: str | None = None) -> dict:
        """Data manager."""
        return self._get_shortcut_service().recalculate_smart_order(folder_id)

    def move_shortcut_to_folder(self, shortcut_id: str, target_folder_id: str) -> bool:
        """Data manager."""
        return self._get_shortcut_service().move_to_folder(shortcut_id, target_folder_id)

    def delete_shortcuts_batch(self, shortcut_ids: list[str]) -> dict:
        """Data manager."""
        return self._get_shortcut_service().delete_batch(shortcut_ids)

    def move_shortcuts_batch(self, shortcut_ids: list[str], target_folder_id: str) -> dict:
        """Data manager."""
        return self._get_shortcut_service().move_batch(shortcut_ids, target_folder_id)

    def copy_shortcuts_batch(self, shortcut_ids: list[str], target_folder_id: str) -> dict:
        """Copy shortcuts to a folder, assigning fresh ids and preserving the sources."""
        return self._get_shortcut_service().copy_batch(shortcut_ids, target_folder_id)

    def set_shortcuts_enabled_batch(self, shortcut_ids: list[str], enabled: bool) -> dict:
        """set_shortcuts_enabled_batch"""
        return self._get_shortcut_service().set_enabled_batch(shortcut_ids, enabled)

    def update_shortcut(self, folder_id: str, shortcut: ShortcutItem) -> bool:
        """update_shortcut"""
        return self._get_shortcut_service().update(folder_id, shortcut)

    def delete_shortcut(self, folder_id: str, shortcut_id: str) -> bool:
        """delete_shortcut"""
        return self._get_shortcut_service().delete(folder_id, shortcut_id)

    def reorder_shortcuts(self, folder_id: str, shortcut_ids: list[str]):
        """reorder_shortcuts"""
        self._get_shortcut_service().reorder(folder_id, shortcut_ids)

    def update_settings(self, *, immediate: bool = True, **kwargs):
        """update_settings"""
        return self._get_settings_service().update(immediate=immediate, **kwargs)

    def get_settings(self) -> AppSettings:
        """get_settings"""
        return self._get_settings_service().get()

    def set_language(self, language: str, immediate: bool = True) -> str:
        """Set the application language without requiring a UI switch control."""
        return self._get_settings_service().set_language(language, immediate=immediate)

    def clean_icon_cache(self, dry_run: bool = False) -> dict:
        """清理图标缓存中的无用、重复和非法文件。

        Delegates to ``self.icon_repository_service.clean_cache()`` for the
        actual file iteration and removal logic.
        """
        return self._get_icon_repository_service().clean_cache(dry_run=dry_run)

    def get_icon_cache_stats(self) -> dict:
        """get_icon_cache_stats — delegates to ``self.icon_repository_service.get_cache_stats()``."""
        return self._get_icon_repository_service().get_cache_stats()

    def get_all_cache_paths(self) -> dict:
        """get_all_cache_paths"""
        return self._get_icon_repository_service().get_all_cache_paths()

    def factory_reset(self, callback=None) -> dict:
        """factory_reset"""
        return self._get_data_loader().factory_reset(callback)

    def backup_full_config(self, save_path: str) -> bool:
        """backup_full_config"""
        return self._get_backup_service_runner().backup_full(save_path)

    # ── Transaction journal helpers ────────────────────────────────

    def _detect_stale_transaction_journal(self) -> None:
        """Check for a stale transaction journal from a previous crash."""
        self._get_data_loader().detect_stale_journal()

    def _attempt_restore_from_latest_backup(self) -> None:
        """Try to restore data.json from the most recent automatic backup."""
        self._get_data_loader().attempt_restore_from_latest_backup()

    def _write_transaction_journal(self, operation: str, extra: dict | None = None) -> None:
        """Write a pre-transaction state snapshot to the recovery directory."""
        self._get_data_loader().write_journal(operation, extra)

    def _clear_transaction_journal(self) -> None:
        """Remove the transaction journal after successful completion."""
        self._get_data_loader().clear_journal()

    def _verify_transaction_consistency(self) -> dict:
        """Post-transaction verification: compare in-memory state with disk."""
        return self._get_data_loader().verify_consistency()

    def restore_full_config(self, backup_path: str) -> bool:
        """Data manager."""
        return self._get_backup_service_runner().restore_full(backup_path)

    def _restore_full_config_safe(self, backup_path: str) -> bool:
        return self._get_backup_service_runner()._restore_full_safe(backup_path)

    def export_shareable_config(self, save_path: str) -> bool:
        """Data manager."""
        return self._get_backup_service_runner().export_shareable(save_path)

    def import_shareable_config(self, import_path: str, merge: bool = True) -> bool:
        """Data manager."""
        return self._get_backup_service_runner().import_shareable(import_path, merge=merge)

    def _import_shareable_config_transactional(self, import_path: str, merge: bool, report: dict) -> bool:
        return self._get_backup_service_runner()._import_shareable_transactional(import_path, merge, report)

    def _import_shareable_config_safe(self, import_path: str, merge: bool = True) -> bool:
        return self._get_backup_service_runner()._import_shareable_safe(import_path, merge=merge)

    def redirect_missing_icon_paths(self, new_icon_path: str) -> int:
        """Redirect missing icon paths to files found beside a newly fixed icon."""
        return self._get_icon_repository_service().redirect_missing_paths(new_icon_path)
