"""Risk classification and audit logging for command shortcuts."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .data_models import ShortcutItem

logger = logging.getLogger(__name__)


@dataclass
class CommandRisk:
    level: str
    code: str
    message: str

    def to_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message}


_DANGEROUS_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("delete_tree", re.compile(r"\b(rmdir|rd)\s+/(s|q)\b", re.I), "递归删除目录"),
    ("delete_file", re.compile(r"\b(del|erase)\s+(/f|/q|/s)?\b", re.I), "删除文件"),
    ("format_disk", re.compile(r"\bformat\s+[a-z]:", re.I), "格式化磁盘"),
    ("shutdown", re.compile(r"\bshutdown\s+/(s|r|g|p)\b", re.I), "关机或重启"),
    ("registry_delete", re.compile(r"\breg\s+delete\b", re.I), "删除注册表项"),
    ("powershell_remove", re.compile(r"\b(remove-item|rm)\b.*\b(-recurse|-force)\b", re.I), "PowerShell 强制删除"),
]


def assess_command_risk(
    shortcut: ShortcutItem,
    command: str | None = None,
    command_type: str | None = None,
) -> list[CommandRisk]:
    """Classify command risk without blocking execution."""
    risks: list[CommandRisk] = []
    command_text = str(command if command is not None else getattr(shortcut, "command", "") or "")
    effective_type = str(
        command_type if command_type is not None else getattr(shortcut, "command_type", "cmd") or "cmd"
    )

    if getattr(shortcut, "run_as_admin", False):
        risks.append(CommandRisk("info", "run_as_admin", "以管理员身份执行"))

    if effective_type == "python" and getattr(shortcut, "python_execution_mode", "") == "legacy_inline":
        risks.append(CommandRisk("warn", "python_inline", "使用进程内 Python 执行"))

    if effective_type == "cmd":
        risks.append(CommandRisk("info", "shell_command", "通过系统 Shell 执行命令"))

    if "{clipboard" in command_text:
        risks.append(CommandRisk("info", "clipboard_variable", "使用剪贴板变量"))

    if "{selected_text" in command_text:
        risks.append(CommandRisk("info", "selected_text_variable", "使用选中文本变量"))

    if effective_type != "builtin":
        for code, pattern, message in _DANGEROUS_PATTERNS:
            if pattern.search(command_text):
                risks.append(CommandRisk("warn", code, message))

    return risks


def audit_command_execution(
    shortcut: ShortcutItem,
    command: str | None = None,
    command_type: str | None = None,
):
    """Write risk audit events to logs only."""
    risks = assess_command_risk(shortcut, command, command_type=command_type)
    name = getattr(shortcut, "name", "") or getattr(shortcut, "id", "") or "<unnamed>"
    if risks:
        log = logger.warning if any(risk.level == "warn" for risk in risks) else logger.info
        log(
            "Command risk audit: shortcut=%s type=%s risks=%s command=%s",
            name,
            command_type if command_type is not None else getattr(shortcut, "command_type", "cmd"),
            [risk.to_dict() for risk in risks],
            command if command is not None else getattr(shortcut, "command", ""),
        )
        return
    logger.info(
        "Command execution audit: shortcut=%s type=%s admin=%s",
        name,
        command_type if command_type is not None else getattr(shortcut, "command_type", "cmd"),
        bool(getattr(shortcut, "run_as_admin", False)),
    )
