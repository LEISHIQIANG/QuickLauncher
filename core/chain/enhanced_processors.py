"""Enhanced processor implementations for action chain.

This module provides optimized and extended processor implementations:
- Text processing: trim, contains, startswith, endswith, regex_replace, etc.
- Logic control: switch_case, try_catch, assert_type, etc.
- Math: abs, ceil, floor, round, min, max, etc.
- List: list_count, list_group_by, list_sum, etc.
- File: file_copy, file_move, file_delete, file_size, etc.
- JSON: json_merge, json_flatten, json_keys, etc.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from typing import Any

__all__ = [
    # Text processors
    "text_trim",
    "text_contains",
    "text_startswith",
    "text_endswith",
    "text_regex_replace",
    "text_count",
    "text_reverse",
    "text_center",
    "text_ljust",
    "text_rjust",

    # Logic processors
    "switch_case",
    "try_catch",
    "assert_type",
    "is_empty",
    "is_numeric",
    "is_json",

    # Math processors
    "math_abs",
    "math_ceil",
    "math_floor",
    "math_round",
    "math_min",
    "math_max",
    "math_clamp",
    "math_random",

    # List processors
    "list_count",
    "list_sum",
    "list_min",
    "list_max",
    "list_avg",
    "list_group_by",
    "list_find",
    "list_remove",

    # File processors
    "file_copy",
    "file_move",
    "file_delete",
    "file_size",
    "file_modified",
    "file_list_dir",

    # JSON processors
    "json_merge",
    "json_flatten",
    "json_keys",
    "json_values",
    "json_length",
    "json_to_csv",
]


# ── Text Processors ──────────────────────────────────────────────────────────

def text_trim(text: str, chars: str = "") -> str:
    """Trim whitespace or specified characters from both ends."""
    if chars:
        return text.strip(chars)
    return text.strip()


def text_contains(text: str, substring: str, case_sensitive: bool = True) -> bool:
    """Check if text contains substring."""
    if not case_sensitive:
        return substring.lower() in text.lower()
    return substring in text


def text_startswith(text: str, prefix: str, case_sensitive: bool = True) -> bool:
    """Check if text starts with prefix."""
    if not case_sensitive:
        return text.lower().startswith(prefix.lower())
    return text.startswith(prefix)


def text_endswith(text: str, suffix: str, case_sensitive: bool = True) -> bool:
    """Check if text ends with suffix."""
    if not case_sensitive:
        return text.lower().endswith(suffix.lower())
    return text.endswith(suffix)


def text_regex_replace(text: str, pattern: str, replacement: str, count: int = 0) -> str:
    """Replace text using regex pattern."""
    if not pattern:
        return text
    try:
        return re.sub(pattern, replacement, text, count=count)
    except re.error as e:
        raise ValueError(f"无效的正则表达式: {e}") from e


def text_count(text: str, substring: str, case_sensitive: bool = True) -> int:
    """Count occurrences of substring in text."""
    if not case_sensitive:
        return text.lower().count(substring.lower())
    return text.count(substring)


def text_reverse(text: str) -> str:
    """Reverse the text."""
    return text[::-1]


def text_center(text: str, width: int, fillchar: str = " ") -> str:
    """Center text in a field of given width."""
    return text.center(width, fillchar)


def text_ljust(text: str, width: int, fillchar: str = " ") -> str:
    """Left justify text in a field of given width."""
    return text.ljust(width, fillchar)


def text_rjust(text: str, width: int, fillchar: str = " ") -> str:
    """Right justify text in a field of given width."""
    return text.rjust(width, fillchar)


# ── Logic Processors ──────────────────────────────────────────────────────────

def switch_case(value: str, cases: dict[str, str], default: str = "") -> str:
    """Switch case logic."""
    return cases.get(value, default)


def try_catch(func, default: str = "", error_var: str = "error") -> dict[str, Any]:
    """Try-catch error handling."""
    try:
        result = func()
        return {"success": True, "output": result, error_var: ""}
    except Exception as e:
        return {"success": False, "output": default, error_var: str(e)}


def assert_type(value: Any, expected_type: str) -> bool:
    """Assert that value is of expected type."""
    type_map = {
        "str": str,
        "string": str,
        "text": str,
        "int": int,
        "integer": int,
        "float": float,
        "number": (int, float),
        "bool": bool,
        "boolean": bool,
        "list": list,
        "array": list,
        "dict": dict,
        "object": dict,
        "json": (dict, list),
    }

    expected = type_map.get(expected_type.lower())
    if expected is None:
        raise ValueError(f"未知类型: {expected_type}")

    return isinstance(value, expected)


def is_empty(value: Any) -> bool:
    """Check if value is empty."""
    if value is None:
        return True
    if isinstance(value, str):
        return len(value.strip()) == 0
    if isinstance(value, list | dict):
        return len(value) == 0
    return False


def is_numeric(value: str) -> bool:
    """Check if string is numeric."""
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def is_json(value: str) -> bool:
    """Check if string is valid JSON."""
    try:
        json.loads(value)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


# ── Math Processors ──────────────────────────────────────────────────────────

def math_abs(value: float) -> float:
    """Absolute value."""
    return abs(value)


def math_ceil(value: float) -> int:
    """Round up to nearest integer."""
    import math
    return math.ceil(value)


def math_floor(value: float) -> int:
    """Round down to nearest integer."""
    import math
    return math.floor(value)


def math_round(value: float, decimals: int = 0) -> float:
    """Round to specified decimal places."""
    return round(value, decimals)


def math_min(*args: float) -> float:
    """Find minimum value."""
    return min(args)


def math_max(*args: float) -> float:
    """Find maximum value."""
    return max(args)


def math_clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value between min and max."""
    return max(min_val, min(value, max_val))


def math_random(min_val: int = 0, max_val: int = 100) -> int:
    """Generate random integer."""
    import random
    return random.randint(min_val, max_val)


# ── List Processors ──────────────────────────────────────────────────────────

def list_count(items: list, value: Any) -> int:
    """Count occurrences of value in list."""
    return items.count(value)


def list_sum(items: list) -> float:
    """Sum all numeric values in list."""
    total = 0.0
    for item in items:
        try:
            total += float(item)
        except (ValueError, TypeError):
            continue
    return total


def list_min(items: list) -> Any:
    """Find minimum value in list."""
    if not items:
        raise ValueError("列表为空")
    return min(items)


def list_max(items: list) -> Any:
    """Find maximum value in list."""
    if not items:
        raise ValueError("列表为空")
    return max(items)


def list_avg(items: list) -> float:
    """Calculate average of numeric values in list."""
    if not items:
        raise ValueError("列表为空")
    total = 0.0
    count = 0
    for item in items:
        try:
            total += float(item)
            count += 1
        except (ValueError, TypeError):
            continue
    if count == 0:
        raise ValueError("列表中没有数值")
    return total / count


def list_group_by(items: list[dict], key: str) -> dict[str, list]:
    """Group list of dicts by key."""
    result: dict[str, list] = {}
    for item in items:
        group_key = str(item.get(key, ""))
        if group_key not in result:
            result[group_key] = []
        result[group_key].append(item)
    return result


def list_find(items: list, predicate) -> Any:
    """Find first item matching predicate."""
    for item in items:
        if predicate(item):
            return item
    return None


def list_remove(items: list, value: Any) -> list:
    """Remove all occurrences of value from list."""
    return [item for item in items if item != value]


# ── File Processors ──────────────────────────────────────────────────────────

def file_copy(src: str, dst: str, overwrite: bool = False) -> str:
    """Copy file to destination."""
    if not os.path.exists(src):
        raise FileNotFoundError(f"源文件不存在: {src}")
    if os.path.exists(dst) and not overwrite:
        raise FileExistsError(f"目标文件已存在: {dst}")

    dst_dir = os.path.dirname(dst)
    if dst_dir:
        os.makedirs(dst_dir, exist_ok=True)

    shutil.copy2(src, dst)
    return dst


def file_move(src: str, dst: str, overwrite: bool = False) -> str:
    """Move file to destination."""
    if not os.path.exists(src):
        raise FileNotFoundError(f"源文件不存在: {src}")
    if os.path.exists(dst) and not overwrite:
        raise FileExistsError(f"目标文件已存在: {dst}")

    dst_dir = os.path.dirname(dst)
    if dst_dir:
        os.makedirs(dst_dir, exist_ok=True)

    shutil.move(src, dst)
    return dst


def file_delete(path: str, to_trash: bool = True) -> bool:
    """Delete file (optionally to trash)."""
    if not os.path.exists(path):
        return False

    if to_trash:
        try:
            from send2trash import send2trash
            send2trash(path)
            return True
        except ImportError:
            pass

    if os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    return True


def file_size(path: str) -> int:
    """Get file size in bytes."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"路径不存在: {path}")
    if os.path.isfile(path):
        return os.path.getsize(path)
    elif os.path.isdir(path):
        total = 0
        for dirpath, _dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)
        return total
    return 0


def file_modified(path: str) -> float:
    """Get file modification time as timestamp."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"路径不存在: {path}")
    return os.path.getmtime(path)


def file_list_dir(path: str, pattern: str = "*", recursive: bool = False) -> list[str]:
    """List files in directory."""
    import glob

    if not os.path.exists(path):
        raise FileNotFoundError(f"路径不存在: {path}")

    if recursive:
        pattern_path = os.path.join(path, "**", pattern)
        return glob.glob(pattern_path, recursive=True)
    else:
        pattern_path = os.path.join(path, pattern)
        return glob.glob(pattern_path)


# ── JSON Processors ──────────────────────────────────────────────────────────

def json_merge(*args: dict) -> dict:
    """Merge multiple JSON objects."""
    result = {}
    for arg in args:
        if isinstance(arg, dict):
            result.update(arg)
    return result


def json_flatten(data: dict, prefix: str = "", separator: str = ".") -> dict:
    """Flatten nested JSON object."""
    result = {}

    def _flatten(obj, current_prefix):
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{current_prefix}{separator}{key}" if current_prefix else key
                _flatten(value, new_key)
        elif isinstance(obj, list):
            for i, value in enumerate(obj):
                new_key = f"{current_prefix}{separator}{i}" if current_prefix else str(i)
                _flatten(value, new_key)
        else:
            result[current_prefix] = obj

    _flatten(data, prefix)
    return result


def json_keys(data: dict) -> list[str]:
    """Get all keys from JSON object."""
    if isinstance(data, dict):
        return list(data.keys())
    return []


def json_values(data: dict) -> list:
    """Get all values from JSON object."""
    if isinstance(data, dict):
        return list(data.values())
    return []


def json_length(data: Any) -> int:
    """Get length of JSON object/array."""
    if isinstance(data, dict | list):
        return len(data)
    return 0


def json_to_csv(data: list[dict], delimiter: str = ",") -> str:
    """Convert list of dicts to CSV string."""
    if not data:
        return ""

    # Get all unique keys
    keys = []
    seen = set()
    for item in data:
        for key in item.keys():
            if key not in seen:
                keys.append(key)
                seen.add(key)

    # Build CSV
    lines = [delimiter.join(keys)]
    for item in data:
        row = [str(item.get(key, "")) for key in keys]
        lines.append(delimiter.join(row))

    return "\n".join(lines)


# ── Helper Functions ──────────────────────────────────────────────────────────

def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int."""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default
