"""Helpers for command profile text fields."""

import json

from core import ShortcutItem


def parse_command_params_text(text: str) -> list[dict]:
    params = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                params.append(raw)
            continue
        parts = [part.strip() for part in line.split(",", 4)]
        while len(parts) < 5:
            parts.append("")
        name, param_type, required, default, choices = parts
        if not name:
            continue
        param_type = (param_type or "text").lower()
        if param_type not in ("text", "choice", "bool", "file", "folder", "number", "password", "textarea"):
            param_type = "text"
        params.append(
            {
                "name": name,
                "type": param_type,
                "required": required.lower() in ("1", "true", "yes", "on", "required", "必填"),
                "default": default,
                "choices": [choice.strip() for choice in choices.split("|") if choice.strip()],
                "sensitive": False,
            }
        )
    return ShortcutItem._normalize_command_params(params)


def format_command_params(params) -> str:
    lines = []
    for param in ShortcutItem._normalize_command_params(params):
        has_extra = (
            any(param.get(key) for key in ("label", "placeholder", "help", "source", "validator", "pattern", "min_value", "max_value"))
            or bool(param.get("multiline"))
            or bool(param.get("advanced"))
            or bool(param.get("sensitive"))
            or param.get("remember") is False
            or param.get("type") in ("number", "password", "textarea")
        )
        if has_extra:
            lines.append(json.dumps(param, ensure_ascii=False, sort_keys=True))
            continue
        choices = "|".join(str(choice) for choice in param.get("choices", []))
        lines.append(
            ",".join(
                [
                    param.get("name", ""),
                    param.get("type", "text"),
                    "true" if param.get("required") else "false",
                    str(param.get("default", "")),
                    choices,
                ]
            )
        )
    return "\n".join(lines)


def parse_command_env_text(text: str) -> dict:
    return ShortcutItem._normalize_command_env(text)


def format_command_env(env: dict) -> str:
    if not isinstance(env, dict):
        return ""
    return "\n".join(f"{key}={value}" for key, value in env.items() if str(key).strip())
