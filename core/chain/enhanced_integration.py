"""Enhanced processor integration module.

This module integrates the enhanced processors into the existing registry system.
"""

from __future__ import annotations

import logging
from typing import Any

from core.command_registry import CommandResult

from .enhanced_definitions import get_enhanced_definitions
from .enhanced_processors import (
    file_copy,
    file_delete,
    file_list_dir,
    file_modified,
    file_move,
    file_size,
    is_empty,
    is_json,
    is_numeric,
    json_flatten,
    json_keys,
    json_length,
    # JSON processors
    json_merge,
    json_to_csv,
    json_values,
    list_avg,
    # List processors
    list_count,
    list_find,
    list_max,
    list_min,
    list_remove,
    list_sum,
    # Math processors
    math_abs,
    math_ceil,
    math_clamp,
    math_floor,
    math_round,
    # Logic processors
    switch_case,
    text_contains,
    text_count,
    text_endswith,
    text_regex_replace,
    text_reverse,
    text_startswith,
    # Text processors
    text_trim,
)

__all__ = [
    "register_enhanced_processors",
    "execute_enhanced_processor",
]

logger = logging.getLogger(__name__)


def _ok(text: str) -> CommandResult:
    """Create a success result with text output."""
    text = str(text)
    return CommandResult(
        success=True,
        message=text,
        display_type="text",
        payload={
            "stdout": text,
            "outputs": {
                "output": text,
                "length": str(len(text)),
                "empty": "true" if not text else "false",
            },
            "raw_outputs": {
                "output": text,
                "length": len(text),
                "empty": not bool(text),
            },
        },
    )


def _ok_bool(value: bool) -> CommandResult:
    """Create a success result with boolean output."""
    bool_text = "true" if value else "false"
    return CommandResult(
        success=True,
        message=bool_text,
        display_type="text",
        payload={
            "stdout": bool_text,
            "outputs": {
                "output": bool_text,
                "not": "false" if value else "true",
            },
            "raw_outputs": {
                "output": value,
                "not": not value,
            },
        },
    )


def _ok_number(value: float) -> CommandResult:
    """Create a success result with number output."""
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value)
    return CommandResult(
        success=True,
        message=text,
        display_type="text",
        payload={
            "stdout": text,
            "outputs": {"output": text},
            "raw_outputs": {"output": value},
        },
    )


def _ok_list(items: list) -> CommandResult:
    """Create a success result with list output."""
    text_items = [str(item) for item in items]
    output = "\n".join(text_items)
    return CommandResult(
        success=True,
        message=output,
        display_type="text",
        payload={
            "stdout": output,
            "outputs": {
                "output": text_items,
                "count": str(len(items)),
                "first": text_items[0] if text_items else "",
                "last": text_items[-1] if text_items else "",
                "items_json": text_items,
            },
            "raw_outputs": {
                "output": items,
                "count": len(items),
                "first": items[0] if items else None,
                "last": items[-1] if items else None,
                "items_json": items,
            },
        },
    )


def _ok_json(value: Any) -> CommandResult:
    """Create a success result with JSON output."""
    import json

    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return CommandResult(
        success=True,
        message=text,
        display_type="text",
        payload={
            "stdout": text,
            "outputs": {"output": text},
            "raw_outputs": {"output": value},
        },
    )


def _ok_file(path: str) -> CommandResult:
    """Create a success result with file path output."""
    import os

    path = str(path or "").strip()
    folder = os.path.dirname(os.path.abspath(path)) if path else ""
    return CommandResult(
        success=True,
        message=path,
        display_type="text",
        payload={
            "stdout": path,
            "outputs": {
                "output": path,
                "path": path,
                "folder": folder,
                "filename": os.path.basename(path),
                "exists": "true" if os.path.exists(path) else "false",
            },
            "raw_outputs": {
                "output": path,
                "path": path,
                "folder": folder,
                "filename": os.path.basename(path),
                "exists": os.path.exists(path),
            },
        },
    )


def _error(message: str) -> CommandResult:
    """Create an error result."""
    return CommandResult(
        success=False,
        message=message,
        display_type="text",
        payload={
            "outputs": {"error": message},
            "diagnostic": {
                "kind": "processor_error",
                "message": message,
            },
        },
        error=message,
    )


def _to_bool(value: Any) -> bool:
    """Convert value to boolean."""
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "ok", "on", "是", "真", "对", "启用"}:
        return True
    if text in {"false", "0", "no", "n", "off", "否", "假", "错", "禁用", ""}:
        return False
    try:
        return float(text) != 0.0
    except ValueError:
        return bool(value)


def _to_num(value: Any, default: float = 0.0) -> float:
    """Convert value to number."""
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return default


def _parse_list(value: Any) -> list[str]:
    """Parse value to list of strings."""
    import ast
    import json

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
        except Exception:
            try:
                parsed = ast.literal_eval(val_str)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except Exception as exc:
                logger.debug("增强处理器列表解析失败，回退为按行/逗号解析: %s", exc, exc_info=True)
    if "\n" in val_str:
        return [line.strip() for line in val_str.splitlines() if line.strip()]
    if "," in val_str:
        return [part.strip() for part in val_str.split(",") if part.strip()]
    return [val_str] if val_str else []


def register_enhanced_processors(registry) -> None:
    """Register enhanced processors with the registry."""
    definitions = get_enhanced_definitions()

    for proc_id, definition in definitions.items():
        handler = _get_handler(proc_id)
        if handler:
            registry.register(definition, handler, owner="enhanced")


def _get_handler(processor_id: str):
    """Get handler for a processor."""
    handlers = {
        # Text processors
        "text_trim": lambda args: _ok(
            text_trim(
                str(args.get("text", "")),
                str(args.get("chars", "")),
            )
        ),
        "text_contains": lambda args: _ok_bool(
            text_contains(
                str(args.get("text", "")),
                str(args.get("substring", "")),
                _to_bool(args.get("case_sensitive", True)),
            )
        ),
        "text_startswith": lambda args: _ok_bool(
            text_startswith(
                str(args.get("text", "")),
                str(args.get("prefix", "")),
                _to_bool(args.get("case_sensitive", True)),
            )
        ),
        "text_endswith": lambda args: _ok_bool(
            text_endswith(
                str(args.get("text", "")),
                str(args.get("suffix", "")),
                _to_bool(args.get("case_sensitive", True)),
            )
        ),
        "text_regex_replace": lambda args: _ok(
            text_regex_replace(
                str(args.get("text", "")),
                str(args.get("pattern", "")),
                str(args.get("replacement", "")),
                int(_to_num(args.get("count", 0))),
            )
        ),
        "text_count": lambda args: _ok_number(
            text_count(
                str(args.get("text", "")),
                str(args.get("substring", "")),
                _to_bool(args.get("case_sensitive", True)),
            )
        ),
        "text_reverse": lambda args: _ok(text_reverse(str(args.get("text", "")))),
        # Logic processors
        "switch_case": lambda args: _ok(
            switch_case(
                str(args.get("value", "")),
                dict(args.get("cases_json", {})),
                str(args.get("default", "")),
            )
        ),
        "is_empty": lambda args: _ok_bool(is_empty(args.get("value"))),
        "is_numeric": lambda args: _ok_bool(is_numeric(str(args.get("text", "")))),
        "is_json": lambda args: _ok_bool(is_json(str(args.get("text", "")))),
        # Math processors
        "math_abs": lambda args: _ok_number(math_abs(_to_num(args.get("number", 0)))),
        "math_ceil": lambda args: _ok_number(math_ceil(_to_num(args.get("number", 0)))),
        "math_floor": lambda args: _ok_number(math_floor(_to_num(args.get("number", 0)))),
        "math_round": lambda args: _ok_number(
            math_round(
                _to_num(args.get("number", 0)),
                int(_to_num(args.get("decimals", 0))),
            )
        ),
        "math_clamp": lambda args: _ok_number(
            math_clamp(
                _to_num(args.get("number", 0)),
                _to_num(args.get("min", 0)),
                _to_num(args.get("max", 100)),
            )
        ),
        # List processors
        "list_count": lambda args: _ok_number(
            list_count(
                _parse_list(args.get("list", "")),
                args.get("value", ""),
            )
        ),
        "list_sum": lambda args: _ok_number(list_sum(_parse_list(args.get("list", "")))),
        "list_min": lambda args: _ok(list_min(_parse_list(args.get("list", "")))),
        "list_max": lambda args: _ok(list_max(_parse_list(args.get("list", "")))),
        "list_avg": lambda args: _ok_number(list_avg(_parse_list(args.get("list", "")))),
        "list_find": lambda args: _ok(
            str(
                list_find(
                    _parse_list(args.get("list", "")),
                    args.get("value", ""),
                )
                or ""
            )
        ),
        "list_remove": lambda args: _ok_list(
            list_remove(
                _parse_list(args.get("list", "")),
                args.get("value", ""),
            )
        ),
        # File processors
        "file_copy": lambda args: _ok_file(
            file_copy(
                str(args.get("src", "")),
                str(args.get("dst", "")),
                _to_bool(args.get("overwrite", False)),
            )
        ),
        "file_move": lambda args: _ok_file(
            file_move(
                str(args.get("src", "")),
                str(args.get("dst", "")),
                _to_bool(args.get("overwrite", False)),
            )
        ),
        "file_delete": lambda args: _ok_bool(
            file_delete(
                str(args.get("path", "")),
                _to_bool(args.get("to_trash", True)),
            )
        ),
        "file_size": lambda args: _ok_number(file_size(str(args.get("path", "")))),
        "file_modified": lambda args: _ok_number(file_modified(str(args.get("path", "")))),
        "file_list_dir": lambda args: _ok_list(
            file_list_dir(
                str(args.get("path", "")),
                str(args.get("pattern", "*")),
                _to_bool(args.get("recursive", False)),
            )
        ),
        # JSON processors
        "json_merge": lambda args: _ok_json(
            json_merge(
                args.get("a", {}),
                args.get("b", {}),
                args.get("c", {}),
            )
        ),
        "json_flatten": lambda args: _ok_json(
            json_flatten(
                args.get("json", {}),
                separator=str(args.get("separator", ".")),
            )
        ),
        "json_keys": lambda args: _ok_list(json_keys(args.get("json", {}))),
        "json_values": lambda args: _ok_list(json_values(args.get("json", {}))),
        "json_length": lambda args: _ok_number(json_length(args.get("json", {}))),
        "json_to_csv": lambda args: _ok(
            json_to_csv(
                args.get("json", []),
                str(args.get("delimiter", ",")),
            )
        ),
    }

    return handlers.get(processor_id)


def execute_enhanced_processor(processor_id: str, args: dict[str, Any]) -> CommandResult:
    """Execute an enhanced processor."""
    try:
        handler = _get_handler(processor_id)
        if handler is None:
            return _error(f"未知的增强处理器: {processor_id}")
        return handler(args)  # type: ignore[no-any-return]
    except Exception as e:
        return _error(f"处理器执行失败: {e}")
