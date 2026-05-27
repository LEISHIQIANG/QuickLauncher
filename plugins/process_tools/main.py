"""Process inspection commands for QuickLauncher."""

from __future__ import annotations

from core.command_registry import CommandAction, CommandResult


def register(api):
    api.register_command(
        id="process_tools.top",
        title="进程资源排行",
        aliases=["proc-top", "top-proc", "process-top", "进程排行"],
        description="按内存或 CPU 列出占用较高的进程",
        category="排障",
        handler=handle_top,
        search_terms=["task manager", "process tools", "资源占用", "任务管理"],
    )
    api.register_command(
        id="process_tools.find",
        title="查找进程",
        aliases=["proc", "ps", "find-proc", "查进程"],
        description="按进程名、PID 或路径关键字查找正在运行的进程",
        category="排障",
        handler=handle_find,
        search_terms=["tasklist", "process tools", "进程搜索"],
    )


def _copy(value: str, label: str = "复制结果") -> list[CommandAction]:
    return [CommandAction(type="copy", label=label, value=value)]


def _process_table_rows(rows: list[dict]) -> list[list[str]]:
    return [
        [
            str(item["pid"]),
            item["name"],
            f"{item['cpu']:.1f}%",
            _fmt_bytes(item["rss"]),
            item["status"],
            item["username"],
            item["exe"],
        ]
        for item in rows
    ]


def _process_table_text(columns: list[str], rows: list[list[str]]) -> str:
    return "\n".join(["\t".join(columns), *["\t".join(row) for row in rows]])


def _fmt_bytes(value: int | float | None) -> str:
    if not value:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def _as_number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _iter_processes():
    import psutil

    attrs = ["pid", "name", "exe", "username", "status", "memory_info", "cpu_percent"]
    for proc in psutil.process_iter(attrs):
        try:
            info = proc.info
            mem = info.get("memory_info")
            rss = getattr(mem, "rss", 0) if mem else 0
            yield {
                "pid": info.get("pid") or proc.pid,
                "name": info.get("name") or "",
                "exe": info.get("exe") or "",
                "username": info.get("username") or "",
                "status": info.get("status") or "",
                "rss": int(_as_number(rss, 0)),
                "cpu": _as_number(info.get("cpu_percent"), 0.0),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue


def handle_top(context):
    raw = (context.args_text or "").strip().lower()
    parts = raw.split()
    mode = "mem"
    limit = 10
    for part in parts:
        if part in {"cpu", "mem", "memory", "内存"}:
            mode = "cpu" if part == "cpu" else "mem"
        elif part.isdigit():
            limit = max(1, min(30, int(part)))

    key = "cpu" if mode == "cpu" else "rss"
    rows = sorted(_iter_processes(), key=lambda item: item[key], reverse=True)[:limit]
    if not rows:
        return CommandResult(success=False, message="没有读取到进程信息", error="无结果")

    title = "CPU" if mode == "cpu" else "内存"
    columns = ["PID", "Name", "CPU", "Memory", "Status", "User", "Path"]
    table_rows = _process_table_rows(rows)
    result = _process_table_text(columns, table_rows)
    return CommandResult(
        success=True,
        message=f"按{title}占用排序 Top {len(rows)}",
        display_type="table",
        payload={
            "window_size": "large",
            "columns": columns,
            "rows": table_rows,
            "copy_format": "tsv",
        },
        actions=_copy(result, "复制进程列表"),
    )


def handle_find(context):
    query = (context.args_text or "").strip().lower()
    if not query:
        return CommandResult(success=False, message="用法: /proc <进程名|PID|路径关键字>", error="缺少输入")

    rows = []
    for item in _iter_processes():
        haystack = " ".join(
            [
                str(item["pid"]),
                item["name"],
                item["exe"],
                item["username"],
                item["status"],
            ]
        ).lower()
        if query in haystack:
            rows.append(item)
        if len(rows) >= 30:
            break

    if not rows:
        return CommandResult(success=False, message=f"没有找到匹配进程: {query}", error="无结果")

    columns = ["PID", "Name", "CPU", "Memory", "Status", "User", "Path"]
    table_rows = _process_table_rows(rows)
    result = _process_table_text(columns, table_rows)
    return CommandResult(
        success=True,
        message=f"找到 {len(rows)} 个匹配进程: {query}",
        display_type="table",
        payload={
            "window_size": "large",
            "columns": columns,
            "rows": table_rows,
            "copy_format": "tsv",
        },
        actions=_copy(result, "复制进程信息"),
    )
