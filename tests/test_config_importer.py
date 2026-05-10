import json
import zipfile
from contextlib import contextmanager

from core.config_importer import ConfigImporter
from core.data_models import AppData, Folder, ShortcutItem, ShortcutType


class FakeDataManager:
    def __init__(self, data):
        self.data = data
        self.saved = False
        self.settings_updates = []

    @contextmanager
    def batch_update(self, immediate=False):
        yield self

    def save(self):
        self.saved = True

    def update_settings(self, **updates):
        self.settings_updates.append(updates)
        for key, value in updates.items():
            if hasattr(self.data.settings, key):
                setattr(self.data.settings, key, value)


def test_legacy_qlpack_export_import_round_trip(tmp_path):
    source_data = AppData()
    source_data.folders = [
        Folder(
            name="Source",
            items=[
                ShortcutItem(
                    name="Docs",
                    type=ShortcutType.URL,
                    url="https://example.com/docs",
                    icon_path="",
                )
            ],
        )
    ]
    source = FakeDataManager(source_data)
    package_path = tmp_path / "shortcuts.qlpack"

    assert ConfigImporter.export_config_legacy(source, str(package_path)) is True

    with zipfile.ZipFile(package_path, "r") as archive:
        assert sorted(archive.namelist()) == ["items.json", "settings.json"]
        items = json.loads(archive.read("items.json").decode("utf-8"))
        assert items[0]["name"] == "Docs"
        assert items[0]["type"] == ShortcutType.URL.value

    target_data = AppData()
    target_data.folders = []
    target = FakeDataManager(target_data)

    assert ConfigImporter.import_config(target, str(package_path)) == 1
    assert target.saved is True
    assert target.settings_updates
    assert len(target.data.folders) == 1
    assert target.data.folders[0].items[0].name == "Docs"
    assert target.data.folders[0].items[0].url == "https://example.com/docs"


def test_import_config_rejects_non_zip_file(tmp_path):
    not_zip = tmp_path / "bad.qlpack"
    not_zip.write_text("not a zip", encoding="utf-8")

    assert ConfigImporter.import_config(FakeDataManager(AppData()), str(not_zip)) == -1
