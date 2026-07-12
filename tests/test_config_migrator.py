"""Tests for config_migrator atomicity: backup, marker, partial recovery."""

from pathlib import Path
from unittest.mock import patch

from core.config_migrator import _BACKUP_DIR, _MIGRATION_MARKER, ConfigMigrator


def _make_old_dir(tmp_path: Path) -> Path:
    """Create a fake old config dir with data.json and other files."""
    old_dir = tmp_path / "old_config"
    old_dir.mkdir()
    (old_dir / "data.json").write_text('{"key": "value"}', encoding="utf-8")
    (old_dir / "settings.ini").write_text("[General]\nlang=zh", encoding="utf-8")
    icons = old_dir / "icons"
    icons.mkdir()
    (icons / "app.png").write_bytes(b"png-data")
    return old_dir


class TestMigrateAtomicity:
    def test_migration_creates_marker(self, tmp_path):
        old_dir = _make_old_dir(tmp_path)
        new_dir = tmp_path / "new_config"

        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            stats = ConfigMigrator.migrate()

        assert stats["success"]
        assert (new_dir / _MIGRATION_MARKER).exists()
        assert (new_dir / "data.json").exists()
        assert (new_dir / "settings.ini").exists()
        assert not old_dir.exists()

    def test_migration_removes_backup_on_success(self, tmp_path):
        old_dir = _make_old_dir(tmp_path)
        new_dir = tmp_path / "new_config"

        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            stats = ConfigMigrator.migrate()

        assert stats["success"]
        assert not (new_dir / _BACKUP_DIR).exists()

    def test_needs_partial_recovery_true(self, tmp_path):
        """Old dir exists + new data.json exists + no marker → partial."""
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
            assert ConfigMigrator.needs_partial_recovery()

    def test_needs_partial_recovery_false_with_marker(self, tmp_path):
        """Old dir exists + marker present → not partial."""
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
            assert not ConfigMigrator.needs_partial_recovery()

    def test_recover_partial_completes_remaining_files(self, tmp_path):
        """Simulate partial migration: data.json moved but settings.ini remains."""
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "settings.ini").write_text("[General]\nlang=zh", encoding="utf-8")
        new_dir = tmp_path / "new_config"
        new_dir.mkdir()
        (new_dir / "data.json").write_text('{"key": "value"}', encoding="utf-8")

        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            stats = ConfigMigrator.recover_partial()

        assert stats["success"]
        assert stats["files_recovered"] >= 1
        assert (new_dir / "settings.ini").exists()
        assert (new_dir / _MIGRATION_MARKER).exists()
        assert not old_dir.exists()

    def test_needs_migration_false_after_partial_recovery(self, tmp_path):
        """After partial recovery, needs_migration() should return False."""
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
            # Before recovery: partial recovery detected
            assert ConfigMigrator.needs_partial_recovery()
            ConfigMigrator.recover_partial()

            # After recovery: neither partial nor full migration needed
            assert not ConfigMigrator.needs_partial_recovery()
            assert not ConfigMigrator.needs_migration()

    def test_needs_migration_true_when_no_data(self, tmp_path):
        """Old data.json exists, new dir has no data.json → needs migration."""
        old_dir = tmp_path / "old_config"
        old_dir.mkdir()
        (old_dir / "data.json").write_text("{}", encoding="utf-8")
        new_dir = tmp_path / "new_config"

        with (
            patch.object(ConfigMigrator, "get_old_config_dir", return_value=old_dir),
            patch.object(ConfigMigrator, "get_new_config_dir", return_value=new_dir),
        ):
            assert ConfigMigrator.needs_migration()
