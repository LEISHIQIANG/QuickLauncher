"""Output-capture result builders and decoding helpers.

The functions in this module are extracted from the legacy
``core.shortcut_command_exec.CommandExecutionMixin``.  They are
responsible for:

* Decoding and truncating captured stdout/stderr bytes
  (:func:`decode_capture_output`, :func:`truncate_output`,
  :func:`decode_bytes`).
* Building the various :class:`CommandResult` shapes used by the
  command panel (success, cancellation, timeout, error, bash fallback).

The legacy class keeps the same method names and now simply delegates
to the module functions.
"""

from __future__ import annotations

import logging
import time

from core.command_exec.output import (
    build_bash_fallback_result as _build_bash_fallback_result_compat,
)
from core.command_exec.output import (
    decode_command_output as _decode_command_output,
)
from core.command_exec.output import (
    truncate_command_output as _truncate_command_output,
)
from core.command_registry import CommandAction, CommandResult
from core.data_models import ShortcutItem

logger = logging.getLogger(__name__)


# ── capture result builders ──────────────────────────────────────


def build_capture_payload(
    *,
    panel_size: str,
    returncode: int,
    start: float,
    stdout: str,
    stderr: str,
    stdout_truncated: bool,
    stderr_truncated: bool,
    stdout_encoding: str,
    stderr_encoding: str,
    decode_fallback_used: bool,
    command: str,
    timed_out: bool = False,
    cancelled: bool = False,
    wrap: bool = False,
) -> dict:
    """Return the standard payload shared by capture results."""
    return {
        "window_size": panel_size,
        "wrap": wrap,
        "exit_code": returncode,
        "duration": time.monotonic() - start,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "stdout_encoding": stdout_encoding,
        "stderr_encoding": stderr_encoding,
        "decode_fallback_used": decode_fallback_used,
        "command": command,
        "cancelled": cancelled,
        "timed_out": timed_out,
    }


def build_capture_error_result(
    message: str,
    error: str,
    panel_size: str,
    *,
    start: float | None = None,
    command: str | None = None,
) -> CommandResult:
    payload: dict = {"window_size": panel_size}
    if start is not None:
        payload["duration"] = time.monotonic() - start
    if command is not None:
        payload["command"] = command
    return CommandResult(
        success=False,
        message=message,
        display_type="log",
        error=error,
        payload=payload,
    )


def build_capture_builtin_result(success: bool, panel_size: str, start: float) -> CommandResult:
    return CommandResult(
        success=success,
        message="内置命令已执行。" if success else "内置命令执行失败",
        display_type="log",
        error="" if success else "执行失败",
        payload={
            "window_size": panel_size,
            "exit_code": 0 if success else 1,
            "duration": time.monotonic() - start,
        },
    )


def build_capture_cancel_result(
    *,
    panel_size: str,
    returncode: int,
    start: float,
    stdout: str,
    stderr: str,
    stdout_truncated: bool,
    stderr_truncated: bool,
    stdout_encoding: str,
    stderr_encoding: str,
    decode_fallback_used: bool,
    command: str,
) -> CommandResult:
    """Build the :class:`CommandResult` for a cancelled capture."""
    message = "\n".join(part for part in ["命令执行已取消。", stdout, stderr] if part)
    return CommandResult(
        success=False,
        message=message,
        display_type="log",
        payload=build_capture_payload(
            panel_size=panel_size,
            returncode=returncode,
            start=start,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            stdout_encoding=stdout_encoding,
            stderr_encoding=stderr_encoding,
            decode_fallback_used=decode_fallback_used,
            command=command,
            cancelled=True,
            timed_out=False,
        ),
        error="已取消",
    )


def build_capture_success_result(
    *,
    panel_size: str,
    returncode: int,
    start: float,
    stdout: str,
    stderr: str,
    stdout_truncated: bool,
    stderr_truncated: bool,
    stdout_encoding: str,
    stderr_encoding: str,
    decode_fallback_used: bool,
    command: str,
    timed_out: bool,
    timeout_value: float,
) -> CommandResult:
    """Build the :class:`CommandResult` for a completed capture."""
    success = (returncode == 0) and not timed_out
    parts = []
    if stdout:
        parts.append(stdout)
    if stderr and not success:
        parts.append(stderr)
    if not parts:
        parts.append("(无输出)")
    message = "\n".join(parts)
    if timed_out:
        message = f"命令执行超时 ({timeout_value:g}s)，已终止。\n\n{message}"
    error = ""
    if timed_out:
        error = "执行超时"
    elif returncode != 0:
        error = stderr.strip().splitlines()[0] if stderr.strip() else f"退出码 {returncode}"
    return CommandResult(
        success=success,
        message=message,
        display_type="log",
        payload=build_capture_payload(
            panel_size=panel_size,
            returncode=returncode,
            start=start,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            stdout_encoding=stdout_encoding,
            stderr_encoding=stderr_encoding,
            decode_fallback_used=decode_fallback_used,
            command=command,
            timed_out=timed_out,
        ),
        actions=[CommandAction(type="copy", label="复制输出", value=message)],
        error=error,
    )


# ── decode / truncate helpers ────────────────────────────────────


def decode_bytes(data: bytes, preferred: str = "auto", command_type: str = "") -> tuple[str, str, bool]:
    """Decode command output while reporting the selected encoding and fallback use."""
    return _decode_command_output(data, preferred, command_type=command_type)


def truncate_output(text: str, max_chars: int) -> tuple[str, bool]:
    text = text or ""
    return _truncate_command_output(text, max_chars)


def decode_capture_output(
    stdout_bytes: bytes,
    stderr_bytes: bytes,
    shortcut: ShortcutItem,
    command_type: str,
    max_chars: int,
) -> tuple[str, str, bool, bool, str, str, bool]:
    """Decode and truncate captured stdout/stderr bytes.

    Returns a 7-element tuple:
    ``(stdout, stderr, stdout_truncated, stderr_truncated,
    stdout_encoding, stderr_encoding, decode_fallback_used)``.
    """
    encoding = getattr(shortcut, "command_encoding", "auto")
    stdout, stdout_encoding, stdout_fallback = decode_bytes(stdout_bytes or b"", encoding, command_type)
    stderr, stderr_encoding, stderr_fallback = decode_bytes(stderr_bytes or b"", encoding, command_type)
    stdout, stdout_truncated = truncate_output(stdout or "", max_chars)
    stderr, stderr_truncated = truncate_output(stderr or "", max_chars)
    return (
        stdout,
        stderr,
        stdout_truncated,
        stderr_truncated,
        stdout_encoding,
        stderr_encoding,
        stdout_fallback or stderr_fallback,
    )


# ── bash fallback (delegates to the existing :mod:`output` helper) ─


def build_bash_fallback_result(
    *,
    panel_size: str,
    returncode: int,
    start: float,
    stdout: str,
    stderr: str,
    stdout_truncated: bool,
    stderr_truncated: bool,
    stdout_encoding: str,
    stderr_encoding: str,
    decode_fallback_used: bool,
    command: str,
    timed_out: bool,
) -> CommandResult:
    """Build the :class:`CommandResult` when the bash direct capture is denied.

    The legacy class method takes keyword-only arguments while the
    :func:`output.build_bash_fallback_result` helper takes positional
    arguments.  This wrapper translates between the two signatures
    so that callers (and the legacy mixin) can use the modern
    keyword-only style while delegating the payload assembly to the
    existing helper.
    """
    return _build_bash_fallback_result_compat(  # type: ignore[no-any-return]
        stdout.encode(stdout_encoding or "utf-8", errors="replace"),
        stderr.encode(stderr_encoding or "utf-8", errors="replace"),
        returncode,
        False,
        timed_out,
        None,
        command,
        0,
        panel_size,
        None,
        start,
    )


__all__ = [
    "build_bash_fallback_result",
    "build_capture_builtin_result",
    "build_capture_cancel_result",
    "build_capture_error_result",
    "build_capture_payload",
    "build_capture_success_result",
    "decode_bytes",
    "decode_capture_output",
    "truncate_output",
]
