from core.data_models import AppData, AppSettings, Folder, ShortcutItem, ShortcutType


def test_shortcut_item_round_trip_preserves_fields():
    item = ShortcutItem(
        name="Open docs",
        type=ShortcutType.URL,
        order=3,
        url="https://example.com",
        icon_path="icon.png",
        run_as_admin=True,
    )

    restored = ShortcutItem.from_dict(item.to_dict())

    assert restored.id == item.id
    assert restored.name == "Open docs"
    assert restored.type == ShortcutType.URL
    assert restored.order == 3
    assert restored.url == "https://example.com"
    assert restored.icon_path == "icon.png"
    assert restored.run_as_admin is True


def test_folder_round_trip_preserves_items_and_sync_fields():
    item = ShortcutItem(name="Tool", type=ShortcutType.FILE, target_path="tool.exe")
    folder = Folder(name="Work", order=2, linked_path="C:/Work", auto_sync=True, items=[item])

    restored = Folder.from_dict(folder.to_dict())

    assert restored.id == folder.id
    assert restored.name == "Work"
    assert restored.linked_path == "C:/Work"
    assert restored.auto_sync is True
    assert len(restored.items) == 1
    assert restored.items[0].target_path == "tool.exe"


def test_app_settings_round_trip_preserves_current_schema():
    settings = AppSettings(
        theme="light",
        bg_mode="image",
        custom_bg_path="background.png",
        popup_auto_close=False,
        special_apps=["cad"],
    )

    restored = AppSettings.from_dict(settings.to_dict())

    assert restored.theme == "light"
    assert restored.bg_mode == "image"
    assert restored.custom_bg_path == "background.png"
    assert restored.popup_auto_close is False
    assert restored.special_apps == ["cad"]


def test_app_data_creates_default_folders_when_missing():
    data = AppData.from_dict({"version": "x", "settings": {}, "folders": []})

    assert data.version == "x"
    assert data.get_dock() is not None
    assert len(data.get_pages()) == 1
