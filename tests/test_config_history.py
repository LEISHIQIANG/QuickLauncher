import gzip
import json
import threading

from core.config_history import ConfigHistoryManager
from core.data_manager import DataManager
from core.data_models import AppData, Folder, ShortcutItem


def _manager(tmp_path):
    manager = object.__new__(DataManager)
    manager.install_dir = tmp_path
    manager.app_dir = tmp_path / "config"
    manager.data_file = manager.app_dir / "data.json"
    manager.icons_dir = tmp_path / "icons"
    manager.auto_backup_dir = manager.app_dir / "auto_backups"
    manager.history_dir = manager.app_dir / "history"
    manager._max_auto_backups = 5
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
    manager.app_dir.mkdir(parents=True)
    manager.icons_dir.mkdir()
    manager.auto_backup_dir.mkdir()
    manager.history_dir.mkdir()
    manager.history_manager = ConfigHistoryManager(manager.history_dir, max_snapshots=20)
    manager.data = AppData(folders=[Folder(id="default", name="常用", items=[ShortcutItem(id="one", name="One")])])
    manager.data_file.write_text(json.dumps(manager.data.to_dict(), ensure_ascii=False), encoding="utf-8")
    manager._last_saved_data_dict = manager.data.to_dict()
    manager._config_status = {"status": "ok", "source": str(manager.data_file), "issues": []}
    return manager


def test_save_records_previous_config_snapshot(tmp_path):
    manager = _manager(tmp_path)

    manager.add_shortcut("default", ShortcutItem(id="two", name="Two"))

    snapshots = manager.list_config_history()
    assert len(snapshots) == 1
    previous = manager.history_manager.load_snapshot_data(snapshots[0].id)
    assert [item["id"] for item in previous["folders"][0]["items"]] == ["one"]


def test_restore_config_history_restores_snapshot(tmp_path):
    manager = _manager(tmp_path)
    manager.add_shortcut("default", ShortcutItem(id="two", name="Two"))
    snapshot_id = manager.list_config_history()[0].id

    assert manager.restore_config_history(snapshot_id)

    restored_ids = [item.id for item in manager.data.folders[0].items]
    assert restored_ids == ["one"]


def test_restore_config_history_rejects_direct_path_outside_history(tmp_path):
    manager = _manager(tmp_path)
    external = tmp_path / "external.json.gz"
    payload = {
        "metadata": {"id": "external", "timestamp": 1, "action": "test", "summary": "", "version": ""},
        "data": AppData(folders=[Folder(id="external", name="External")]).to_dict(),
    }
    with gzip.open(external, "wb") as f:
        f.write(json.dumps(payload).encode("utf-8"))

    assert not manager.restore_config_history(str(external))
    assert manager.data.get_folder_by_id("external") is None
    assert manager.data.get_folder_by_id("default") is not None
