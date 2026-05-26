"""Variable expansion helpers for command shortcuts."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional

_MAX_EXTERNAL_INPUT_BYTES = 1 * 1024 * 1024


def _sanitize_external_input(value: str) -> str:
    if not value:
        return ""
    if "\0" in value:
        value = value.replace("\0", "")
    encoded = value.encode("utf-8", errors="surrogateescape")
    if len(encoded) > _MAX_EXTERNAL_INPUT_BYTES:
        encoded = encoded[:_MAX_EXTERNAL_INPUT_BYTES]
        value = encoded.decode("utf-8", errors="replace")
    return value


class CommandVariableError(ValueError):
    """Raised when a command variable cannot be resolved."""


_TOKEN_RE = re.compile(r"(?<!\{)\{([^{}\r\n]+)\}(?!\})")
_VALUE_ONLY_VARIABLES = {"clipboard", "selected_text", "date", "time", "app_dir", "config_dir", "input"}
_EXTERNAL_INPUT_VARIABLES = {"clipboard", "selected_text", "input"}


def quote_windows_arg(value: str) -> str:
    """Quote one value so it is safe as a single Windows command argument."""
    return subprocess.list2cmdline([value or ""])


def get_app_dir() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).parent)
    return str(Path(__file__).resolve().parent.parent)


def get_config_dir() -> str:
    return os.path.join(get_app_dir(), "config")


def read_clipboard_text() -> str:
    """Read clipboard text without requiring Qt main-thread access."""
    try:
        import win32clipboard
        import win32con

        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                return data or ""
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_TEXT):
                data = win32clipboard.GetClipboardData(win32con.CF_TEXT)
                if isinstance(data, (bytes, bytearray)):
                    try:
                        return data.decode("mbcs", errors="replace")
                    except Exception:
                        return data.decode(errors="replace")
                return data or ""
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass
    return ""


def collect_input_prompts(text: str) -> list[str]:
    """Return unique prompts used by {input} variables in command text."""
    prompts: list[str] = []
    seen = set()
    for match in _TOKEN_RE.finditer(text or ""):
        raw, _ = _split_spec(match.group(1).strip())
        if raw == "input":
            prompt = ""
        elif raw.startswith("input:"):
            prompt = raw[6:].strip()
        else:
            continue
        if prompt not in seen:
            seen.add(prompt)
            prompts.append(prompt)
    return prompts


def should_expand_command_variables(command_type: str, enabled: Optional[bool]) -> bool:
    """Return whether a command shortcut should expand template variables."""
    if command_type == "builtin":
        return False
    if enabled is None:
        return False
    return bool(enabled)


def find_unquoted_external_command_variables(text: str) -> list[str]:
    """Return external input variables that are unsafe for shell command expansion."""
    unsafe: list[str] = []
    seen = set()
    for match in _TOKEN_RE.finditer(text or ""):
        spec = match.group(1).strip()
        base, should_quote = _split_spec(spec)
        root = base.split(":", 1)[0]
        is_external = root in _EXTERNAL_INPUT_VARIABLES or base.startswith("param:") or base.startswith("chain:")
        if is_external and not should_quote and spec not in seen:
            seen.add(spec)
            unsafe.append(spec)
    return unsafe


def is_value_only_variable_command(text: str) -> bool:
    """Return True when text is only a value placeholder, not an executable command."""
    value = (text or "").strip()
    if not value:
        return False
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    match = _TOKEN_RE.fullmatch(value)
    if not match:
        return False
    base, _ = _split_spec(match.group(1).strip())
    return base in _VALUE_ONLY_VARIABLES or base.startswith("input:")


def resolve_command_variables(
    text: str,
    *,
    input_values: Optional[Dict[str, str]] = None,
    param_values: Optional[Dict[str, str]] = None,
    chain_values: Optional[Dict[str, str]] = None,
    selected_text_provider: Optional[Callable[[], str]] = None,
    clipboard_provider: Optional[Callable[[], str]] = None,
    app_dir: Optional[str] = None,
    config_dir: Optional[str] = None,
    strict_unknown: bool = True,
) -> str:
    """Expand supported command variables in text.

    Double braces are preserved as literal braces, e.g. "{{date}}" becomes "{date}".
    """
    if not text:
        return text

    left_guard = "\0QL_LEFT_BRACE\0"
    right_guard = "\0QL_RIGHT_BRACE\0"
    guarded = text.replace("{{", left_guard).replace("}}", right_guard)
    now = datetime.now()
    inputs = input_values or {}
    params = param_values or {}
    chain = chain_values or {}
    clipboard_reader = clipboard_provider or read_clipboard_text

    def repl(match: re.Match) -> str:
        spec = match.group(1).strip()
        base, should_quote = _split_spec(spec)

        if base == "clipboard":
            value = _sanitize_external_input(clipboard_reader())
        elif base == "selected_text":
            if not selected_text_provider:
                raise CommandVariableError("{selected_text} 需要在窗口关闭后触发模式下使用")
            value = _sanitize_external_input(selected_text_provider())
        elif base == "date":
            value = now.strftime("%Y-%m-%d")
        elif base == "time":
            value = now.strftime("%H:%M:%S")
        elif base == "app_dir":
            value = app_dir if app_dir is not None else get_app_dir()
        elif base == "config_dir":
            value = config_dir if config_dir is not None else get_config_dir()
        elif base == "input":
            value = _sanitize_external_input(_lookup_input_value(inputs, ""))
        elif base.startswith("input:"):
            prompt = base[6:].strip()
            value = _sanitize_external_input(_lookup_input_value(inputs, prompt))
        elif base.startswith("param:"):
            name = base[6:].strip()
            if not name:
                raise CommandVariableError(f"变量名称无效: {{{spec}}}")
            value = _sanitize_external_input(_lookup_named_value(params, name, "参数"))
        elif base.startswith("chain:"):
            name = base[6:].strip()
            if not name:
                raise CommandVariableError(f"变量名称无效: {{{spec}}}")
            value = _sanitize_external_input(_lookup_named_value(chain, name, "动作链变量"))
        else:
            if not strict_unknown:
                return match.group(0)
            raise CommandVariableError(f"未知变量: {{{spec}}}")

        return quote_windows_arg(value) if should_quote else value

    resolved = _TOKEN_RE.sub(repl, guarded)
    return resolved.replace(left_guard, "{").replace(right_guard, "}")


def _split_spec(spec: str) -> tuple[str, bool]:
    if spec.endswith(":q"):
        return spec[:-2].strip(), True
    return spec, False


def _lookup_named_value(values: Dict[str, str], name: str, label: str) -> str:
    if name in values:
        return values[name]
    raise CommandVariableError(f"缺少{label}: {name}")


def _lookup_input_value(input_values: Dict[str, str], prompt: str) -> str:
    if prompt in input_values:
        return input_values[prompt]
    if not prompt and "input" in input_values:
        return input_values["input"]
    label = prompt or "输入内容"
    raise CommandVariableError(f"缺少运行时输入: {label}")
