from types import SimpleNamespace

from core.config_validation import sanitize_settings_dict
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


def test_normalize_trigger_settings_keeps_modifier_free_keyboard_and_alt_mouse_triggers():
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

    assert normalized["popup_trigger_mode"] == "keyboard"
    assert normalized["popup_trigger_keys"] == ["p"]
    assert normalized["popup_trigger_button"] == ""
    assert normalized["popup_trigger_modifiers"] == []
    assert normalized["popup_special_trigger_mode"] == "mouse"
    assert normalized["popup_special_trigger_button"] == "middle"
    assert normalized["popup_special_trigger_modifiers"] == ["alt"]


def test_normalize_trigger_settings_disables_mouse_trigger_for_taskbar_source():
    settings = SimpleNamespace(
        popup_trigger_source="taskbar",
        popup_trigger_mode="mouse",
        popup_trigger_keys=[],
        popup_trigger_button="",
        popup_trigger_modifiers=[],
        popup_special_trigger_source="mouse",
        popup_special_trigger_mode="mouse",
        popup_special_trigger_keys=[],
        popup_special_trigger_button="middle",
        popup_special_trigger_modifiers=["ctrl"],
    )

    normalized = normalize_trigger_settings(settings)

    assert normalized["popup_trigger_mode"] == "mouse"
    assert normalized["popup_trigger_button"] == ""
    assert normalized["popup_trigger_keys"] == []
    assert normalized["popup_trigger_modifiers"] == []
    assert normalized["popup_special_trigger_button"] == "middle"


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


def test_app_settings_from_dict_preserves_taskbar_trigger_without_middle_button():
    settings = AppSettings.from_dict(
        {
            "popup_trigger_source": "taskbar",
            "popup_trigger_mode": "mouse",
            "popup_trigger_keys": [],
            "popup_trigger_button": "",
            "popup_trigger_modifiers": [],
        }
    )

    assert settings.popup_trigger_source == "taskbar"
    assert settings.popup_trigger_button == ""
    assert settings.popup_trigger_modifiers == []


def test_sanitize_settings_dict_preserves_taskbar_trigger_source():
    sanitized = sanitize_settings_dict(
        {
            "popup_trigger_source": "taskbar",
            "popup_trigger_mode": "mouse",
            "popup_trigger_keys": [],
            "popup_trigger_button": "",
            "popup_trigger_modifiers": [],
            "popup_taskbar_trigger_ctrl": True,
            "popup_special_trigger_source": "taskbar",
            "popup_special_trigger_mode": "mouse",
            "popup_special_trigger_keys": [],
            "popup_special_trigger_button": "",
            "popup_special_trigger_modifiers": [],
            "popup_special_taskbar_trigger_ctrl": True,
        }
    )

    assert sanitized["popup_trigger_source"] == "taskbar"
    assert sanitized["popup_trigger_button"] == ""
    assert sanitized["popup_taskbar_trigger_ctrl"] is True
    assert sanitized["popup_special_trigger_source"] == "taskbar"
    assert sanitized["popup_special_trigger_button"] == ""
    assert sanitized["popup_special_taskbar_trigger_ctrl"] is True


def test_trigger_config_to_hotkey_only_for_keyboard_mode():
    assert trigger_config_to_hotkey("keyboard", ["p"], ["ctrl", "shift"]) == "ctrl+shift+p"
    assert trigger_config_to_hotkey("keyboard", ["q"], ["alt"]) == "alt+q"
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

    assert is_conflict is False
    assert "保存" in message


def test_trigger_config_keeps_extended_and_generic_keyboard_keys():
    config = normalize_trigger_config("keyboard", ["capslock", "browserback", "vk_e8"], "", [])

    assert config.keys == ["capslock", "browserback", "vk_e8"]


def test_mouse_trigger_requires_button_after_strict_normalization():
    is_conflict, message = check_trigger_conflict(mode="mouse", keys=[], button="", modifiers=[])

    assert is_conflict is True
    assert "必须指定鼠标按键" in message


def test_plain_left_and_right_mouse_triggers_are_preserved_with_warning():
    left = normalize_trigger_config("mouse", [], "left", [], fill_defaults=True)
    right = normalize_trigger_config("mouse", [], "right", [], fill_defaults=True)

    left_conflict, left_message = check_trigger_conflict(mode="mouse", button="left", modifiers=[])
    right_conflict, right_message = check_trigger_conflict(mode="mouse", button="right", modifiers=[])

    assert left.button == "left"
    assert right.button == "right"
    assert left.modifiers == []
    assert right.modifiers == []
    assert left_conflict is False
    assert right_conflict is False
    assert "拦截正常点击" in left_message
    assert "拦截正常点击" in right_message


def test_alt_q_keyboard_trigger_is_supported_without_warning():
    is_conflict, message = check_trigger_conflict(
        mode="keyboard",
        keys=["q"],
        button="",
        modifiers=["alt"],
    )

    assert is_conflict is False
    assert message == ""
