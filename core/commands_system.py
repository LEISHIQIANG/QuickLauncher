"""System information built-in command handlers."""

from __future__ import annotations

import logging
import os
import platform
from datetime import datetime

from .command_registry import CommandAction, CommandContext, CommandResult

logger = logging.getLogger(__name__)


def _format_bytes(value: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value or 0)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def _proc_info_block(info: dict) -> str:
    mem = getattr(info.get("memory_info"), "rss", 0) or 0
    cpu = info.get("cpu_percent")
    lines = [
        f"PID: {info.get('pid')}",
        f"名称: {info.get('name') or '?'}",
        f"内存: {_format_bytes(mem)}",
    ]
    if cpu is not None:
        lines.append(f"CPU: {cpu}%")
    exe = info.get("exe") or ""
    if exe:
        lines.append(f"路径: {exe}")
    return "\n".join(lines)


def cmd_process(context: CommandContext) -> CommandResult:
    import psutil

    args = context.args_text.strip()
    parts = args.split()
    mode = parts[0].lower() if parts else "top"

    if mode == "kill" and len(parts) >= 2:
        try:
            pid = int(parts[1])
            proc = psutil.Process(pid)
            name = proc.name()
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            return CommandResult(success=True, message=f"已终止进程 PID {pid}: {name}")
        except Exception as e:
            return CommandResult(success=False, message=f"终止进程失败: {e}", error="终止失败")

    keyword = ""
    if mode in ("find", "search", "查找") and len(parts) >= 2:
        keyword = " ".join(parts[1:]).lower()
    elif mode not in ("top", "mem", "memory", "cpu", ""):
        keyword = args.lower()

    rows: list[dict] = []
    for proc in psutil.process_iter(["pid", "name", "exe", "memory_info", "cpu_percent"]):
        try:
            info = dict(proc.info)
        except Exception:
            continue
        haystack = f"{info.get('name') or ''} {info.get('exe') or ''}".lower()
        if keyword and keyword not in haystack:
            continue
        rows.append(info)

    if keyword:
        rows.sort(key=lambda item: getattr(item.get("memory_info"), "rss", 0) or 0, reverse=True)
        selected = rows[:20]
        if not selected:
            return CommandResult(success=True, message=f"未找到匹配进程: {keyword}")
        title = f"匹配进程: {keyword}"
    else:
        sort_cpu = mode == "cpu"
        rows.sort(
            key=lambda item: (
                (item.get("cpu_percent") or 0) if sort_cpu else (getattr(item.get("memory_info"), "rss", 0) or 0)
            ),
            reverse=True,
        )
        selected = rows[:10]
        title = "CPU 占用最高进程" if sort_cpu else "内存占用最高进程"

    message = title + "\n\n" + "\n\n".join(_proc_info_block(info) for info in selected)
    return CommandResult(
        success=True,
        message=message,
        payload={"rows": selected},
        actions=[CommandAction(type="copy", label="复制进程列表", value=message)],
    )


def cmd_sysreport(context: CommandContext) -> CommandResult:
    import psutil

    try:
        vm = psutil.virtual_memory()
        disk_target = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
        disk = psutil.disk_usage(disk_target)
        net = psutil.net_io_counters()
        boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
        cpu_percent = psutil.cpu_percent(interval=0.1)

        lines = [
            "系统快照",
            f"系统: {platform.platform()}",
            f"启动时间: {boot_time}",
            f"CPU: {cpu_percent:.1f}% | 核心: {psutil.cpu_count(logical=True)}",
            f"内存: {_format_bytes(vm.used)} / {_format_bytes(vm.total)} ({vm.percent:.1f}%)",
            f"磁盘: {_format_bytes(disk.used)} / {_format_bytes(disk.total)} ({disk.percent:.1f}%)",
            f"网络累计: 发送 {_format_bytes(net.bytes_sent)} / 接收 {_format_bytes(net.bytes_recv)}",
        ]
        try:
            battery = psutil.sensors_battery()
            if battery is not None:
                power = "接入电源" if battery.power_plugged else "电池供电"
                lines.append(f"电池: {battery.percent:.1f}% ({power})")
        except Exception:
            logger.debug("获取电池信息失败", exc_info=True)

        message = "\n".join(lines)
        return CommandResult(
            success=True,
            message=message,
            actions=[CommandAction(type="copy", label="复制系统快照", value=message)],
        )
    except Exception as e:
        return CommandResult(success=False, message=f"生成系统快照失败: {e}", error="系统信息失败")
