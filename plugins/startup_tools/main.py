"""Windows startup and PATH inspection commands for QuickLauncher."""

from __future__ import annotations

import os
from pathlib import Path

from core.command_registry import CommandAction, CommandResult


def register(api):
    api.register_command(
        id="startup_tools.audit",
        title="启动项审计",
        aliases=["startup-audit", "startup-check", "启动项", "开机启动"],
        description="列出常见 Run 注册表项和 Startup 文件夹中的启动项",
        category="排障",
        handler=handle_startup_audit,
        search_terms=["windows startup", "run registry", "开机自启", "启动项管理"],
    )
    api.register_command(
        id="startup_tools.path",
        title="PATH 健康检查",
        aliases=["path-audit", "env-path", "path-check", "环境变量检查"],
        description="检查 PATH 中的重复项、缺失目录和过长条目",
        category="排障",
        handler=handle_path_audit,
        search_terms=["environment variables", "path health", "环境变量", "路径诊断"],
    )


def _copy(value: str, label: str = "复制结果") -> list[CommandAction]:
    return [CommandAction(type="copy", label=label, value=value)]


def _status_to_list_status(status: str) -> str:
    normalized = (status or "").upper()
    if normalized == "OK":
        return "success"
    if normalized in {"MISSING?", "UNKNOWN"}:
        return "warning"
    return "info"


def handle_startup_audit(context):
    entries = []
    entries.extend(_registry_startup_entries())
    entries.extend(_startup_folder_entries())

    if not entries:
        return CommandResult(success=True, message="没有发现常见启动项")

    lines = [f"发现 {len(entries)} 个常见启动项:"]
    for entry in entries:
        status = _entry_status(entry.get("target", ""))
        lines.append(f"[{status}] {entry['name']}  ({entry['source']})")
        lines.append(f"  {entry['command']}")

    result = "\n".join(lines)
    return CommandResult(
        success=True,
        message=f"发现 {len(entries)} 个常见启动项",
        display_type="list",
        payload={
            "window_size": "medium",
            "items": [
                {
                    "title": entry["name"],
                    "status": _status_to_list_status(_entry_status(entry.get("target", ""))),
                    "detail": f"{entry['source']}\n{entry['command']}",
                }
                for entry in entries
            ],
        },
        actions=_copy(result, "复制启动项报告"),
    )


def _registry_startup_entries() -> list[dict[str, str]]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    roots = [
        (winreg.HKEY_CURRENT_USER, "HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_CURRENT_USER, "HKCU", r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
        (winreg.HKEY_LOCAL_MACHINE, "HKLM", r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, "HKLM", r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
    ]
    entries: list[dict[str, str]] = []
    for root, root_name, key_path in roots:
        try:
            with winreg.OpenKey(root, key_path, 0, winreg.KEY_READ) as key:
                index = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    command = str(value)
                    entries.append(
                        {
                            "name": name,
                            "command": command,
                            "target": _extract_target(command),
                            "source": f"{root_name}\\{key_path}",
                        }
                    )
                    index += 1
        except OSError:
            continue
    return entries


def _startup_folder_entries() -> list[dict[str, str]]:
    folders = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("PROGRAMDATA")
    if appdata:
        folders.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")
    if programdata:
        folders.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")

    entries: list[dict[str, str]] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for item in sorted(folder.iterdir()):
            if item.name.startswith("."):
                continue
            target = _resolve_shortcut_target(item)
            entries.append(
                {
                    "name": item.name,
                    "command": target or str(item),
                    "target": target or str(item),
                    "source": str(folder),
                }
            )
    return entries


def _resolve_shortcut_target(path: Path) -> str:
    if path.suffix.lower() != ".lnk" or os.name != "nt":
        return str(path)
    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(path))
        return shortcut.TargetPath or str(path)
    except Exception:
        return str(path)


def _extract_target(command: str) -> str:
    text = os.path.expandvars((command or "").strip())
    if not text:
        return ""
    if text.startswith('"'):
        end = text.find('"', 1)
        if end > 1:
            return text[1:end]
    parts = text.split()
    return parts[0] if parts else text


def _entry_status(target: str) -> str:
    if not target:
        return "UNKNOWN"
    expanded = os.path.expandvars(target)
    if Path(expanded).exists():
        return "OK"
    if expanded.lower().endswith((".dll", ".cpl")):
        return "CHECK"
    return "MISSING?"


def handle_path_audit(context):
    raw_path = os.environ.get("PATH", "")
    entries = [p.strip() for p in raw_path.split(os.pathsep) if p.strip()]
    normalized_seen: dict[str, int] = {}
    duplicates: list[str] = []
    missing: list[str] = []
    very_long: list[str] = []

    for entry in entries:
        expanded = os.path.expandvars(entry)
        norm = os.path.normcase(os.path.normpath(expanded))
        normalized_seen[norm] = normalized_seen.get(norm, 0) + 1
        if normalized_seen[norm] == 2:
            duplicates.append(expanded)
        if len(expanded) > 180:
            very_long.append(expanded)
        if not Path(expanded).is_dir():
            missing.append(expanded)

    lines = [
        f"PATH 条目数: {len(entries)}",
        f"重复目录: {len(duplicates)}",
        f"缺失目录: {len(missing)}",
        f"过长条目: {len(very_long)}",
    ]
    if duplicates:
        lines.append("\n重复目录:")
        lines.extend(f"  {item}" for item in duplicates[:12])
    if missing:
        lines.append("\n缺失目录:")
        lines.extend(f"  {item}" for item in missing[:20])
    if very_long:
        lines.append("\n过长条目:")
        lines.extend(f"  {item}" for item in very_long[:8])

    result = "\n".join(lines)
    items = [
        {"title": "PATH 条目数", "status": "info", "detail": str(len(entries))},
        {
            "title": "重复目录",
            "status": "warning" if duplicates else "success",
            "detail": "\n".join(duplicates[:12]) or "0",
        },
        {"title": "缺失目录", "status": "warning" if missing else "success", "detail": "\n".join(missing[:20]) or "0"},
        {
            "title": "过长条目",
            "status": "warning" if very_long else "success",
            "detail": "\n".join(very_long[:8]) or "0",
        },
    ]
    return CommandResult(
        success=True,
        message=result,
        display_type="list",
        payload={"window_size": "medium", "items": items},
        actions=_copy(result, "复制 PATH 报告"),
    )
