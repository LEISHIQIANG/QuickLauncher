"""Tests for core.config_validation module."""

import pytest

from core.config_validation import (
    _clamp,
    _safe_bool,
    _safe_float,
    _safe_int,
    _safe_string_list,
    sanitize_app_data_dict,
    sanitize_settings_dict,
    validate_app_data_dict,
)

# ---------------------------------------------------------------------------
# _clamp
# ---------------------------------------------------------------------------


def test_clamp_within_range():
    assert _clamp(5, 0, 10) == 5


def test_clamp_below_minimum():
    assert _clamp(-3, 0, 10) == 0


def test_clamp_above_maximum():
    assert _clamp(15, 0, 10) == 10


def test_clamp_at_boundaries():
    assert _clamp(0, 0, 10) == 0
    assert _clamp(10, 0, 10) == 10


def test_clamp_float():
    assert _clamp(5.5, 0.0, 1.0) == 1.0
    assert _clamp(0.3, 0.0, 1.0) == 0.3


def test_clamp_equal_bounds():
    assert _clamp(5, 10, 10) == 10


# ---------------------------------------------------------------------------
# _safe_bool
# ---------------------------------------------------------------------------


def test_safe_bool_true():
    assert _safe_bool(True, False) is True


def test_safe_bool_false():
    assert _safe_bool(False, True) is False


def test_safe_bool_non_bool_returns_default():
    assert _safe_bool(1, False) is False
    assert _safe_bool("yes", True) is True
    assert _safe_bool(None, False) is False
    assert _safe_bool(0, True) is True


# ---------------------------------------------------------------------------
# _safe_int
# ---------------------------------------------------------------------------


def test_safe_int_valid():
    report = {}
    result = _safe_int("bg_alpha", 50, 90, report)
    assert result == 50


def test_safe_int_clamped_too_high():
    report = {"warnings": [], "skipped_settings": []}
    result = _safe_int("bg_alpha", 200, 90, report)
    assert result == 100


def test_safe_int_clamped_too_low():
    report = {"warnings": [], "skipped_settings": []}
    result = _safe_int("bg_alpha", -10, 90, report)
    assert result == 0


def test_safe_int_invalid_type():
    report = {"warnings": [], "skipped_settings": []}
    result = _safe_int("bg_alpha", "not_a_number", 90, report)
    assert result == 90


def test_safe_int_none_value():
    report = {"warnings": [], "skipped_settings": []}
    result = _safe_int("bg_alpha", None, 90, report)
    assert result == 90


def test_safe_int_string_number():
    report = {}
    result = _safe_int("bg_alpha", "75", 90, report)
    assert result == 75


def test_safe_int_float_string():
    report = {}
    result = _safe_int("bg_alpha", "50.7", 90, report)
    assert result == 50


# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------


def test_safe_float_valid():
    report = {}
    result = _safe_float("icon_alpha", 0.5, 1.0, report)
    assert result == 0.5


def test_safe_float_clamped_high():
    report = {"warnings": [], "skipped_settings": []}
    result = _safe_float("icon_alpha", 2.0, 1.0, report)
    assert result == 1.0


def test_safe_float_clamped_low():
    report = {"warnings": [], "skipped_settings": []}
    result = _safe_float("icon_alpha", -0.5, 1.0, report)
    assert result == 0.0


def test_safe_float_invalid():
    report = {"warnings": [], "skipped_settings": []}
    result = _safe_float("icon_alpha", "abc", 1.0, report)
    assert result == 1.0


def test_safe_float_string_number():
    report = {}
    result = _safe_float("icon_alpha", "0.75", 1.0, report)
    assert result == 0.75


# ---------------------------------------------------------------------------
# _safe_string_list
# ---------------------------------------------------------------------------


def test_safe_string_list_valid():
    report = {}
    result = _safe_string_list("enabled_plugins", ["plug1", "plug2"], [], report)
    assert result == ["plug1", "plug2"]


def test_safe_string_list_deduplicates():
    report = {}
    result = _safe_string_list("enabled_plugins", ["Plug1", "plug1", "PLUG1"], [], report)
    assert len(result) == 1
    assert result[0] == "Plug1"


def test_safe_string_list_skips_empty():
    report = {}
    result = _safe_string_list("enabled_plugins", ["", "  ", "valid"], [], report)
    assert result == ["valid"]


def test_safe_string_list_skips_too_long():
    report = {}
    long_str = "x" * 300
    result = _safe_string_list("enabled_plugins", [long_str, "ok"], [], report)
    assert result == ["ok"]


def test_safe_string_list_non_list_returns_default():
    report = {"warnings": [], "skipped_settings": []}
    result = _safe_string_list("enabled_plugins", "not_a_list", ["default"], report)
    assert result == ["default"]


def test_safe_string_list_none_returns_default():
    report = {"warnings": [], "skipped_settings": []}
    result = _safe_string_list("enabled_plugins", None, ["default"], report)
    assert result == ["default"]


def test_safe_string_list_max_items():
    report = {}
    items = [f"item_{i}" for i in range(300)]
    result = _safe_string_list("enabled_plugins", items, [], report)
    assert len(result) == 256


# ---------------------------------------------------------------------------
# sanitize_settings_dict
# ---------------------------------------------------------------------------


def test_sanitize_settings_dict_non_dict():
    report = {"warnings": [], "skipped_settings": []}
    result = sanitize_settings_dict("not_a_dict", report)
    assert isinstance(result, dict)
    assert result["theme"] == "dark"


def test_sanitize_settings_dict_valid():
    settings = {"theme": "light", "bg_alpha": 80, "icon_alpha": 0.5, "auto_start": True}
    result = sanitize_settings_dict(settings)
    assert result["theme"] == "light"
    assert result["bg_alpha"] == 80
    assert result["icon_alpha"] == 0.5
    assert result["auto_start"] is True


def test_sanitize_settings_dict_invalid_theme():
    report = {"warnings": [], "skipped_settings": []}
    settings = {"theme": "rainbow"}
    result = sanitize_settings_dict(settings, report)
    assert result["theme"] == "dark"  # default preserved
    assert len(report["skipped_settings"]) > 0


def test_sanitize_settings_dict_unknown_keys_ignored():
    settings = {"unknown_key": "value", "theme": "dark"}
    result = sanitize_settings_dict(settings)
    assert "unknown_key" not in result
    assert result["theme"] == "dark"


def test_sanitize_settings_dict_invalid_bool():
    report = {"warnings": [], "skipped_settings": []}
    settings = {"auto_start": "yes"}
    result = sanitize_settings_dict(settings, report)
    assert result["auto_start"] is False  # default


def test_sanitize_settings_dict_color_validation():
    settings = {"edge_highlight_color": "#ff0000"}
    result = sanitize_settings_dict(settings)
    assert result["edge_highlight_color"] == "#ff0000"


def test_sanitize_settings_dict_invalid_color():
    report = {"warnings": [], "skipped_settings": []}
    settings = {"edge_highlight_color": "red"}
    result = sanitize_settings_dict(settings, report)
    assert result["edge_highlight_color"] == "#ffffff"  # default


def test_sanitize_settings_dict_string_too_long():
    report = {"warnings": [], "skipped_settings": []}
    settings = {"last_version": "x" * 3000}
    result = sanitize_settings_dict(settings, report)
    assert result["last_version"] == ""  # default


def test_sanitize_settings_dict_string_list():
    settings = {"enabled_plugins": ["plug1", "plug2"]}
    result = sanitize_settings_dict(settings)
    assert result["enabled_plugins"] == ["plug1", "plug2"]


# ---------------------------------------------------------------------------
# sanitize_app_data_dict
# ---------------------------------------------------------------------------


def test_sanitize_app_data_dict_non_dict():
    with pytest.raises(ValueError, match="root_not_object"):
        sanitize_app_data_dict("not_a_dict")


def test_sanitize_app_data_dict_valid():
    data = {
        "version": "2.5",
        "settings": {"theme": "dark"},
        "folders": [{"id": "f1", "items": [{"id": "s1"}]}],
    }
    result = sanitize_app_data_dict(data)
    assert result["version"] == "2.5"
    assert isinstance(result["settings"], dict)
    assert len(result["folders"]) == 1
    assert result["folders"][0]["id"] == "f1"


def test_sanitize_app_data_dict_folders_not_list():
    data = {"settings": {}, "folders": "not_a_list"}
    with pytest.raises(ValueError, match="folders_not_list"):
        sanitize_app_data_dict(data)


def test_sanitize_app_data_dict_non_dict_folder_skipped():
    data = {"settings": {}, "folders": ["bad", {"id": "good"}]}
    result = sanitize_app_data_dict(data)
    assert len(result["folders"]) == 1
    assert result["folders"][0]["id"] == "good"


def test_sanitize_app_data_dict_non_dict_items_filtered():
    data = {
        "settings": {},
        "folders": [{"id": "f1", "items": ["bad", {"id": "good"}]}],
    }
    result = sanitize_app_data_dict(data)
    assert len(result["folders"][0]["items"]) == 1
    assert result["folders"][0]["items"][0]["id"] == "good"


def test_sanitize_app_data_dict_items_not_list_replaced():
    data = {
        "settings": {},
        "folders": [{"id": "f1", "items": "not_a_list"}],
    }
    result = sanitize_app_data_dict(data)
    assert result["folders"][0]["items"] == []


def test_sanitize_app_data_dict_no_settings_uses_default():
    data = {"folders": []}
    result = sanitize_app_data_dict(data)
    assert isinstance(result["settings"], dict)
    assert result["settings"]["theme"] == "dark"


# ---------------------------------------------------------------------------
# validate_app_data_dict
# ---------------------------------------------------------------------------


def test_validate_app_data_dict_valid():
    data = {
        "settings": {"theme": "dark"},
        "folders": [
            {"id": "f1", "items": [{"id": "s1", "type": "file"}]},
        ],
    }
    issues = validate_app_data_dict(data)
    assert issues == []


def test_validate_app_data_dict_root_not_object():
    issues = validate_app_data_dict("not_a_dict")
    assert "root_not_object" in issues


def test_validate_app_data_dict_settings_not_object():
    issues = validate_app_data_dict({"settings": "not_a_dict", "folders": []})
    assert "settings_not_object" in issues


def test_validate_app_data_dict_folders_not_list():
    issues = validate_app_data_dict({"folders": "not_a_list"})
    assert "folders_not_list" in issues


def test_validate_app_data_dict_duplicate_folder_ids():
    data = {
        "folders": [
            {"id": "f1", "items": []},
            {"id": "f1", "items": []},
        ],
    }
    issues = validate_app_data_dict(data)
    assert any("duplicate_folder_id" in i for i in issues)


def test_validate_app_data_dict_duplicate_shortcut_ids():
    data = {
        "folders": [
            {
                "id": "f1",
                "items": [
                    {"id": "s1", "type": "file"},
                    {"id": "s1", "type": "file"},
                ],
            },
        ],
    }
    issues = validate_app_data_dict(data)
    assert any("duplicate_shortcut_id" in i for i in issues)


def test_validate_app_data_dict_folder_not_object():
    data = {"folders": ["not_a_dict"]}
    issues = validate_app_data_dict(data)
    assert "folder_0_not_object" in issues


def test_validate_app_data_dict_item_not_object():
    data = {"folders": [{"id": "f1", "items": ["not_a_dict"]}]}
    issues = validate_app_data_dict(data)
    assert "folder_0_item_0_not_object" in issues


def test_validate_app_data_dict_folder_items_not_list():
    data = {"folders": [{"id": "f1", "items": "not_a_list"}]}
    issues = validate_app_data_dict(data)
    assert "folder_0_items_not_list" in issues


def test_validate_app_data_dict_invalid_shortcut_type():
    data = {
        "folders": [
            {"id": "f1", "items": [{"id": "s1", "type": "unknown_type"}]},
        ],
    }
    issues = validate_app_data_dict(data)
    assert any("invalid_shortcut_type" in i for i in issues)


def test_validate_app_data_dict_valid_types():
    valid_types = {"file", "folder", "url"}
    for vtype in valid_types:
        data = {
            "folders": [{"id": "f1", "items": [{"id": "s1", "type": vtype}]}],
        }
        issues = validate_app_data_dict(data)
        assert not any("invalid_shortcut_type" in i for i in issues)


def test_validate_app_data_dict_none_settings_ok():
    data = {"settings": None, "folders": []}
    issues = validate_app_data_dict(data)
    assert "settings_not_object" not in issues


def test_validate_app_data_dict_empty():
    data = {}
    issues = validate_app_data_dict(data)
    assert issues == []
