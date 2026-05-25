"""Windows Event Log Inspector plugin — read and analyze system/application logs."""

from __future__ import annotations

import subprocess
import time

from core.command_registry import CommandAction, CommandResult

LOG_TYPES = ("System", "Application")
HOURS_BACK = 24
MAX_EVENTS_SCAN = 500
MAX_RESULTS = 30


def register(api):
    api.register_command(
        id="event_inspector.recent",
        title="最近错误",
        aliases=["event-recent", "最近错误", "错误日志"],
        description="显示最近 24 小时内的系统/应用错误和警告摘要",
        category="排障",
        handler=_handle_recent,
        search_terms=["windows event log", "蓝屏", "crash", "系统错误"],
    )

    api.register_command(
        id="event_inspector.search",
        title="搜索事件",
        aliases=["event-search", "event-find", "搜索事件"],
        description="在系统/应用日志中搜索关键词（EventID、来源、描述）",
        category="排障",
        handler=_handle_search,
        search_terms=["find event", "事件搜索", "日志搜索"],
    )

    api.register_command(
        id="event_inspector.source",
        title="按来源查看",
        aliases=["event-source", "事件来源"],
        description="按来源名称过滤并聚合事件日志",
        category="排障",
        handler=_handle_source,
        search_terms=["event source", "来源统计", "事件源"],
    )


def _read_events_wevtutil(log_name: str, hours_back: int, max_events: int) -> list[dict]:
    query = f"*[System[TimeCreated[timediff(@SystemTime) <= {hours_back * 3600000}]]]"
    try:
        result = subprocess.run(
            ["wevtutil", "qe", log_name, "/q:" + query, "/c:" + str(max_events), "/f:text"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            creationflags=0x08000000,
        )
        if result.returncode != 0:
            return []
        return _parse_wevtutil_output(result.stdout.decode("utf-8", errors="replace"))
    except Exception:
        return []


def _parse_wevtutil_output(text: str) -> list[dict]:
    events = []
    current: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith("Event[") or line.startswith("Event "):
            if current:
                events.append(current)
                current = {}
            current["_index"] = line
            continue
        if ": " in line:
            key, _, value = line.partition(": ")
            key = key.strip()
            value = value.strip()
            if key == "Level":
                current["level"] = value
            elif key == "Provider":
                current["source"] = value
            elif key == "Event ID":
                current["event_id"] = value
            elif key == "TimeCreated":
                current["time"] = value
            elif key == "Message":
                current["message"] = value[:200]
    if current:
        events.append(current)
    return events[-MAX_RESULTS:]


def _try_win32evtlog(log_name: str, hours_back: int, max_events: int) -> list[dict] | None:
    try:
        import win32evtlog
        import win32evtlogutil
    except ImportError:
        return None

    events = []
    since_ms = int(time.time() * 1000) - hours_back * 3600 * 1000

    try:
        hand = win32evtlog.OpenEventLog(None, log_name)
    except Exception:
        return None

    try:
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        while len(events) < max_events:
            chunk = win32evtlog.ReadEventLog(hand, flags, 0)
            if not chunk:
                break
            for event in chunk:
                if event.TimeGenerated and int(time.mktime(event.TimeGenerated.timetuple()) * 1000) < since_ms:
                    continue

                level_map = {1: "ERROR", 2: "WARNING", 4: "INFO", 8: "AUDIT"}
                level = level_map.get(event.EventType, str(event.EventType))
                source = str(event.SourceName or "")
                event_id = str(event.EventID & 0x3FFFFFFF)
                ts = str(event.TimeGenerated) if event.TimeGenerated else ""
                try:
                    desc = win32evtlogutil.SafeFormatMessage(event)
                except Exception:
                    try:
                        desc = str(event.StringInserts) if event.StringInserts else ""
                    except Exception:
                        desc = ""

                events.append({
                    "level": level,
                    "source": source,
                    "event_id": event_id,
                    "time": ts,
                    "message": desc[:300],
                })

                if len(events) >= max_events:
                    break

            if len(events) >= max_events:
                break
    finally:
        try:
            win32evtlog.CloseEventLog(hand)
        except Exception:
            pass

    return events


def _read_events(log_name: str) -> list[dict]:
    result = _try_win32evtlog(log_name, HOURS_BACK, MAX_EVENTS_SCAN)
    if result is not None:
        return result
    return _read_events_wevtutil(log_name, HOURS_BACK, MAX_EVENTS_SCAN)


def _level_priority(level: str) -> int:
    lowered = level.lower()
    if "error" in lowered or "critical" in lowered:
        return 0
    if "warning" in lowered:
        return 1
    return 2


def _handle_recent(context) -> CommandResult:
    all_events: list[dict] = []
    for log_type in LOG_TYPES:
        all_events.extend(_read_events(log_type))

    if not all_events:
        return CommandResult(
            success=True,
            message=f"最近 {HOURS_BACK} 小时内未发现错误或警告事件。",
        )

    all_events.sort(key=lambda e: _level_priority(e.get("level", "")))

    errors = [e for e in all_events if "error" in e.get("level", "").lower()]
    warnings = [e for e in all_events if "warning" in e.get("level", "").lower()]

    source_summary: dict[str, int] = {}
    for e in all_events:
        src = e.get("source", "未知")
        source_summary[src] = source_summary.get(src, 0) + 1
    top_sources = sorted(source_summary.items(), key=lambda x: -x[1])[:8]

    lines = [
        f"最近 {HOURS_BACK} 小时事件摘要",
        f"错误: {len(errors)}  警告: {len(warnings)}  总计: {len(all_events)}",
    ]

    if top_sources:
        lines.append("")
        lines.append("高频来源:")
        for src, count in top_sources:
            err_count = sum(1 for e in all_events if e.get("source") == src and "error" in e.get("level", "").lower())
            marker = " ❌" if err_count else ""
            lines.append(f"  {src}: {count} 次{marker}")

    if errors:
        lines.append("")
        lines.append(f"最新错误 (最多 {MAX_RESULTS} 条):")
        for e in errors[:MAX_RESULTS]:
            ts = e.get("time", "")
            src = e.get("source", "")
            eid = e.get("event_id", "")
            msg = e.get("message", "")[:80]
            lines.append(f"  [{ts}] {src} (ID:{eid})")
            if msg:
                lines.append(f"    {msg}")

    result = "\n".join(lines)
    return CommandResult(
        success=True,
        message=result,
        actions=[CommandAction(type="copy", label="复制报告", value=result)],
    )


def _handle_search(context) -> CommandResult:
    query = (context.args_text or "").strip()
    if not query:
        return CommandResult(
            success=False,
            message="用法: /event-search <关键词>\n例如: /event-search 1001 或 /event-search .NET",
            error="缺少输入",
        )

    all_events: list[dict] = []
    for log_type in LOG_TYPES:
        for e in _read_events(log_type):
            haystack = " ".join(str(v) for v in e.values()).lower()
            if query.lower() in haystack:
                all_events.append(e)

    if not all_events:
        return CommandResult(
            success=True,
            message=f"在日志中未找到匹配 \"{query}\" 的事件。",
        )

    lines = [f"找到 {len(all_events)} 个匹配 \"{query}\" 的事件:"]
    for e in all_events[:MAX_RESULTS]:
        ts = e.get("time", "")
        level = e.get("level", "")
        src = e.get("source", "")
        eid = e.get("event_id", "")
        msg = e.get("message", "")[:100]
        lines.append(f"  [{level}] [{ts}] {src} (ID:{eid})")
        if msg:
            lines.append(f"    {msg}")

    if len(all_events) > MAX_RESULTS:
        lines.append(f"... 还有 {len(all_events) - MAX_RESULTS} 条")

    result = "\n".join(lines)
    return CommandResult(
        success=True,
        message=result,
        actions=[CommandAction(type="copy", label="复制结果", value=result)],
    )


def _handle_source(context) -> CommandResult:
    source_name = (context.args_text or "").strip()
    all_events: list[dict] = []
    for log_type in LOG_TYPES:
        all_events.extend(_read_events(log_type))

    if not source_name:
        src_count: dict[str, int] = {}
        src_errors: dict[str, int] = {}
        for e in all_events:
            s = e.get("source", "未知")
            src_count[s] = src_count.get(s, 0) + 1
            if "error" in e.get("level", "").lower():
                src_errors[s] = src_errors.get(s, 0) + 1

        sorted_src = sorted(src_count.items(), key=lambda x: -x[1])[:20]
        lines = [f"日志来源聚合 (共 {len(src_count)} 个来源):"]
        for s, count in sorted_src:
            err = src_errors.get(s, 0)
            err_mark = f" ❌{err}错误" if err else ""
            lines.append(f"  {s}: {count} 条{err_mark}")

        result = "\n".join(lines)
        return CommandResult(
            success=True,
            message=result,
            actions=[CommandAction(type="copy", label="复制聚合", value=result)],
        )

    filtered = [e for e in all_events if source_name.lower() in e.get("source", "").lower()]
    if not filtered:
        return CommandResult(
            success=True,
            message=f"未找到来源包含 \"{source_name}\" 的事件。",
        )

    lines = [f"来源 \"{source_name}\" 共 {len(filtered)} 条事件:"]
    for e in filtered[:MAX_RESULTS]:
        ts = e.get("time", "")
        level = e.get("level", "")
        eid = e.get("event_id", "")
        msg = e.get("message", "")[:100]
        lines.append(f"  [{level}] [{ts}] ID:{eid}")
        if msg:
            lines.append(f"    {msg}")

    result = "\n".join(lines)
    return CommandResult(
        success=True,
        message=result,
        actions=[CommandAction(type="copy", label="复制结果", value=result)],
    )
