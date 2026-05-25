"""Diagnostics aggregation and export."""

from __future__ import annotations

import json
import logging
import os
import platform
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config_validation import validate_app_data

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticItem:
    title: str
    status: str
    summary: str
    details: str = ""
    action: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "status": self.status,
            "summary": self.summary,
            "details": self.details,
            "action": self.action,
        }


def collect_diagnostics(data_manager, tray_app=None) -> list[DiagnosticItem]:
    """Collect user-facing diagnostics without mutating state."""
    items: list[DiagnosticItem] = []

    config_status = getattr(data_manager, "get_config_status", lambda: {})()
    status = config_status.get("status", "unknown")
    issues = config_status.get("issues", [])
    items.append(DiagnosticItem(
        "配置文件",
        status if status in ("ok", "warn", "error") else "unknown",
        "配置已加载" if status == "ok" else "配置存在问题",
        "; ".join(map(str, issues)) or f"source={config_status.get('source', '')}",
        "如状态为 error，请从数据设置中恢复备份。",
    ))

    try:
        schema_issues = validate_app_data(data_manager.data)
        items.append(DiagnosticItem(
            "配置结构",
            "ok" if not schema_issues else "warn",
            "结构校验通过" if not schema_issues else f"发现 {len(schema_issues)} 个结构问题",
            "; ".join(schema_issues),
        ))
    except Exception as exc:
        items.append(DiagnosticItem("配置结构", "error", "结构校验失败", str(exc)))

    try:
        from hooks.hooks_wrapper import HooksDLL

        probe = HooksDLL.probe_default()
        hook_status = "ok" if probe.get("loaded") and probe.get("compatible") else "warn"
        summary = probe.get("summary", "") or "hooks.dll 状态未知"
        items.append(DiagnosticItem(
            "Hook DLL",
            hook_status,
            summary,
            json.dumps(probe, ensure_ascii=False),
            "如不兼容，请重新构建 hooks.dll。",
        ))
    except Exception as exc:
        items.append(DiagnosticItem("Hook DLL", "error", "无法检测 hooks.dll", str(exc)))

    try:
        from .hotkey_conflict_checker import check_conflict, normalize_hotkey

        hotkey_map = {}
        conflicts = []

        for folder in getattr(data_manager.data, "folders", []) or []:
            for shortcut in getattr(folder, "items", []) or []:
                hotkey = str(getattr(shortcut, "hotkey", "") or "").strip()
                if not hotkey:
                    continue

                normalized = normalize_hotkey(hotkey)
                name = getattr(shortcut, "name", "")

                # 检查与系统热键冲突
                is_conflict, conflict_desc = check_conflict(hotkey)
                if is_conflict:
                    conflicts.append(f"{name}: {conflict_desc}")

                # 检查快捷方式之间的重复
                if normalized in hotkey_map:
                    conflicts.append(f"{name} 与 {hotkey_map[normalized]} 热键重复: {normalized}")
                else:
                    hotkey_map[normalized] = name

        status = "error" if conflicts else "ok"
        summary = f"检测到 {len(conflicts)} 个冲突" if conflicts else f"无冲突，共 {len(hotkey_map)} 个热键"
        details = "\n".join(conflicts[:20]) if conflicts else f"已配置热键的快捷方式: {len(hotkey_map)} 个"

        items.append(DiagnosticItem(
            "快捷方式热键",
            status,
            summary,
            details,
            "可在热键对话框中修改冲突的热键" if conflicts else "",
        ))
    except Exception as exc:
        items.append(DiagnosticItem("快捷方式热键", "unknown", "无法检测热键冲突", str(exc)))

    try:
        from .windows_uipi import get_process_elevation_status

        elevation = get_process_elevation_status()
        is_elevated = elevation.get("elevated", False)
        items.append(DiagnosticItem(
            "权限状态",
            "ok",
            "管理员运行" if is_elevated else "普通权限运行",
            json.dumps(elevation, ensure_ascii=False),
        ))
    except Exception as exc:
        items.append(DiagnosticItem("权限状态", "unknown", "无法读取权限状态", str(exc)))

    try:
        from .auto_start_manager import get_auto_start_check_result

        enabled, reason = get_auto_start_check_result()
        settings = data_manager.get_settings()
        configured = bool(getattr(settings, "auto_start", False)) if settings else False
        state = "ok" if enabled == configured else "warn"
        items.append(DiagnosticItem("开机启动", state, f"配置={configured}, 任务={enabled}", reason))
    except Exception as exc:
        items.append(DiagnosticItem("开机启动", "unknown", "无法检测开机启动", str(exc)))

    try:
        icon_stats = data_manager.get_icon_cache_stats()
        total_files = icon_stats.get('total_files', 0)
        total_size_mb = icon_stats.get('total_size_mb', 0)
        status = "warn" if total_size_mb > 100 or total_files > 1000 else "ok"
        items.append(DiagnosticItem("图标缓存", status, f"{total_files} 个文件，{total_size_mb} MB", json.dumps(icon_stats, ensure_ascii=False)))
    except Exception as exc:
        items.append(DiagnosticItem("图标缓存", "unknown", "无法读取图标缓存", str(exc)))

    try:
        from .shortcut_health import check_shortcuts

        health_issues = check_shortcuts(data_manager.data)
        error_count = sum(1 for issue in health_issues if issue.severity == "error")
        warn_count = sum(1 for issue in health_issues if issue.severity == "warn")
        debug_count = sum(1 for issue in health_issues if issue.severity == "debug")
        info_count = sum(1 for issue in health_issues if issue.severity == "info")
        fixable_count = sum(1 for issue in health_issues if issue.fix_action)
        status = "error" if error_count else ("warn" if warn_count else "ok")
        important_issues = [issue for issue in health_issues if issue.severity in ("error", "warn")]
        details = "\n".join(
            f"[{issue.severity.upper()}] {issue.title} - {issue.shortcut_name or issue.folder_name}"
            for issue in important_issues[:20]
        )
        if not details and (debug_count or info_count):
            details = f"无严重问题，仅有 {debug_count} 个调试信息和 {info_count} 个提示信息"
        items.append(DiagnosticItem(
            "图标检查",
            status,
            f"ERROR {error_count} / WARN {warn_count} / 其他 {debug_count + info_count} / 可修复 {fixable_count}",
            details,
            "可在系统设置 -> 日志修复 -> 图标检查中执行修复。" if fixable_count else "",
        ))
    except Exception as exc:
        items.append(DiagnosticItem("图标检查", "unknown", "无法执行图标检查", str(exc)))

    try:
        memory_guard = getattr(tray_app, "memory_guard", None)
        if memory_guard:
            memory = memory_guard.get_status()
            mem_status = memory.get("status", "unknown")
            current_mb = memory.get("current_mb", 0)
            summary = f"{current_mb} MB ({mem_status})"
            items.append(DiagnosticItem("内存状态", "warn" if mem_status in ("moderate", "critical") else "ok", summary, json.dumps(memory, ensure_ascii=False)))
        else:
            items.append(DiagnosticItem("内存状态", "unknown", "内存监控未启用", "memory_guard 未初始化"))
    except Exception as exc:
        items.append(DiagnosticItem("内存状态", "unknown", "无法读取内存状态", str(exc)))

    try:
        history = getattr(data_manager, "history_manager", None)
        if history is None:
            items.append(DiagnosticItem("配置历史", "unknown", "历史管理器未启用", "history_manager 未初始化"))
        else:
            count = len(history.list_snapshots())
            status = "warn" if count == 0 else "ok"
            items.append(DiagnosticItem("配置历史", status, f"已保存 {count} 个快照"))
    except Exception as exc:
        items.append(DiagnosticItem("配置历史", "unknown", "无法读取配置历史", str(exc)))

    try:
        from .folder_sync import get_folder_sync_status

        sync_status = get_folder_sync_status()
        failed = [v for v in sync_status.values() if not v.get("ok")]
        items.append(DiagnosticItem(
            "文件夹同步",
            "warn" if failed else "ok",
            f"{len(sync_status)} 个分类有同步记录，失败 {len(failed)} 个",
            json.dumps(sync_status, ensure_ascii=False),
        ))
    except Exception as exc:
        items.append(DiagnosticItem("文件夹同步", "unknown", "无法读取同步状态", str(exc)))

    try:
        log_file = Path(getattr(data_manager, "app_dir", "")) / "error.log"
        recent_errors = _recent_error_lines(log_file)
        items.append(DiagnosticItem(
            "最近错误",
            "warn" if recent_errors else "ok",
            f"{len(recent_errors)} 条 ERROR/CRITICAL",
            "\n".join(recent_errors[-20:]),
            str(log_file),
        ))
    except Exception as exc:
        items.append(DiagnosticItem("最近错误", "unknown", "无法读取错误日志", str(exc)))
    return items


def export_diagnostics_zip(data_manager, export_path: str, tray_app=None) -> bool:
    """Export diagnostics and recent logs to a zip package."""
    try:
        items = collect_diagnostics(data_manager, tray_app)
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "platform": platform.platform(),
            "cwd": os.getcwd(),
            "diagnostics": [item.to_dict() for item in items],
            "config_status": getattr(data_manager, "get_config_status", lambda: {})(),
        }
        payload = _sanitize_dict(payload)
        with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("diagnostics.json", json.dumps(payload, ensure_ascii=False, indent=2))
            log_dir = Path(getattr(data_manager, "app_dir", ""))
            for name in ("error.log", "faulthandler.log"):
                path = log_dir / name
                if path.exists() and path.is_file():
                    zf.write(path, name)
        return True
    except Exception as exc:
        logger.exception("export diagnostics failed: %s", exc)
        return False


def _recent_error_lines(log_file: Path) -> list[str]:
    if not log_file.exists():
        return []
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace")
        lines = [line for line in text.splitlines() if " - ERROR - " in line or " - CRITICAL - " in line]
        return lines[-200:]
    except Exception:
        return []


def _sanitize_text(value: str) -> str:
    """Replace user-specific paths with '<USER_HOME>' placeholder."""
    result = str(value or "")
    home = os.path.expanduser("~")
    if home and len(home) > 3:
        result = result.replace(home, "<USER_HOME>")
    for var in ("USERPROFILE", "USERNAME", "COMPUTERNAME"):
        val = os.environ.get(var, "")
        if val and len(val) > 2:
            result = result.replace(val, f"<{var}>")
    return result


def _sanitize_dict(data: object) -> object:
    """Recursively sanitize sensitive values in nested structures."""
    if isinstance(data, dict):
        return {k: _sanitize_dict(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_sanitize_dict(item) for item in data]
    if isinstance(data, str):
        return _sanitize_text(data)
    return data
