"""Risk classification for command shortcuts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .data_models import ShortcutItem


@dataclass
class CommandRisk:
    level: str
    code: str
    message: str
    requires_confirmation: bool = False

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "requires_confirmation": self.requires_confirmation,
        }


_DANGEROUS_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("delete_tree", re.compile(r"\b(rmdir|rd)\s+/(s|q)\b", re.I), "递归删除目录"),
    ("delete_file", re.compile(r"\b(del|erase)\s+(/f|/q|/s)?\b", re.I), "删除文件"),
    ("format_disk", re.compile(r"\bformat\s+[a-z]:", re.I), "格式化磁盘"),
    ("shutdown", re.compile(r"\bshutdown\s+/(s|r|g|p)\b", re.I), "关机或重启"),
    ("registry_delete", re.compile(r"\breg\s+delete\b", re.I), "删除注册表项"),
    ("powershell_remove", re.compile(r"\b(remove-item|rm)\b.*\b(-recurse|-force)\b", re.I), "PowerShell 强制删除"),
    (
        "powershell_exec_policy",
        re.compile(r"\bset-executionpolicy\b|(?:^|\s)-executionpolicy\s+bypass\b", re.I),
        "修改或绕过 PowerShell 执行策略",
    ),
    ("service_control", re.compile(r"\b(sc|net)\s+(delete|stop|start|config)\b", re.I), "控制系统服务"),
    ("diskpart", re.compile(r"\bdiskpart\b|\bbcdedit\b|\bbootrec\b", re.I), "磁盘或启动配置命令"),
    ("takeown_icacls", re.compile(r"\b(takeown|icacls)\b.*\b(/grant|/reset|/f)\b", re.I), "修改文件所有权或 ACL"),
    (
        "cmd_chain_delete",
        re.compile(r"\bcmd(?:\.exe)?\b.*\s/[ck]\s+.*\b(del|erase|rd|rmdir)\b", re.I),
        "通过 cmd 链式删除",
    ),
    ("taskkill_force", re.compile(r"\btaskkill\b.*\s/f\b", re.I), "强制结束进程"),
]

_CONFIRMATION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("delete_tree", re.compile(r"\b(rmdir|rd)\b(?=[^\r\n]*\s/s\b)(?=[^\r\n]*\s/q\b)", re.I), "递归静默删除目录"),
    ("delete_file", re.compile(r"\b(del|erase)\b(?=[^\r\n]*\s/s\b)(?=[^\r\n]*\s/q\b)", re.I), "递归静默删除文件"),
    ("rm_rf", re.compile(r"\brm\b(?=[^\r\n]*-[A-Za-z]*r)(?=[^\r\n]*-[A-Za-z]*f)", re.I), "rm -rf 删除"),
    (
        "powershell_remove",
        re.compile(r"\b(remove-item|rm)\b(?=[^\r\n]*\b-recurse\b)(?=[^\r\n]*\b-force\b)", re.I),
        "PowerShell 递归强制删除",
    ),
    ("format_disk", re.compile(r"\bformat\s+[a-z]:", re.I), "格式化磁盘"),
    ("diskpart", re.compile(r"\bdiskpart\b|\bbcdedit\b|\bbootrec\b", re.I), "磁盘或启动配置命令"),
    (
        "registry_delete_critical",
        re.compile(
            r"\breg\s+delete\s+"
            r"(?:(?:HKLM|HKEY_LOCAL_MACHINE)\\(?:SYSTEM|SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run)"
            r"|(?:HKCU|HKEY_CURRENT_USER)\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run)",
            re.I,
        ),
        "删除关键注册表项",
    ),
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

    if effective_type == "cmd":
        risks.append(CommandRisk("info", "shell_command", "通过系统 Shell 执行命令"))

    if effective_type == "powershell":
        risks.append(CommandRisk("info", "powershell_command", "PowerShell command execution"))

    if "{{clipboard" in command_text:
        risks.append(CommandRisk("info", "clipboard_variable", "使用剪贴板变量"))

    if "{{selected_text" in command_text:
        risks.append(CommandRisk("info", "selected_text_variable", "使用选中文本变量"))

    if effective_type != "builtin":
        confirmation_codes: set[str] = set()
        for code, pattern, message in _CONFIRMATION_PATTERNS:
            if pattern.search(command_text):
                confirmation_codes.add(code)
                if code not in {danger_code for danger_code, _, _ in _DANGEROUS_PATTERNS}:
                    risks.append(CommandRisk("critical", code, message, requires_confirmation=True))

        for code, pattern, message in _DANGEROUS_PATTERNS:
            if pattern.search(command_text):
                requires_confirmation = code in confirmation_codes
                risks.append(
                    CommandRisk(
                        "critical" if requires_confirmation else "warn",
                        code,
                        message,
                        requires_confirmation=requires_confirmation,
                    )
                )

    return risks
