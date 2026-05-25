"""Shortcut health checks and repair helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from .command_risk import assess_command_risk
from .data_models import AppData, ShortcutItem, ShortcutType


@dataclass
class HealthIssue:
    id: str
    severity: str
    issue_type: str
    title: str
    message: str
    folder_id: str = ""
    folder_name: str = ""
    shortcut_id: str = ""
    shortcut_name: str = ""
    fix_action: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "issue_type": self.issue_type,
            "title": self.title,
            "message": self.message,
            "folder_id": self.folder_id,
            "folder_name": self.folder_name,
            "shortcut_id": self.shortcut_id,
            "shortcut_name": self.shortcut_name,
            "fix_action": self.fix_action,
        }


def _split_icon_location(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        return ""
    if "," in raw:
        return raw.rsplit(",", 1)[0].strip()
    return raw


def check_shortcuts(data: AppData) -> list[HealthIssue]:
    """Scan shortcuts and return health issues."""
    issues: list[HealthIssue] = []
    seen: dict[tuple[str, str], tuple[ShortcutItem, str]] = {}

    def add(issue_type: str, severity: str, title: str, message: str, folder, shortcut, fix_action: str = ""):
        issue_id = f"{issue_type}:{getattr(folder, 'id', '')}:{getattr(shortcut, 'id', '')}:{len(issues)}"
        issues.append(
            HealthIssue(
                id=issue_id,
                severity=severity,
                issue_type=issue_type,
                title=title,
                message=message,
                folder_id=getattr(folder, "id", ""),
                folder_name=getattr(folder, "name", ""),
                shortcut_id=getattr(shortcut, "id", ""),
                shortcut_name=getattr(shortcut, "name", ""),
                fix_action=fix_action,
            )
        )

    for folder in getattr(data, "folders", []) or []:
        if getattr(folder, "linked_path", "") and getattr(folder, "auto_sync", False):
            linked = getattr(folder, "linked_path", "")
            if not os.path.isdir(linked):
                dummy = ShortcutItem(id="", name=getattr(folder, "name", ""))
                add("missing_linked_folder", "error", "同步目录不可用", f"绑定目录不存在: {linked}", folder, dummy, "disable_folder_sync")

        for shortcut in getattr(folder, "items", []) or []:
            name_key = (str(getattr(shortcut, "name", "")).casefold(), str(getattr(shortcut, "type", "")).casefold())
            if name_key in seen and name_key[0]:
                first_item, first_folder = seen[name_key]
                add("duplicate_name", "debug", "重复名称", f"全局存在同名快捷方式 (首次出现于分类: {first_folder})", folder, shortcut)
            else:
                seen[name_key] = (shortcut, getattr(folder, "name", ""))

            shortcut_type = getattr(shortcut, "type", ShortcutType.FILE)
            if shortcut_type in (ShortcutType.FILE, ShortcutType.FOLDER):
                target = str(getattr(shortcut, "target_path", "") or "").strip()
                if not target:
                    add("missing_target", "error", "目标路径为空", "文件/文件夹快捷方式缺少目标路径", folder, shortcut, "delete_shortcut")
                elif not os.path.exists(target):
                    add("missing_target", "error", "目标路径不存在", target, folder, shortcut, "delete_shortcut")

            working_dir = str(getattr(shortcut, "working_dir", "") or "").strip()
            if working_dir and not os.path.isdir(working_dir):
                add("missing_working_dir", "warn", "工作目录不存在", working_dir, folder, shortcut, "clear_working_dir")

            icon_path = _split_icon_location(getattr(shortcut, "icon_path", ""))
            if icon_path and not os.path.exists(icon_path):
                add("missing_icon", "warn", "图标路径不存在", icon_path, folder, shortcut, "clear_icon")

            if shortcut_type == ShortcutType.URL:
                raw_url = str(getattr(shortcut, "url", "") or "").strip()
                parsed = urlparse(raw_url)
                if parsed.scheme and parsed.scheme.lower() not in ("http", "https"):
                    add("url_scheme", "warn", "URL 协议非常规", parsed.scheme, folder, shortcut)
                elif not parsed.scheme and not parsed.netloc and (not raw_url or "." not in parsed.path):
                    add("url_invalid", "error", "URL 格式无效", raw_url, folder, shortcut)

            if shortcut_type == ShortcutType.COMMAND:
                for risk in assess_command_risk(shortcut):
                    add("command_risk", risk.level, "命令风险提示", risk.message, folder, shortcut)
                command_text = str(getattr(shortcut, "command", "") or "").strip()
                cmd_type = str(getattr(shortcut, "command_type", "cmd") or "cmd")
                if cmd_type == "cmd" and command_text:
                    exe_path = _extract_command_executable(command_text)
                    if exe_path and not os.path.exists(exe_path):
                        add("missing_command_target", "warn", "命令入口文件不存在", exe_path, folder, shortcut)

    return issues


def _extract_command_executable(command: str) -> str:
    text = command.strip()
    if not text:
        return ""
    if text[0] == '"':
        end = text.find('"', 1)
        if end > 0:
            return text[1:end]
    parts = text.split(maxsplit=1)
    first = parts[0]
    if os.sep in first or "/" in first or "\\" in first:
        return first
    return ""


def apply_health_fixes(data_manager, issue_ids: list[str]) -> dict:
    """Apply safe automated fixes for selected issue ids."""
    wanted = set(issue_ids or [])
    if not wanted:
        return {"requested": 0, "applied": 0, "failed": 0}

    issues = [issue for issue in check_shortcuts(data_manager.data) if issue.id in wanted and issue.fix_action]
    action_priority = {
        "delete_shortcut": 0,
        "clear_icon": 1,
        "clear_working_dir": 1,
        "disable_folder_sync": 1,
        "disable_shortcut": 2,
    }
    issues.sort(key=lambda issue: action_priority.get(issue.fix_action, 9))
    applied = 0
    skipped = 0
    deleted_shortcuts: set[str] = set()
    with data_manager.batch_update(immediate=True):
        for issue in issues:
            if issue.shortcut_id in deleted_shortcuts:
                skipped += 1
                continue

            if issue.fix_action == "disable_folder_sync":
                folder = _find_folder(data_manager.data, issue.folder_id)
                if folder and getattr(folder, "auto_sync", False):
                    folder.auto_sync = False
                    applied += 1
                continue

            folder, shortcut = data_manager._find_shortcut_with_folder(issue.shortcut_id)
            if not shortcut:
                continue
            if issue.fix_action == "delete_shortcut":
                items = getattr(folder, "items", None)
                if not isinstance(items, list):
                    continue
                original_count = len(items)
                try:
                    items.remove(shortcut)
                except ValueError:
                    folder.items = [item for item in items if getattr(item, "id", "") != issue.shortcut_id]
                if len(getattr(folder, "items", []) or []) < original_count:
                    deleted_shortcuts.add(issue.shortcut_id)
                    applied += 1
            elif issue.fix_action == "clear_icon":
                icon_location = _split_icon_location(getattr(shortcut, "icon_path", ""))
                if icon_location and not os.path.exists(icon_location):
                    shortcut.icon_path = ""
                    applied += 1
                else:
                    skipped += 1
            elif issue.fix_action == "clear_working_dir":
                wd = str(getattr(shortcut, "working_dir", "") or "").strip()
                if wd and not os.path.isdir(wd):
                    shortcut.working_dir = ""
                    applied += 1
                else:
                    skipped += 1
            elif issue.fix_action == "disable_shortcut":
                shortcut.enabled = False
                applied += 1
        if applied:
            data_manager.save(immediate=True)

    failed = max(0, len(issues) - applied - skipped)
    return {"requested": len(issues), "applied": applied, "skipped": skipped, "failed": failed}


def _find_folder(data: AppData, folder_id: str):
    for folder in getattr(data, "folders", []) or []:
        if getattr(folder, "id", "") == folder_id:
            return folder
    return None
