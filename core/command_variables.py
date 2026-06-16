"""Variable expansion helpers for command shortcuts."""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import socket
import subprocess
import urllib.request
from collections.abc import Callable
from datetime import datetime

from core.network_security import read_limited_response, safe_urlopen
from runtime_paths import app_root

logger = logging.getLogger(__name__)

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


_TOKEN_RE = re.compile(r"(?<!\{)\{\{([^{}\r\n]+)\}\}(?!\})")
_LEGACY_TOKEN_RE = re.compile(r"(?<!\{)\{([^{}\r\n]+)\}(?!\})")
_ESCAPED_LEFT = "\0QL_ESCAPED_LEFT\0"
_ESCAPED_RIGHT = "\0QL_ESCAPED_RIGHT\0"
_VALUE_ONLY_VARIABLES = {
    "clipboard",
    "selected_text",
    "selected_file",
    "selected_file_name",
    "selected_file_dir",
    "selected_files",
    "date",
    "time",
    "app_dir",
    "config_dir",
    "input",
    "lan_ip",
    "wan_ip",
}
_EXTERNAL_INPUT_VARIABLES = {
    "clipboard",
    "selected_text",
    "selected_file",
    "selected_file_name",
    "selected_file_dir",
    "selected_files",
    "input",
}


def _guard_escaped_double_braces(text: str) -> str:
    return (text or "").replace("{{{{", _ESCAPED_LEFT).replace("}}}}", _ESCAPED_RIGHT)


def _restore_escaped_double_braces(text: str) -> str:
    return (text or "").replace(_ESCAPED_LEFT, "{{").replace(_ESCAPED_RIGHT, "}}")


def _is_known_variable_spec(spec: str, *, include_url: bool = False) -> bool:
    base, _ = _split_spec((spec or "").strip())
    base_key = base.lower()
    if base_key in _VALUE_ONLY_VARIABLES:
        return True
    if base_key.startswith("input:") and base[6:].strip():
        return True
    if base_key.startswith("param:") and base[6:].strip():
        return True
    if base_key.startswith("chain:") and base[6:].strip():
        return True
    return include_url and base_key == "url"


def find_unknown_variable_specs(text: str, *, include_url: bool = False) -> list[str]:
    """Return unique double-brace variable specs that are not supported."""
    unknown: list[str] = []
    seen: set[str] = set()
    guarded = _guard_escaped_double_braces(text or "")
    for match in _TOKEN_RE.finditer(guarded):
        spec = match.group(1).strip()
        if _is_known_variable_spec(spec, include_url=include_url):
            continue
        if spec not in seen:
            seen.add(spec)
            unknown.append(spec)
    return unknown


def uses_selected_file_variables(text: str) -> bool:
    """Return whether text contains an active single- or multi-file variable."""
    guarded = _guard_escaped_double_braces(text or "")
    for match in _TOKEN_RE.finditer(guarded):
        base, _ = _split_spec(match.group(1).strip())
        if base.lower() in {"selected_file", "selected_file_name", "selected_file_dir", "selected_files"}:
            return True
    return False


def migrate_legacy_variable_syntax(text: str, *, include_url: bool = False) -> str:
    """Convert whitelisted legacy {var} placeholders to {{var}} placeholders.

    Unknown single-brace content is intentionally preserved so Python f-strings,
    PowerShell blocks, JSON, and other code are not rewritten.
    """
    if not text:
        return text

    def repl(match: re.Match) -> str:
        spec = match.group(1).strip()
        if _is_known_variable_spec(spec, include_url=include_url):
            return "{{" + spec + "}}"  # type: ignore[no-any-return]
        return match.group(0)  # type: ignore[no-any-return]

    return _LEGACY_TOKEN_RE.sub(repl, text)


def quote_windows_arg(value: str) -> str:
    """Quote one value so it is safe as a single Windows command argument."""
    return subprocess.list2cmdline([value or ""])


def quote_bash_arg(value: str) -> str:
    """Quote one value so it is safe as a single POSIX shell argument (Git Bash).

    Converts backslashes to forward slashes for Windows path compatibility,
    then wraps in single quotes (safest for bash).
    """
    v = (value or "").replace("\\", "/")
    if not v:
        return "''"
    v = v.replace("'", "'\\''")
    return f"'{v}'"


def quote_powershell_arg(value: str) -> str:
    """Quote one value as a literal PowerShell string."""
    v = value or ""
    return "'" + v.replace("'", "''") + "'"


def get_app_dir() -> str:
    return str(app_root())


def get_config_dir() -> str:
    return os.path.join(get_app_dir(), "config")


def get_default_lan_ipv4() -> str:
    """Return the IPv4 address used by the default outbound route."""
    errors: list[str] = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            ip_text = sock.getsockname()[0]
        finally:
            sock.close()
        parsed = ipaddress.ip_address(ip_text)
        if parsed.version == 4 and not parsed.is_loopback and not parsed.is_unspecified:
            return ip_text  # type: ignore[no-any-return]
    except Exception as exc:
        errors.append(str(exc))

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip_text = info[4][0]
            parsed = ipaddress.ip_address(ip_text)
            if parsed.version == 4 and not parsed.is_loopback and not parsed.is_unspecified:
                return ip_text  # type: ignore[return-value]
    except Exception as exc:
        errors.append(str(exc))

    detail = "; ".join(part for part in errors if part) or "no usable IPv4 address"
    raise CommandVariableError("无法获取默认出口内网 IPv4: " + detail)


def fetch_public_wan_ipv4(timeout: float = 2.0) -> str:
    """Fetch the current public IPv4, rejecting IPv6 and invalid responses."""
    endpoints = [
        ("https://api.ipify.org?format=json", "json"),
        ("https://ifconfig.me/ip", "text"),
        ("https://ipinfo.io/ip", "text"),
    ]
    last_error = ""
    saw_ipv6 = False
    for url, response_type in endpoints:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "QuickLauncher/1.0"})
            with safe_urlopen(req, timeout=timeout) as resp:
                raw = read_limited_response(resp, 4096).decode("utf-8", errors="replace").strip()
            ip_text = json.loads(raw).get("ip", "").strip() if response_type == "json" else raw.split()[0].strip()
            parsed = ipaddress.ip_address(ip_text)
            if parsed.version == 4:
                return ip_text
            if parsed.version == 6:
                saw_ipv6 = True
                last_error = "service returned IPv6"
        except Exception as exc:
            last_error = str(exc)
    if saw_ipv6:
        raise CommandVariableError("无法获取公网 IPv4: 服务仅返回 IPv6")
    raise CommandVariableError("无法获取公网 IPv4: " + (last_error or "公网 IP 服务无响应"))


def read_clipboard_text() -> str:
    """Read clipboard text without requiring Qt main-thread access.

    Delegates to ClipboardService for thread-safe COM-initialized access.
    """
    try:
        from .clipboard_service import clipboard_service

        return clipboard_service.read_text_win32()
    except Exception:
        logger.debug("读取剪贴板文本失败", exc_info=True)
    return ""


def collect_input_prompts(text: str) -> list[str]:
    """Return unique prompts used by {{input}} variables in command text."""
    prompts: list[str] = []
    seen = set()
    guarded = _guard_escaped_double_braces(text or "")
    for match in _TOKEN_RE.finditer(guarded):
        raw, _ = _split_spec(match.group(1).strip())
        raw_key = raw.lower()
        if raw_key == "input":
            prompt = ""
        elif raw_key.startswith("input:"):
            prompt = raw[6:].strip()
        else:
            continue
        if prompt not in seen:
            seen.add(prompt)
            prompts.append(prompt)
    return prompts


def should_expand_command_variables(command_type: str, enabled: bool | None) -> bool:
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
    guarded = _guard_escaped_double_braces(text or "")
    for match in _TOKEN_RE.finditer(guarded):
        spec = match.group(1).strip()
        base, should_quote = _split_spec(spec)
        base_key = base.lower()
        root = base_key.split(":", 1)[0]
        is_external = (
            root in _EXTERNAL_INPUT_VARIABLES or base_key.startswith("param:") or base_key.startswith("chain:")
        )
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
    match = _TOKEN_RE.fullmatch(_guard_escaped_double_braces(value))
    if not match:
        return False
    base, _ = _split_spec(match.group(1).strip())
    base_key = base.lower()
    return (
        base_key in _VALUE_ONLY_VARIABLES
        or base_key.startswith("input:")
        or base_key.startswith("param:")
        or base_key.startswith("chain:")
    )


def resolve_command_variables(
    text: str,
    *,
    input_values: dict[str, str] | None = None,
    param_values: dict[str, str] | None = None,
    chain_values: dict[str, str] | None = None,
    selected_files: list[str] | None = None,
    selected_text_provider: Callable[[], str] | None = None,
    clipboard_provider: Callable[[], str] | None = None,
    app_dir: str | None = None,
    config_dir: str | None = None,
    strict_unknown: bool = True,
    raw_mode: bool = False,
    bash_mode: bool = False,
    powershell_mode: bool = False,
) -> str:
    """Expand supported command variables in text.

    Escaped double braces are preserved as literal braces, e.g. "{{{{date}}}}" becomes "{{date}}".
    If raw_mode is True, returns text unchanged (skips variable expansion).
    """
    if not text:
        return text

    if raw_mode:
        return text

    guarded = _guard_escaped_double_braces(text)
    now = datetime.now()
    inputs = input_values or {}
    params = param_values or {}
    chain = chain_values or {}
    files = [_sanitize_external_input(str(path or "")) for path in (selected_files or []) if str(path or "")]
    clipboard_reader = clipboard_provider or read_clipboard_text

    def repl(match: re.Match) -> str:
        spec = match.group(1).strip()
        base, should_quote = _split_spec(spec)
        base_key = base.lower()

        if base_key == "clipboard":
            value = _sanitize_external_input(clipboard_reader())
        elif base_key == "selected_text":
            if not selected_text_provider:
                raise CommandVariableError("{{selected_text}} 需要在窗口关闭后触发模式下使用")
            value = _sanitize_external_input(selected_text_provider())
        elif base_key == "selected_file":
            value = _first_selected_file(files, "selected_file")
        elif base_key == "selected_file_name":
            value = os.path.basename(_first_selected_file(files, "selected_file_name"))
        elif base_key == "selected_file_dir":
            value = os.path.dirname(_first_selected_file(files, "selected_file_dir"))
        elif base_key == "selected_files":
            if should_quote:
                qfn = quote_bash_arg if bash_mode else quote_powershell_arg if powershell_mode else quote_windows_arg
                return " ".join(qfn(path) for path in files)
            value = "\n".join(files)
        elif base_key == "date":
            value = now.strftime("%Y-%m-%d")
        elif base_key == "time":
            value = now.strftime("%H:%M:%S")
        elif base_key == "app_dir":
            value = app_dir if app_dir is not None else get_app_dir()
        elif base_key == "config_dir":
            value = config_dir if config_dir is not None else get_config_dir()
        elif base_key == "lan_ip":
            value = get_default_lan_ipv4()
        elif base_key == "wan_ip":
            value = fetch_public_wan_ipv4()
        elif base_key == "input":
            value = _sanitize_external_input(_lookup_input_value(inputs, ""))
        elif base_key.startswith("input:"):
            prompt = base[6:].strip()
            value = _sanitize_external_input(_lookup_input_value(inputs, prompt))
        elif base_key.startswith("param:"):
            name = base[6:].strip()
            if not name:
                raise CommandVariableError("变量名称无效: {{" + spec + "}}")
            value = _sanitize_external_input(_lookup_named_value(params, name, "参数"))
        elif base_key.startswith("chain:"):
            name = base[6:].strip()
            if not name:
                raise CommandVariableError("变量名称无效: {{" + spec + "}}")
            value = _sanitize_external_input(_lookup_named_value(chain, name, "动作链变量"))
        else:
            if not strict_unknown:
                return match.group(0)  # type: ignore[no-any-return]
            raise CommandVariableError("未知变量: {{" + spec + "}}")

        if should_quote:
            if bash_mode:
                return quote_bash_arg(value)
            if powershell_mode:
                return quote_powershell_arg(value)
            return quote_windows_arg(value)
        return value

    resolved = _TOKEN_RE.sub(repl, guarded)
    return _restore_escaped_double_braces(resolved)


def _first_selected_file(files: list[str], label: str) -> str:
    if files:
        return files[0]
    return ""


def _split_spec(spec: str) -> tuple[str, bool]:
    if spec.endswith(":q"):
        return spec[:-2].strip(), True
    return spec, False


def _lookup_named_value(values: dict[str, str], name: str, label: str) -> str:
    if name in values:
        return values[name]
    raise CommandVariableError(f"缺少{label}: {name}")


def _lookup_input_value(input_values: dict[str, str], prompt: str) -> str:
    if prompt in input_values:
        return input_values[prompt]
    if not prompt and "input" in input_values:
        return input_values["input"]
    label = prompt or "输入内容"
    raise CommandVariableError(f"缺少运行时输入: {label}")
