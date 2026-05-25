from core.data_models import AppData, AppSettings, Folder, ShortcutItem, ShortcutType
from core.project_cache_cleaner import clean_unused_project_cache


class Manager:
    def __init__(self, install_dir, data):
        self.install_dir = install_dir
        self.data = data


def test_clean_unused_project_cache_keeps_configured_icon_and_background(tmp_path):
    temp_icons = tmp_path / "temp_icons"
    favicons = temp_icons / "favicons"
    favicons.mkdir(parents=True)

    used_icon = favicons / "used.png"
    stale_icon = favicons / "stale.png"
    background = temp_icons / "background.png"
    orphan_preview = temp_icons / "settings_panel_icons_preview.png"
    used_icon.write_bytes(b"used")
    stale_icon.write_bytes(b"stale")
    background.write_bytes(b"bg")
    orphan_preview.write_bytes(b"preview")

    item = ShortcutItem(id="url", name="URL", type=ShortcutType.URL, icon_path=str(used_icon))
    data = AppData(
        settings=AppSettings(theme="light", custom_bg_path=str(background)),
        folders=[Folder(id="f", name="Folder", items=[item])],
    )

    stats = clean_unused_project_cache(Manager(tmp_path, data))

    assert stats["total_removed"] == 2
    assert used_icon.exists()
    assert background.exists()
    assert not stale_icon.exists()
    assert not orphan_preview.exists()


def test_clean_unused_project_cache_cleans_project_cache_dirs(tmp_path):
    pycache = tmp_path / "core" / "__pycache__"
    pytest_cache = tmp_path / ".pytest_cache" / "v" / "cache"
    ruff_cache = tmp_path / ".ruff_cache" / "0.1"
    restore_temp = tmp_path / "ql_restore_icons_abc"
    pycache.mkdir(parents=True)
    pytest_cache.mkdir(parents=True)
    ruff_cache.mkdir(parents=True)
    restore_temp.mkdir(parents=True)
    (pycache / "module.cpython-313.pyc").write_bytes(b"pyc")
    (pytest_cache / "nodeids").write_text("x", encoding="utf-8")
    (ruff_cache / "cache.bin").write_bytes(b"ruff")
    (restore_temp / "icon.png").write_bytes(b"icon")

    stats = clean_unused_project_cache(Manager(tmp_path, AppData()))

    assert stats["total_removed"] >= 4
    assert not (pycache / "module.cpython-313.pyc").exists()
    assert not (tmp_path / ".pytest_cache").exists()
    assert not (tmp_path / ".ruff_cache").exists()
    assert not restore_temp.exists()


def test_clean_unused_project_cache_dry_run_preserves_files(tmp_path):
    temp_icons = tmp_path / "temp_icons"
    temp_icons.mkdir()
    orphan = temp_icons / "orphan.png"
    orphan.write_bytes(b"orphan")

    stats = clean_unused_project_cache(Manager(tmp_path, AppData()), dry_run=True)

    assert stats["total_removed"] == 1
    assert orphan.exists()
