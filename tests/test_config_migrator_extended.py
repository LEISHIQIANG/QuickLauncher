"""Extended tests for config_migrator: directory resolution, edge cases, error paths."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config_migrator import _MIGRATION_MARKER, ConfigMigrator

# ---------------------------------------------------------------------------
# get_old_config_dir
# ---------------------------------------------------------------------------


class TestGetOldConfigDir:
    def test_uses_appdata_env_var(self):
        with patch.dict(os.environ, {"APPDATA": r"C:\Users\Test\AppData\Roaming"}, clear=False):
            d = ConfigMigrator.get_old_config_dir()
            assert d == Path(r"C:\Users\Test\AppData\Roaming") / "QuickLauncher"

    def test_falls_back_when_appdata_empty(self):
        with patch.dict(os.environ, {"APPDATA": ""}, clear=False):
            d = ConfigMigrator.get_old_config_dir()
            expected_base = Path(os.path.expanduser("~")) / "AppData" / "Roaming"
            assert d == expected_base / "QuickLauncher"

    def test_falls_back_when_appdata_missing(self):
        env = {k: v for k, v in os.environ.items() if k != "APPDATA"}
        with patch.dict(os.environ, env, clear=True):
            d = ConfigMigrator.get_old_config_dir()
            expected_base = Path(os.path.expanduser("~")) / "AppData" / "Roaming"
            assert d == expected_base / "QuickLauncher"


# ---------------------------------------------------------------------------
# get_new_config_dir
# ---------------------------------------------------------------------------


class TestGetNewConfigDir:
    def test_frozen_mode_uses_executable_parent(self):
        mock_sys = MagicMock()
        mock_sys.frozen = True
        mock_sys.executable = r"C:\Apps\QuickLauncher\QuickLauncher.exe"
        with patch("core.config_migrator.sys", mock_sys):
            d = ConfigMigrator.get_new_config_dir()
            assert d == Path(r"C:\Apps\QuickLauncher\config")

    def test_dev_mode_uses_file_parent_parent(self):
        mock_sys = MagicMock()
        mock_sys.frozen = False
        with patch("core.config_migrator.sys", mock_sys):
            d = ConfigMigrator.get_new_config_dir()
            # __file__ is .../core/config_migrator.py, parent.parent is project root
            assert d.name == "config"


# ---------------------------------------------------------------------------
# needs_migration edge cases
# ---------------------------------------------------------------------------


class TestNeedsMigrationExtended:
    def test_false_when_old_data_missing(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        new_dir = tmp_path / "new_config"
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            assert not ConfigMigrator.needs_migration()

    def test_false_when_old_dir_not_exists(self, tmp_path):
        old_dir = tmp_path / "nonexistent"
        new_dir = tmp_path / "new_config"
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            assert not ConfigMigrator.needs_migration()

    def test_true_when_old_data_exists_no_new_data(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "data.json").write_text("{}", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            assert ConfigMigrator.needs_migration()

    def test_true_when_new_data_exists_but_no_marker_and_old_dir_exists(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "data.json").write_text("{}", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        new_dir.mkdir()
        (new_dir / "data.json").write_text("{}", encoding="utf-8")
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            assert ConfigMigrator.needs_migration()

    def test_false_when_new_data_and_marker_exist(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "data.json").write_text("{}", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        new_dir.mkdir()
        (new_dir / "data.json").write_text("{}", encoding="utf-8")
        (new_dir / _MIGRATION_MARKER).write_text("done", encoding="utf-8")
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            assert not ConfigMigrator.needs_migration()

    def test_false_when_new_data_exists_marker_exists_old_gone(self, tmp_path):
        new_dir = tmp_path / "new_config"
        new_dir.mkdir()
        (new_dir / "data.json").write_text("{}", encoding="utf-8")
        (new_dir / _MIGRATION_MARKER).write_text("done", encoding="utf-8")
        old_dir = tmp_path / "nonexistent_old"
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            assert not ConfigMigrator.needs_migration()


# ---------------------------------------------------------------------------
# needs_partial_recovery edge cases
# ---------------------------------------------------------------------------


class TestNeedsPartialRecoveryExtended:
    def test_false_when_old_dir_not_exists(self, tmp_path):
        old_dir = tmp_path / "nonexistent"
        new_dir = tmp_path / "new_config"
        new_dir.mkdir()
        (new_dir / "data.json").write_text("{}", encoding="utf-8")
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            assert not ConfigMigrator.needs_partial_recovery()

    def test_false_when_new_data_missing(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        new_dir = tmp_path / "new_config"
        new_dir.mkdir()
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            assert not ConfigMigrator.needs_partial_recovery()


# ---------------------------------------------------------------------------
# migrate edge cases
# ---------------------------------------------------------------------------


class TestMigrateExtended:
    def test_migrate_no_old_dir_returns_success(self, tmp_path):
        old_dir = tmp_path / "nonexistent"
        new_dir = tmp_path / "new_config"
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            stats = ConfigMigrator.migrate()
        assert stats["success"]
        assert stats["files_moved"] == 0

    def test_migrate_old_data_missing_returns_success(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        new_dir = tmp_path / "new_config"
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            stats = ConfigMigrator.migrate()
        assert stats["success"]

    def test_migrate_calls_progress_callback(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "data.json").write_text("{}", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        callback = MagicMock()
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            ConfigMigrator.migrate(progress_callback=callback)
        assert callback.call_count >= 2

    def test_migrate_progress_callback_exception_ignored(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "data.json").write_text("{}", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        callback = MagicMock(side_effect=RuntimeError("boom"))
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            stats = ConfigMigrator.migrate(progress_callback=callback)
        assert stats["success"]

    def test_migrate_moves_files_and_dirs(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "data.json").write_text('{"k":1}', encoding="utf-8")
        sub = old_dir / "icons"
        sub.mkdir()
        (sub / "a.png").write_bytes(b"img")
        new_dir = tmp_path / "new_config"
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            stats = ConfigMigrator.migrate()
        assert stats["success"]
        assert stats["files_moved"] >= 2
        assert (new_dir / "data.json").exists()
        assert (new_dir / "icons" / "a.png").exists()

    def test_migrate_preserves_marker_content(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "data.json").write_text("{}", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            ConfigMigrator.migrate()
        marker_content = (new_dir / _MIGRATION_MARKER).read_text(encoding="utf-8")
        assert "migration_completed" in marker_content

    def test_migrate_deletes_empty_old_dir(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "data.json").write_text("{}", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            ConfigMigrator.migrate()
        assert not old_dir.exists()

    def test_migrate_partial_data_missing_calls_recover(self, tmp_path):
        """When old_data.json is missing but new_data.json and old_dir exist, should call recover_partial."""
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "settings.ini").write_text("[g]", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        new_dir.mkdir()
        (new_dir / "data.json").write_text("{}", encoding="utf-8")
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            stats = ConfigMigrator.migrate()
        assert stats["success"]
        assert stats["files_recovered"] >= 1

    def test_migrate_single_file(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "data.json").write_text("{}", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            stats = ConfigMigrator.migrate()
        assert stats["success"]
        assert stats["files_moved"] == 1


# ---------------------------------------------------------------------------
# recover_partial edge cases
# ---------------------------------------------------------------------------


class TestRecoverPartialExtended:
    def test_recover_no_old_dir_returns_success(self, tmp_path):
        old_dir = tmp_path / "nonexistent"
        new_dir = tmp_path / "new_config"
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            stats = ConfigMigrator.recover_partial()
        assert stats["success"]
        assert stats["files_recovered"] == 0

    def test_recover_calls_progress_callback(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "settings.ini").write_text("[g]", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        new_dir.mkdir()
        callback = MagicMock()
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            ConfigMigrator.recover_partial(progress_callback=callback)
        assert callback.call_count >= 1

    def test_recover_progress_callback_exception_ignored(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "settings.ini").write_text("[g]", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        new_dir.mkdir()
        callback = MagicMock(side_effect=RuntimeError("fail"))
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            stats = ConfigMigrator.recover_partial(progress_callback=callback)
        assert stats["success"]

    def test_recover_with_directory(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        sub = old_dir / "plugins"
        sub.mkdir()
        (sub / "ext.py").write_text("# ext", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        new_dir.mkdir()
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            stats = ConfigMigrator.recover_partial()
        assert stats["success"]
        assert (new_dir / "plugins" / "ext.py").exists()

    def test_recover_writes_marker_with_recovered_content(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "data.json").write_text("{}", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        new_dir.mkdir()
        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            ConfigMigrator.recover_partial()
        marker = (new_dir / _MIGRATION_MARKER).read_text(encoding="utf-8")
        assert "recovered_from_partial" in marker

    def test_recover_handles_file_error_gracefully(self, tmp_path):
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "bad_file.txt").write_text("data", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        new_dir.mkdir()
        # Patch shutil.move to fail for the file
        original_move = __import__("shutil").move

        def failing_move(src, dst):
            if "bad_file" in src:
                raise PermissionError("access denied")
            return original_move(src, dst)

        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
            patch("shutil.move", side_effect=failing_move),
        ):
            stats = ConfigMigrator.recover_partial()
        assert len(stats["errors"]) >= 1
        # But overall may still succeed depending on implementation
        assert "success" in stats
