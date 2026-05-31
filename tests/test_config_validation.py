import json
import logging

from core.config_validation import load_valid_data_file, validate_app_data_dict
from core.data_models import AppData

logger = logging.getLogger(__name__)


def test_validate_app_data_dict_detects_duplicate_shortcut_ids():
    data = AppData().to_dict()
    data["folders"][0]["items"] = [
        {"id": "same", "name": "A", "type": "file"},
        {"id": "same", "name": "B", "type": "file"},
    ]

    issues = validate_app_data_dict(data)

    assert "duplicate_shortcut_id:same" in issues


def test_load_valid_data_file_rejects_non_object(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps([]), encoding="utf-8")

    try:
        load_valid_data_file(path)
    except ValueError as exc:
        assert "root_not_object" in str(exc)
    else:
        raise AssertionError("invalid config should be rejected")


def test_validate_recognizes_chain_type():
    """chain 类型应被配置校验认可，不产生 invalid_shortcut_type issue。"""
    data = AppData().to_dict()
    data["folders"][0]["items"] = [
        {"id": "c1", "name": "My Chain", "type": "chain", "chain_steps": [{"shortcut_id": "ref"}]},
    ]
    issues = validate_app_data_dict(data)
    for issue in issues:
        assert "invalid_shortcut_type" not in issue


# ── appended tests ──────────────────────────────────────────────

from core.config_validation import (  # noqa: E402
    _clamp,
    _safe_float,
    _safe_int,
    latest_valid_backup,
    sanitize_app_data_dict,
    sanitize_settings_dict,
    validate_app_data,
)


def test_clamp_min_equals_max():
    """_clamp 当 min==max 时始终返回该值"""
    assert _clamp(5, 10, 10) == 10
    assert _clamp(10, 10, 10) == 10
    assert _clamp(15, 10, 10) == 10


def test_clamp_value_exactly_at_boundary():
    """_clamp 值恰好在边界上"""
    assert _clamp(0, 0, 100) == 0
    assert _clamp(100, 0, 100) == 100
    assert _clamp(50, 0, 100) == 50


def test_safe_int_at_min_boundary():
    """_safe_int 值恰好在最小边界"""
    result = _safe_int("bg_alpha", 0, 90, None)
    assert result == 0


def test_safe_int_at_max_boundary():
    """_safe_int 值恰好在最大边界"""
    result = _safe_int("bg_alpha", 100, 90, None)
    assert result == 100


def test_safe_float_at_min_boundary():
    """_safe_float 值恰好在最小边界"""
    result = _safe_float("icon_alpha", 0.0, 1.0, None)
    assert result == 0.0


def test_safe_float_at_max_boundary():
    """_safe_float 值恰好在最大边界"""
    result = _safe_float("icon_alpha", 1.0, 1.0, None)
    assert result == 1.0


def test_sanitize_settings_dict_valid_non_defaults():
    """sanitize_settings_dict 使用非默认有效值"""
    settings = {"bg_alpha": 50, "icon_alpha": 0.5, "theme": "light", "sort_mode": "smart"}
    result = sanitize_settings_dict(settings)
    assert result["bg_alpha"] == 50
    assert result["icon_alpha"] == 0.5
    assert result["theme"] == "light"
    assert result["sort_mode"] == "smart"


def test_sanitize_settings_dict_bg_alpha_above_100():
    """sanitize_settings_dict 将超过 100 的 bg_alpha 截断到 100"""
    settings = {"bg_alpha": 255}
    result = sanitize_settings_dict(settings)
    assert result["bg_alpha"] == 100


def test_sanitize_settings_dict_int_fields_at_boundaries():
    """sanitize_settings_dict 所有整数字段在边界值"""
    from core.config_validation import _INT_RANGES

    boundary_settings = {}
    for key, (lo, _hi) in _INT_RANGES.items():
        boundary_settings[key] = lo
    result = sanitize_settings_dict(boundary_settings)
    for key, (lo, _hi) in _INT_RANGES.items():
        assert result[key] == lo, f"{key} should be {lo}"

    boundary_settings = {}
    for key, (_lo, hi) in _INT_RANGES.items():
        boundary_settings[key] = hi
    result = sanitize_settings_dict(boundary_settings)
    for key, (_lo, hi) in _INT_RANGES.items():
        assert result[key] == hi, f"{key} should be {hi}"


def test_sanitize_settings_dict_float_fields_at_boundaries():
    """sanitize_settings_dict 所有浮点字段在边界值"""
    from core.config_validation import _FLOAT_RANGES

    for boundary in (0.0, 1.0):
        boundary_settings = {key: boundary for key in _FLOAT_RANGES}
        result = sanitize_settings_dict(boundary_settings)
        for key in _FLOAT_RANGES:
            assert result[key] == boundary


def test_sanitize_settings_dict_string_choice_valid_and_invalid():
    """sanitize_settings_dict 字符串选项字段的合法与非法值"""
    result_valid = sanitize_settings_dict({"theme": "light", "bg_mode": "acrylic"})
    assert result_valid["theme"] == "light"
    assert result_valid["bg_mode"] == "acrylic"

    result_invalid = sanitize_settings_dict({"theme": "invalid_theme", "bg_mode": "nope"})
    assert result_invalid["theme"] == "dark"  # fallback to default
    assert result_invalid["bg_mode"] == "theme"


def test_sanitize_settings_dict_list_string_fields():
    """sanitize_settings_dict 列表字符串字段"""
    result = sanitize_settings_dict({"special_apps": ["app1", "app2", ""], "enabled_plugins": ["plug_a"]})
    assert "app1" in result["special_apps"]
    assert "app2" in result["special_apps"]
    assert "" not in result["special_apps"]
    assert "plug_a" in result["enabled_plugins"]


def test_sanitize_app_data_dict_valid_nested():
    """sanitize_app_data_dict 正常嵌套数据"""
    data = {
        "version": "2.5",
        "settings": {"bg_alpha": 80, "theme": "dark"},
        "folders": [{"id": "f1", "name": "Folder1", "items": [{"id": "i1", "name": "Item", "type": "file"}]}],
    }
    result = sanitize_app_data_dict(data)
    assert result["settings"]["bg_alpha"] == 80
    assert len(result["folders"]) == 1
    assert result["folders"][0]["items"][0]["id"] == "i1"


def test_validate_app_data_dict_nested_folders_and_items():
    """validate_app_data_dict 带嵌套文件夹和项目"""
    data = AppData().to_dict()
    data["folders"] = [
        {"id": "f1", "name": "A", "items": [{"id": "s1", "name": "S1", "type": "file"}]},
        {"id": "f2", "name": "B", "items": [{"id": "s2", "name": "S2", "type": "folder"}]},
    ]
    issues = validate_app_data_dict(data)
    assert not any("duplicate" in i for i in issues)
    assert not any("invalid_shortcut_type" in i for i in issues)


def test_validate_app_data_with_instance():
    """validate_app_data 使用 AppData 实例"""
    app_data = AppData()
    issues = validate_app_data(app_data)
    assert isinstance(issues, list)


def test_load_valid_data_file_valid_json(tmp_path):
    """load_valid_data_file 加载有效 JSON 文件"""
    data = AppData().to_dict()
    path = tmp_path / "valid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    app_data, issues = load_valid_data_file(path)
    assert isinstance(app_data, AppData)
    assert isinstance(issues, list)


def test_load_valid_data_file_malformed_json(tmp_path):
    """load_valid_data_file 处理格式错误的 JSON"""
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    try:
        load_valid_data_file(path)
    except (json.JSONDecodeError, ValueError):
        logger.debug("加载损坏JSON数据文件", exc_info=True)
    else:
        raise AssertionError("malformed JSON should raise")


def test_latest_valid_backup_no_dir(tmp_path):
    """latest_valid_backup 目录不存在时返回 None"""
    result = latest_valid_backup(tmp_path / "nonexistent")
    assert result is None


def test_latest_valid_backup_with_valid_files(tmp_path):
    """latest_valid_backup 返回最新的有效备份"""
    data = AppData().to_dict()
    backup1 = tmp_path / "data_001.json"
    backup1.write_text(json.dumps(data), encoding="utf-8")
    backup2 = tmp_path / "data_002.json"
    backup2.write_text(json.dumps(data), encoding="utf-8")
    # Ensure backup2 is newer
    import os
    import time

    old_time = time.time() - 100
    os.utime(backup1, (old_time, old_time))

    result = latest_valid_backup(tmp_path)
    assert result == backup2
