from types import SimpleNamespace

from core.data_models import AppSettings, ShortcutItem, ShortcutType
from core.trigger_config import normalize_trigger_config, normalize_trigger_settings, trigger_config_to_hotkey
from core.trigger_conflict_checker import check_trigger_conflict


def test_normalize_trigger_config_filters_invalid_values():
    config = normalize_trigger_config(
        "keyboard",
        ["A", "unknown", "F25", "pageup", "a"],
        "bad-button",
        ["Ctrl", "cmd", "bad", "ctrl"],
    )

    assert config.mode == "keyboard"
    assert config.keys == ["a", "pageup"]
    assert config.button == ""
    assert config.modifiers == ["ctrl", "win"]


def test_normalize_trigger_settings_repairs_invalid_persisted_keyboard_trigger():
    settings = SimpleNamespace(
        popup_trigger_mode="keyboard",
        popup_trigger_keys=["unknown"],
        popup_trigger_button="",
        popup_trigger_modifiers=[],
        popup_special_trigger_mode="hybrid",
        popup_special_trigger_keys=[],
        popup_special_trigger_button="",
        popup_special_trigger_modifiers=["alt"],
    )

    normalized = normalize_trigger_settings(settings)

    assert normalized["popup_trigger_mode"] == "mouse"
    assert normalized["popup_trigger_button"] == "middle"
    assert normalized["popup_trigger_keys"] == []
    assert normalized["popup_special_trigger_mode"] == "mouse"
    assert normalized["popup_special_trigger_button"] == "middle"


def test_normalize_trigger_settings_repairs_unsafe_persisted_triggers():
    settings = SimpleNamespace(
        popup_trigger_mode="keyboard",
        popup_trigger_keys=["p"],
        popup_trigger_button="",
        popup_trigger_modifiers=[],
        popup_special_trigger_mode="mouse",
        popup_special_trigger_keys=[],
        popup_special_trigger_button="middle",
        popup_special_trigger_modifiers=["alt"],
    )

    normalized = normalize_trigger_settings(settings)

    assert normalized["popup_trigger_mode"] == "mouse"
    assert normalized["popup_trigger_button"] == "middle"
    assert normalized["popup_trigger_modifiers"] == []
    assert normalized["popup_special_trigger_mode"] == "mouse"
    assert normalized["popup_special_trigger_button"] == "middle"
    assert normalized["popup_special_trigger_modifiers"] == ["ctrl"]


def test_app_settings_from_dict_normalizes_trigger_fields():
    settings = AppSettings.from_dict(
        {
            "popup_trigger_mode": "keyboard",
            "popup_trigger_keys": ["bad"],
            "popup_trigger_button": "",
            "popup_trigger_modifiers": [],
        }
    )

    assert settings.popup_trigger_mode == "mouse"
    assert settings.popup_trigger_button == "middle"
    assert settings.popup_trigger_keys == []


def test_trigger_config_to_hotkey_only_for_keyboard_mode():
    assert trigger_config_to_hotkey("keyboard", ["p"], ["ctrl", "shift"]) == "ctrl+shift+p"
    assert trigger_config_to_hotkey("hybrid", ["p"], ["ctrl"]) == ""


def test_keyboard_trigger_conflicts_with_existing_shortcut_hotkey():
    shortcut = ShortcutItem(type=ShortcutType.HOTKEY)
    shortcut.name = "保存"
    shortcut.hotkey = "Ctrl+Shift+F6"

    is_conflict, message = check_trigger_conflict(
        mode="keyboard",
        keys=["f6"],
        button="",
        modifiers=["ctrl", "shift"],
        shortcuts=[shortcut],
    )

    assert is_conflict is True
    assert "保存" in message


def test_mouse_trigger_requires_button_after_strict_normalization():
    is_conflict, message = check_trigger_conflict(mode="mouse", keys=[], button="", modifiers=[])

    assert is_conflict is True
    assert "必须指定鼠标按键" in message
