"""DateTime processors for action chains."""

from __future__ import annotations

import datetime
import time
from typing import Any

from core.command_registry import CommandResult

from ._proc_helpers import ok, string_values


def execute_extra_datetime_processor(processor_id: str, values: dict[str, Any]) -> CommandResult | None:
    """Handle datetime processors. Returns None if not a datetime processor."""
    text_values = string_values(values)

    if processor_id == "datetime_now":
        fmt = text_values.get("format", "%Y-%m-%d %H:%M:%S")
        return ok(datetime.datetime.now().strftime(fmt))
    if processor_id == "datetime_format":
        dt_str = text_values.get("datetime", "")
        fmt = text_values.get("format", "%Y-%m-%d %H:%M:%S")
        try:
            dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.datetime.strptime(dt_str, fmt)
        return ok(dt.strftime(fmt))
    if processor_id == "datetime_add":
        dt_str = text_values.get("datetime", "")
        fmt = text_values.get("format", "%Y-%m-%d %H:%M:%S")
        try:
            dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.datetime.strptime(dt_str, fmt)
        dt += datetime.timedelta(
            days=int(text_values.get("days", "0") or "0"),
            hours=int(text_values.get("hours", "0") or "0"),
            minutes=int(text_values.get("minutes", "0") or "0"),
            seconds=int(text_values.get("seconds", "0") or "0"),
        )
        return ok(dt.strftime(fmt))
    if processor_id == "datetime_diff":
        dt1_str = text_values.get("datetime1", "")
        dt2_str = text_values.get("datetime2", "")
        unit = text_values.get("unit", "seconds")
        try:
            dt1 = datetime.datetime.fromisoformat(dt1_str.replace("Z", "+00:00"))
        except ValueError:
            dt1 = datetime.datetime.strptime(dt1_str, "%Y-%m-%d %H:%M:%S")
        try:
            dt2 = datetime.datetime.fromisoformat(dt2_str.replace("Z", "+00:00"))
        except ValueError:
            dt2 = datetime.datetime.strptime(dt2_str, "%Y-%m-%d %H:%M:%S")
        secs = (dt1 - dt2).total_seconds()
        factor = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400, "weeks": 604800}.get(unit, 1)
        return ok(str(secs / factor))
    if processor_id == "timestamp_now":
        return ok(str(time.time()))
    if processor_id == "timestamp_to_datetime":
        ts = float(text_values.get("timestamp", "0"))
        fmt = text_values.get("format", "%Y-%m-%d %H:%M:%S")
        return ok(datetime.datetime.fromtimestamp(ts).strftime(fmt))
    if processor_id == "datetime_to_timestamp":
        dt_str = text_values.get("datetime", "")
        fmt = text_values.get("format", "%Y-%m-%d %H:%M:%S")
        try:
            dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.datetime.strptime(dt_str, fmt)
        return ok(str(dt.timestamp()))

    return None
