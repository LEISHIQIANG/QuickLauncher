"""Shortcut health checks and repair helpers."""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.parse import urlparse

from .command_risk import assess_command_risk
from .data_models import AppData, ShortcutItem, ShortcutType
from .runtime_constants import COMMAND_CHAIN_MAX_STEPS
from .shortcut_url_exec import UrlExecutionMixin

logger = logging.getLogger(__name__)

MAX_CHAIN_STEPS = COMMAND_CHAIN_MAX_STEPS
MAX_FAVICON_REFRESH_WORKERS = 8

_WINDOWS_ENV_VAR_RE = re.compile(r"%[^%]+%")


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


def _expanded_path(path: str) -> str:
    return os.path.expanduser(os.path.expandvars(str(path or "").strip()))


def _has_unresolved_env_var(path: str) -> bool:
    raw = str(path or "")
    if not raw:
        return False
    return bool(_WINDOWS_ENV_VAR_RE.search(_expanded_path(raw)))


def _shortcut_type(shortcut: ShortcutItem) -> ShortcutType:
    value = getattr(shortcut, "type", ShortcutType.FILE)
    if isinstance(value, ShortcutType):
        return value
    try:
        return ShortcutType(str(value))
    except Exception:
        return ShortcutType.FILE


def _resolve_lnk_target(path: str) -> str:
    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(path)
        return str(getattr(shortcut, "TargetPath", "") or "").strip()
    except Exception:
        return ""


def check_shortcuts(data: AppData) -> list[HealthIssue]:
    """Scan shortcuts and return health issues."""
    issues: list[HealthIssue] = []
    seen: dict[tuple[str, str], tuple[ShortcutItem, str]] = {}
    shortcut_map: dict[str, ShortcutItem] = {}
    _type_counter: dict[tuple[str, str, str], int] = {}

    for folder in getattr(data, "folders", []) or []:
        for shortcut in getattr(folder, "items", []) or []:
            shortcut_id = str(getattr(shortcut, "id", "") or "")
            if shortcut_id:
                shortcut_map[shortcut_id] = shortcut

    def add(issue_type: str, severity: str, title: str, message: str, folder, shortcut, fix_action: str = ""):
        folder_id = getattr(folder, "id", "")
        shortcut_id = getattr(shortcut, "id", "")
        counter_key = (issue_type, folder_id, shortcut_id)
        _type_counter[counter_key] = _type_counter.get(counter_key, 0) + 1
        suffix = _type_counter[counter_key]
        issue_id = f"{issue_type}:{folder_id}:{shortcut_id}:{suffix}"
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
            linked = str(getattr(folder, "linked_path", "") or "").strip()
            if _has_unresolved_env_var(linked):
                dummy = ShortcutItem(id="", name=getattr(folder, "name", ""))
                add(
                    "unresolved_env_var",
                    "warn",
                    "Folder link has unresolved environment variable",
                    linked,
                    folder,
                    dummy,
                )
            elif not os.path.isdir(_expanded_path(linked)):
                dummy = ShortcutItem(id="", name=getattr(folder, "name", ""))
                add(
                    "missing_linked_folder",
                    "error",
                    "Linked folder is unavailable",
                    f"Linked folder does not exist: {linked}",
                    folder,
                    dummy,
                    "disable_folder_sync",
                )

        for shortcut in getattr(folder, "items", []) or []:
            shortcut_type = _shortcut_type(shortcut)
            name_key = (str(getattr(shortcut, "name", "")).casefold(), shortcut_type.value)
            if name_key in seen and name_key[0]:
                _first_item, first_folder = seen[name_key]
                add(
                    "duplicate_name",
                    "debug",
                    "Duplicate name",
                    f"Another shortcut with the same name exists in folder: {first_folder}",
                    folder,
                    shortcut,
                )
            else:
                seen[name_key] = (shortcut, getattr(folder, "name", ""))

            if shortcut_type in (ShortcutType.FILE, ShortcutType.FOLDER):
                target = str(getattr(shortcut, "target_path", "") or "").strip()
                if not target:
                    add(
                        "missing_target",
                        "error",
                        "Target path is empty",
                        "File/folder shortcut has no target path.",
                        folder,
                        shortcut,
                        "delete_shortcut",
                    )
                elif _has_unresolved_env_var(target):
                    add(
                        "unresolved_env_var",
                        "warn",
                        "Target path has unresolved environment variable",
                        target,
                        folder,
                        shortcut,
                    )
                elif not os.path.exists(_expanded_path(target)):
                    add(
                        "missing_target",
                        "error",
                        "Target path does not exist",
                        target,
                        folder,
                        shortcut,
                        "delete_shortcut",
                    )
                elif target.lower().endswith(".lnk"):
                    link_target = _resolve_lnk_target(_expanded_path(target))
                    if link_target and _has_unresolved_env_var(link_target):
                        add(
                            "unresolved_env_var",
                            "warn",
                            "Shortcut target has unresolved environment variable",
                            link_target,
                            folder,
                            shortcut,
                        )
                    elif link_target and not os.path.exists(_expanded_path(link_target)):
                        add(
                            "lnk_target_missing",
                            "error",
                            "Shortcut target does not exist",
                            link_target,
                            folder,
                            shortcut,
                            "delete_shortcut",
                        )

            working_dir = str(getattr(shortcut, "working_dir", "") or "").strip()
            if working_dir and _has_unresolved_env_var(working_dir):
                add(
                    "unresolved_env_var",
                    "warn",
                    "Working directory has unresolved environment variable",
                    working_dir,
                    folder,
                    shortcut,
                )
            elif working_dir and not os.path.isdir(_expanded_path(working_dir)):
                add(
                    "missing_working_dir",
                    "warn",
                    "Working directory does not exist",
                    working_dir,
                    folder,
                    shortcut,
                    "clear_working_dir",
                )

            icon_path = _split_icon_location(getattr(shortcut, "icon_path", ""))
            if icon_path and _has_unresolved_env_var(icon_path):
                add(
                    "unresolved_env_var",
                    "warn",
                    "Icon path has unresolved environment variable",
                    icon_path,
                    folder,
                    shortcut,
                )
            elif icon_path and not os.path.exists(_expanded_path(icon_path)):
                fix_action = "refresh_favicon" if shortcut_type == ShortcutType.URL else "clear_icon"
                add("missing_icon", "warn", "Icon path does not exist", icon_path, folder, shortcut, fix_action)

            if shortcut_type == ShortcutType.URL:
                raw_url = str(getattr(shortcut, "url", "") or "").strip()
                prepared_url, error = UrlExecutionMixin._prepare_url(raw_url)
                if error:
                    add("url_invalid", "error", "URL is invalid", error or raw_url, folder, shortcut)
                else:
                    parsed = urlparse(prepared_url)
                    if not parsed.scheme:
                        add("url_invalid", "error", "URL is invalid", prepared_url, folder, shortcut)
                    elif parsed.scheme in ("http", "https") and not icon_path:
                        add(
                            "missing_icon",
                            "warn",
                            "URL icon is missing",
                            prepared_url,
                            folder,
                            shortcut,
                            "refresh_favicon",
                        )

            if shortcut_type == ShortcutType.BATCH_LAUNCH:
                _check_batch_launch(shortcut, folder, shortcut_map, add)

            if shortcut_type == ShortcutType.COMMAND:
                for risk in assess_command_risk(shortcut):
                    add("command_risk", risk.level, "Command risk", risk.message, folder, shortcut)
                command_text = str(getattr(shortcut, "command", "") or "").strip()
                cmd_type = str(getattr(shortcut, "command_type", "cmd") or "cmd")
                if cmd_type == "cmd" and command_text:
                    exe_path = _extract_command_executable(command_text)
                    if exe_path and _has_unresolved_env_var(exe_path):
                        add(
                            "unresolved_env_var",
                            "warn",
                            "Command entry has unresolved environment variable",
                            exe_path,
                            folder,
                            shortcut,
                        )
                    elif exe_path and not os.path.exists(_expanded_path(exe_path)):
                        add(
                            "missing_command_target",
                            "warn",
                            "Command entry file does not exist",
                            exe_path,
                            folder,
                            shortcut,
                        )

    return issues


def _check_batch_launch(shortcut: ShortcutItem, folder, shortcut_map: dict[str, ShortcutItem], add) -> None:
    steps = list(getattr(shortcut, "batch_launch_steps", []) or [])
    if not steps:
        add(
            "batch_launch_empty",
            "warn",
            "Batch launch has no items",
            "Batch launch shortcut has no items.",
            folder,
            shortcut,
        )
        return

    if len(steps) > MAX_CHAIN_STEPS:
        add(
            "batch_launch_too_long",
            "warn",
            "Batch launch has too many items",
            f"Batch launch shortcut has more than {MAX_CHAIN_STEPS} items.",
            folder,
            shortcut,
        )

    for step in steps:
        step_id = str(step.get("shortcut_id") or "").strip() if isinstance(step, dict) else ""
        if not step_id:
            add(
                "batch_launch_step_missing_id",
                "error",
                "Batch launch item has no shortcut",
                "Batch launch item is missing a shortcut id.",
                folder,
                shortcut,
            )
            continue
        target = shortcut_map.get(step_id)
        if target is None:
            add(
                "batch_launch_missing_reference",
                "error",
                "Batch launch item target is missing",
                step_id,
                folder,
                shortcut,
            )
            continue
        if getattr(target, "id", "") == getattr(shortcut, "id", ""):
            add("batch_launch_self_reference", "error", "Batch launch references itself", step_id, folder, shortcut)
        elif _shortcut_type(target) == ShortcutType.BATCH_LAUNCH:
            add(
                "batch_launch_nested",
                "error",
                "Nested chains or batch launches are not supported",
                step_id,
                folder,
                shortcut,
            )


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


@dataclass
class HealthFixPreview:
    issue_id: str
    issue_type: str
    action: str
    shortcut_id: str
    shortcut_name: str
    description: str
    safe: bool  # True = low-risk fix, False = destructive (e.g. delete)


def preview_health_fixes(data_manager, issue_ids: list[str]) -> list[HealthFixPreview]:
    """Dry-run: return preview of what each fix would do, without modifying data."""
    wanted = set(issue_ids or [])
    if not wanted:
        return []

    issues = [issue for issue in check_shortcuts(data_manager.data) if issue.id in wanted and issue.fix_action]
    previews: list[HealthFixPreview] = []
    for issue in issues:
        action = issue.fix_action
        safe = action in ("clear_icon", "clear_working_dir", "disable_folder_sync", "refresh_favicon")
        descriptions = {
            "delete_shortcut": f"Will delete shortcut: {issue.shortcut_name}",
            "clear_icon": f"Will clear icon path for: {issue.shortcut_name}",
            "refresh_favicon": f"Will automatically fetch website icon again for: {issue.shortcut_name}",
            "clear_working_dir": f"Will clear working directory for: {issue.shortcut_name}",
            "disable_folder_sync": f"Will disable folder sync: {issue.folder_name}",
        }
        previews.append(
            HealthFixPreview(
                issue_id=issue.id,
                issue_type=issue.issue_type,
                action=action,
                shortcut_id=issue.shortcut_id,
                shortcut_name=issue.shortcut_name,
                description=descriptions.get(action, f"Apply {action} to {issue.shortcut_name}"),
                safe=safe,
            )
        )
    return previews


def apply_health_fixes(data_manager, issue_ids: list[str]) -> dict:
    """Apply safe automated fixes for selected issue ids."""
    wanted = set(issue_ids or [])
    if not wanted:
        return {"requested": 0, "applied": 0, "failed": 0}

    issues = [issue for issue in check_shortcuts(data_manager.data) if issue.id in wanted and issue.fix_action]
    action_priority = {
        "delete_shortcut": 0,
        "clear_icon": 1,
        "refresh_favicon": 1,
        "clear_working_dir": 1,
        "disable_folder_sync": 1,
    }
    issues.sort(key=lambda issue: action_priority.get(issue.fix_action, 9))
    favicon_results = _refresh_url_favicons_parallel(data_manager, issues)
    applied = 0
    skipped = 0
    failed = 0
    deleted_shortcuts: set[str] = set()
    mark_history = getattr(data_manager, "_mark_history", None)
    if callable(mark_history):
        try:
            mark_history("Shortcut health fixes", f"Applying {len(issues)} selected health fix(es)")
        except Exception as exc:
            logger.debug("标记历史记录失败: %s", exc, exc_info=True)
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
                failed += 1
                continue
            if issue.fix_action == "delete_shortcut":
                items = getattr(folder, "items", None)
                if not isinstance(items, list):
                    failed += 1
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
                if icon_location and not os.path.exists(_expanded_path(icon_location)):
                    shortcut.icon_path = ""
                    applied += 1
                else:
                    skipped += 1
            elif issue.fix_action == "refresh_favicon":
                icon_path = favicon_results.get(issue.id, "")
                if icon_path:
                    shortcut.icon_path = icon_path
                    applied += 1
                else:
                    failed += 1
            elif issue.fix_action == "clear_working_dir":
                wd = str(getattr(shortcut, "working_dir", "") or "").strip()
                if wd and not os.path.isdir(_expanded_path(wd)):
                    shortcut.working_dir = ""
                    applied += 1
                else:
                    skipped += 1
        if applied:
            data_manager.save(immediate=True)
            try:
                from .event_log import log_event

                log_event(
                    "shortcut.health_fix",
                    f"Applied {applied} health fix(es)",
                    {"applied": applied, "skipped": skipped, "failed": failed},
                )
            except Exception as exc:
                logger.debug("记录健康修复事件失败: %s", exc, exc_info=True)

    return {"requested": len(issues), "applied": applied, "skipped": skipped, "failed": failed}


def _refresh_url_favicons_parallel(data_manager, issues: list[HealthIssue]) -> dict[str, str]:
    refresh_issues = [issue for issue in issues if issue.fix_action == "refresh_favicon"]
    if not refresh_issues:
        return {}

    tasks = []
    for issue in refresh_issues:
        _folder, shortcut = data_manager._find_shortcut_with_folder(issue.shortcut_id)
        if not shortcut:
            continue
        raw_url = str(getattr(shortcut, "url", "") or "").strip()
        if raw_url:
            tasks.append((issue.id, raw_url))
    if not tasks:
        return {}

    worker_count = _favicon_refresh_worker_count(len(tasks))
    if worker_count <= 1:
        return {issue_id: path for issue_id, path in (_fetch_favicon_for_url(task) for task in tasks) if path}

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="FaviconRefresh") as executor:
        future_map = {executor.submit(_fetch_favicon_for_url, task): task[0] for task in tasks}
        for future in as_completed(future_map):
            issue_id = future_map[future]
            try:
                _result_issue_id, icon_path = future.result()
            except Exception as exc:
                logger.debug("并发自动获取网址图标失败: %s", exc, exc_info=True)
                continue
            if icon_path:
                results[issue_id] = icon_path
    return results


def _favicon_refresh_worker_count(task_count: int) -> int:
    if task_count <= 1:
        return 1
    return min(MAX_FAVICON_REFRESH_WORKERS, max(2, task_count))


def _fetch_favicon_for_url(task: tuple[str, str]) -> tuple[str, str]:
    issue_id, raw_url = task
    return issue_id, _refresh_url_favicon(raw_url)


def _refresh_url_favicon(raw_url: str) -> str:
    raw_url = str(raw_url or "").strip()
    if not raw_url:
        return ""
    try:
        prepared_url, error = UrlExecutionMixin._prepare_url(raw_url)
        if error:
            return ""
        parsed = urlparse(prepared_url)
        if parsed.scheme not in ("http", "https"):
            return ""
    except Exception as exc:
        logger.debug("准备网址图标刷新 URL 失败: %s", exc, exc_info=True)
        return ""
    try:
        from .favicon_cache import fetch_favicon

        return fetch_favicon(prepared_url, force_refresh=True) or ""
    except Exception as exc:
        logger.debug("自动重新获取网址图标失败: %s", exc, exc_info=True)
        return ""


def _refresh_shortcut_favicon(shortcut: ShortcutItem) -> str:
    if _shortcut_type(shortcut) != ShortcutType.URL:
        return ""
    return _refresh_url_favicon(str(getattr(shortcut, "url", "") or ""))


def _find_folder(data: AppData, folder_id: str):
    for folder in getattr(data, "folders", []) or []:
        if getattr(folder, "id", "") == folder_id:
            return folder
    return None


def save_health_state(state_dir, issues: list[HealthIssue]) -> bool:
    """Save shortcut health scan summary to shortcut_health_state.json."""
    import json
    from datetime import datetime
    from pathlib import Path

    try:
        state_path = Path(state_dir) / "shortcut_health_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        error_count = sum(1 for i in issues if i.severity == "error")
        warn_count = sum(1 for i in issues if i.severity in ("warn", "warning"))
        fixable_count = sum(1 for i in issues if i.fix_action)
        state = {
            "last_scan_at": datetime.now().isoformat(timespec="seconds"),
            "error_count": error_count,
            "warn_count": warn_count,
            "fixable_count": fixable_count,
            "total_issues": len(issues),
        }
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def load_health_state(state_dir) -> dict | None:
    """Load shortcut health scan summary if available."""
    import json
    from pathlib import Path

    try:
        state_path = Path(state_dir) / "shortcut_health_state.json"
        if not state_path.exists():
            return None
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None
