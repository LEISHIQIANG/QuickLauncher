"""Data validation processors for action chains."""

from __future__ import annotations

import re
import socket
import urllib.parse
from typing import Any

from core.command_registry import CommandResult

from ._proc_helpers import ok_bool, string_values, to_num


def execute_extra_validation_processor(processor_id: str, values: dict[str, Any]) -> CommandResult | None:
    """Handle validation processors. Returns None if not a validation processor."""
    text_values = string_values(values)

    if processor_id == "validate_email":
        return ok_bool(bool(re.match(r"^[\w.%+-]+@[\w.-]+\.[a-zA-Z]{2,}$", text_values.get("email", ""))))
    if processor_id == "validate_url":
        try:
            p = urllib.parse.urlparse(text_values.get("url", ""))
            return ok_bool(all([p.scheme, p.netloc]))
        except Exception:
            return ok_bool(False)
    if processor_id == "validate_ip":
        ip = text_values.get("ip", "")
        try:
            socket.inet_pton(socket.AF_INET, ip)
            return ok_bool(True)
        except OSError:
            try:
                socket.inet_pton(socket.AF_INET6, ip)
                return ok_bool(True)
            except OSError:
                return ok_bool(False)
    if processor_id == "validate_phone":
        phone = re.sub(r"[\s-]", "", text_values.get("phone", ""))
        return ok_bool(bool(re.match(r"^(\+86)?1[3-9]\d{9}$", phone)))
    if processor_id == "validate_regex":
        try:
            return ok_bool(bool(re.match(text_values.get("pattern", ""), text_values.get("text", ""))))
        except re.error:
            return ok_bool(False)
    if processor_id == "validate_range":
        v = to_num(values.get("value", 0))
        lo = to_num(values.get("min", 0))
        hi = to_num(values.get("max", 100))
        return ok_bool(lo <= v <= hi)
    if processor_id == "validate_length":
        t = text_values.get("text", "")
        lo = int(text_values.get("min", "0") or "0")
        hi = int(text_values.get("max", "0") or "0")
        result = True
        if lo > 0 and len(t) < lo:
            result = False
        if hi > 0 and len(t) > hi:
            result = False
        return ok_bool(result)

    return None
