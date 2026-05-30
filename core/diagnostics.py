"""Diagnostics aggregation and export."""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config_validation import validate_app_data

logger = logging.getLogger(__name__)

MAX_DIAGNOSTIC_TEXT_BYTES = 512 * 1024
MAX_PLUGIN_ERROR_LINES = 200
MAX_SHORTCUT_ISSUES = 50
MAX_EVENTS_LINES = 200

# Per-export redaction counter (reset before each export)
_redaction_lock = threading.Lock()
_redaction_counts: dict[str, int] = {}

# Pre-compiled sensitive patterns for _sanitize_text
_SENSITIVE_PATTERNS = [
    # --token=<value>, --token <value>, --api-key=<value>
    (
        re.compile(
            r"(--(?:token|api[-_]?key|password|passwd|secret|bearer|auth[-_]?token)[=\s]+)\S+",
            re.IGNORECASE,
        ),
        r"\1<REDACTED>",
        "cli_token",
    ),
    # token=<value>, apikey=<value>, password=<value> in query strings or env
    (
        re.compile(
            r"((?:token|apikey|api_key|password|passwd|secret|bearer|authorization)[=:])" r"(['\"]?)([^\s&'\"]{4,})\2",
            re.IGNORECASE,
        ),
        r"\1\2<REDACTED>\2",
        "param_token",
    ),
    # Bearer <token> in Authorization headers
    (re.compile(r"(Bearer\s+)\S{8,}", re.IGNORECASE), r"\1<REDACTED>", "bearer_token"),
    # Basic <base64> in Authorization headers
    (re.compile(r"(Basic\s+)\S{8,}", re.IGNORECASE), r"\1<REDACTED>", "basic_auth"),
    # Header-shaped secrets in logs and JSONL payloads.
    (
        re.compile(r"\b((?:Authorization|Proxy-Authorization|X-Api-Key)\s*:\s*)[^\r\n]+", re.IGNORECASE),
        r"\1<REDACTED>",
        "auth_header",
    ),
    (
        re.compile(r"\b((?:Cookie|Set-Cookie)\s*:\s*)[^\r\n]+", re.IGNORECASE),
        r"\1<REDACTED>",
        "cookie_header",
    ),
    # Additional common query-string or form keys.
    (
        re.compile(
            r"((?:access_token|refresh_token|client_secret|x-api-key|sessionid|session_id)[=:])"
            r"(['\"]?)([^\s&'\"]{4,})\2",
            re.IGNORECASE,
        ),
        r"\1\2<REDACTED>\2",
        "secret_param",
    ),
]


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
    items.append(
        DiagnosticItem(
            "配置文件",
            status if status in ("ok", "warn", "error") else "unknown",
            "配置已加载" if status == "ok" else "配置存在问题",
            "; ".join(map(str, issues)) or f"source={config_status.get('source', '')}",
            "如状态为 error，请从数据设置中恢复备份。",
        )
    )

    recovery = config_status.get("recovery", {}) if isinstance(config_status, dict) else {}
    if isinstance(recovery, dict) and recovery:
        recovery_status = str(recovery.get("status") or "unknown")
        item_status = "ok" if recovery_status == "ok" else "warn"
        if recovery_status == "failed":
            item_status = "error"
        reason = str(recovery.get("reason") or "")
        summary_parts = [recovery_status]
        if reason:
            summary_parts.append(f" - {reason}")
        recovered_from = str(recovery.get("recovered_from") or "")
        if recovered_from:
            summary_parts.append(f" (来源: {recovered_from})")
        action_text = "打开配置历史或导入完整备份进行恢复。" if item_status != "ok" else ""
        items.append(
            DiagnosticItem(
                "配置恢复",
                item_status,
                "".join(summary_parts),
                json.dumps(recovery, ensure_ascii=False),
                action_text,
            )
        )

    try:
        schema_issues = validate_app_data(data_manager.data)
        items.append(
            DiagnosticItem(
                "配置结构",
                "ok" if not schema_issues else "warn",
                "结构校验通过" if not schema_issues else f"发现 {len(schema_issues)} 个结构问题",
                "; ".join(schema_issues),
            )
        )
    except Exception as exc:
        items.append(DiagnosticItem("配置结构", "error", "结构校验失败", str(exc)))

    try:
        from hooks.hooks_wrapper import HooksDLL

        probe = HooksDLL.probe_default()
        hook_status = "ok" if probe.get("loaded") and probe.get("compatible") else "warn"
        summary = probe.get("summary", "") or "hooks.dll 状态未知"
        items.append(
            DiagnosticItem(
                "Hook DLL",
                hook_status,
                summary,
                json.dumps(probe, ensure_ascii=False),
                "如不兼容，请重新构建 hooks.dll。",
            )
        )
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

        items.append(
            DiagnosticItem(
                "快捷方式热键",
                status,
                summary,
                details,
                "可在热键对话框中修改冲突的热键" if conflicts else "",
            )
        )
    except Exception as exc:
        items.append(DiagnosticItem("快捷方式热键", "unknown", "无法检测热键冲突", str(exc)))

    try:
        from .windows_uipi import get_process_elevation_status

        elevation = get_process_elevation_status()
        is_elevated = elevation.get("elevated", False)
        items.append(
            DiagnosticItem(
                "权限状态",
                "ok",
                "管理员运行" if is_elevated else "普通权限运行",
                json.dumps(elevation, ensure_ascii=False),
            )
        )
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
        total_files = icon_stats.get("total_files", 0)
        total_size_mb = icon_stats.get("total_size_mb", 0)
        status = "warn" if total_size_mb > 100 or total_files > 1000 else "ok"
        items.append(
            DiagnosticItem(
                "图标缓存",
                status,
                f"{total_files} 个文件，{total_size_mb} MB",
                json.dumps(icon_stats, ensure_ascii=False),
            )
        )
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
        items.append(
            DiagnosticItem(
                "图标检查",
                status,
                f"ERROR {error_count} / WARN {warn_count} / 其他 {debug_count + info_count} / 可修复 {fixable_count}",
                details,
                "可在系统设置 -> 日志修复 -> 图标检查中执行修复。" if fixable_count else "",
            )
        )
    except Exception as exc:
        items.append(DiagnosticItem("图标检查", "unknown", "无法执行图标检查", str(exc)))

    try:
        from .command_exec import known_shell_execution_entries

        audit_entries = known_shell_execution_entries()
        shell_true_count = sum(1 for entry in audit_entries if entry.get("python_shell_true"))
        items.append(
            DiagnosticItem(
                "命令执行审计",
                "warn" if shell_true_count else "ok",
                f"已登记 {len(audit_entries)} 个 shell 执行入口，其中 shell=True {shell_true_count} 个",
                json.dumps(audit_entries, ensure_ascii=False),
                "新增命令执行入口必须补充审计记录、输入来源和保留 shell 的原因。",
            )
        )
    except Exception as exc:
        items.append(DiagnosticItem("命令执行审计", "unknown", "无法读取命令执行审计表", str(exc)))

    # Cached health state from shortcut_health_window scans
    try:
        from .shortcut_health import load_health_state

        config_dir = getattr(data_manager, "config_dir", None)
        if config_dir:
            cached = load_health_state(config_dir)
            if cached:
                last_scan = cached.get("last_scan_at", "未知")
                cached_errors = cached.get("error_count", 0)
                cached_warns = cached.get("warn_count", 0)
                cached_fixable = cached.get("fixable_count", 0)
                items.append(
                    DiagnosticItem(
                        "健康检查缓存",
                        "error" if cached_errors else ("warn" if cached_warns else "ok"),
                        (
                            f"上次扫描: {last_scan} | ERROR {cached_errors}"
                            f" / WARN {cached_warns} / 可修复 {cached_fixable}"
                        ),
                        json.dumps(cached, ensure_ascii=False),
                        "可在图标检查窗口中重新扫描。",
                    )
                )
    except Exception:
        pass

    try:
        memory_guard = getattr(tray_app, "memory_guard", None)
        if memory_guard:
            memory = memory_guard.get_status()
            mem_status = memory.get("status", "unknown")
            current_mb = memory.get("current_mb", 0)
            summary = f"{current_mb} MB ({mem_status})"
            items.append(
                DiagnosticItem(
                    "内存状态",
                    "warn" if mem_status in ("moderate", "critical") else "ok",
                    summary,
                    json.dumps(memory, ensure_ascii=False),
                )
            )
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
        items.append(
            DiagnosticItem(
                "文件夹同步",
                "warn" if failed else "ok",
                f"{len(sync_status)} 个分类有同步记录，失败 {len(failed)} 个",
                json.dumps(sync_status, ensure_ascii=False),
            )
        )
    except Exception as exc:
        items.append(DiagnosticItem("文件夹同步", "unknown", "无法读取同步状态", str(exc)))

    try:
        log_file = Path(getattr(data_manager, "app_dir", "")) / "error.log"
        recent_errors = _recent_error_lines(log_file)
        items.append(
            DiagnosticItem(
                "最近错误",
                "warn" if recent_errors else "ok",
                f"{len(recent_errors)} 条 ERROR/CRITICAL",
                "\n".join(recent_errors[-20:]),
                str(log_file),
            )
        )
    except Exception as exc:
        items.append(DiagnosticItem("最近错误", "unknown", "无法读取错误日志", str(exc)))

    # Update system status
    try:
        from services.update.session import latest_session_state

        from . import APP_VERSION

        update_root = str(Path(getattr(data_manager, "app_dir", "")) / "downloads" / "updates")
        session = latest_session_state(update_root)
        update_state = _read_json_file(Path(getattr(data_manager, "app_dir", "")) / ".update_state.json") or {}
        if session:
            install_info = session.get("install", {}) if isinstance(session.get("install"), dict) else {}
            install_status = install_info.get("status", "unknown")
            target_version = session.get("version", "")
            pre_backup = install_info.get("pre_install_backup", "")
            session_status = session.get("status", "unknown")

            status_map = {
                "pending": "ok",
                "created": "ok",
                "installed": "ok",
                "first_start_confirmed": "ok",
                "failed": "error",
                "installing": "warn",
            }
            diag_status = status_map.get(session_status, "warn")

            parts = [f"当前版本: {APP_VERSION}"]
            if target_version:
                parts.append(f"目标版本: {target_version}")
            parts.append(f"会话状态: {session_status}")
            if install_status and install_status != "pending":
                parts.append(f"安装状态: {install_status}")
            if pre_backup:
                parts.append(f"安装前备份: {'已创建' if os.path.isfile(pre_backup) else '未找到'}")

            items.append(
                DiagnosticItem(
                    "更新系统",
                    diag_status,
                    " | ".join(parts),
                    json.dumps(session, ensure_ascii=False),
                    "如更新失败，可从安装前备份恢复配置。",
                )
            )
        else:
            check_status = str(update_state.get("last_check_status") or "")
            check_error = str(update_state.get("last_check_error") or "")
            summary = f"当前版本: {APP_VERSION}，无更新会话记录"
            if check_status:
                summary += f"，最近检查: {check_status}"
            items.append(
                DiagnosticItem(
                    "更新系统",
                    "warn" if check_status == "failed" else "ok",
                    summary,
                    json.dumps(update_state, ensure_ascii=False) if update_state else check_error,
                )
            )
    except Exception as exc:
        items.append(DiagnosticItem("更新系统", "unknown", "无法读取更新状态", str(exc)))

    return items


def export_diagnostics_zip(data_manager, export_path: str, tray_app=None, export_level: str = "standard") -> bool:
    """Export diagnostics and recent logs to a zip package.

    export_level: "standard" (default), "full" (more logs), "minimal" (diagnostics.json only).
    """
    _reset_redaction_counts()
    try:
        items = collect_diagnostics(data_manager, tray_app)
        log_dir = Path(getattr(data_manager, "app_dir", ""))
        config_dir = Path(getattr(data_manager, "config_dir", ""))
        logging_disabled = _is_logging_disabled(data_manager)
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "platform": platform.platform(),
            "cwd": os.getcwd(),
            "diagnostics": [item.to_dict() for item in items],
            "config_status": getattr(data_manager, "get_config_status", lambda: {})(),
            "logging_disabled": logging_disabled,
            "export_level": export_level,
        }
        payload = _sanitize_dict(payload)
        with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
            included_files: list[str] = []
            _write_json(zf, included_files, "diagnostics.json", payload)

            if export_level == "minimal":
                # Minimal: only diagnostics.json + manifest
                redaction = get_redaction_counts()
                if redaction:
                    _write_json(zf, included_files, "redaction_report.json", redaction)
                manifest = _build_manifest(payload, included_files, logging_disabled)
                zf.writestr("manifest.json", json.dumps(_sanitize_dict(manifest), ensure_ascii=False, indent=2))
                return True

            recovery_state = _read_json_file(log_dir / "recovery" / "recovery_state.json")
            if recovery_state is not None:
                _write_json(zf, included_files, "recovery_state.json", recovery_state)

            update_state = _read_json_file(log_dir / ".update_state.json")
            if update_state is not None:
                _write_json(zf, included_files, "update_state.json", update_state)
            update_session = _read_latest_update_session(log_dir)
            if update_session is not None:
                _write_json(zf, included_files, "update_session.json", update_session)

            plugin_errors = _read_tail_lines(log_dir / "plugin_errors.jsonl", MAX_PLUGIN_ERROR_LINES)
            if plugin_errors:
                zf.writestr("plugin_errors_tail.jsonl", "\n".join(_sanitize_jsonl_lines(plugin_errors)))
                included_files.append("plugin_errors_tail.jsonl")

            shortcut_summary = _build_shortcut_health_summary(data_manager)
            if shortcut_summary is not None:
                _write_json(zf, included_files, "shortcut_health_summary.json", shortcut_summary)

            # Include events.jsonl (operation timeline)
            events_path = config_dir / "events.jsonl"
            if events_path.exists() and events_path.is_file():
                events_lines = _read_tail_lines(events_path, MAX_EVENTS_LINES)
                if events_lines:
                    zf.writestr("events.jsonl", "\n".join(_sanitize_jsonl_lines(events_lines)))
                    included_files.append("events.jsonl")

            for name in ("error.log", "faulthandler.log", "crash.log"):
                path = log_dir / name
                if path.exists() and path.is_file():
                    zf.writestr(name, _sanitize_text(_read_tail_text(path)))
                    included_files.append(name)

            # Full level: include rotated logs
            if export_level == "full":
                for name in ("error.log.1", "faulthandler.log.1"):
                    path = log_dir / name
                    if path.exists() and path.is_file():
                        zf.writestr(f"logs/{name}", _sanitize_text(_read_tail_text(path)))
                        included_files.append(f"logs/{name}")

            redaction = get_redaction_counts()
            if redaction:
                _write_json(zf, included_files, "redaction_report.json", redaction)

            manifest = _build_manifest(payload, included_files, logging_disabled)
            zf.writestr("manifest.json", json.dumps(_sanitize_dict(manifest), ensure_ascii=False, indent=2))
        return True
    except Exception as exc:
        logger.exception("export diagnostics failed: %s", exc)
        return False


def _build_manifest(payload: dict, included_files: list[str], logging_disabled: bool) -> dict:
    return {
        "schema": 1,
        "generated_at": payload["generated_at"],
        "export_level": payload.get("export_level", "standard"),
        "files": ["manifest.json"] + included_files,
        "limits": {
            "max_text_bytes_per_file": MAX_DIAGNOSTIC_TEXT_BYTES,
            "max_plugin_error_lines": MAX_PLUGIN_ERROR_LINES,
            "max_shortcut_issues": MAX_SHORTCUT_ISSUES,
            "max_events_lines": MAX_EVENTS_LINES,
        },
        "logging_disabled": logging_disabled,
    }


def _recent_error_lines(log_file: Path) -> list[str]:
    if not log_file.exists():
        return []
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace")
        lines = [line for line in text.splitlines() if " - ERROR - " in line or " - CRITICAL - " in line]
        return lines[-200:]
    except Exception:
        return []


def _is_logging_disabled(data_manager) -> bool:
    settings = getattr(getattr(data_manager, "data", None), "settings", None)
    if settings is None:
        return False
    if hasattr(settings, "enable_logging"):
        return not bool(settings.enable_logging)
    return bool(getattr(settings, "disable_logging", False))


def _write_json(zf: zipfile.ZipFile, included_files: list[str], name: str, payload: object) -> None:
    zf.writestr(name, json.dumps(_sanitize_dict(payload), ensure_ascii=False, indent=2))
    included_files.append(name)


def _read_json_file(path: Path) -> object | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        return json.loads(_read_tail_text(path))
    except Exception:
        return None


def _read_latest_update_session(log_dir: Path) -> object | None:
    try:
        from services.update.session import latest_session_state

        state = latest_session_state(log_dir / "downloads" / "updates")
        return state or None
    except Exception:
        return None


def _read_tail_lines(path: Path, max_lines: int) -> list[str]:
    text = _read_tail_text(path)
    if not text:
        return []
    return text.splitlines()[-max(1, int(max_lines)) :]


def _sanitize_jsonl_lines(lines: list[str]) -> list[str]:
    sanitized = []
    for line in lines:
        try:
            payload = json.loads(line)
            sanitized.append(json.dumps(_sanitize_dict(payload), ensure_ascii=False, separators=(",", ":")))
        except Exception:
            sanitized.append(_sanitize_text(line))
    return sanitized


def _build_shortcut_health_summary(data_manager) -> dict | None:
    try:
        from .shortcut_health import check_shortcuts

        issues = check_shortcuts(data_manager.data)
        counts: dict[str, int] = {}
        for issue in issues:
            severity = str(getattr(issue, "severity", "unknown") or "unknown")
            counts[severity] = counts.get(severity, 0) + 1
        return {
            "total": len(issues),
            "counts": counts,
            "fixable": sum(1 for issue in issues if getattr(issue, "fix_action", "")),
            "issues": [issue.to_dict() for issue in issues[:MAX_SHORTCUT_ISSUES]],
            "truncated": len(issues) > MAX_SHORTCUT_ISSUES,
        }
    except Exception as exc:
        return {"error": str(exc)}


def _read_tail_text(path: Path, max_bytes: int = MAX_DIAGNOSTIC_TEXT_BYTES) -> str:
    try:
        if not path.exists() or not path.is_file():
            return ""
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
                prefix = f"[truncated first {size - max_bytes} bytes]\n"
            else:
                prefix = ""
            return prefix + handle.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _reset_redaction_counts() -> None:
    """Reset redaction counters before a new export."""
    with _redaction_lock:
        _redaction_counts.clear()


def _bump_redaction(category: str, count: int = 1) -> None:
    """Increment redaction counter for a category."""
    with _redaction_lock:
        _redaction_counts[category] = _redaction_counts.get(category, 0) + count


def get_redaction_counts() -> dict[str, int]:
    """Return a snapshot of current redaction counters."""
    with _redaction_lock:
        return dict(_redaction_counts)


def _sanitize_text(value: str) -> str:
    """Replace user-specific paths and sensitive tokens with placeholders."""
    result = str(value or "")
    home = os.path.expanduser("~")
    if home and len(home) > 3:
        if home in result:
            _bump_redaction("user_home")
            result = result.replace(home, "<USER_HOME>")
    for var in ("USERPROFILE", "USERNAME", "COMPUTERNAME"):
        val = os.environ.get(var, "")
        if val and len(val) > 2 and val in result:
            _bump_redaction(var.lower())
            result = result.replace(val, f"<{var}>")

    for pattern, replacement, category in _SENSITIVE_PATTERNS:
        matches = pattern.findall(result)
        if matches:
            _bump_redaction(category, len(matches))
            result = pattern.sub(replacement, result)
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
