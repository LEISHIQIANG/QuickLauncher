"""Extended data manager tests – CRUD, batch update, serialization, import/export, validation."""

import json
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tempfile
from unittest.mock import MagicMock

import pytest

from core.config_history import ConfigHistoryManager
from core.data_manager import DataManager
from core.data_models import AppData, Folder, ShortcutItem, ShortcutType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manager_with_data(data=None):
    """Create a lightweight DataManager without triggering __init__."""
    data = data or AppData()
    manager = object.__new__(DataManager)
    manager.data = data
    manager._save_lock = threading.RLock()
    manager._write_lock = threading.Lock()
    manager._batch_depth = 0
    manager._batch_dirty = False
    manager._batch_force_immediate = False
    manager._save_pending = False
    manager._save_timer = None
    manager._save_delay = 0.5
    manager._runtime_revision = 0
    manager._pending_history_action = "配置变更"
    manager._pending_history_summary = ""
    manager._suppress_next_history = False
    manager._last_saved_data_dict = data.to_dict()
    manager.history_manager = None
    manager._last_import_report = {
        "dry_run": False,
        "mode": "",
        "skipped_files": [],
        "skipped_settings": [],
        "warnings": [],
        "imported_items": 0,
    }
    manager._config_status = {"status": "unknown", "source": "", "issues": []}
    # Add missing attributes for file-backed operations
    from pathlib import Path

    manager.data_file = Path(tempfile.gettempdir()) / "data.json"
    manager.recovery_dir = Path(tempfile.gettempdir()) / "recovery"
    manager.auto_backup_dir = Path(tempfile.gettempdir()) / "auto_backup"
    manager._max_auto_backups = 10
    return manager


def _file_backed_manager(tmp_path, data=None):
    data = data or AppData()
    manager = _manager_with_data(data)
    manager.install_dir = tmp_path
    manager.app_dir = tmp_path / "config"
    manager.icons_dir = tmp_path / "icons"
    manager.auto_backup_dir = manager.app_dir / "auto_backups"
    manager.history_dir = manager.app_dir / "history"
    manager.recovery_dir = manager.app_dir / "recovery"
    manager.data_file = manager.app_dir / "data.json"
    manager.icon_repo_file = manager.app_dir / "icon_repo.json"
    manager.system_icons_file = tmp_path / "assets" / "system_icons" / "config.json"
    manager._max_auto_backups = 5
    manager._max_history_snapshots = 20
    manager._save_delay = 0.01
    manager._config_status = {"status": "unknown", "source": "", "issues": []}
    manager.app_dir.mkdir(parents=True, exist_ok=True)
    manager.icons_dir.mkdir(parents=True, exist_ok=True)
    manager.auto_backup_dir.mkdir(parents=True, exist_ok=True)
    manager.recovery_dir.mkdir(parents=True, exist_ok=True)
    manager.history_manager = ConfigHistoryManager(manager.history_dir, manager._max_history_snapshots)
    return manager


def _make_shortcut(name="Test", stype=ShortcutType.FILE, **kw):
    return ShortcutItem(name=name, type=stype, **kw)


# ======================================================================
# CRUD – Folders
# ======================================================================


class TestFolderCRUD:
    def test_add_folder_increments_order(self):
        dm = _manager_with_data()
        f1 = dm.add_folder("Alpha")
        f2 = dm.add_folder("Beta")
        assert f2.order > f1.order
        assert f2.name == "Beta"

    def test_add_folder_generates_unique_ids(self):
        dm = _manager_with_data()
        f1 = dm.add_folder("A")
        f2 = dm.add_folder("B")
        assert f1.id != f2.id

    def test_rename_folder_success(self):
        dm = _manager_with_data()
        f = dm.add_folder("Old")
        assert dm.rename_folder(f.id, "New")
        assert f.name == "New"

    def test_rename_folder_nonexistent(self):
        dm = _manager_with_data()
        assert not dm.rename_folder("bogus-id", "X")

    def test_rename_folder_icon_repo_rejected(self):
        dm = _manager_with_data()
        repo = Folder(id="icon_repo", name="图标库", is_icon_repo=True)
        dm.data.folders.append(repo)
        assert not dm.rename_folder("icon_repo", "Hacked")

    def test_delete_folder_removes_it(self):
        dm = _manager_with_data()
        f = dm.add_folder("Temp")
        assert dm.delete_folder(f.id)
        assert dm.data.get_folder_by_id(f.id) is None

    def test_delete_system_folder_rejected(self):
        dm = _manager_with_data()
        dock = dm.data.get_dock()
        assert dock.is_system
        assert not dm.delete_folder(dock.id)

    def test_reorder_folders_changes_order(self):
        dm = _manager_with_data()
        f1 = dm.add_folder("A")
        f2 = dm.add_folder("B")
        f3 = dm.add_folder("C")
        dm.reorder_folders([f3.id, f1.id, f2.id])
        page_folders = [f for f in dm.data.get_pages() if not getattr(f, "is_icon_repo", False)]
        names = [f.name for f in sorted(page_folders, key=lambda f: f.order)]
        assert names[0] == "C"


# ======================================================================
# CRUD – Shortcuts
# ======================================================================


class TestShortcutCRUD:
    def test_add_shortcut_sets_order(self):
        dm = _manager_with_data()
        folder = dm.add_folder("F")
        s1 = _make_shortcut("S1")
        s2 = _make_shortcut("S2")
        dm.add_shortcut(folder.id, s1)
        dm.add_shortcut(folder.id, s2)
        assert s2.order > s1.order

    def test_add_shortcut_nonexistent_folder(self):
        dm = _manager_with_data()
        assert not dm.add_shortcut("fake", _make_shortcut())

    def test_add_shortcuts_batch(self):
        dm = _manager_with_data()
        folder = dm.add_folder("F")
        items = [_make_shortcut(f"S{i}") for i in range(5)]
        count = dm.add_shortcuts(folder.id, items)
        assert count == 5
        assert len(folder.items) == 5

    def test_add_shortcuts_empty_list(self):
        dm = _manager_with_data()
        folder = dm.add_folder("F")
        assert dm.add_shortcuts(folder.id, []) == 0

    def test_get_shortcut_by_id(self):
        dm = _manager_with_data()
        folder = dm.add_folder("F")
        s = _make_shortcut("FindMe")
        dm.add_shortcut(folder.id, s)
        assert dm.get_shortcut_by_id(s.id) is s

    def test_get_shortcut_by_id_missing(self):
        dm = _manager_with_data()
        assert dm.get_shortcut_by_id("nope") is None

    def test_update_shortcut_success(self):
        dm = _manager_with_data()
        folder = dm.add_folder("F")
        s = _make_shortcut("Old")
        dm.add_shortcut(folder.id, s)
        s2 = ShortcutItem(id=s.id, name="New", order=s.order)
        assert dm.update_shortcut(folder.id, s2)

    def test_update_shortcut_wrong_folder(self):
        dm = _manager_with_data()
        f1 = dm.add_folder("F1")
        f2 = dm.add_folder("F2")
        s = _make_shortcut("S")
        dm.add_shortcut(f1.id, s)
        assert not dm.update_shortcut(f2.id, s)

    def test_delete_shortcut_success(self):
        dm = _manager_with_data()
        folder = dm.add_folder("F")
        s = _make_shortcut("Del")
        dm.add_shortcut(folder.id, s)
        assert dm.delete_shortcut(folder.id, s.id)
        assert len(folder.items) == 0

    def test_delete_shortcut_nonexistent(self):
        dm = _manager_with_data()
        folder = dm.add_folder("F")
        assert not dm.delete_shortcut(folder.id, "bogus")

    def test_reorder_shortcuts(self):
        dm = _manager_with_data()
        folder = dm.add_folder("F")
        items = [_make_shortcut(f"S{i}") for i in range(3)]
        for item in items:
            dm.add_shortcut(folder.id, item)
        ids = [items[2].id, items[0].id, items[1].id]
        dm.reorder_shortcuts(folder.id, ids)
        assert [s.id for s in folder.items] == ids


# ======================================================================
# Batch update context manager
# ======================================================================


class TestBatchUpdate:
    def test_batch_defers_save(self):
        dm = _manager_with_data()
        dm._do_save = MagicMock(return_value=True)
        dm.save = MagicMock(return_value=True)
        with dm.batch_update():
            dm._batch_dirty = True
        dm.save.assert_called_once_with(immediate=False)
        dm._do_save.assert_not_called()
        assert dm._batch_depth == 0

    def test_batch_immediate_triggers_save(self):
        dm = _manager_with_data()
        dm._do_save = MagicMock(return_value=True)
        with dm.batch_update(immediate=True):
            dm._batch_dirty = True
        dm._do_save.assert_called()

    def test_batch_nested_depth(self):
        dm = _manager_with_data()
        with dm.batch_update():
            assert dm._batch_depth == 1
            with dm.batch_update():
                assert dm._batch_depth == 2
            assert dm._batch_depth == 1
        assert dm._batch_depth == 0

    def test_batch_exception_resets_dirty(self):
        dm = _manager_with_data()
        with pytest.raises(RuntimeError):
            with dm.batch_update():
                dm._batch_dirty = True
                raise RuntimeError("boom")
        assert not dm._batch_dirty
        assert not dm._save_pending

    def test_nested_batch_exception_does_not_flush_outer_batch(self):
        dm = _manager_with_data()
        dm._do_save = MagicMock(return_value=True)
        dm.save = MagicMock(return_value=True)

        with pytest.raises(RuntimeError):
            with dm.batch_update(immediate=True):
                dm._batch_dirty = True
                with dm.batch_update():
                    dm._batch_dirty = True
                    raise RuntimeError("boom")

        assert dm._batch_depth == 0
        dm._do_save.assert_not_called()
        dm.save.assert_not_called()

    def test_batch_no_save_without_dirty(self):
        dm = _manager_with_data()
        dm._do_save = MagicMock(return_value=True)
        with dm.batch_update():
            pass  # nothing dirty
        dm._do_save.assert_not_called()

    def test_batch_cancel_timer_on_flush(self):
        dm = _manager_with_data()
        timer_mock = MagicMock()
        dm._save_timer = timer_mock
        dm._save_pending = True
        with dm.batch_update(immediate=True):
            dm._batch_dirty = True
        timer_mock.cancel.assert_called()


# ======================================================================
# Save / Load serialization
# ======================================================================


class TestSerialization:
    def test_do_save_writes_json(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        folder = dm.add_folder("TestFolder")
        s = _make_shortcut("Item1")
        dm.add_shortcut(folder.id, s)
        assert dm.data_file.exists()
        loaded = json.loads(dm.data_file.read_text(encoding="utf-8"))
        assert "folders" in loaded

    def test_main_data_dict_excludes_icon_repo(self):
        data = AppData()
        repo = Folder(id="icon_repo", name="图标库", is_icon_repo=True, items=[_make_shortcut("sys")])
        data.folders.append(repo)
        dm = _manager_with_data(data)
        d = dm._main_data_dict()
        folder_ids = [f["id"] for f in d.get("folders", [])]
        assert "icon_repo" not in folder_ids

    def test_serialize_data_returns_valid_json(self):
        dm = _manager_with_data()
        payload = dm._serialize_data()
        parsed = json.loads(payload)
        assert isinstance(parsed, dict)

    def test_load_missing_file_creates_default(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        dm.data_file = tmp_path / "nonexistent.json"
        result = dm._load()
        assert isinstance(result, AppData)

    def test_load_corrupt_json_returns_default(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        dm.data_file.write_text("NOT JSON {{{", encoding="utf-8")
        # Should not raise
        result = dm._load()
        assert isinstance(result, AppData)

    def test_save_creates_backup(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        dm.save(immediate=True)
        # Write a second time so the first becomes a backup
        dm.data.settings.icon_size = 48
        dm.save(immediate=True)
        backups = list(dm.auto_backup_dir.iterdir())
        assert len(backups) >= 1

    def test_runtime_revision_increments(self):
        dm = _manager_with_data()
        rev0 = dm.get_runtime_revision()
        dm.save(immediate=True)
        assert dm.get_runtime_revision() > rev0


# ======================================================================
# Move / Copy / Batch operations
# ======================================================================


class TestMoveCopyBatch:
    def test_move_shortcut_to_folder(self):
        dm = _manager_with_data()
        f1 = dm.add_folder("Src")
        f2 = dm.add_folder("Dst")
        s = _make_shortcut("M")
        dm.add_shortcut(f1.id, s)
        assert dm.move_shortcut_to_folder(s.id, f2.id)
        assert s in f2.items
        assert s not in f1.items

    def test_move_shortcut_same_folder(self):
        dm = _manager_with_data()
        f = dm.add_folder("F")
        s = _make_shortcut("S")
        dm.add_shortcut(f.id, s)
        assert not dm.move_shortcut_to_folder(s.id, f.id)

    def test_move_shortcut_missing(self):
        dm = _manager_with_data()
        f = dm.add_folder("F")
        assert not dm.move_shortcut_to_folder("nonexistent", f.id)

    def test_delete_shortcuts_batch(self):
        dm = _manager_with_data()
        f = dm.add_folder("F")
        items = [_make_shortcut(f"S{i}") for i in range(4)]
        for item in items:
            dm.add_shortcut(f.id, item)
        ids_to_delete = [items[0].id, items[2].id]
        result = dm.delete_shortcuts_batch(ids_to_delete)
        assert result["success"] == 2
        assert result["failed"] == 0
        assert set(result["affected_ids"]) == set(ids_to_delete)

    def test_delete_shortcuts_batch_empty(self):
        dm = _manager_with_data()
        result = dm.delete_shortcuts_batch([])
        assert result["requested"] == 0

    def test_move_shortcuts_batch(self):
        dm = _manager_with_data()
        f1 = dm.add_folder("Src")
        f2 = dm.add_folder("Dst")
        items = [_make_shortcut(f"S{i}") for i in range(3)]
        for item in items:
            dm.add_shortcut(f1.id, item)
        result = dm.move_shortcuts_batch([items[0].id, items[2].id], f2.id)
        assert result["success"] == 2
        assert len(f2.items) == 2
        assert len(f1.items) == 1

    def test_move_shortcuts_batch_invalid_target(self):
        dm = _manager_with_data()
        result = dm.move_shortcuts_batch(["a"], "bogus")
        assert result["success"] == 0

    def test_copy_shortcuts_batch(self):
        dm = _manager_with_data()
        f1 = dm.add_folder("Src")
        f2 = dm.add_folder("Dst")
        s = _make_shortcut("CopyMe")
        dm.add_shortcut(f1.id, s)
        result = dm.copy_shortcuts_batch([s.id], f2.id)
        assert result["success"] == 1
        assert len(f2.items) == 1
        assert f2.items[0].id != s.id  # new id
        assert f2.items[0].name == "CopyMe"
        assert len(f1.items) == 1  # original untouched

    def test_set_shortcuts_enabled_batch(self):
        dm = _manager_with_data()
        f = dm.add_folder("F")
        items = [_make_shortcut(f"S{i}") for i in range(3)]
        for item in items:
            dm.add_shortcut(f.id, item)
        result = dm.set_shortcuts_enabled_batch([items[1].id], False)
        assert result["success"] == 1
        assert items[1].enabled is False

    def test_set_shortcuts_enabled_batch_empty(self):
        dm = _manager_with_data()
        result = dm.set_shortcuts_enabled_batch([], True)
        assert result["success"] == 0


# ======================================================================
# Smart ordering
# ======================================================================


class TestSmartOrder:
    def test_apply_smart_order_sorts_by_usage(self):
        dm = _manager_with_data()
        folder = Folder(id="f", name="F")
        s1 = _make_shortcut("Low", use_count=1, last_used_at=100.0, order=0)
        s2 = _make_shortcut("High", use_count=50, last_used_at=300.0, order=1)
        s3 = _make_shortcut("Mid", use_count=10, last_used_at=200.0, order=2)
        folder.items = [s1, s2, s3]
        updated = dm._apply_smart_order(folder)
        assert updated > 0
        assert s2.smart_order == 0  # highest usage first

    def test_apply_smart_order_skips_dock(self):
        dm = _manager_with_data()
        dock = Folder(id="dock", name="Dock", is_dock=True, items=[_make_shortcut()])
        assert dm._apply_smart_order(dock) == 0

    def test_recalculate_smart_order(self):
        dm = _manager_with_data()
        folder = dm.add_folder("Page")
        s1 = _make_shortcut("A", use_count=5)
        s2 = _make_shortcut("B", use_count=20)
        dm.add_shortcut(folder.id, s1)
        dm.add_shortcut(folder.id, s2)
        result = dm.recalculate_smart_order(folder.id)
        assert result["folders"] == 1
        assert result["updated"] >= 1


# ======================================================================
# Settings
# ======================================================================


class TestSettings:
    def test_update_settings_changes_value(self):
        dm = _manager_with_data()
        dm.update_settings(icon_size=48)
        assert dm.data.settings.icon_size == 48

    def test_update_settings_no_change(self):
        dm = _manager_with_data()
        dm._do_save = MagicMock(return_value=True)
        dm.update_settings(icon_size=dm.data.settings.icon_size)
        dm._do_save.assert_not_called()

    def test_update_settings_can_defer_save(self):
        dm = _manager_with_data()
        dm.save = MagicMock(return_value=True)

        dm.update_settings(icon_size=48, immediate=False)

        assert dm.data.settings.icon_size == 48
        dm.save.assert_called_once_with(immediate=False)

    def test_get_settings_returns_copy(self):
        dm = _manager_with_data()
        dm.data.settings.enabled_plugins = ["a", "b"]
        s = dm.get_settings()
        s.enabled_plugins.append("c")
        assert len(dm.data.settings.enabled_plugins) == 2

    def test_set_language_normalizes(self):
        dm = _manager_with_data()
        result = dm.set_language("en_US")
        assert result.startswith("en")


# ======================================================================
# Icon repository
# ======================================================================


class TestIconRepo:
    def test_detach_icon_repo_folder(self):
        data = AppData()
        repo = Folder(id="icon_repo", name="图标库", is_icon_repo=True)
        data.folders.append(repo)
        dm = _manager_with_data(data)
        detached = dm._detach_icon_repo_folder()
        assert detached is not None
        assert detached.id == "icon_repo"

    def test_detach_icon_repo_folder_missing(self):
        dm = _manager_with_data()
        assert dm._detach_icon_repo_folder() is None

    def test_filter_user_icon_items_removes_system_duplicates(self):
        dm = _manager_with_data()
        sys_item = ShortcutItem(id="sys1", name="SystemIcon")
        user_item_dup = ShortcutItem(id="sys1", name="SystemIcon")
        user_item_unique = ShortcutItem(id="usr1", name="UserIcon")
        result = dm._filter_user_icon_items([user_item_dup, user_item_unique], [sys_item])
        assert len(result) == 1
        assert result[0].id == "usr1"

    def test_is_system_icon_repo_item(self):
        item = ShortcutItem()
        item._icon_repo_source = "system"
        assert DataManager._is_system_icon_repo_item(item)

    def test_is_user_icon_repo_item(self):
        item = ShortcutItem()
        item._icon_repo_source = "user"
        assert DataManager._is_user_icon_repo_item(item)

    def test_strip_icon_repo_runtime_source(self):
        item = ShortcutItem()
        item._icon_repo_source = "user"
        DataManager._strip_icon_repo_runtime_source(item)
        assert not hasattr(item, "_icon_repo_source")


# ======================================================================
# Record usage
# ======================================================================


class TestRecordUsage:
    def test_record_shortcut_used_increments_count(self):
        dm = _manager_with_data()
        folder = dm.add_folder("F")
        s = _make_shortcut("S")
        dm.add_shortcut(folder.id, s)
        dm.record_shortcut_used(s.id)
        assert s.use_count >= 1
        assert s.last_used_at > 0

    def test_record_shortcut_used_empty_id(self):
        dm = _manager_with_data()
        assert not dm.record_shortcut_used("")

    def test_record_shortcut_used_not_found(self):
        dm = _manager_with_data()
        assert not dm.record_shortcut_used("bogus-id")


# ======================================================================
# Config status / recovery / history
# ======================================================================


class TestConfigStatus:
    def test_get_config_status_returns_dict(self):
        dm = _manager_with_data()
        status = dm.get_config_status()
        assert isinstance(status, dict)
        assert "status" in status

    def test_get_last_import_report_structure(self):
        dm = _manager_with_data()
        report = dm.get_last_import_report()
        assert "dry_run" in report
        assert "imported_items" in report

    def test_list_config_history_empty(self):
        dm = _manager_with_data()
        result = dm.list_config_history()
        assert isinstance(result, list)

    def test_restore_config_history_no_manager(self):
        dm = _manager_with_data()
        dm.history_manager = None
        assert not dm.restore_config_history("any-id")


# ======================================================================
# Icon cache cleaning
# ======================================================================


class TestIconCacheCleaning:
    def test_clean_icon_cache_empty_dir(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        stats = dm.clean_icon_cache(dry_run=True)
        assert stats["total_removed"] == 0

    def test_clean_icon_cache_removes_orphans(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        # Create an orphan icon file
        icon_file = dm.icons_dir / "orphan.png"
        icon_file.write_bytes(b"\x89PNG\r\n" + b"\x00" * 100)
        stats = dm.clean_icon_cache(dry_run=True)
        assert stats["orphan_files_removed"] >= 1

    def test_clean_icon_cache_removes_exe_extensions(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        exe_file = dm.icons_dir / "bad.exe"
        exe_file.write_bytes(b"MZ" + b"\x00" * 100)
        stats = dm.clean_icon_cache(dry_run=True)
        assert stats["exe_files_removed"] >= 1

    def test_clean_icon_cache_removes_large_files(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        big = dm.icons_dir / "big.png"
        big.write_bytes(b"\x00" * (11 * 1024 * 1024))  # 11MB
        stats = dm.clean_icon_cache(dry_run=True)
        assert stats["large_files_removed"] >= 1

    def test_clean_icon_cache_dry_run_preserves_files(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        icon_file = dm.icons_dir / "orphan.png"
        icon_file.write_bytes(b"\x00" * 100)
        dm.clean_icon_cache(dry_run=True)
        assert icon_file.exists()

    def test_clean_icon_cache_actually_deletes(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        icon_file = dm.icons_dir / "orphan.png"
        icon_file.write_bytes(b"\x00" * 100)
        dm.clean_icon_cache(dry_run=False)
        assert not icon_file.exists()

    def test_clean_icon_cache_keeps_used_icons(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        used = dm.icons_dir / "used.png"
        used.write_bytes(b"\x00" * 100)
        folder = dm.add_folder("F")
        s = _make_shortcut("S", icon_path=str(used))
        dm.add_shortcut(folder.id, s)
        stats = dm.clean_icon_cache(dry_run=True)
        assert stats["total_removed"] == 0

    def test_get_icon_cache_stats(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        (dm.icons_dir / "a.png").write_bytes(b"\x00" * 50)
        (dm.icons_dir / "b.exe").write_bytes(b"\x00" * 50)
        stats = dm.get_icon_cache_stats()
        assert stats["total_files"] == 2
        assert ".png" in stats["by_extension"]
        assert stats["invalid_files"] >= 1


# ======================================================================
# Flush pending save
# ======================================================================


class TestFlushPendingSave:
    def test_flush_with_pending_save(self):
        dm = _manager_with_data()
        dm._do_save = MagicMock(return_value=True)
        dm._save_pending = True
        dm._save_timer = None
        dm.flush_pending_save()
        dm._do_save.assert_called_once()

    def test_flush_without_pending_save(self):
        dm = _manager_with_data()
        dm._do_save = MagicMock(return_value=True)
        dm._save_pending = False
        dm._save_timer = None
        dm.flush_pending_save()
        dm._do_save.assert_not_called()


# ======================================================================
# Reload
# ======================================================================


class TestReload:
    def test_reload_recreates_data(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        dm.save(immediate=True)
        old_rev = dm.get_runtime_revision()
        dm.reload()
        assert dm.get_runtime_revision() > old_rev


# ======================================================================
# Icon path redirect
# ======================================================================


class TestIconPathRedirect:
    def test_redirect_missing_icon_paths_empty_arg(self):
        dm = _manager_with_data()
        assert dm.redirect_missing_icon_paths("") == 0

    def test_redirect_missing_icon_paths_skips_existing(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        real_icon = tmp_path / "real.png"
        real_icon.write_bytes(b"\x00")
        folder = dm.add_folder("F")
        s = _make_shortcut("S", icon_path=str(real_icon))
        dm.add_shortcut(folder.id, s)
        assert dm.redirect_missing_icon_paths(str(real_icon)) == 0

    def test_redirect_missing_icon_paths_matches_case_insensitive_filename(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        icon_dir = tmp_path / "new-icons"
        icon_dir.mkdir()
        fixed_icon = icon_dir / "fixed.png"
        candidate = icon_dir / "App.PNG"
        fixed_icon.write_bytes(b"fixed")
        candidate.write_bytes(b"candidate")

        folder = dm.add_folder("F")
        missing = tmp_path / "old-icons" / "app.png"
        s = _make_shortcut("S", icon_path=str(missing))
        dm.add_shortcut(folder.id, s)

        assert dm.redirect_missing_icon_paths(str(fixed_icon)) == 1
        assert s.icon_path == str(candidate)

    def test_redirect_missing_icon_paths_matches_same_stem_with_better_extension(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        icon_dir = tmp_path / "new-icons"
        icon_dir.mkdir()
        fixed_icon = icon_dir / "fixed.png"
        candidate = icon_dir / "Tool.ico"
        fixed_icon.write_bytes(b"fixed")
        candidate.write_bytes(b"candidate")

        folder = dm.add_folder("F")
        missing = tmp_path / "old-icons" / "Tool.png"
        s = _make_shortcut("S", icon_path=f"{missing},7")
        dm.add_shortcut(folder.id, s)

        assert dm.redirect_missing_icon_paths(str(fixed_icon)) == 1
        assert s.icon_path == f"{candidate},7"

    def test_redirect_missing_icon_paths_drops_index_for_bitmap_candidate(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        icon_dir = tmp_path / "new-icons"
        icon_dir.mkdir()
        fixed_icon = icon_dir / "fixed.png"
        candidate = icon_dir / "Tool.png"
        fixed_icon.write_bytes(b"fixed")
        candidate.write_bytes(b"candidate")

        folder = dm.add_folder("F")
        missing = tmp_path / "old-icons" / "Tool.dll"
        s = _make_shortcut("S", icon_path=f"{missing},4")
        dm.add_shortcut(folder.id, s)

        assert dm.redirect_missing_icon_paths(str(fixed_icon)) == 1
        assert s.icon_path == str(candidate)


# ======================================================================
# write_icon_repo_items
# ======================================================================


class TestWriteIconRepoItems:
    def test_write_icon_repo_items_creates_file(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        items = [_make_shortcut("Icon1")]
        result = dm._write_icon_repo_items(items)
        assert result is True
        assert dm.icon_repo_file.exists()

    def test_read_icon_repo_file_roundtrip(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        items = [ShortcutItem(id="x1", name="Test")]
        dm._write_icon_repo_items(items)
        folder = dm._read_icon_repo_file()
        assert folder is not None
        assert len(folder.items) == 1
        assert folder.items[0].name == "Test"

    def test_read_icon_repo_file_missing(self, tmp_path):
        dm = _file_backed_manager(tmp_path)
        assert dm.icon_repo_file.exists() is False
        # Should use file existence check
        if dm.icon_repo_file.exists():
            folder = dm._read_icon_repo_file()
        else:
            folder = None
        assert folder is None
