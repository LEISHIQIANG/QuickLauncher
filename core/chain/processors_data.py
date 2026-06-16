"""Hash, color, set, dict, and string formatting processors for action chains."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from core.command_registry import CommandResult

from ._proc_helpers import (
    ok,
    ok_list,
    parse_list,
    string_values,
    try_json_parse,
    value_to_text,
)


def execute_extra_data_processor(processor_id: str, values: dict[str, Any]) -> CommandResult | None:
    """Handle hash, color, set, dict, and string formatting processors. Returns None if not handled."""
    text_values = string_values(values)

    # -- Hashing --
    if processor_id == "hash_md5":
        return ok(hashlib.md5(text_values.get("text", "").encode("utf-8")).hexdigest())
    if processor_id == "hash_sha1":
        return ok(hashlib.sha1(text_values.get("text", "").encode("utf-8")).hexdigest())
    if processor_id == "hash_sha256":
        return ok(hashlib.sha256(text_values.get("text", "").encode("utf-8")).hexdigest())
    if processor_id == "hash_sha512":
        return ok(hashlib.sha512(text_values.get("text", "").encode("utf-8")).hexdigest())
    if processor_id == "hash_crc32":
        import zlib as _zl

        return ok(format(_zl.crc32(text_values.get("text", "").encode("utf-8")) & 0xFFFFFFFF, "08x"))
    if processor_id == "hash_uuid":
        import uuid as _uu

        return ok(str(_uu.uuid4()))

    # -- Color --
    if processor_id == "color_hex_to_rgb":
        h = text_values.get("hex", "#000000").lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return ok(f"({r}, {g}, {b})")
    if processor_id == "color_rgb_to_hex":
        r = int(text_values.get("r", "0") or "0")
        g = int(text_values.get("g", "0") or "0")
        b = int(text_values.get("b", "0") or "0")
        return ok(f"#{r:02x}{g:02x}{b:02x}")
    if processor_id == "color_brightness":
        h = text_values.get("hex", "#000000").lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return ok(str((r * 299 + g * 587 + b * 114) / 1000 / 255 * 100))
    if processor_id == "color_complementary":
        h = text_values.get("hex", "#000000").lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return ok(f"#{255 - r:02x}{255 - g:02x}{255 - b:02x}")
    if processor_id == "color_random":
        import random as _rr

        return ok(f"#{_rr.randint(0, 0xffffff):06x}")

    # -- Set operations --
    if processor_id == "set_union":
        a, b = parse_list(values.get("set1", "")), parse_list(values.get("set2", ""))  # type: ignore[assignment]
        return ok_list(list(set(a) | set(b)))  # type: ignore[call-overload]
    if processor_id == "set_intersection":
        a, b = parse_list(values.get("set1", "")), parse_list(values.get("set2", ""))  # type: ignore[assignment]
        return ok_list(list(set(a) & set(b)))  # type: ignore[call-overload]
    if processor_id == "set_difference":
        a, b = parse_list(values.get("set1", "")), parse_list(values.get("set2", ""))  # type: ignore[assignment]
        return ok_list(list(set(a) - set(b)))  # type: ignore[call-overload]
    if processor_id == "set_unique":
        lst = parse_list(values.get("list", ""))
        seen = set()
        result = []
        for x in lst:
            if x not in seen:
                seen.add(x)
                result.append(x)
        return ok_list(result)

    # -- Dict operations --
    if processor_id == "dict_keys":
        d = try_json_parse(values.get("json", "{}"))
        return ok_list(list(d.keys()) if isinstance(d, dict) else [])
    if processor_id == "dict_values":
        d = try_json_parse(values.get("json", "{}"))
        return ok_list([value_to_text(v) for v in d.values()] if isinstance(d, dict) else [])
    if processor_id == "dict_merge":
        a = try_json_parse(values.get("a", "{}"))
        b = try_json_parse(values.get("b", "{}"))
        result = dict(a) if isinstance(a, dict) else {}  # type: ignore[assignment]
        if isinstance(b, dict):
            result.update(b)  # type: ignore[attr-defined]
        return ok(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if processor_id == "dict_get":
        d = try_json_parse(values.get("json", "{}"))
        k = text_values.get("key", "")
        return ok(value_to_text(d.get(k, values.get("default", ""))) if isinstance(d, dict) else "")
    if processor_id == "dict_set":
        d_raw = try_json_parse(values.get("json", "{}"))
        d = dict(d_raw) if isinstance(d_raw, dict) else {}
        d[text_values.get("key", "")] = values.get("value", "")
        return ok(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
    if processor_id == "dict_filter":
        d = try_json_parse(values.get("json", "{}"))
        keys = parse_list(values.get("keys", ""))
        if isinstance(d, dict):
            d = {k: v for k, v in d.items() if k in keys}
        return ok(json.dumps(d, ensure_ascii=False, separators=(",", ":")))

    # -- String formatting --
    if processor_id == "str_pad_left":
        return ok(
            text_values.get("text", "").rjust(
                int(text_values.get("width", "0") or "0"), text_values.get("fillchar", " ") or " "
            )
        )
    if processor_id == "str_pad_right":
        return ok(
            text_values.get("text", "").ljust(
                int(text_values.get("width", "0") or "0"), text_values.get("fillchar", " ") or " "
            )
        )
    if processor_id == "str_truncate":
        t = text_values.get("text", "")
        ml = int(text_values.get("max_length", "100") or "100")
        s = text_values.get("suffix", "...")
        return ok(t if len(t) <= ml else t[: ml - len(s)] + s)
    if processor_id == "str_repeat":
        return ok(text_values.get("text", "") * int(text_values.get("count", "1") or "1"))

    return None
