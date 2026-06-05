"""Extended processor integration module.

This module integrates the extended processors into the existing registry system.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from core.command_registry import CommandResult

from .extended_definitions import get_extended_definitions
from .extended_processors import (
    base64_decode,
    # Encoding/Decoding
    base64_encode,
    color_brightness,
    color_complementary,
    # Color
    color_hex_to_rgb,
    color_random,
    color_rgb_to_hex,
    # Compression
    compress_gzip,
    compress_zlib,
    datetime_add,
    datetime_diff,
    datetime_format,
    # Date/Time
    datetime_now,
    datetime_parse,
    datetime_part,
    datetime_to_timestamp,
    decompress_gzip,
    decompress_zlib,
    dict_filter,
    dict_get,
    # Dict operations
    dict_keys,
    dict_merge,
    dict_set,
    dict_values,
    env_expand,
    # Environment
    env_get,
    env_list,
    env_set,
    hash_crc32,
    # Hash
    hash_md5,
    hash_sha1,
    hash_sha256,
    hash_sha512,
    hash_uuid,
    hex_decode,
    hex_encode,
    html_decode,
    html_encode,
    math_cos,
    math_factorial,
    math_fibonacci,
    math_gcd,
    math_lcm,
    math_log,
    # Math extended
    math_sin,
    math_sqrt,
    math_tan,
    # Network
    net_ip_address,
    net_ping,
    net_port_check,
    net_url_parse,
    set_difference,
    set_intersection,
    # Set operations
    set_union,
    set_unique,
    # String formatting
    str_format,
    str_pad_left,
    str_pad_right,
    str_repeat,
    str_truncate,
    sys_cpu_count,
    sys_current_dir,
    sys_home_dir,
    sys_hostname,
    # System info
    sys_platform,
    sys_temp_dir,
    sys_username,
    sys_version,
    timestamp_now,
    timestamp_to_datetime,
    url_decode,
    url_encode,
    # Validation
    validate_email,
    validate_ip,
    validate_length,
    validate_phone,
    validate_range,
    validate_regex,
    validate_url,
)

__all__ = [
    "register_extended_processors",
    "execute_extended_processor",
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


def _to_int(value: Any, default: int = 0) -> int:
    """Convert value to integer."""
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default


def _parse_list(value: Any) -> list[str]:
    """Parse value to list of strings."""
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
        except Exception as exc:
            logger.debug("扩展处理器列表解析失败，回退为按行/逗号解析: %s", exc, exc_info=True)
    if "\n" in val_str:
        return [line.strip() for line in val_str.splitlines() if line.strip()]
    if "," in val_str:
        return [part.strip() for part in val_str.split(",") if part.strip()]
    return [val_str] if val_str else []


def _parse_json(value: Any) -> Any:
    """Parse value to JSON."""
    if isinstance(value, dict | list):
        return value
    if not value:
        return {}
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return {}


def register_extended_processors(registry) -> None:
    """Register extended processors with the registry."""
    definitions = get_extended_definitions()

    for proc_id, definition in definitions.items():
        handler = _get_handler(proc_id)
        if handler:
            registry.register(definition, handler, owner="extended")


def _get_handler(processor_id: str):
    """Get handler for a processor."""
    handlers = {
        # Date/Time processors
        "datetime_now": lambda args: _ok(datetime_now(str(args.get("format", "%Y-%m-%d %H:%M:%S")))),
        "datetime_format": lambda args: _ok(datetime_format(str(args.get("datetime", "")), str(args.get("format", "%Y-%m-%d %H:%M:%S")))),
        "datetime_parse": lambda args: _ok_json(datetime_parse(str(args.get("datetime", "")), str(args.get("format", "%Y-%m-%d %H:%M:%S")))),
        "datetime_add": lambda args: _ok(datetime_add(
            str(args.get("datetime", "")),
            _to_int(args.get("days", 0)),
            _to_int(args.get("hours", 0)),
            _to_int(args.get("minutes", 0)),
            _to_int(args.get("seconds", 0)),
            str(args.get("format", "%Y-%m-%d %H:%M:%S")),
        )),
        "datetime_diff": lambda args: _ok_number(datetime_diff(
            str(args.get("datetime1", "")),
            str(args.get("datetime2", "")),
            str(args.get("unit", "seconds")),
        )),
        "datetime_part": lambda args: _ok_number(datetime_part(
            str(args.get("datetime", "")),
            str(args.get("part", "year")),
            str(args.get("format", "%Y-%m-%d %H:%M:%S")),
        )),
        "timestamp_now": lambda args: _ok_number(timestamp_now()),
        "timestamp_to_datetime": lambda args: _ok(timestamp_to_datetime(
            _to_num(args.get("timestamp", 0)),
            str(args.get("format", "%Y-%m-%d %H:%M:%S")),
        )),
        "datetime_to_timestamp": lambda args: _ok_number(datetime_to_timestamp(
            str(args.get("datetime", "")),
            str(args.get("format", "%Y-%m-%d %H:%M:%S")),
        )),

        # Encoding/Decoding processors
        "base64_encode": lambda args: _ok(base64_encode(str(args.get("text", "")), str(args.get("encoding", "utf-8")))),
        "base64_decode": lambda args: _ok(base64_decode(str(args.get("text", "")), str(args.get("encoding", "utf-8")))),
        "url_encode": lambda args: _ok(url_encode(str(args.get("text", "")))),
        "url_decode": lambda args: _ok(url_decode(str(args.get("text", "")))),
        "html_encode": lambda args: _ok(html_encode(str(args.get("text", "")))),
        "html_decode": lambda args: _ok(html_decode(str(args.get("text", "")))),
        "hex_encode": lambda args: _ok(hex_encode(str(args.get("text", "")), str(args.get("encoding", "utf-8")))),
        "hex_decode": lambda args: _ok(hex_decode(str(args.get("text", "")), str(args.get("encoding", "utf-8")))),

        # System info processors
        "sys_platform": lambda args: _ok(sys_platform()),
        "sys_version": lambda args: _ok(sys_version()),
        "sys_hostname": lambda args: _ok(sys_hostname()),
        "sys_username": lambda args: _ok(sys_username()),
        "sys_cpu_count": lambda args: _ok_number(sys_cpu_count()),
        "sys_current_dir": lambda args: _ok(sys_current_dir()),
        "sys_home_dir": lambda args: _ok(sys_home_dir()),
        "sys_temp_dir": lambda args: _ok(sys_temp_dir()),

        # Network processors
        "net_ip_address": lambda args: _ok(net_ip_address(str(args.get("hostname", "")))),
        "net_ping": lambda args: _ok_bool(net_ping(str(args.get("host", "")), _to_num(args.get("timeout", 3.0)))),
        "net_port_check": lambda args: _ok_bool(net_port_check(
            str(args.get("host", "")),
            _to_int(args.get("port", 80)),
            _to_num(args.get("timeout", 3.0)),
        )),
        "net_url_parse": lambda args: _ok_json(net_url_parse(str(args.get("url", "")))),

        # Validation processors
        "validate_email": lambda args: _ok_bool(validate_email(str(args.get("email", "")))),
        "validate_url": lambda args: _ok_bool(validate_url(str(args.get("url", "")))),
        "validate_ip": lambda args: _ok_bool(validate_ip(str(args.get("ip", "")))),
        "validate_phone": lambda args: _ok_bool(validate_phone(str(args.get("phone", "")), str(args.get("country", "CN")))),
        "validate_regex": lambda args: _ok_bool(validate_regex(str(args.get("text", "")), str(args.get("pattern", "")))),
        "validate_range": lambda args: _ok_bool(validate_range(
            _to_num(args.get("value", 0)),
            _to_num(args.get("min", 0)),
            _to_num(args.get("max", 100)),
        )),
        "validate_length": lambda args: _ok_bool(validate_length(
            str(args.get("text", "")),
            _to_int(args.get("min", 0)),
            _to_int(args.get("max", 0)),
        )),

        # Hash processors
        "hash_md5": lambda args: _ok(hash_md5(str(args.get("text", "")), str(args.get("encoding", "utf-8")))),
        "hash_sha1": lambda args: _ok(hash_sha1(str(args.get("text", "")), str(args.get("encoding", "utf-8")))),
        "hash_sha256": lambda args: _ok(hash_sha256(str(args.get("text", "")), str(args.get("encoding", "utf-8")))),
        "hash_sha512": lambda args: _ok(hash_sha512(str(args.get("text", "")), str(args.get("encoding", "utf-8")))),
        "hash_crc32": lambda args: _ok(hash_crc32(str(args.get("text", "")), str(args.get("encoding", "utf-8")))),
        "hash_uuid": lambda args: _ok(hash_uuid()),

        # Color processors
        "color_hex_to_rgb": lambda args: _ok(str(color_hex_to_rgb(str(args.get("hex", "#000000"))))),
        "color_rgb_to_hex": lambda args: _ok(color_rgb_to_hex(
            _to_int(args.get("r", 0)),
            _to_int(args.get("g", 0)),
            _to_int(args.get("b", 0)),
        )),
        "color_brightness": lambda args: _ok_number(color_brightness(str(args.get("hex", "#000000")))),
        "color_complementary": lambda args: _ok(color_complementary(str(args.get("hex", "#000000")))),
        "color_random": lambda args: _ok(color_random()),

        # Set operations
        "set_union": lambda args: _ok_list(set_union(_parse_list(args.get("set1", "")), _parse_list(args.get("set2", "")))),
        "set_intersection": lambda args: _ok_list(set_intersection(_parse_list(args.get("set1", "")), _parse_list(args.get("set2", "")))),
        "set_difference": lambda args: _ok_list(set_difference(_parse_list(args.get("set1", "")), _parse_list(args.get("set2", "")))),
        "set_unique": lambda args: _ok_list(set_unique(_parse_list(args.get("list", "")))),

        # Dictionary operations
        "dict_keys": lambda args: _ok_list(dict_keys(_parse_json(args.get("json", {})))),
        "dict_values": lambda args: _ok_list(dict_values(_parse_json(args.get("json", {})))),
        "dict_merge": lambda args: _ok_json(dict_merge(
            _parse_json(args.get("a", {})),
            _parse_json(args.get("b", {})),
            _parse_json(args.get("c", {})),
        )),
        "dict_get": lambda args: _ok(str(dict_get(
            _parse_json(args.get("json", {})),
            str(args.get("key", "")),
            args.get("default"),
        ))),
        "dict_set": lambda args: _ok_json(dict_set(
            _parse_json(args.get("json", {})),
            str(args.get("key", "")),
            args.get("value"),
        )),
        "dict_filter": lambda args: _ok_json(dict_filter(
            _parse_json(args.get("json", {})),
            _parse_list(args.get("keys", "")),
        )),

        # String formatting
        "str_format": lambda args: _ok(str_format(str(args.get("template", "")), **_parse_json(args.get("args", {})))),
        "str_pad_left": lambda args: _ok(str_pad_left(
            str(args.get("text", "")),
            _to_int(args.get("width", 0)),
            str(args.get("fillchar", " ")),
        )),
        "str_pad_right": lambda args: _ok(str_pad_right(
            str(args.get("text", "")),
            _to_int(args.get("width", 0)),
            str(args.get("fillchar", " ")),
        )),
        "str_truncate": lambda args: _ok(str_truncate(
            str(args.get("text", "")),
            _to_int(args.get("max_length", 100)),
            str(args.get("suffix", "...")),
        )),
        "str_repeat": lambda args: _ok(str_repeat(
            str(args.get("text", "")),
            _to_int(args.get("count", 1)),
        )),

        # Compression processors
        "compress_gzip": lambda args: _ok(base64.b64encode(compress_gzip(
            str(args.get("text", "")),
            str(args.get("encoding", "utf-8")),
        )).decode("ascii")),
        "decompress_gzip": lambda args: _ok(decompress_gzip(
            base64.b64decode(str(args.get("text", ""))),
            str(args.get("encoding", "utf-8")),
        )),
        "compress_zlib": lambda args: _ok(base64.b64encode(compress_zlib(
            str(args.get("text", "")),
            str(args.get("encoding", "utf-8")),
        )).decode("ascii")),
        "decompress_zlib": lambda args: _ok(decompress_zlib(
            base64.b64decode(str(args.get("text", ""))),
            str(args.get("encoding", "utf-8")),
        )),

        # Environment processors
        "env_get": lambda args: _ok(env_get(str(args.get("key", "")), str(args.get("default", "")))),
        "env_set": lambda args: _ok(env_set(str(args.get("key", "")), str(args.get("value", "")))),
        "env_list": lambda args: _ok_json(env_list()),
        "env_expand": lambda args: _ok(env_expand(str(args.get("text", "")))),

        # Math extended processors
        "math_sin": lambda args: _ok_number(math_sin(_to_num(args.get("angle", 0)))),
        "math_cos": lambda args: _ok_number(math_cos(_to_num(args.get("angle", 0)))),
        "math_tan": lambda args: _ok_number(math_tan(_to_num(args.get("angle", 0)))),
        "math_sqrt": lambda args: _ok_number(math_sqrt(_to_num(args.get("number", 0)))),
        "math_log": lambda args: _ok_number(math_log(_to_num(args.get("number", 1)), _to_num(args.get("base", 2.718281828459045)))),
        "math_factorial": lambda args: _ok_number(math_factorial(_to_int(args.get("number", 0)))),
        "math_gcd": lambda args: _ok_number(math_gcd(_to_int(args.get("a", 0)), _to_int(args.get("b", 0)))),
        "math_lcm": lambda args: _ok_number(math_lcm(_to_int(args.get("a", 0)), _to_int(args.get("b", 0)))),
        "math_fibonacci": lambda args: _ok_list(math_fibonacci(_to_int(args.get("count", 10)))),
    }

    return handlers.get(processor_id)


def execute_extended_processor(processor_id: str, args: dict[str, Any]) -> CommandResult:
    """Execute an extended processor."""
    try:
        handler = _get_handler(processor_id)
        if handler is None:
            return _error(f"未知的扩展处理器: {processor_id}")
        return handler(args)
    except Exception as e:
        return _error(f"处理器执行失败: {e}")
