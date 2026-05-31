"""Command output decoding and truncation helpers."""

from __future__ import annotations

import ctypes
import locale
import logging
import os
import time

from core.runtime_constants import normalize_command_output_max_chars

logger = logging.getLogger(__name__)


def decode_command_output(
    data: bytes | str,
    preferred: str = "auto",
    command_type: str | None = None,
) -> tuple[str, str, bool]:
    """Decode command output while reporting the selected encoding and fallback use.

    For CMD commands on Windows, the console's active OEM code page
    is tried before UTF-8 since cmd.exe output is never UTF-8 by default.
    """
    if isinstance(data, str):
        return data, "text", False
    data = data or b""

    candidates: list[str] = []
    preferred = str(preferred or "auto").lower().strip()
    if preferred and preferred != "auto":
        candidates.append(preferred)

    # Determine the Windows OEM code page (e.g. cp936 on zh-CN, cp437 on en-US)
    oem_enc = None
    if os.name == "nt":
        try:
            oem_cp = ctypes.windll.kernel32.GetOEMCP()
            if oem_cp:
                oem_enc = f"cp{oem_cp}"
        except Exception as exc:
            logger.debug("获取OEM代码页失败: %s", exc, exc_info=True)

    effective_type = str(command_type or "").lower().strip() if command_type else ""

    if effective_type == "cmd" and oem_enc:
        # cmd.exe output uses the console's active OEM code page.
        # Trying UTF-8 first would silently produce mojibake for non-ASCII
        # output (Chinese, accented characters, etc.) because most cmd.exe
        # byte sequences decode without error under utf-8 but render wrong.
        candidates.append(oem_enc)

    candidates.append("utf-8")

    if effective_type != "cmd" and oem_enc:
        candidates.append(oem_enc)

    try:
        pref = locale.getpreferredencoding(False)
        if pref:
            candidates.append(pref)
    except Exception as exc:
        logger.debug("获取首选编码失败: %s", exc, exc_info=True)
    candidates.extend(["mbcs", "gbk"])

    seen = set()
    ordered = []
    for enc in candidates:
        key = enc.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(enc)

    for idx, enc in enumerate(ordered):
        try:
            return data.decode(enc), enc, idx > 0
        except Exception:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8", True


def truncate_command_output(text: str, max_chars: int) -> tuple[str, bool]:
    text = text or ""
    max_chars = normalize_command_output_max_chars(max_chars)
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "\n\n[输出过长，已截断]", True


def build_bash_fallback_result(
    stdout_bytes,
    stderr_bytes,
    returncode,
    cancelled,
    timed_out,
    shortcut,
    command,
    max_chars,
    panel_size,
    command_type,
    start,
):
    """Build a result dict for the bash script-fallback capture path.

    Returns a CommandResult instance.
    """
    # Lazy import to avoid circular: command_registry imports are not needed
    # at module-load time.
    from core.command_registry import CommandAction, CommandResult

    stdout, stdout_enc, stdout_fb = decode_command_output(
        stdout_bytes or b"", getattr(shortcut, "command_encoding", "auto"), command_type=command_type
    )
    stderr, stderr_enc, stderr_fb = decode_command_output(
        stderr_bytes or b"", getattr(shortcut, "command_encoding", "auto"), command_type=command_type
    )
    stdout, stdout_truncated = truncate_command_output(stdout or "", max_chars)
    stderr, stderr_truncated = truncate_command_output(stderr or "", max_chars)

    message_parts = []
    if cancelled:
        message_parts.append("命令执行已取消。")
    if stdout:
        message_parts.append(stdout)
    if stderr and not (returncode == 0 and not timed_out and not cancelled):
        message_parts.append(stderr)
    if not message_parts:
        message_parts.append("(无输出)")
    message = "\n".join(message_parts)
    if timed_out:
        message = f"命令执行超时，已终止。\n\n{message}"

    error = ""
    if cancelled:
        error = "已取消"
    elif timed_out:
        error = "执行超时"
    elif returncode != 0:
        error = stderr.strip().splitlines()[0] if stderr.strip() else f"退出码 {returncode}"

    payload = {
        "window_size": panel_size,
        "wrap": False,
        "exit_code": returncode,
        "duration": time.monotonic() - start,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "stdout_encoding": stdout_enc,
        "stderr_encoding": stderr_enc,
        "decode_fallback_used": stdout_fb or stderr_fb,
        "command": command,
        "cancelled": cancelled,
        "timed_out": timed_out,
        "fallback_script": True,
    }
    return CommandResult(
        success=(returncode == 0) and not timed_out and not cancelled,
        message=message,
        display_type="log",
        payload=payload,
        actions=[CommandAction(type="copy", label="复制输出", value=message)],
        error=error,
    )
