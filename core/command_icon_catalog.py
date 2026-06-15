"""Fixed icon assignments for selected high-value built-in commands."""

from __future__ import annotations

BUILTIN_COMMAND_ICON_PREFIX = "builtin-command:"

BUILTIN_COMMAND_ICON_IDS = frozenset(
    {
        "base64",
        "clip",
        "color",
        "config",
        "copy-path",
        "dns",
        "env",
        "git",
        "hash",
        "help",
        "ip",
        "json",
        "jwt",
        "netdiag",
        "port",
        "process",
        "qr",
        "restart",
        "selected",
        "sysreport",
        "timestamp",
        "topmost",
        "urlencode",
        "uuid",
        "wifi",
    }
)


def builtin_command_icon_path(command_id: str) -> str:
    """Return the immutable virtual icon path for a selected built-in command."""
    normalized = str(command_id or "").strip().lower()
    if normalized not in BUILTIN_COMMAND_ICON_IDS:
        return ""
    return f"{BUILTIN_COMMAND_ICON_PREFIX}{normalized}"


def builtin_command_id_from_icon_path(icon_path: str) -> str:
    """Extract a known built-in command id from a virtual icon path."""
    text = str(icon_path or "").strip()
    if not text.startswith(BUILTIN_COMMAND_ICON_PREFIX):
        return ""
    command_id = text[len(BUILTIN_COMMAND_ICON_PREFIX) :].strip().lower()
    return command_id if command_id in BUILTIN_COMMAND_ICON_IDS else ""
