"""Command profile helpers shared by command execution paths."""

from __future__ import annotations

from ..data_models import ShortcutItem
from .runtime import normalize_command_type


def command_param_defs(shortcut: ShortcutItem) -> list[dict]:
    try:
        return ShortcutItem._normalize_command_params(getattr(shortcut, "command_params", []))
    except Exception:
        return []


def command_param_values(shortcut: ShortcutItem) -> dict[str, str]:
    values = {}
    for param in command_param_defs(shortcut):
        values[param["name"]] = str(param.get("default") or "")
    runtime = getattr(shortcut, "_runtime_param_values", None)
    if isinstance(runtime, dict):
        values.update({str(k): str(v) for k, v in runtime.items()})
    return values


def merge_runtime_env(shortcut: ShortcutItem, base_env: dict | None) -> dict:
    env = dict(base_env or {})
    command_env = getattr(shortcut, "command_env", {}) or {}
    if isinstance(command_env, str):
        command_env = ShortcutItem._normalize_command_env(command_env)
    if isinstance(command_env, dict):
        for key, value in command_env.items():
            key = str(key or "").strip()
            if key:
                env[key] = str(value)
    return env


def command_panel_size(shortcut: ShortcutItem) -> str:
    size = str(getattr(shortcut, "command_panel_size", "medium") or "medium").lower().strip()
    return size if size in ("small", "medium", "large") else "medium"


def effective_command_type(command_type: str | None) -> str:
    return normalize_command_type(command_type)
