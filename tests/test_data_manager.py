"""Data manager regression tests."""

import json
import os
import sys
import threading
import types
import zipfile

import pytest

from core.config_history import ConfigHistoryManager
from core.data_manager import DataManager
from core.data_models import AppData, Folder, ShortcutItem, ShortcutType

data_manager_module = sys.modules["core.data_manager"]


def _manager_with_data(data):
    manager = object.__new__(DataManager)
    manager.data = data
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
    manager._last_saved_data_dict = data.to_dict()
    manager.history_manager = None
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


def test_factory_reset_returns_cleanup_stats(monkeypatch, tmp_path):
    fake_winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        KEY_ALL_ACCESS=0,
        OpenKey=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing")),
        DeleteValue=lambda *args, **kwargs: None,
        CloseKey=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)

    app_dir = tmp_path / "config"
    icons_dir = tmp_path / "icons"
    app_dir.mkdir()
    icons_dir.mkdir()
    (app_dir / "data.json").write_text("{}", encoding="utf-8")
    (icons_dir / "cached.ico").write_text("icon", encoding="utf-8")

    manager = object.__new__(DataManager)
    manager._save_lock = threading.RLock()
    manager._write_lock = threading.Lock()
    manager.app_dir = app_dir
    manager.icons_dir = icons_dir

    stats = manager.factory_reset()

    assert stats["files_removed"] == 2
    assert stats["dirs_removed"] == 0
    assert stats["registry_keys_removed"] == 0
    assert isinstance(stats["errors"], list)
    assert isinstance(manager.data, AppData)


def test_record_shortcut_used_updates_matching_item(monkeypatch):
    shortcut = ShortcutItem(id="shortcut-1", name="App")
    manager = object.__new__(DataManager)
    manager._save_lock = threading.RLock()
    manager._write_lock = threading.Lock()
    manager.data = AppData(folders=[Folder(id="default", name="常用", items=[shortcut])])
    saves = []
    monkeypatch.setattr(manager, "save", lambda *args, **kwargs: saves.append(True))

    assert manager.record_shortcut_used("shortcut-1")
    assert shortcut.use_count == 1
    assert shortcut.last_used_at > 0
    assert saves == [True]


def test_record_shortcut_used_missing_id_does_not_save(monkeypatch):
    shortcut = ShortcutItem(id="shortcut-1", name="App")
    manager = object.__new__(DataManager)
    manager._save_lock = threading.RLock()
    manager._write_lock = threading.Lock()
    manager.data = AppData(folders=[Folder(id="default", name="常用", items=[shortcut])])
    saves = []
    monkeypatch.setattr(manager, "save", lambda *args, **kwargs: saves.append(True))

    assert not manager.record_shortcut_used("missing")
    assert shortcut.use_count == 0
    assert saves == []


def test_record_shortcut_used_refreshes_smart_order(monkeypatch):
    low = ShortcutItem(id="low", name="Low", order=0, use_count=4, last_used_at=1)
    high = ShortcutItem(id="high", name="High", order=1, use_count=5, last_used_at=10)
    data = AppData(folders=[Folder(id="default", name="Default", items=[low, high])])
    data.settings.sort_mode = "smart"
    manager = _manager_with_data(data)
    saves = []
    monkeypatch.setattr(manager, "_do_save", lambda: saves.append(True))
    monkeypatch.setattr("core.data_models.time.time", lambda: 1000.0)

    assert manager.record_shortcut_used("low")

    assert low.use_count == 5
    assert low.last_used_at == 1000.0
    assert low.smart_order == 0
    assert high.smart_order == 1
    assert low.order == 0
    assert high.order == 1
    assert saves == [True]


def test_sort_mode_and_smart_order_are_compatible_defaults():
    settings = AppData.from_dict({"settings": {}, "folders": []}).settings
    item = ShortcutItem.from_dict({"name": "App"})

    assert settings.sort_mode == "custom"
    assert item.smart_order is None
    item.smart_order = 3
    assert item.to_dict()["smart_order"] == 3


def test_recalculate_smart_order_does_not_change_custom_order(monkeypatch):
    low = ShortcutItem(id="low", name="Low", order=0, use_count=1, last_used_at=1)
    high = ShortcutItem(id="high", name="High", order=1, use_count=5, last_used_at=10)
    manager = _manager_with_data(AppData(folders=[Folder(id="default", name="常用", items=[low, high])]))
    monkeypatch.setattr(manager, "_do_save", lambda: None)

    stats = manager.recalculate_smart_order()

    assert stats["updated"] == 2
    assert low.order == 0
    assert high.order == 1
    assert high.smart_order == 0
    assert low.smart_order == 1


def test_batch_delete_move_and_enable(monkeypatch):
    one = ShortcutItem(id="one", name="One")
    two = ShortcutItem(id="two", name="Two")
    source = Folder(id="source", name="Source", items=[one, two])
    target = Folder(id="target", name="Target", items=[])
    manager = _manager_with_data(AppData(folders=[source, target]))
    monkeypatch.setattr(manager, "_do_save", lambda: None)

    disabled = manager.set_shortcuts_enabled_batch(["one", "missing"], False)
    moved = manager.move_shortcuts_batch(["two", "missing"], "target")
    deleted = manager.delete_shortcuts_batch(["one", "missing"])

    assert disabled["success"] == 1
    assert disabled["failed"] == 1
    assert one.enabled is False
    assert moved["success"] == 1
    assert target.items == [two]
    assert deleted["success"] == 1
    assert source.items == []


def test_batch_update_coalesces_multiple_saves(monkeypatch):
    manager = _manager_with_data(AppData())
    saves = []
    monkeypatch.setattr(manager, "_do_save", lambda: saves.append("save"))

    with manager.batch_update(immediate=True):
        manager.save()
        manager.save(immediate=True)
        manager.save()

    assert saves == ["save"]


def test_replace_data_file_restores_original_when_fallback_copy_fails(monkeypatch, tmp_path):
    manager = _file_backed_manager(tmp_path)
    manager.data_file.write_text("original", encoding="utf-8")
    temp_file = manager.data_file.with_suffix(".tmp")
    temp_file.write_text("new", encoding="utf-8")
    real_copyfile = data_manager_module.shutil.copyfile

    monkeypatch.setattr(data_manager_module.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("locked")))

    calls = []

    def flaky_copyfile(src, dst):
        calls.append((str(src), str(dst)))
        if str(src) == str(temp_file):
            manager.data_file.write_text("partial", encoding="utf-8")
            raise OSError("copy failed")
        return real_copyfile(src, dst)

    monkeypatch.setattr(data_manager_module.shutil, "copyfile", flaky_copyfile)

    with pytest.raises(OSError):
        manager._replace_data_file(temp_file)

    assert manager.data_file.read_text(encoding="utf-8") == "original"


def test_failed_save_does_not_advance_saved_snapshot(monkeypatch, tmp_path):
    old_data = AppData(folders=[Folder(id="old", name="Old")])
    manager = _file_backed_manager(tmp_path, old_data)
    old_dict = old_data.to_dict()
    manager.data_file.write_text(json.dumps(old_dict, ensure_ascii=False), encoding="utf-8")
    manager._last_saved_data_dict = old_dict

    manager.data = AppData(folders=[Folder(id="new", name="New")])
    monkeypatch.setattr(manager, "_replace_data_file", lambda temp_file: (_ for _ in ()).throw(OSError("disk full")))

    manager.save(immediate=True)

    assert manager._last_saved_data_dict == old_dict
    assert manager.list_config_history() == []

    monkeypatch.setattr(manager, "_replace_data_file", lambda temp_file: os.replace(temp_file, manager.data_file))
    manager.save(immediate=True)

    snapshots = manager.list_config_history()
    assert len(snapshots) == 1
    previous = manager.history_manager.load_snapshot_data(snapshots[0].id)
    assert previous["folders"][0]["id"] == "old"


def test_load_quarantines_bad_config_and_recovers_from_auto_backup(tmp_path):
    manager = _file_backed_manager(tmp_path)
    backup_data = AppData(folders=[Folder(id="backup", name="Backup")])
    manager.data_file.write_text("{broken", encoding="utf-8")
    backup_path = manager.auto_backup_dir / "data_20260527_120000_000000.json"
    backup_path.write_text(json.dumps(backup_data.to_dict(), ensure_ascii=False), encoding="utf-8")

    loaded = manager._load()

    assert loaded.folders[0].id == "backup"
    assert json.loads(manager.data_file.read_text(encoding="utf-8"))["folders"][0]["id"] == "backup"
    bad_files = list(manager.recovery_dir.glob("bad_data_*.json"))
    assert len(bad_files) == 1
    report = manager.get_recovery_report()
    assert report["status"] == "recovered"
    assert report["recovered_from"] == str(backup_path)
    assert report["quarantined_path"] == str(bad_files[0])


def test_load_falls_back_to_default_when_no_backup(tmp_path):
    manager = _file_backed_manager(tmp_path)
    manager.data_file.write_text("{broken", encoding="utf-8")

    loaded = manager._load()

    assert isinstance(loaded, AppData)
    assert manager.get_recovery_report()["status"] == "fallback_default"
    assert list(manager.recovery_dir.glob("bad_data_*.json"))


def test_restore_config_history_rolls_back_memory_when_save_fails(monkeypatch, tmp_path):
    old_data = AppData(folders=[Folder(id="old", name="Old")])
    new_data = AppData(folders=[Folder(id="new", name="New")])
    manager = _file_backed_manager(tmp_path, old_data)
    snapshot = manager.history_manager.record_snapshot(new_data.to_dict(), action="test")
    monkeypatch.setattr(manager, "save", lambda immediate=False: False)

    assert snapshot is not None
    assert not manager.restore_config_history(snapshot.id)
    assert manager.data.folders[0].id == "old"
    assert manager._last_saved_data_dict == old_data.to_dict()


def test_backup_full_config_rejects_failed_save(monkeypatch, tmp_path):
    manager = _file_backed_manager(tmp_path)
    backup_path = tmp_path / "backup.zip"
    monkeypatch.setattr(manager, "save", lambda immediate=False: False)

    assert not manager.backup_full_config(str(backup_path))
    assert not backup_path.exists()


def test_restore_full_config_rolls_back_icons_and_memory_when_save_fails(monkeypatch, tmp_path):
    old_data = AppData(folders=[Folder(id="old", name="Old")])
    new_data = AppData(folders=[Folder(id="new", name="New")])
    manager = _file_backed_manager(tmp_path, old_data)
    old_icon = manager.icons_dir / "old.ico"
    old_icon.write_text("old", encoding="utf-8")
    backup = tmp_path / "full.zip"
    with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", json.dumps(new_data.to_dict(), ensure_ascii=False))
        zf.writestr("icons/new.ico", b"new")
    monkeypatch.setattr(manager, "save", lambda immediate=False: False)

    assert not manager.restore_full_config(str(backup))
    assert manager.data.folders[0].id == "old"
    assert (manager.icons_dir / "old.ico").read_text(encoding="utf-8") == "old"
    assert not (manager.icons_dir / "new.ico").exists()


def test_import_shareable_config_strips_elevated_commands(tmp_path):
    manager = _file_backed_manager(tmp_path)
    import_path = tmp_path / "share.zip"
    payload = {
        "items": [
            {
                "type": "command",
                "name": "Py",
                "command_type": "python",
                "command": "print('x')",
                "run_as_admin": True,
            }
        ]
    }
    with zipfile.ZipFile(import_path, "w") as zf:
        zf.writestr("config.json", json.dumps(payload))

    assert manager.import_shareable_config(str(import_path))

    imported = manager.data.folders[-1].items[0]
    assert imported.run_as_admin is False


def test_restore_full_config_preserves_security_sensitive_fields(tmp_path):
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.name = "Py"
    shortcut.command_type = "python"
    shortcut.command = "print('x')"
    shortcut.run_as_admin = True
    data = AppData(folders=[Folder(name="Commands", items=[shortcut])])
    manager = _file_backed_manager(tmp_path, data)
    backup_path = tmp_path / "backup.zip"

    assert manager.backup_full_config(str(backup_path))
    manager.data = AppData()

    assert manager.restore_full_config(str(backup_path))
    restored = manager.data.folders[0].items[0]
    assert restored.run_as_admin is True
    assert restored.command_type == "python"


def test_load_recovers_from_latest_valid_auto_backup(tmp_path):
    manager = _file_backed_manager(tmp_path)
    manager.data_file.write_text("{not-json", encoding="utf-8")
    valid = AppData(folders=[Folder(id="restored", name="Restored")]).to_dict()
    backup = manager.auto_backup_dir / "data_20260522_120000_000000.json"
    backup.write_text(json.dumps(valid, ensure_ascii=False), encoding="utf-8")

    loaded = manager._load()

    assert loaded.get_folder_by_id("restored") is not None
    assert manager.get_config_status()["status"] == "warn"
    assert manager.data_file.read_text(encoding="utf-8") == backup.read_text(encoding="utf-8")


def test_restore_config_history_round_trip(tmp_path):
    old = AppData(folders=[Folder(id="old", name="Old")])
    new = AppData(folders=[Folder(id="new", name="New")])
    manager = _file_backed_manager(tmp_path, new)
    snapshot = manager.history_manager.record_snapshot(old.to_dict(), action="test", summary="old config")
    assert snapshot is not None

    assert manager.restore_config_history(snapshot.id)

    assert manager.data.get_folder_by_id("old") is not None
    assert manager.data.get_folder_by_id("new") is None


def test_restore_full_config_sanitizes_settings_and_skips_bad_icons(tmp_path):
    data = AppData(folders=[Folder(id="f", name="Folder", items=[ShortcutItem(id="s", name="Shortcut")])]).to_dict()
    data["settings"]["icon_size"] = 9999
    data["settings"]["bg_alpha"] = -5
    data["settings"]["bg_solid_color"] = "not-a-color"
    data["settings"]["custom_bg_path"] = "background.png"
    backup = tmp_path / "backup.zip"
    with zipfile.ZipFile(backup, "w") as zf:
        zf.writestr("data.json", json.dumps(data, ensure_ascii=False))
        zf.writestr("background.png", b"bg")
        zf.writestr("icons/bad.exe", b"bad")

    manager = _file_backed_manager(tmp_path)

    assert manager.restore_full_config(str(backup))
    assert manager.data.settings.icon_size == 128
    assert manager.data.settings.bg_alpha == 0
    assert manager.data.settings.bg_solid_color == "#2b2b2b"
    report = manager.get_last_import_report()
    assert report["has_warnings"]
    assert any(item["name"] == "icons/bad.exe" for item in report["skipped_files"])


def test_import_shareable_config_skips_unsafe_icon_but_imports_item(tmp_path):
    package = tmp_path / "share.zip"
    item = {
        "id": "old",
        "name": "Imported",
        "type": "url",
        "url": "https://example.com",
        "icon_path": "icons/payload.exe",
    }
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("config.json", json.dumps({"items": [item]}, ensure_ascii=False))
        zf.writestr("icons/payload.exe", b"bad")

    manager = _file_backed_manager(tmp_path)

    assert manager.import_shareable_config(str(package))
    imported_folder = next(folder for folder in manager.data.folders if folder.name == "导入图标")
    assert imported_folder.items[0].name == "Imported"
    assert imported_folder.items[0].icon_path == ""
    report = manager.get_last_import_report()
    assert report["imported_items"] == 1
    assert report["has_warnings"]


def test_restore_full_config_rejects_path_traversal(tmp_path):
    """zip-slip: path traversal entries are ignored."""
    data = AppData(folders=[Folder(id="f", name="Safe")]).to_dict()
    backup = tmp_path / "backup.zip"
    with zipfile.ZipFile(backup, "w") as zf:
        zf.writestr("data.json", json.dumps(data, ensure_ascii=False))
        zf.writestr("../../../windows/evil.txt", b"malicious")

    manager = _file_backed_manager(tmp_path)

    assert manager.restore_full_config(str(backup))
    assert manager.data.get_folder_by_id("f") is not None
    report = manager.get_last_import_report()
    assert report.get("has_warnings", False)


def test_restore_full_config_rejects_oversized_json(tmp_path, monkeypatch):
    """Data.json exceeding MAX_CONFIG_BYTES is rejected."""
    from core.import_security import MAX_CONFIG_BYTES

    backup = tmp_path / "backup.zip"
    with zipfile.ZipFile(backup, "w") as zf:
        huge = "x" * (MAX_CONFIG_BYTES + 100)
        zf.writestr("data.json", huge)

    manager = _file_backed_manager(tmp_path)

    assert not manager.restore_full_config(str(backup))
    report = manager.get_last_import_report()
    assert report["has_warnings"]


def test_import_shareable_config_rejects_path_traversal(tmp_path):
    """Import ZIP with path traversal in icon entry is rejected."""
    package = tmp_path / "share.zip"
    item = {"name": "Test", "type": "url", "url": "https://example.com"}
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("config.json", json.dumps({"items": [item]}, ensure_ascii=False))
        zf.writestr("../data.json", b"evil")

    manager = _file_backed_manager(tmp_path)

    assert manager.import_shareable_config(str(package))
    report = manager.get_last_import_report()
    assert report["imported_items"] == 1


def test_import_shareable_config_icon_write_failure_is_transactional(monkeypatch, tmp_path):
    import builtins

    package = tmp_path / "share.zip"
    item = {"name": "Test", "type": "url", "url": "https://example.com", "icon_path": "icons/icon.png"}
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("config.json", json.dumps({"items": [item]}, ensure_ascii=False))
        zf.writestr("icons/icon.png", b"png")

    manager = _file_backed_manager(tmp_path)
    original_open = builtins.open

    def flaky_open(path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if "ql_import_icons_" in str(path) and "w" in mode:
            raise OSError("icon write failed")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)

    assert not manager.import_shareable_config(str(package))
    assert all(folder.name != "\u5bfc\u5165\u56fe\u6807" for folder in manager.data.folders)
    assert list(manager.icons_dir.iterdir()) == []


def test_import_shareable_config_save_failure_rolls_back_memory_and_icons(monkeypatch, tmp_path):
    package = tmp_path / "share.zip"
    item = {"name": "Test", "type": "url", "url": "https://example.com", "icon_path": "icons/icon.png"}
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("config.json", json.dumps({"items": [item]}, ensure_ascii=False))
        zf.writestr("icons/icon.png", b"png")

    original_data = AppData(folders=[Folder(id="old", name="Old")])
    manager = _file_backed_manager(tmp_path, original_data)
    monkeypatch.setattr(
        manager,
        "_replace_data_file",
        lambda temp_file: (_ for _ in ()).throw(OSError("replace failed")),
    )

    assert not manager.import_shareable_config(str(package))
    assert [folder.id for folder in manager.data.folders] == ["old"]
    assert list(manager.icons_dir.iterdir()) == []
    assert manager.get_last_import_report()["imported_items"] == 0


def test_import_shareable_config_merge_false_replaces_import_folder(tmp_path):
    manager = _file_backed_manager(tmp_path)

    first = tmp_path / "first.zip"
    with zipfile.ZipFile(first, "w") as zf:
        zf.writestr("config.json", json.dumps({"items": [{"name": "One", "type": "url"}]}, ensure_ascii=False))
    second = tmp_path / "second.zip"
    with zipfile.ZipFile(second, "w") as zf:
        zf.writestr("config.json", json.dumps({"items": [{"name": "Two", "type": "url"}]}, ensure_ascii=False))

    assert manager.import_shareable_config(str(first))
    assert manager.import_shareable_config(str(second), merge=False)

    imported_folder = next(folder for folder in manager.data.folders if folder.name == "\u5bfc\u5165\u56fe\u6807")
    assert [item.name for item in imported_folder.items] == ["Two"]


def test_backup_full_config_includes_icons(tmp_path):
    """Backup includes icon files stored in icons_dir."""
    shortcut = ShortcutItem(id="s", name="App")
    shortcut.icon_path = ""
    data = AppData(folders=[Folder(id="f", name="Folder", items=[shortcut])])
    manager = _file_backed_manager(tmp_path, data)

    icon_file = manager.icons_dir / "custom.png"
    icon_file.write_bytes(b"png-data")
    shortcut.icon_path = str(icon_file)
    shortcut.icon_source = "custom"

    backup_path = tmp_path / "backup.zip"
    assert manager.backup_full_config(str(backup_path))

    with zipfile.ZipFile(backup_path, "r") as zf:
        names = zf.namelist()
        assert "data.json" in names
        assert any(n.startswith("icons/") and n.endswith(".png") for n in names)


def test_backup_full_config_includes_background(tmp_path):
    """Backup includes custom background when bg_mode is image."""
    data = AppData()
    data.settings.bg_mode = "image"
    data.settings.custom_bg_path = str(tmp_path / "bg.jpg")
    (tmp_path / "bg.jpg").write_bytes(b"jpeg-data")

    manager = _file_backed_manager(tmp_path, data)

    backup_path = tmp_path / "backup.zip"
    assert manager.backup_full_config(str(backup_path))

    with zipfile.ZipFile(backup_path, "r") as zf:
        names = zf.namelist()
        assert "data.json" in names
        assert any(n.startswith("background") for n in names)


def test_restore_full_config_recovers_background(tmp_path):
    """Restored backup restores custom background to app_dir."""
    data = AppData(folders=[Folder(id="f", name="Folder")])
    data.settings.bg_mode = "image"
    data.settings.custom_bg_path = "background.png"
    backup = tmp_path / "backup.zip"
    with zipfile.ZipFile(backup, "w") as zf:
        zf.writestr("data.json", json.dumps(data.to_dict(), ensure_ascii=False))
        zf.writestr("background.png", b"bg-content")

    manager = _file_backed_manager(tmp_path)

    assert manager.restore_full_config(str(backup))
    assert manager.data.settings.custom_bg_path
    assert os.path.exists(manager.data.settings.custom_bg_path)


def test_restore_full_config_cleans_background_when_icon_restore_fails(monkeypatch, tmp_path):
    old_data = AppData(folders=[Folder(id="old", name="Old")])
    manager = _file_backed_manager(tmp_path, old_data)
    old_icon = manager.icons_dir / "old.png"
    old_icon.write_bytes(b"old-icon")

    new_data = AppData(folders=[Folder(id="new", name="New")])
    new_data.settings.bg_mode = "image"
    new_data.settings.custom_bg_path = "background.png"
    backup = tmp_path / "backup.zip"
    with zipfile.ZipFile(backup, "w") as zf:
        zf.writestr("data.json", json.dumps(new_data.to_dict(), ensure_ascii=False))
        zf.writestr("background.png", b"bg-content")
        zf.writestr("icons/new.png", b"new-icon")

    monkeypatch.setattr(
        data_manager_module.shutil, "move", lambda src, dst: (_ for _ in ()).throw(OSError("move failed"))
    )

    assert not manager.restore_full_config(str(backup))
    assert manager.data.get_folder_by_id("old") is not None
    assert old_icon.exists()
    assert not list(manager.app_dir.glob("restored_bg_*"))


def test_restore_full_config_skips_unsupported_background_extension(tmp_path):
    data = AppData(folders=[Folder(id="f", name="Folder")])
    data.settings.bg_mode = "image"
    data.settings.custom_bg_path = "background.exe"
    backup = tmp_path / "backup.zip"
    with zipfile.ZipFile(backup, "w") as zf:
        zf.writestr("data.json", json.dumps(data.to_dict(), ensure_ascii=False))
        zf.writestr("background.exe", b"not-an-image")

    manager = _file_backed_manager(tmp_path)

    assert manager.restore_full_config(str(backup))
    assert manager.data.settings.custom_bg_path == ""
    report = manager.get_last_import_report()
    assert report["has_warnings"]


def test_save_creates_auto_backup(tmp_path):
    """save(immediate=True) writes an auto-backup file."""
    data = AppData(folders=[Folder(id="f", name="Test")])
    manager = _file_backed_manager(tmp_path, data)
    manager.data_file.write_text(json.dumps(data.to_dict(), ensure_ascii=False), encoding="utf-8")
    manager._last_saved_data_dict = data.to_dict()

    existing = list(manager.auto_backup_dir.iterdir())
    assert len(existing) == 0

    manager.save(immediate=True)

    backups = list(manager.auto_backup_dir.glob("data_*.json"))
    assert len(backups) >= 1


def test_load_corrupted_falls_back_to_default(tmp_path):
    """Corrupted data.json with no auto-backups returns default AppData."""
    manager = _file_backed_manager(tmp_path)
    manager.data_file.write_text("{invalid-json", encoding="utf-8")
    for f in manager.auto_backup_dir.iterdir():
        f.unlink()

    result = manager._load()
    assert isinstance(result, AppData)
    assert len(result.folders) >= 1
    status = manager.get_config_status()
    assert status["status"] in ("warn", "error")
