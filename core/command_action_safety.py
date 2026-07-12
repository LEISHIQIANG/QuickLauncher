"""Validation and normalization for command result actions."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from core.command_registry import CommandAction

ALLOWED_ACTION_TYPES = {
    "copy",
    "copy_table",
    "copy_json",
    "open_url",
    "open_file",
    "open_folder",
    "save_text",
    "save_file",
    "save_csv",
    "save_json",
    "rerun",
    "close_qr_server",
}
MAX_ACTIONS = 32
MAX_ACTION_LABEL_CHARS = 80
MAX_ACTION_VALUE_CHARS = 256 * 1024
MAX_ACTION_PAYLOAD_ITEMS = 32
MAX_ACTION_PAYLOAD_VALUE_CHARS = 4096


def sanitize_command_actions(actions: Any) -> list[CommandAction]:
    """Return actions that are safe for UI rendering and execution."""

    if not isinstance(actions, list):
        return []
    sanitized: list[CommandAction] = []
    for action in actions:
        normalized = normalize_command_action(action)
        if normalized is None:
            continue
        sanitized.append(normalized)
        if len(sanitized) >= MAX_ACTIONS:
            break
    return sanitized


def normalize_command_action(action: Any) -> CommandAction | None:
    if isinstance(action, CommandAction):
        candidate = CommandAction(
            type=str(action.type or ""),
            label=str(action.label or ""),
            value=str(action.value or ""),
            enabled=bool(action.enabled),
            danger=bool(action.danger),
            primary=bool(action.primary),
            payload=dict(action.payload or {}) if isinstance(action.payload, dict) else {},
        )
    elif isinstance(action, dict):
        candidate = CommandAction(
            type=str(action.get("type") or ""),
            label=str(action.get("label") or ""),
            value=str(action.get("value") or ""),
            enabled=bool(action.get("enabled", True)),
            danger=bool(action.get("danger", False)),
            primary=bool(action.get("primary", False)),
            payload=dict(action.get("payload") or {}) if isinstance(action.get("payload"), dict) else {},
        )
    elif hasattr(action, "type") and hasattr(action, "label"):
        # SDK CommandAction (extensions.sdk.CommandAction) — same fields,
        # different class; convert via attribute access.
        candidate = CommandAction(
            type=str(getattr(action, "type", "") or ""),
            label=str(getattr(action, "label", "") or ""),
            value=str(getattr(action, "value", "") or ""),
            enabled=bool(getattr(action, "enabled", True)),
            danger=bool(getattr(action, "danger", False)),
            primary=bool(getattr(action, "primary", False)),
            payload=(
                dict(getattr(action, "payload", None) or {})
                if isinstance(getattr(action, "payload", None), dict)
                else {}
            ),
        )
    else:
        return None

    candidate.type = candidate.type.strip().lower()
    if candidate.type == "create_shortcut":
        candidate.type = "open_url"
    if candidate.type not in ALLOWED_ACTION_TYPES:
        return None

    candidate.label = _limit_text(candidate.label.strip(), MAX_ACTION_LABEL_CHARS)
    candidate.value = _limit_text(candidate.value, MAX_ACTION_VALUE_CHARS)
    candidate.payload = _safe_payload(candidate.payload)

    if candidate.type == "open_url" and not is_safe_action_url(candidate.value):
        return None
    if candidate.type == "open_file" and not is_safe_action_file(candidate.value):
        return None
    if candidate.type == "open_folder" and not is_safe_action_folder(candidate.value):
        return None
    if candidate.type == "save_file" and not is_safe_action_file(candidate.value):
        return None
    return candidate


def is_safe_action_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def is_safe_action_file(value: str) -> bool:
    path = str(value or "").strip()
    return bool(path) and "\x00" not in path and os.path.isfile(path)


def is_safe_action_folder(value: str) -> bool:
    path = str(value or "").strip()
    return bool(path) and "\x00" not in path and os.path.isdir(path)


def _limit_text(value: str, max_chars: int) -> str:
    text = str(value or "")
    return text[:max_chars] if len(text) > max_chars else text


def _safe_payload(payload: dict[str, Any]) -> dict[str, str]:
    safe: dict[str, str] = {}
    if not isinstance(payload, dict):
        return safe
    for key, value in payload.items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        safe[key_text[:MAX_ACTION_LABEL_CHARS]] = _limit_text(str(value or ""), MAX_ACTION_PAYLOAD_VALUE_CHARS)
        if len(safe) >= MAX_ACTION_PAYLOAD_ITEMS:
            break
    return safe
