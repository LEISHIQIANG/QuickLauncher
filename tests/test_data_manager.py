import json
import os
from pathlib import Path

from core.data_manager import DataManager
from core.data_models import AppData, Folder


def make_manager(tmp_path: Path) -> DataManager:
    manager = object.__new__(DataManager)
    manager.data = AppData()
    manager.data_file = tmp_path / "data.json"
    manager.auto_backup_dir = tmp_path / "auto_backups"
    manager._max_auto_backups = 5
    return manager


def test_do_save_writes_valid_json(tmp_path):
    manager = make_manager(tmp_path)
    manager.data.folders.append(Folder(name="Extra"))

    manager._do_save()

    payload = json.loads(manager.data_file.read_text(encoding="utf-8"))
    assert payload["settings"]
    assert any(folder["name"] == "Extra" for folder in payload["folders"])


def test_do_save_keeps_original_when_serialization_fails(tmp_path):
    manager = make_manager(tmp_path)
    manager.data_file.write_text('{"version":"old"}', encoding="utf-8")

    class BrokenData:
        def to_dict(self):
            return {"bad": {object()}}

    manager.data = BrokenData()
    manager._do_save()

    assert manager.data_file.read_text(encoding="utf-8") == '{"version":"old"}'
    assert json.loads(manager.data_file.read_text(encoding="utf-8"))["version"] == "old"


def test_auto_backup_creates_backups(tmp_path):
    manager = make_manager(tmp_path)
    manager.data_file.write_text('{"version":"seed"}', encoding="utf-8")

    for idx in range(2):
        manager.data.version = str(idx)
        manager._do_save()

    backups = sorted(manager.auto_backup_dir.glob("data_*.json"))
    assert backups
    assert json.loads(manager.data_file.read_text(encoding="utf-8"))["version"] == "1"


def test_prune_auto_backups_targets_oldest_files(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    manager.auto_backup_dir.mkdir()
    manager._max_auto_backups = 5

    backups = []
    for idx in range(7):
        backup = manager.auto_backup_dir / f"data_{idx}.json"
        backup.write_text("{}", encoding="utf-8")
        os.utime(backup, (idx, idx))
        backups.append(backup)

    deleted = []

    def fake_unlink(path_self):
        deleted.append(path_self.name)

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    manager._prune_auto_backups()

    assert deleted == ["data_1.json", "data_0.json"]
