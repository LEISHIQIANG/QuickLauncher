"""Tests for config_importer: export/import logic, rollback, preview, path handling."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import zipfile
from unittest.mock import MagicMock

from core.config_importer import ConfigImporter
from core.data_models import AppSettings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dm_mock(folders=None, data=None):
    """Create a DataManager mock."""
    dm = MagicMock()
    if data is not None:
        dm.data = data
    elif folders is not None:
        dm.data = MagicMock()
        dm.data.folders = folders
        dm.data.settings = AppSettings()
    else:
        dm.data = None
    return dm


def _make_zip_with_entries(entries: dict[str, str | bytes], tmp_path) -> str:
    """Create a zip file with given entries. Returns path."""
    path = str(tmp_path / "test_export.zip")
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            if isinstance(content, str):
                zf.writestr(name, content.encode("utf-8"))
            else:
                zf.writestr(name, content)
    return path


# ---------------------------------------------------------------------------
# export_config
# ---------------------------------------------------------------------------


class TestExportConfig:
    def test_returns_false_when_dm_is_none(self):
        result = ConfigImporter.export_config(None, "/tmp/out.zip")
        assert result is False

    def test_returns_false_when_data_is_none(self):
        dm = _make_dm_mock()
        dm.data = None
        result = ConfigImporter.export_config(dm, "/tmp/out.zip")
        assert result is False

    def test_returns_false_when_data_is_falsy(self):
        dm = MagicMock()
        dm.data = MagicMock()
        dm.data.__bool__ = lambda self: False
        result = ConfigImporter.export_config(dm, "/tmp/out.zip")
        assert result is False

    def test_delegates_to_backup_full_config(self):
        dm = _make_dm_mock()
        dm.data = MagicMock()
        dm.backup_full_config.return_value = True
        result = ConfigImporter.export_config(dm, "/tmp/out.zip")
        assert result is True
        dm.backup_full_config.assert_called_once_with("/tmp/out.zip")

    def test_returns_false_when_backup_fails(self):
        dm = _make_dm_mock()
        dm.data = MagicMock()
        dm.backup_full_config.return_value = False
        result = ConfigImporter.export_config(dm, "/tmp/out.zip")
        assert result is False

    def test_returns_false_on_exception(self):
        dm = _make_dm_mock()
        dm.data = MagicMock()
        dm.backup_full_config.side_effect = OSError("disk full")
        result = ConfigImporter.export_config(dm, "/tmp/out.zip")
        assert result is False


# ---------------------------------------------------------------------------
# import_config - early validation
# ---------------------------------------------------------------------------


class TestImportConfigValidation:
    def test_returns_minus_one_for_non_zip(self, tmp_path):
        bad_file = tmp_path / "not_a_zip.txt"
        bad_file.write_text("hello", encoding="utf-8")
        dm = _make_dm_mock()
        result = ConfigImporter.import_config(dm, str(bad_file))
        assert result == -1

    def test_returns_minus_one_for_missing_both_jsons(self, tmp_path):
        zip_path = _make_zip_with_entries({"README.txt": "nothing"}, tmp_path)
        dm = _make_dm_mock()
        result = ConfigImporter.import_config(dm, zip_path)
        assert result == -1

    def test_returns_minus_one_for_corrupt_zip(self, tmp_path):
        bad_zip = tmp_path / "corrupt.zip"
        bad_zip.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
        dm = _make_dm_mock()
        result = ConfigImporter.import_config(dm, str(bad_zip))
        assert result == -1


# ---------------------------------------------------------------------------
# _rollback_legacy_import
# ---------------------------------------------------------------------------


class TestRollbackLegacyImport:
    def test_restores_data(self):
        dm = MagicMock()
        old_data = MagicMock()
        ConfigImporter._rollback_legacy_import(dm, old_data, None, None, [])
        assert dm.data is old_data

    def test_restores_last_saved_data_dict(self):
        dm = MagicMock()
        old_saved = {"key": "value"}
        ConfigImporter._rollback_legacy_import(dm, None, old_saved, None, [])
        assert dm._last_saved_data_dict == old_saved

    def test_restores_config_status(self):
        dm = MagicMock()
        old_status = {"dirty": False}
        ConfigImporter._rollback_legacy_import(dm, None, None, old_status, [])
        assert dm._config_status == old_status

    def test_removes_written_icon_files(self, tmp_path):
        icon1 = tmp_path / "icon1.png"
        icon1.write_bytes(b"png")
        icon2 = tmp_path / "icon2.ico"
        icon2.write_bytes(b"ico")
        dm = MagicMock()
        ConfigImporter._rollback_legacy_import(dm, None, None, None, [str(icon1), str(icon2)])
        assert not icon1.exists()
        assert not icon2.exists()

    def test_handles_none_path_in_icon_list(self, tmp_path):
        icon1 = tmp_path / "icon1.png"
        icon1.write_bytes(b"png")
        dm = MagicMock()
        ConfigImporter._rollback_legacy_import(dm, None, None, None, [None, "", str(icon1)])
        assert not icon1.exists()

    def test_handles_nonexistent_icon_path(self):
        dm = MagicMock()
        # Should not raise
        ConfigImporter._rollback_legacy_import(dm, None, None, None, ["/nonexistent/path/icon.png"])

    def test_handles_all_none_args(self):
        dm = MagicMock()
        # Should not raise even with all None
        ConfigImporter._rollback_legacy_import(dm, None, None, None, [])

    def test_handles_dm_attribute_error(self):
        dm = MagicMock(spec=[])  # No attributes
        # Should not raise - errors are silently caught
        ConfigImporter._rollback_legacy_import(dm, MagicMock(), MagicMock(), {}, [])


# ---------------------------------------------------------------------------
# _preview_full_backup
# ---------------------------------------------------------------------------


class TestPreviewFullBackup:
    def test_counts_items_in_folders(self, tmp_path):
        data_json = json.dumps(
            {
                "version": "1.0",
                "folders": [
                    {"name": "F1", "items": [{"name": "a"}, {"name": "b"}]},
                    {"name": "F2", "items": [{"name": "c"}]},
                ],
                "settings": {},
            }
        )
        zip_path = _make_zip_with_entries({"data.json": data_json}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_full_backup(dm, zf, safe_index, report)
        assert count == 3

    def test_handles_empty_folders(self, tmp_path):
        data_json = json.dumps({"version": "1.0", "folders": [], "settings": {}})
        zip_path = _make_zip_with_entries({"data.json": data_json}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_full_backup(dm, zf, safe_index, report)
        assert count == 0

    def test_handles_folders_not_list(self, tmp_path):
        data_json = json.dumps({"version": "1.0", "folders": "bad", "settings": {}})
        zip_path = _make_zip_with_entries({"data.json": data_json}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_full_backup(dm, zf, safe_index, report)
        assert count == 0

    def test_handles_folder_not_dict(self, tmp_path):
        data_json = json.dumps(
            {
                "version": "1.0",
                "folders": ["not_a_dict", {"name": "ok", "items": [{"name": "x"}]}],
                "settings": {},
            }
        )
        zip_path = _make_zip_with_entries({"data.json": data_json}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_full_backup(dm, zf, safe_index, report)
        assert count == 1

    def test_handles_items_not_list(self, tmp_path):
        data_json = json.dumps(
            {
                "version": "1.0",
                "folders": [{"name": "F1", "items": "bad"}],
                "settings": {},
            }
        )
        zip_path = _make_zip_with_entries({"data.json": data_json}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_full_backup(dm, zf, safe_index, report)
        assert count == 0

    def test_handles_items_not_all_dicts(self, tmp_path):
        data_json = json.dumps(
            {
                "version": "1.0",
                "folders": [{"name": "F1", "items": [{"name": "a"}, "bad", 42]}],
                "settings": {},
            }
        )
        zip_path = _make_zip_with_entries({"data.json": data_json}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_full_backup(dm, zf, safe_index, report)
        assert count == 1

    def test_returns_minus_one_on_invalid_json(self, tmp_path):
        zip_path = _make_zip_with_entries({"data.json": "NOT VALID JSON {{{"}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_full_backup(dm, zf, safe_index, report)
        assert count == -1

    def test_handles_no_data_json_entry(self, tmp_path):
        zip_path = _make_zip_with_entries({"other.txt": "hello"}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_full_backup(dm, zf, safe_index, report)
        assert count == -1


# ---------------------------------------------------------------------------
# _preview_legacy
# ---------------------------------------------------------------------------


class TestPreviewLegacy:
    def test_counts_valid_items(self, tmp_path):
        items = json.dumps(
            [
                {"name": "Chrome", "type": "url", "icon_path": ""},
                {"name": "Notepad", "type": "hotkey", "icon_path": ""},
            ]
        )
        zip_path = _make_zip_with_entries({"items.json": items}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_legacy(dm, zf, safe_index, report)
        assert count == 2

    def test_skips_non_dict_items(self, tmp_path):
        items = json.dumps([{"name": "a"}, "bad", 42])
        zip_path = _make_zip_with_entries({"items.json": items}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_legacy(dm, zf, safe_index, report)
        assert count == 1

    def test_handles_items_not_list(self, tmp_path):
        items = json.dumps({"name": "single_item"})
        zip_path = _make_zip_with_entries({"items.json": items}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_legacy(dm, zf, safe_index, report)
        assert count == -1

    def test_handles_invalid_json(self, tmp_path):
        zip_path = _make_zip_with_entries({"items.json": "NOT JSON"}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_legacy(dm, zf, safe_index, report)
        assert count == -1

    def test_limits_to_2048_items(self, tmp_path):
        items_list = [{"name": f"item{i}", "type": "url"} for i in range(3000)]
        items = json.dumps(items_list)
        zip_path = _make_zip_with_entries({"items.json": items}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_legacy(dm, zf, safe_index, report)
        assert count == 2048

    def test_skips_disallowed_icon_paths(self, tmp_path):
        items = json.dumps(
            [
                {"name": "a", "icon_path": "icons/bad.exe"},
            ]
        )
        zip_path = _make_zip_with_entries(
            {
                "items.json": items,
                "icons/bad.exe": b"\x00" * 10,
            },
            tmp_path,
        )
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_legacy(dm, zf, safe_index, report)
        assert count == 1
        # The icon should be skipped
        assert any("unsupported icon extension" in s.get("reason", "") for s in report.get("skipped_files", []))

    def test_handles_empty_icon_path(self, tmp_path):
        items = json.dumps([{"name": "a", "icon_path": ""}])
        zip_path = _make_zip_with_entries({"items.json": items}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_legacy(dm, zf, safe_index, report)
        assert count == 1

    def test_handles_null_icon_path(self, tmp_path):
        items = json.dumps([{"name": "a", "icon_path": None}])
        zip_path = _make_zip_with_entries({"items.json": items}, tmp_path)
        dm = _make_dm_mock()
        report = {"skipped_files": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_legacy(dm, zf, safe_index, report)
        assert count == 1

    def test_preview_with_settings_json(self, tmp_path):
        items = json.dumps([{"name": "a", "icon_path": ""}])
        settings = json.dumps({"theme": "dark", "bg_alpha": 80})
        zip_path = _make_zip_with_entries(
            {
                "items.json": items,
                "settings.json": settings,
            },
            tmp_path,
        )
        dm = _make_dm_mock()
        report = {"skipped_files": [], "skipped_settings": [], "warnings": []}
        with zipfile.ZipFile(zip_path, "r") as zf:
            from core.import_security import build_safe_zip_index

            safe_index = build_safe_zip_index(zf, report)
            count = ConfigImporter._preview_legacy(dm, zf, safe_index, report)
        assert count == 1
        assert report.get("mode") == "legacy"


# ---------------------------------------------------------------------------
# _import_full_backup (via import_config)
# ---------------------------------------------------------------------------


class TestImportFullBackup:
    def test_returns_minus_one_when_restore_fails(self, tmp_path):
        data_json = json.dumps({"folders": [], "settings": {}})
        zip_path = _make_zip_with_entries({"data.json": data_json}, tmp_path)
        dm = _make_dm_mock()
        dm.restore_full_config.return_value = False
        result = ConfigImporter.import_config(dm, zip_path)
        assert result == -1

    def test_returns_count_on_success(self, tmp_path):
        data_json = json.dumps(
            {
                "folders": [
                    {"name": "F1", "items": [{"name": "a"}, {"name": "b"}]},
                ],
                "settings": {},
            }
        )
        zip_path = _make_zip_with_entries({"data.json": data_json}, tmp_path)
        folder = MagicMock()
        folder.items = [MagicMock(), MagicMock()]
        dm = _make_dm_mock(folders=[folder])
        dm.restore_full_config.return_value = True
        result = ConfigImporter.import_config(dm, zip_path)
        assert result == 2


# ---------------------------------------------------------------------------
# import_config dry_run
# ---------------------------------------------------------------------------


class TestImportConfigDryRun:
    def test_dry_run_full_backup(self, tmp_path):
        data_json = json.dumps(
            {
                "folders": [{"name": "F1", "items": [{"name": "a"}]}],
                "settings": {},
            }
        )
        zip_path = _make_zip_with_entries({"data.json": data_json}, tmp_path)
        dm = _make_dm_mock()
        dm._reset_import_report.return_value = new_report()
        result = ConfigImporter.import_config(dm, zip_path, dry_run=True)
        assert result == 1

    def test_dry_run_legacy(self, tmp_path):
        items = json.dumps([{"name": "a", "icon_path": ""}])
        zip_path = _make_zip_with_entries({"items.json": items}, tmp_path)
        dm = _make_dm_mock()
        dm._reset_import_report.return_value = new_report()
        result = ConfigImporter.import_config(dm, zip_path, dry_run=True)
        assert result == 1


def new_report():
    return {
        "dry_run": False,
        "mode": "",
        "skipped_files": [],
        "skipped_settings": [],
        "warnings": [],
        "imported_items": 0,
    }
