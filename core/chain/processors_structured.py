"""Structured data and URL processors for action chains."""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from core.command_registry import CommandResult


def json_get(values: dict[str, str]) -> str:
    raw = values.get("json", "")
    path = values.get("path", "")
    data: Any = json.loads(raw)
    for part in _path_parts(path):
        if isinstance(data, list):
            data = data[int(part)]
        elif isinstance(data, dict):
            data = data[part]
        else:
            raise KeyError(part)
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def json_set(values: dict[str, str]) -> str:
    raw = values.get("json", "").strip()
    data: Any = json.loads(raw) if raw else {}
    if not isinstance(data, dict | list):
        data = {}
    parts = _path_parts(values.get("path", ""))
    if not parts:
        return json.dumps(_parse_scalar(values.get("value", "")), ensure_ascii=False, separators=(",", ":"))
    current = data
    for part in parts[:-1]:
        if isinstance(current, list):
            index = int(part)
            while len(current) <= index:
                current.append({})
            if not isinstance(current[index], dict | list):
                current[index] = {}
            current = current[index]
        else:
            if part not in current or not isinstance(current.get(part), dict | list):
                current[part] = {}
            current = current[part]
    last = parts[-1]
    value = _parse_scalar(values.get("value", ""))
    if isinstance(current, list):
        index = int(last)
        while len(current) <= index:
            current.append(None)
        current[index] = value
    else:
        current[last] = value
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def url_encode(values: dict[str, str]) -> str:
    text = values.get("text", "")
    mode = values.get("mode", "encode").strip().lower()
    if mode == "decode":
        return urllib.parse.unquote(text)
    return urllib.parse.quote(text)


def json_parse(values: dict[str, str]) -> str:
    json_str = values.get("json_str", "").strip()
    parsed = json.loads(json_str)
    return json.dumps(parsed, indent=2, ensure_ascii=False)


def json_template(values: dict[str, str]) -> str:
    raw = values.get("json", "").strip()
    template = values.get("template", "{output}") or "{output}"
    data: Any = json.loads(raw) if raw else {}
    result = template
    for match in re.finditer(r"\{([^{}]+)\}", template):
        expr = match.group(1).strip()
        if not expr:
            continue
        try:
            value = _json_path_value(data, expr)
        except Exception:
            value = ""
        result = result.replace(match.group(0), _stringify_json_value(value))
    return result


def execute_extra_json_processor(processor_id: str, values: dict[str, Any]) -> CommandResult | None:
    text_values = _string_values(values)

    if processor_id == "json_merge":
        a = _try_json_parse(values.get("a", "{}"))
        b = _try_json_parse(values.get("b", "{}"))
        merged = dict(a) if isinstance(a, dict) else {}
        if isinstance(b, dict):
            merged.update(b)
        return _ok(json.dumps(merged, ensure_ascii=False, separators=(",", ":")))

    if processor_id == "json_flatten":
        data = _try_json_parse(values.get("json", "{}"))
        separator = text_values.get("separator", ".")
        result = {}

        def _flatten(obj, prefix):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    next_key = f"{prefix}{separator}{key}" if prefix else key
                    _flatten(value, next_key)
            elif isinstance(obj, list):
                for index, value in enumerate(obj):
                    next_key = f"{prefix}{separator}{index}" if prefix else str(index)
                    _flatten(value, next_key)
            else:
                result[prefix] = obj

        _flatten(data, "")
        return _ok(json.dumps(result, ensure_ascii=False, separators=(",", ":")))

    if processor_id == "json_keys":
        data = _try_json_parse(values.get("json", "{}"))
        return _ok_list(list(data.keys()) if isinstance(data, dict) else [])

    if processor_id == "json_values":
        data = _try_json_parse(values.get("json", "{}"))
        return _ok_list([_value_to_text(value) for value in data.values()] if isinstance(data, dict) else [])

    if processor_id == "json_length":
        data = _try_json_parse(values.get("json", "{}"))
        return _ok(str(len(data)) if isinstance(data, dict | list) else "0")

    return None


def _path_parts(path: str) -> list[str]:
    text = str(path or "").strip()
    if not text:
        return []
    parts: list[str] = []
    token = ""
    in_bracket = False
    quote = ""
    for char in text:
        if quote:
            if char == quote:
                quote = ""
            else:
                token += char
            continue
        if in_bracket and char in {"'", '"'}:
            quote = char
            continue
        if char == "[" and not in_bracket:
            if token:
                parts.append(token)
                token = ""
            in_bracket = True
            continue
        if char == "]" and in_bracket:
            if token:
                parts.append(token.strip())
                token = ""
            in_bracket = False
            continue
        if char == "." and not in_bracket:
            if token:
                parts.append(token)
                token = ""
            continue
        token += char
    if token:
        parts.append(token.strip())
    return [part for part in parts if part != ""]


def _parse_scalar(value: str) -> Any:
    text = str(value or "").strip()
    if text in {"true", "false"}:
        return text == "true"
    if text in {"是", "真"}:
        return True
    if text in {"否", "假"}:
        return False
    if text == "null" or text == "空":
        return None
    try:
        return json.loads(text)
    except Exception:
        return value


def _json_path_value(data: Any, path: str) -> Any:
    current = data
    for part in _path_parts(path):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(part)
    return current


def _stringify_json_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, bool):
        return _bool_text(value)
    if isinstance(value, list | dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _try_json_parse(value: Any) -> Any:
    if isinstance(value, dict | list):
        return value
    text = _value_to_text(value).strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {}


def _ok(text: str) -> CommandResult:
    text = str(text)
    return _ok_outputs({"output": text, "length": str(len(text)), "empty": _bool_text(not bool(text))})


def _ok_list(items: list[str], *, delimiter: str = "\n") -> CommandResult:
    output = delimiter.join(str(item) for item in items)
    return _ok_outputs(
        {
            "output": list(items) if delimiter == "\n" else output,
            "count": str(len(items)),
            "first": items[0] if items else "",
            "last": items[-1] if items else "",
            "items_json": items,
        }
    )


def _ok_outputs(outputs: dict[str, Any]) -> CommandResult:
    raw_outputs = {str(k): v for k, v in dict(outputs or {}).items() if str(k).strip()}
    normalized = {str(k): _value_to_text(v) for k, v in raw_outputs.items()}
    first = next(iter(normalized.values()), "")
    return CommandResult(
        success=True,
        message=first,
        display_type="text",
        payload={"stdout": first, "outputs": normalized, "raw_outputs": raw_outputs},
    )


def _string_values(values: dict[str, Any]) -> dict[str, str]:
    return {str(key): _value_to_text(value) for key, value in dict(values or {}).items()}


def _value_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(_value_to_text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"
