from __future__ import annotations

from core.command_param_validation import validate_param_value, validate_param_values
from core.command_registry import CommandParam


def test_validate_required_and_port_range():
    assert validate_param_value(CommandParam(name="port", required=True), "") == "port 为必填参数"
    assert validate_param_value(CommandParam(name="port", validator="port"), "0") == "port 端口范围应为 1-65535"
    assert validate_param_value(CommandParam(name="port", validator="port"), "443") == ""


def test_validate_json_and_domain():
    assert validate_param_value(CommandParam(name="body", validator="json"), '{"ok": true}') == ""
    assert "JSON 无效" in validate_param_value(CommandParam(name="body", validator="json"), "{bad")
    assert validate_param_value(CommandParam(name="host", validator="domain"), "example.com") == ""
    assert "域名无效" in validate_param_value(CommandParam(name="host", validator="domain"), "bad host")


def test_validate_regex_and_number_min_max():
    param = CommandParam(name="code", validator="regex", pattern=r"[A-Z]{3}\d{2}")
    assert validate_param_value(param, "ABC12") == ""
    assert "格式不匹配" in validate_param_value(param, "abc12")
    number = CommandParam(name="count", validator="number", min_value="2", max_value="5")
    assert validate_param_value(number, "3") == ""
    assert "不能小于" in validate_param_value(number, "1")


def test_validate_choice_bool_and_batch_values():
    choice = CommandParam(name="env", type="choice", choices=["prod", "stage"])
    assert validate_param_value(choice, "prod") == ""
    assert "以下选项之一" in validate_param_value(choice, "dev")

    bool_param = CommandParam(name="enabled", type="bool")
    assert validate_param_value(bool_param, "true") == ""
    assert validate_param_value(bool_param, "否") == ""
    assert "布尔值" in validate_param_value(bool_param, "maybe")

    errors = validate_param_values(
        [CommandParam(name="port", validator="port"), choice],
        {"port": "70000", "env": "dev"},
    )
    assert len(errors) == 2
