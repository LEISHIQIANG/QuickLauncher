import json

from core.config_validation import load_valid_data_file, validate_app_data_dict
from core.data_models import AppData


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
