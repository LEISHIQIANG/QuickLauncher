"""Standard-user direct launch channel for shortcuts and commands.

Elevation intentionally stays on the icon execution path:
ShellExecuteW with the "runas" verb. This module owns the single downgrade
path only: create through Explorer's medium-integrity token.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import time

logger = logging.getLogger(__name__)

PRIVILEGE_LAUNCH_TIMEOUT_SECONDS = 3.0
PRIVILEGE_LAUNCH_DEADLINE_SLACK_SECONDS = 0.15
STANDARD_USER_POLL_SECONDS = 0.15
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_CMD_META_CHARS = set("&|<>^")


def launch_via_explorer_com(target: str, parameters: str = "", directory: str = "", show: int = 1) -> tuple[bool, str]:
    """Launch via standard user Explorer.exe COM dispatch to bypass seclogon / privilege limitations."""
    _com_initialized = False
    try:
        import pythoncom

        pythoncom.CoInitialize()
        _com_initialized = True
    except Exception:
        pass

    try:
        import ctypes

        import win32com.client

        hwnd = ctypes.windll.user32.GetShellWindow()
        if not hwnd:
            return False, "GetShellWindow returned null"

        shell_windows = win32com.client.Dispatch("Shell.Windows")
        if not shell_windows:
            return False, "Failed to dispatch Shell.Windows"

        for i in range(int(shell_windows.Count)):
            window = shell_windows.Item(i)
            if window and hasattr(window, "HWND") and int(window.HWND) == hwnd:
                doc = window.Document
                if doc:
                    shell_app = doc.Application
                    if shell_app:
                        shell_app.ShellExecute(target, parameters or "", directory or "", "open", show)
                        logger.info("Successfully launched standard-user process via Explorer COM fallback: %s", target)
                        return True, ""

        return False, "Desktop shell window not found in Shell.Windows"
    except Exception as exc:
        logger.debug("Explorer COM launch failed: %s", exc)
        return False, str(exc)
    finally:
        if _com_initialized:
            try:
                import pythoncom

                pythoncom.CoUninitialize()
            except Exception:
                pass


def launch_as_standard_user(
    target: str,
    parameters: str | None = None,
    directory: str | None = None,
    show_cmd: int = 1,
    timeout_seconds: float = PRIVILEGE_LAUNCH_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Launch using Explorer's medium-integrity token.

    Direct process creation is preferred for executables. For folders,
    documents, URLs, and shell aliases, a medium-integrity cmd/start hop lets
    Windows resolve the same association that ShellExecute would use.
    """
    if os.name != "nt":
        return False, "unsupported platform"

    params = parameters or ""
    cwd = directory or ""
    requested_timeout = min(
        float(timeout_seconds or PRIVILEGE_LAUNCH_TIMEOUT_SECONDS),
        PRIVILEGE_LAUNCH_TIMEOUT_SECONDS,
    )
    internal_timeout = max(0.05, requested_timeout - PRIVILEGE_LAUNCH_DEADLINE_SLACK_SECONDS)
    deadline = time.monotonic() + internal_timeout

    try:
        from . import auto_start_manager as autostart

        if _looks_like_missing_filesystem_target(target):
            return False, "target does not exist"

        if _can_create_process_directly(target):
            remaining = _remaining_seconds(deadline)
            if remaining <= 0:
                return False, "standard-user launch timed out"
            if autostart._launch_via_explorer_token(
                target,
                params,
                cwd,
                timeout_seconds=remaining,
                poll_seconds=STANDARD_USER_POLL_SECONDS,
            ):
                return True, ""
            # Fallback 1: Try COM direct launch
            launched, com_err = launch_via_explorer_com(target, params, cwd, show_cmd)
            if launched:
                return True, ""
            if _remaining_seconds(deadline) <= 0:
                return False, f"standard-user launch timed out (COM: {com_err})"

        remaining = _remaining_seconds(deadline)
        if remaining <= 0:
            return False, "standard-user launch timed out"
        if not params:
            explorer = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "explorer.exe")
            if autostart._launch_via_explorer_token(
                explorer,
                subprocess.list2cmdline([target]),
                cwd,
                timeout_seconds=remaining,
                poll_seconds=STANDARD_USER_POLL_SECONDS,
            ):
                return True, ""
            # Fallback 2: Try COM launch without params
            launched, com_err = launch_via_explorer_com(target, "", cwd, show_cmd)
            if launched:
                return True, ""
            return False, f"Explorer token launch failed: COM={com_err}"

        comspec = os.environ.get("ComSpec") or os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "cmd.exe",
        )
        start_line = _build_cmd_start_line(target, params)
        cmd_args = subprocess.list2cmdline(["/d", "/s", "/c", start_line])
        remaining = _remaining_seconds(deadline)
        if remaining <= 0:
            return False, "standard-user launch timed out"
        if autostart._launch_via_explorer_token(
            comspec,
            cmd_args,
            cwd,
            timeout_seconds=remaining,
            poll_seconds=STANDARD_USER_POLL_SECONDS,
        ):
            return True, ""
        # Fallback 3: Try COM launch with params
        launched, com_err = launch_via_explorer_com(target, params, cwd, show_cmd)
        if launched:
            return True, ""
        return False, f"Explorer token launch failed: COM={com_err}"
    except Exception as exc:
        logger.debug("Standard-user direct channel failed: %s", exc, exc_info=True)
        # Try COM launch as ultimate safety net
        try:
            launched, com_err = launch_via_explorer_com(target, params, cwd, show_cmd)
            if launched:
                return True, ""
        except Exception:
            pass
        return False, str(exc)


def _can_create_process_directly(target: str) -> bool:
    if not target:
        return False
    suffix = os.path.splitext(target)[1].lower()
    return suffix in {".exe", ".com"} and os.path.isfile(target)


def _looks_like_missing_filesystem_target(target: str) -> bool:
    if not target:
        return True
    if _URI_SCHEME_RE.match(target):
        return False
    if os.path.exists(target):
        return False
    return os.path.isabs(target) or bool(os.path.dirname(target))


def _build_cmd_start_line(target: str, parameters: str = "") -> str:
    _validate_cmd_start_value(target, field="target")
    pieces = ["start", '""', _cmd_quote(target)]
    if parameters:
        pieces.extend(_cmd_quote_argument(arg) for arg in _split_windows_arguments(parameters))
    return " ".join(pieces)


def _cmd_quote(value: str) -> str:
    value = value or ""
    if '"' in value:
        raise ValueError("target contains an unsupported quote character")
    return f'"{value}"'


def _validate_cmd_start_value(value: str, *, field: str, allow_quotes: bool = False) -> None:
    if any(ch in (value or "") for ch in ("\x00", "\r", "\n")):
        raise ValueError(f"{field} contains control characters")
    if not allow_quotes and '"' in (value or ""):
        raise ValueError(f"{field} contains quotes")


def _cmd_quote_argument(value: str) -> str:
    _validate_cmd_start_value(value, field="parameters")
    if not value or any(ch.isspace() or ch in _CMD_META_CHARS for ch in value):
        return f'"{value}"'
    return value


def _split_windows_arguments(command_line: str) -> list[str]:
    command_line = command_line or ""
    if any(ch in command_line for ch in ("\x00", "\r", "\n")):
        raise ValueError("parameters contain control characters")
    if not command_line.strip():
        return []
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        argc = ctypes.c_int()
        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32
        shell32.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        argv = shell32.CommandLineToArgvW(command_line, ctypes.byref(argc))
        if not argv:
            raise ValueError("parameters are not a valid Windows command line")
        try:
            return [argv[i] for i in range(argc.value)]
        finally:
            kernel32.LocalFree(argv)
    return shlex.split(command_line, posix=False)


def _remaining_seconds(deadline: float) -> float:
    return max(0.0, min(PRIVILEGE_LAUNCH_TIMEOUT_SECONDS, deadline - time.monotonic()))
