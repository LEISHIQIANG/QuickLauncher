"""Unified execution and audit for command result actions."""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.command_action_safety import normalize_command_action
from core.command_registry import CommandAction
from infrastructure.process import runtime as process_runtime

logger = logging.getLogger(__name__)

SaveDialog = Callable[[Any, str, str, str], tuple[str, str]]


@dataclass
class ActionExecutionContext:
    source: str = ""
    parent: Any = None
    set_clipboard_text: Callable[[str], None] | None = None
    save_file_dialog: SaveDialog | None = None
    rerun_callback: Callable[[], None] | None = None


def execute_command_action(action: CommandAction | dict | Any, context: ActionExecutionContext | None = None) -> bool:
    """Execute a sanitized command-result action through one audited path."""

    context = context or ActionExecutionContext()
    normalized = normalize_command_action(action)
    if normalized is None or not getattr(normalized, "enabled", True):
        return False
    ok = False
    error = ""
    try:
        action_type = normalized.type
        if action_type in {"copy", "copy_table", "copy_json"}:
            if not normalized.value:
                return False
            _set_clipboard(context, normalized.value)
        elif action_type == "open_url":
            _open_shell_target(normalized.value)
        elif action_type in {"open_file", "open_folder"}:
            _open_path(normalized.value)
        elif action_type == "save_text":
            _save_text(context, normalized.value, "保存文本", "", "文本文件 (*.txt);;所有文件 (*)", "utf-8")
        elif action_type == "save_csv":
            _save_text(
                context,
                normalized.value,
                "保存 CSV",
                "command-result.csv",
                "CSV 文件 (*.csv);;所有文件 (*)",
                "utf-8-sig",
            )
        elif action_type == "save_json":
            _save_text(
                context,
                normalized.value,
                "保存 JSON",
                "command-result.json",
                "JSON 文件 (*.json);;所有文件 (*)",
                "utf-8",
            )
        elif action_type == "save_file":
            _save_file(context, normalized.value)
        elif action_type == "rerun":
            if context.rerun_callback is None:
                return False
            context.rerun_callback()
        elif action_type == "close_qr_server":
            from core.commands import stop_qr_file_server

            stop_qr_file_server(int(normalized.value))
        else:
            return False
        ok = True
        return True
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        error = str(exc)
        logger.warning("执行命令结果动作失败: %s", exc, exc_info=True)
        return False
    finally:
        _audit_action(normalized, context, ok=ok, error=error)


def _set_clipboard(context: ActionExecutionContext, text: str) -> None:
    if context.set_clipboard_text is not None:
        context.set_clipboard_text(text)
        return
    from qt_compat import QApplication

    QApplication.clipboard().setText(text)  # type: ignore[unused-ignore, union-attr]


def _save_text(
    context: ActionExecutionContext,
    text: str,
    title: str,
    default_name: str,
    file_filter: str,
    encoding: str,
) -> None:
    path = _get_save_path(context, title, default_name, file_filter)
    if not path:
        return
    with open(path, "w", encoding=encoding, newline="" if encoding == "utf-8-sig" else None) as handle:
        handle.write(text)


def _save_file(context: ActionExecutionContext, src_path: str) -> None:
    source = Path(src_path)
    default_name = source.name if source.is_file() else "command-result"
    path = _get_save_path(context, "保存文件", default_name, "所有文件 (*)")
    if path and source.is_file():
        shutil.copy2(source, path)


def _get_save_path(context: ActionExecutionContext, title: str, default_name: str, file_filter: str) -> str:
    if context.save_file_dialog is None:
        raise RuntimeError("save file dialog is not configured")
    path, _ = context.save_file_dialog(context.parent, title, default_name, file_filter)
    return str(path or "")


def _open_path(path: str) -> None:
    if os.name == "nt":
        _open_shell_target(path)
        return
    process_runtime.popen(["explorer", path])


def _open_shell_target(target: str) -> None:
    from core.shortcut_executor import ShortcutExecutor

    launched, error = ShortcutExecutor._launch_with_privilege(target, run_as_admin=False)
    if not launched:
        raise OSError(error or f"failed to open target: {target}")


def _audit_action(action: CommandAction, context: ActionExecutionContext, *, ok: bool, error: str = "") -> None:
    try:
        from core.event_log import log_event

        log_event(
            "command.action",
            f"Command action {action.type} {'succeeded' if ok else 'failed'}",
            {
                "source": context.source,
                "type": action.type,
                "label": action.label,
                "value": _redact_value(action),
                "ok": ok,
                "error": error,
            },
        )
    except (ImportError, RuntimeError, TypeError, ValueError):
        logger.debug("记录命令结果动作审计失败", exc_info=True)


def _redact_value(action: CommandAction) -> str:
    value = str(action.value or "")
    if action.type in {"copy", "copy_table", "copy_json", "save_text", "save_csv", "save_json"}:
        return f"<{len(value)} chars>"
    return value[:512]
