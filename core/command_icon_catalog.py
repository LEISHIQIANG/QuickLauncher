"""Stable virtual icon assignments for built-in commands."""

from __future__ import annotations

BUILTIN_COMMAND_ICON_PREFIX = "builtin-command:"

BUILTIN_COMMAND_ICON_IDS = frozenset(
    {
        "about",
        "auto-backups",
        "base64",
        "cidr",
        "clean-cache",
        "clean-icons",
        "clip",
        "color",
        "config",
        "config-file",
        "config-history",
        "config-repair",
        "conflict",
        "copy-path",
        "data-dir",
        "diagnostics",
        "dns",
        "env",
        "error-log",
        "explorer",
        "git",
        "god",
        "hash",
        "help",
        "history-dir",
        "hosts",
        "icons-dir",
        "ip",
        "install-dir",
        "json",
        "jwt",
        "log",
        "netdiag",
        "path-audit",
        "pin_off",
        "pin_on",
        "plugin-list",
        "plugin-new",
        "plugin-reload",
        "port",
        "process",
        "qr",
        "quit",
        "reload-hooks",
        "restart",
        "selected",
        "shortcut-health",
        "sysreport",
        "timestamp",
        "tls",
        "topmost",
        "urlencode",
        "uuid",
        "wifi",
    }
)


def normalize_builtin_command_icon_id(command_id: str) -> str:
    """Return the normalized visual icon id for a registered command."""
    normalized = str(command_id or "").strip().lower()
    return normalized if normalized in BUILTIN_COMMAND_ICON_IDS else ""


def builtin_command_icon_path(command_id: str) -> str:
    """Return the immutable virtual icon path for a known built-in command."""
    normalized = normalize_builtin_command_icon_id(command_id)
    if not normalized:
        return ""
    return f"{BUILTIN_COMMAND_ICON_PREFIX}{normalized}"


def builtin_command_id_from_icon_path(icon_path: str) -> str:
    """Extract a known built-in command id from a virtual icon path."""
    text = str(icon_path or "").strip()
    if not text.startswith(BUILTIN_COMMAND_ICON_PREFIX):
        return ""
    command_id = text[len(BUILTIN_COMMAND_ICON_PREFIX) :]
    return normalize_builtin_command_icon_id(command_id)


def is_builtin_command_icon_path(icon_path: str) -> bool:
    """Return whether icon_path references a supported virtual command icon."""
    return bool(builtin_command_id_from_icon_path(icon_path))
