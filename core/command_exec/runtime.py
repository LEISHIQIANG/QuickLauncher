"""Command runtime normalization helpers."""

from __future__ import annotations

SUPPORTED_COMMAND_TYPES = frozenset({"cmd", "powershell", "python", "bash", "builtin"})

COMMAND_TYPE_ALIASES = {
    "command": "cmd",
    "shell": "cmd",
    "bat": "cmd",
    "batch": "cmd",
    "ps": "powershell",
    "pwsh": "powershell",
    "python3": "python",
    "py": "python",
    "git-bash": "bash",
    "gitbash": "bash",
    "sh": "bash",
}


def normalize_command_type(command_type: str | None) -> str:
    value = str(command_type or "cmd").strip().lower()
    return COMMAND_TYPE_ALIASES.get(value, value or "cmd")


def is_supported_command_type(command_type: str | None) -> bool:
    return normalize_command_type(command_type) in SUPPORTED_COMMAND_TYPES
