"""Shared helper utilities for chain processor modules."""

from __future__ import annotations

import json
import logging
from typing import Any

from core.command_registry import CommandResult

logger = logging.getLogger(__name__)


def value_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(value_to_text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def string_values(values: dict[str, Any]) -> dict[str, str]:
    return {str(k): value_to_text(v) for k, v in dict(values or {}).items()}


def to_bool(value: Any) -> bool:
    text = value_to_text(value).strip().lower()
    if text in {"true", "1", "yes", "y", "ok", "on", "是", "真", "对", "启用"}:
        return True
    if text in {"false", "0", "no", "n", "off", "否", "假", "错", "禁用", ""}:
        return False
    try:
        return float(text) != 0.0
    except ValueError:
        return True


def to_num(value: Any, default: float = 0.0) -> float:
    if not value:
        return default
    try:
        return float(str(value).strip())
    except ValueError:
        return default


def parse_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not value:
        return []
    val_str = str(value).strip()
    if val_str.startswith("[") and val_str.endswith("]"):
        try:
            parsed = json.loads(val_str)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except (json.JSONDecodeError, TypeError):
            logger.debug("parse_list JSON 解析失败，回退为逐行分割", exc_info=True)
    return [line for line in val_str.splitlines() if line.strip()]


def try_json_parse(value: Any) -> Any:
    if isinstance(value, dict | list):
        return value
    if not value or str(value).strip() == "":
        return {}
    try:
        return json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return {}


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def ok(text: str) -> CommandResult:
    text = str(text)
    return ok_outputs({"output": text, "length": str(len(text)), "empty": bool_text(not bool(text))})


def ok_bool(value: bool) -> CommandResult:
    return ok_outputs({"output": bool_text(value), "not": bool_text(not value)})


def ok_list(items: list[str], *, delimiter: str = "\n") -> CommandResult:
    output = delimiter.join(str(item) for item in items)
    return ok_outputs(
        {
            "output": list(items) if delimiter == "\n" else output,
            "count": str(len(items)),
            "first": items[0] if items else "",
            "last": items[-1] if items else "",
            "items_json": items,
        }
    )


def ok_outputs(outputs: dict[str, Any]) -> CommandResult:
    raw_outputs = {str(k): v for k, v in dict(outputs or {}).items() if str(k).strip()}
    normalized = {str(k): value_to_text(v) for k, v in raw_outputs.items()}
    first = next(iter(normalized.values()), "")
    return CommandResult(
        success=True,
        message=first,
        display_type="text",
        payload={"stdout": first, "outputs": normalized, "raw_outputs": raw_outputs},
    )
