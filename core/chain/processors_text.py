"""Enhanced text and logic processors for action chains."""

from __future__ import annotations

import json
import re
from typing import Any

from core.command_registry import CommandResult

from ._proc_helpers import (
    ok,
    ok_bool,
    string_values,
    to_bool,
    try_json_parse,
    value_to_text,
)


def execute_extra_text_processor(processor_id: str, values: dict[str, Any]) -> CommandResult | None:
    """Handle enhanced text and logic processors. Returns None if not a text/logic processor."""
    text_values = string_values(values)

    # ── Enhanced: Text processing ──
    if processor_id == "text_trim":
        text = text_values.get("text", "")
        chars = text_values.get("chars", "")
        return ok(text.strip(chars) if chars else text.strip())
    if processor_id == "text_contains":
        text = text_values.get("text", "")
        sub = text_values.get("substring", "")
        cs = to_bool(values.get("case_sensitive", True))
        return ok_bool(sub.lower() in text.lower() if not cs else sub in text)
    if processor_id == "text_startswith":
        text = text_values.get("text", "")
        prefix = text_values.get("prefix", "")
        cs = to_bool(values.get("case_sensitive", True))
        return ok_bool(text.lower().startswith(prefix.lower()) if not cs else text.startswith(prefix))
    if processor_id == "text_endswith":
        text = text_values.get("text", "")
        suffix = text_values.get("suffix", "")
        cs = to_bool(values.get("case_sensitive", True))
        return ok_bool(text.lower().endswith(suffix.lower()) if not cs else text.endswith(suffix))
    if processor_id == "text_regex_replace":
        text = text_values.get("text", "")
        pattern = text_values.get("pattern", "")
        repl = text_values.get("replacement", "")
        cnt = int(text_values.get("count", "0") or "0")
        if not pattern:
            return ok(text)
        return ok(re.sub(pattern, repl, text, count=cnt))
    if processor_id == "text_count":
        text = text_values.get("text", "")
        sub = text_values.get("substring", "")
        cs = to_bool(values.get("case_sensitive", True))
        cnt = text.lower().count(sub.lower()) if not cs else text.count(sub)
        return ok(str(cnt))
    if processor_id == "text_reverse":
        return ok(text_values.get("text", "")[::-1])

    # ── Enhanced: Logic control ──
    if processor_id == "switch_case":
        val = text_values.get("value", "")
        cases = try_json_parse(values.get("cases_json", "{}"))
        default = text_values.get("default", "")
        if isinstance(cases, dict) and val in cases:
            return ok(value_to_text(cases[val]))
        return ok(default)
    if processor_id == "try_catch":
        return ok(text_values.get("input", "") or text_values.get("default", ""))
    if processor_id == "assert_type":
        val = values.get("value")  # type: ignore[assignment]
        t = text_values.get("type", "text").lower()
        result = False
        if t in ("str", "string", "text"):
            result = isinstance(val, str)
        elif t in ("int", "integer"):
            result = isinstance(val, int) or (isinstance(val, str) and val.strip().isdigit())
        elif t in ("float", "number"):
            try:
                float(val)
                result = True
            except (ValueError, TypeError):
                result = False
        elif t in ("bool", "boolean"):
            result = isinstance(val, bool)
        elif t in ("list", "array"):
            result = isinstance(val, list)
        elif t in ("dict", "object", "json"):
            result = isinstance(val, dict)
        return ok_bool(result)
    if processor_id == "is_empty":
        v = values.get("value")
        empty = v is None or str(v).strip() == "" or (hasattr(v, "__len__") and len(v) == 0)
        return ok_bool(empty)
    if processor_id == "is_numeric":
        try:
            float(text_values.get("text", ""))
            return ok_bool(True)
        except ValueError:
            return ok_bool(False)
    if processor_id == "is_json":
        try:
            json.loads(text_values.get("text", ""))
            return ok_bool(True)
        except (json.JSONDecodeError, TypeError):
            return ok_bool(False)

    return None
