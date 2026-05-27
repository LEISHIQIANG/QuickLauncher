"""Validation functions for command preprocessing."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class ValidationResult:
    """Result of a validation check."""

    valid: bool
    error: str = ""
    suggestion: str = ""


def validate_path(path: str, must_exist: bool = False) -> ValidationResult:
    """Validate file/directory path."""
    if not path or not path.strip():
        return ValidationResult(False, "路径为空", "请提供有效路径")

    normalized = os.path.normpath(path.strip())

    if ".." in normalized:
        return ValidationResult(False, "检测到路径遍历", "使用绝对路径或相对路径")

    if must_exist and not os.path.exists(normalized):
        return ValidationResult(False, f"路径不存在: {normalized}", "检查路径是否正确")

    return ValidationResult(True)


def validate_url(url: str, allowed_schemes: list[str] | None = None) -> ValidationResult:
    """Validate URL format."""
    if not url or not url.strip():
        return ValidationResult(False, "URL 为空", "请提供有效 URL")

    try:
        parsed = urlparse(url.strip())
        if not parsed.scheme:
            return ValidationResult(False, "缺少 URL 协议", "例如: https://example.com")

        if allowed_schemes and parsed.scheme not in allowed_schemes:
            return ValidationResult(
                False, f"不允许的协议: {parsed.scheme}", f"允许的协议: {', '.join(allowed_schemes)}"
            )

        return ValidationResult(True)
    except Exception as e:
        return ValidationResult(False, f"URL 格式无效: {e}", "检查 URL 格式")


def validate_numeric(value: str, min_val: float | None = None, max_val: float | None = None) -> ValidationResult:
    """Validate numeric value and range."""
    if not value or not value.strip():
        return ValidationResult(False, "数值为空", "请提供数值")

    try:
        num = float(value.strip())
        if min_val is not None and num < min_val:
            return ValidationResult(False, f"数值过小: {num}", f"最小值: {min_val}")
        if max_val is not None and num > max_val:
            return ValidationResult(False, f"数值过大: {num}", f"最大值: {max_val}")
        return ValidationResult(True)
    except ValueError:
        return ValidationResult(False, f"无效数值: {value}", "请提供有效数字")


def validate_choice(value: str, choices: list[str]) -> ValidationResult:
    """Validate value is in allowed choices."""
    if not value or not value.strip():
        return ValidationResult(False, "值为空", f"允许的值: {', '.join(choices)}")

    if value.strip() not in choices:
        return ValidationResult(False, f"无效选择: {value}", f"允许的值: {', '.join(choices)}")

    return ValidationResult(True)


def validate_command_length(command: str, max_length: int = 10000) -> ValidationResult:
    """Validate command length."""
    if not command:
        return ValidationResult(False, "命令为空", "请提供命令内容")

    if len(command) > max_length:
        return ValidationResult(False, f"命令过长: {len(command)} 字符", f"最大长度: {max_length}")

    return ValidationResult(True)


_VARIABLE_PATTERN = re.compile(r"^\{\{[a-zA-Z_][^{}\r\n]*(?::q)?\}\}$")


def validate_variable_syntax(variable: str) -> ValidationResult:
    """Validate variable syntax."""
    if not variable:
        return ValidationResult(False, "变量为空", "例如: {{clipboard}}")

    if not _VARIABLE_PATTERN.match(variable):
        return ValidationResult(False, "变量语法无效", "格式: {{name}} 或 {{name:q}}")

    return ValidationResult(True)


_ENV_VAR_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def validate_environment_variable(name: str, value: str) -> ValidationResult:
    """Validate environment variable name and value."""
    if not name or not name.strip():
        return ValidationResult(False, "环境变量名为空", "请提供变量名")

    if not _ENV_VAR_NAME_PATTERN.match(name.strip()):
        return ValidationResult(False, "环境变量名无效", "仅允许字母、数字和下划线")

    if "\0" in value:
        return ValidationResult(False, "环境变量值包含空字节", "移除空字节")

    return ValidationResult(True)
