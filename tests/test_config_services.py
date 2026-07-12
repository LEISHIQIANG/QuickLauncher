import json
import os
import threading
import time
import zipfile

from core.config_services import (
    ConfigBackupService,
    ConfigDataStore,
    ConfigPackageService,
    ConfigRecoveryService,
    SaveScheduler,
)
from core.data_models import AppData, Folder
from core.import_security import build_safe_zip_index, new_import_report


def test_config_backup_service_creates_and_prunes_auto_backups(tmp_path):
    data_file = tmp_path / "data.json"
    data_file.write_text('{"folders":[]}', encoding="utf-8")
    backup_dir = tmp_path / "auto_backups"
    service = ConfigBackupService(backup_dir, max_auto_backups=2)

    first = service.create_auto_backup(data_file)
    assert first is not None
    assert first.read_text(encoding="utf-8") == '{"folders":[]}'

    old_backup = backup_dir / "data_20000101_000000_000000.json"
    old_backup.write_text("old", encoding="utf-8")
    very_old_backup = backup_dir / "data_19990101_000000_000000.json"
    very_old_backup.write_text("very-old", encoding="utf-8")
    now = time.time()
    os.utime(old_backup, (now - 10, now - 10))
    os.utime(very_old_backup, (now - 20, now - 20))

    service.prune_auto_backups()

    backups = service.list_auto_backups()
    assert len(backups) == 2
    assert first in backups
    assert old_backup in backups
    assert not very_old_backup.exists()


def test_config_backup_service_missing_data_file_is_noop(tmp_path):
    service = ConfigBackupService(tmp_path / "auto_backups", max_auto_backups=2)

    assert service.create_auto_backup(tmp_path / "missing.json") is None
    assert service.list_auto_backups() == []


def test_save_scheduler_runs_delayed_callback():
    fired = threading.Event()
    scheduler = SaveScheduler(delay=0.01, owner="test-save")

    scheduler.schedule(fired.set)

    assert fired.wait(1.0)
    assert scheduler.current_timer is None


def test_save_scheduler_cancel_prevents_callback():
    fired = threading.Event()
    scheduler = SaveScheduler(delay=0.2, owner="test-save")

    scheduler.schedule(fired.set)
    thread = scheduler.current_timer
    scheduler.cancel()

    if thread is not None:
        thread.join(timeout=1.0)
    assert not fired.wait(0.05)
    assert scheduler.pending is False


def test_config_data_store_serializes_valid_payload(tmp_path):
    store = ConfigDataStore(tmp_path / "data.json")
    payload = store.serialize_data({"settings": {}, "folders": []})

    assert json.loads(payload) == {"settings": {}, "folders": []}


def test_config_data_store_rejects_fatal_schema(tmp_path):
    store = ConfigDataStore(tmp_path / "data.json")

    try:
        store.serialize_data({"folders": "bad"})
    except ValueError as exc:
        assert "folders_not_list" in str(exc)
    else:
        raise AssertionError("fatal config schema should be rejected")


def test_config_recovery_service_recovers_latest_valid_backup(tmp_path):
    data_file = tmp_path / "config" / "data.json"
    backup_dir = tmp_path / "config" / "auto_backups"
    recovery_dir = tmp_path / "config" / "recovery"
    data_file.parent.mkdir(parents=True)
    backup_dir.mkdir()
    backup = backup_dir / "data_20260528_120000_000000.json"
    backup.write_text(
        json.dumps(AppData(folders=[Folder(id="backup", name="Backup")]).to_dict(), ensure_ascii=False),
        encoding="utf-8",
    )
    service = ConfigRecoveryService(recovery_dir, backup_dir, data_file)

    result = service.recover_from_latest_backup("broken", tmp_path / "bad.json")

    assert result is not None
    assert result.data.folders[0].id == "backup"
    assert result.report.status == "recovered"
    assert result.report.recovered_from == str(backup)
    assert json.loads(data_file.read_text(encoding="utf-8"))["folders"][0]["id"] == "backup"


def test_config_package_service_writes_and_restores_extra_config_files(tmp_path):
    app_dir = tmp_path / "config"
    app_dir.mkdir()
    (app_dir / "custom_themes.json").write_text('[{"name":"Theme"}]', encoding="utf-8")
    (app_dir / "command_history.json").write_text('[{"command":"open"}]', encoding="utf-8")
    package = tmp_path / "backup.zip"

    service = ConfigPackageService(app_dir)
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as zf:
        service.write_extra_config_files(zf)

    restore_dir = tmp_path / "restore"
    restore_dir.mkdir()
    restore_service = ConfigPackageService(restore_dir)
    report = new_import_report()
    with zipfile.ZipFile(package, "r") as zf:
        safe_index = build_safe_zip_index(zf, report)
        restore_service.restore_extra_config_files(zf, safe_index, report)

    assert (restore_dir / "custom_themes.json").read_text(encoding="utf-8") == '[{"name":"Theme"}]'
    assert (restore_dir / "command_history.json").read_text(encoding="utf-8") == '[{"command":"open"}]'
