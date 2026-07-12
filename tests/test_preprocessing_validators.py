"""Tests for preprocessing validators."""

from core.preprocessing.validators import (
    validate_choice,
    validate_command_length,
    validate_environment_variable,
    validate_numeric,
    validate_path,
    validate_url,
    validate_variable_syntax,
)


def test_validate_path_empty():
    result = validate_path("")
    assert not result.valid
    assert "路径为空" in result.error


def test_validate_path_traversal():
    result = validate_path("../../etc/passwd")
    assert not result.valid
    assert "路径遍历" in result.error


def test_validate_path_valid():
    result = validate_path("C:\\Users\\test")
    assert result.valid


def test_validate_url_empty():
    result = validate_url("")
    assert not result.valid
    assert "URL 为空" in result.error


def test_validate_url_no_scheme():
    result = validate_url("example.com")
    assert not result.valid
    assert "缺少 URL 协议" in result.error


def test_validate_url_valid():
    result = validate_url("https://example.com")
    assert result.valid


def test_validate_url_allowed_schemes():
    result = validate_url("ftp://example.com", allowed_schemes=["http", "https"])
    assert not result.valid
    assert "不允许的协议" in result.error


def test_validate_numeric_empty():
    result = validate_numeric("")
    assert not result.valid


def test_validate_numeric_invalid():
    result = validate_numeric("abc")
    assert not result.valid
    assert "无效数值" in result.error


def test_validate_numeric_valid():
    result = validate_numeric("42")
    assert result.valid


def test_validate_numeric_range():
    result = validate_numeric("5", min_val=10, max_val=100)
    assert not result.valid
    assert "数值过小" in result.error

    result = validate_numeric("150", min_val=10, max_val=100)
    assert not result.valid
    assert "数值过大" in result.error


def test_validate_choice_empty():
    result = validate_choice("", ["a", "b", "c"])
    assert not result.valid


def test_validate_choice_invalid():
    result = validate_choice("d", ["a", "b", "c"])
    assert not result.valid
    assert "无效选择" in result.error


def test_validate_choice_valid():
    result = validate_choice("b", ["a", "b", "c"])
    assert result.valid


def test_validate_command_length_empty():
    result = validate_command_length("")
    assert not result.valid
    assert "命令为空" in result.error


def test_validate_command_length_too_long():
    result = validate_command_length("x" * 20000, max_length=1000)
    assert not result.valid
    assert "命令过长" in result.error


def test_validate_command_length_valid():
    result = validate_command_length("echo hello")
    assert result.valid


def test_validate_variable_syntax_empty():
    result = validate_variable_syntax("")
    assert not result.valid


def test_validate_variable_syntax_invalid():
    result = validate_variable_syntax("{123}")
    old_result = validate_variable_syntax("{clipboard}")
    assert not result.valid
    assert not old_result.valid
    assert "变量语法无效" in result.error


def test_validate_variable_syntax_valid():
    result = validate_variable_syntax("{{clipboard}}")
    assert result.valid

    result = validate_variable_syntax("{{clipboard:q}}")
    assert result.valid

    result = validate_variable_syntax("{{input:名称:q}}")
    assert result.valid


def test_validate_environment_variable_empty_name():
    result = validate_environment_variable("", "value")
    assert not result.valid


def test_validate_environment_variable_invalid_name():
    result = validate_environment_variable("123abc", "value")
    assert not result.valid
    assert "环境变量名无效" in result.error


def test_validate_environment_variable_null_byte():
    result = validate_environment_variable("VAR", "value\0test")
    assert not result.valid
    assert "空字节" in result.error


def test_validate_environment_variable_valid():
    result = validate_environment_variable("MY_VAR", "value")
    assert result.valid
