from core.config_migrator import ConfigMigrator


def test_needs_migration_when_old_data_exists_and_new_missing(tmp_path, monkeypatch):
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "data.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(ConfigMigrator, "get_old_config_dir", staticmethod(lambda: old_dir))
    monkeypatch.setattr(ConfigMigrator, "get_new_config_dir", staticmethod(lambda: new_dir))

    assert ConfigMigrator.needs_migration() is True


def test_migrate_copies_config_and_preserves_data(tmp_path, monkeypatch):
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    (old_dir / "data.json").write_text('{"version":"legacy"}', encoding="utf-8")
    (old_dir / "icons").mkdir()
    (old_dir / "icons" / "x.png").write_bytes(b"icon")

    monkeypatch.setattr(ConfigMigrator, "get_old_config_dir", staticmethod(lambda: old_dir))
    monkeypatch.setattr(ConfigMigrator, "get_new_config_dir", staticmethod(lambda: new_dir))

    stats = ConfigMigrator.migrate()

    assert stats["success"] is True
    assert (new_dir / "data.json").read_text(encoding="utf-8") == '{"version":"legacy"}'
    assert (new_dir / "icons" / "x.png").read_bytes() == b"icon"
