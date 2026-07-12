"""Pure validation helpers for command-panel parameters."""

from __future__ import annotations

import ipaddress
import json
import os
import re
from urllib.parse import urlparse

from core.command_registry import CommandParam

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,63}$|^(localhost)$",
    re.IGNORECASE,
)

BOOL_VALUES = {"1", "0", "true", "false", "yes", "no", "on", "off", "是", "否"}


def validate_param_values(params: list[CommandParam], values: dict[str, str]) -> list[str]:
    """Return all validation errors for a command parameter set."""

    errors: list[str] = []
    value_map = {str(k): str(v) for k, v in dict(values or {}).items()}
    for param in params or []:
        errors.append(validate_param_value(param, value_map.get(param.name, "")))
    return [error for error in errors if error]


def validate_param_value(param: CommandParam, value: str) -> str:
    """Return an error message when value violates param, or an empty string."""

    text = str(value or "")
    stripped = text.strip()
    name = param.label or param.name
    if param.required and not stripped:
        return f"{name} 为必填参数"

    validator = (param.validator or "").lower().strip()
    param_type = (param.type or "text").lower().strip()
    if not validator:
        if param_type in ("file", "folder", "number"):
            validator = param_type
        elif param_type == "textarea":
            validator = ""
    if not stripped and not param.required:
        return ""

    if param_type == "choice":
        choices = [str(choice) for choice in list(param.choices or [])]
        if choices and text not in choices:
            return f"{name} 必须是以下选项之一: {', '.join(choices)}"

    if param_type == "bool" and stripped.lower() not in BOOL_VALUES:
        return f"{name} 必须是布尔值"

    if validator == "file" and not os.path.isfile(stripped):
        return f"{name} 文件不存在"
    if validator == "folder" and not os.path.isdir(stripped):
        return f"{name} 文件夹不存在"
    if validator == "path" and ("\x00" in stripped or not stripped):
        return f"{name} 路径无效"
    if validator == "url":
        parsed = urlparse(stripped)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return f"{name} URL 无效"
    if validator == "domain" and not DOMAIN_RE.match(stripped):
        return f"{name} 域名无效"
    if validator == "ip":
        try:
            ipaddress.ip_address(stripped)
        except ValueError:
            return f"{name} IP 地址无效"
    if validator == "port":
        try:
            port = int(stripped)
        except ValueError:
            return f"{name} 端口必须是整数"
        if port < 1 or port > 65535:
            return f"{name} 端口范围应为 1-65535"
    if validator == "json":
        try:
            json.loads(text)
        except Exception as exc:
            return f"{name} JSON 无效: {exc}"
    if validator == "regex":
        pattern = str(param.pattern or "")
        if pattern:
            try:
                if re.fullmatch(pattern, text) is None:
                    return f"{name} 格式不匹配"
            except re.error as exc:
                return f"{name} 正则无效: {exc}"
    if validator == "number":
        try:
            number = float(stripped)
        except ValueError:
            return f"{name} 必须是数字"
        min_value = _parse_float(param.min_value)
        max_value = _parse_float(param.max_value)
        if min_value is not None and number < min_value:
            return f"{name} 不能小于 {param.min_value}"
        if max_value is not None and number > max_value:
            return f"{name} 不能大于 {param.max_value}"
    return ""


def _parse_float(value: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
