"""Command execution helpers for ShortcutExecutor."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from qt_compat import QObject, pyqtSignal

from .command_exec import (
    SUPPORTED_COMMAND_TYPES,
    chain_values,
    command_panel_size,
    command_param_defs,
    command_param_values,
    decode_command_output,
    merge_runtime_env,
    normalize_command_type,
    truncate_command_output,
)
from .command_param_validation import validate_param_values
from .command_registry import (
    CommandAction,
    CommandContext,
    CommandParam,
    CommandResult,
    set_pending_command_result,
    take_pending_command_result,
)
from .command_risk import assess_command_risk
from .command_variables import (
    CommandVariableError,
    find_unquoted_external_command_variables,
    is_value_only_variable_command,
    read_clipboard_text,
    resolve_command_variables,
    should_expand_command_variables,
)
from .data_models import ShortcutItem
from .runtime_constants import (
    COMMAND_CAPTURE_POLL_SECONDS,
    COMMAND_CAPTURE_UPDATE_INTERVAL_SECONDS,
    DEFAULT_COMMAND_OUTPUT_MAX_CHARS,
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    PROCESS_TERMINATE_WAIT_SECONDS,
    normalize_command_timeout_seconds,
)

logger = logging.getLogger(__name__)
ShortcutExecutor = None
WINDOWS_DIRECT_COMMAND_LINE_MAX_CHARS = 30000


class MainThreadInvoker(QObject):
    execute_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.execute_signal.connect(self._on_execute)

    def _on_execute(self, func):
        try:
            func()
        except Exception as e:
            logger.error(f"MainThreadInvoker execution failed: {e}")


_main_thread_invoker = None


def init_main_thread_invoker():
    global _main_thread_invoker
    if _main_thread_invoker is None:
        _main_thread_invoker = MainThreadInvoker()


def _write_atomic(path: str, content: str) -> None:
    """Write content to path atomically via tempfile + rename to avoid races."""
    dir_name = os.path.dirname(path)
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            suffix=os.path.splitext(path)[1],
            dir=dir_name if dir_name else None,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(fd)
        os.replace(tmp_path, path)
        tmp_path = None
    except Exception:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except Exception as exc:
                logger.debug("删除临时文件失败: %s", exc, exc_info=True)
        raise


def _pipe_reader(pipe, output_queue, name):
    """Read lines from a pipe and put them on a queue for the on_update path."""
    try:
        while True:
            chunk = pipe.readline()
            if not chunk:
                break
            output_queue.put((name, chunk))
    finally:
        try:
            pipe.close()
        except Exception as exc:
            logger.debug("关闭管道失败: %s", exc, exc_info=True)


def _bash_fallback_result(
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
) -> CommandResult:
    """Build a CommandResult for the bash script-fallback capture path."""
    stdout, stdout_encoding, stdout_fallback = decode_command_output(
        stdout_bytes or b"", getattr(shortcut, "command_encoding", "auto"), command_type=command_type
    )
    stderr, stderr_encoding, stderr_fallback = decode_command_output(
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
        "stdout_encoding": stdout_encoding,
        "stderr_encoding": stderr_encoding,
        "decode_fallback_used": stdout_fallback or stderr_fallback,
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


class CommandExecutionMixin:
    _PARAM_TOKEN_RE = re.compile(r"(?<!\{)\{\{param:([^{}\r\n:]+)(?::q)?\}\}(?!\})")
    _CHAIN_TOKEN_RE = re.compile(r"(?<!\{)\{\{chain:([^{}\r\n:]+)(?::q)?\}\}(?!\})")
    _SUPPORTED_COMMAND_TYPES = SUPPORTED_COMMAND_TYPES
    _DESTRUCTIVE_CONFIRMATION_ATTR = "_destructive_command_confirmed"
    _executor: ThreadPoolExecutor | None = None
    _executor_lock = threading.Lock()

    @classmethod
    def _get_executor(cls) -> ThreadPoolExecutor:
        if cls._executor is None:
            with cls._executor_lock:
                if cls._executor is None:
                    cls._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="CmdExec")
        return cls._executor

    @staticmethod
    def _normalize_command_type(command_type: str) -> str:
        return normalize_command_type(command_type)

    @staticmethod
    def _cmd_launcher() -> str | None:
        candidates = []
        if os.name == "nt":
            candidates.extend(
                [
                    os.environ.get("ComSpec"),
                    os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Sysnative", "cmd.exe"),
                    os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"),
                    shutil.which("cmd.exe"),
                    shutil.which("cmd"),
                ]
            )
        else:
            candidates.extend([os.environ.get("SHELL"), shutil.which("sh")])
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return ShortcutExecutor._resolve_long_path(os.path.abspath(candidate))
        return None

    @staticmethod
    def _cmd_launcher_error() -> str:
        return "CMD shell is not available. Check ComSpec or the Windows system directory."

    @staticmethod
    def _cmd_argv(command: str, *, keep_open: bool = False) -> list[str]:
        cmd_exe = ShortcutExecutor._cmd_launcher()
        if not cmd_exe:
            raise FileNotFoundError(ShortcutExecutor._cmd_launcher_error())
        if os.name == "nt":
            return [cmd_exe, "/d", "/s", "/k" if keep_open else "/c", command]
        return [cmd_exe, "-c", command]

    @staticmethod
    def _cmd_has_newline(command: str) -> bool:
        return "\n" in (command or "") or "\r" in (command or "")

    @staticmethod
    def _cmd_stdin_argv() -> list[str]:
        cmd_exe = ShortcutExecutor._cmd_launcher()
        if not cmd_exe:
            raise FileNotFoundError(ShortcutExecutor._cmd_launcher_error())
        if os.name == "nt":
            return [cmd_exe, "/d", "/q", "/k", "prompt $H"]
        return [cmd_exe]

    @staticmethod
    def _cmd_stdin_script(command: str) -> bytes:
        normalized = str(command or "").replace("\r\n", "\n").replace("\r", "\n")
        script = "@echo off\r\nchcp 65001 >nul\r\n" + normalized.replace("\n", "\r\n")
        if not script.endswith("\r\n"):
            script += "\r\n"
        script += "exit /b %ERRORLEVEL%\r\n"
        return script.encode("utf-8")

    @staticmethod
    def _clean_cmd_stdin_output_bytes(data: bytes) -> bytes:
        cleaned = data or b""
        for token in (b"\r\n\x08 \x08", b"\n\x08 \x08", b"\x08 \x08"):
            cleaned = cleaned.replace(token, b"")
        return cleaned

    @staticmethod
    def _command_preprocessing_result(shortcut: ShortcutItem, command: str, command_type: str):
        try:
            from core import data_manager
            from core.preprocessing.pipeline import (
                PreprocessingContext,
                PreprocessingPipeline,
                create_pipeline_from_settings,
            )

            settings = None
            if data_manager is not None and hasattr(data_manager, "get_settings"):
                try:
                    settings = data_manager.get_settings()
                except Exception:
                    settings = None
            pipeline = (
                create_pipeline_from_settings(settings)
                if settings is not None
                else PreprocessingPipeline(rate_limiting=False)
            )
            return pipeline.process(
                PreprocessingContext(
                    shortcut_id=str(getattr(shortcut, "id", "") or ""),
                    shortcut_name=str(getattr(shortcut, "name", "") or ""),
                    command=command,
                    command_type=command_type,
                    working_dir=(getattr(shortcut, "working_dir", "") or "").strip(),
                    raw_mode=bool(getattr(shortcut, "raw_mode", False)),
                    run_as_admin=bool(getattr(shortcut, "run_as_admin", False)),
                    param_values=ShortcutExecutor._command_param_values(shortcut),
                )
            )
        except Exception as e:
            logger.debug("Command preprocessing failed open: %s", e, exc_info=True)
            return None

    @staticmethod
    def _preprocessing_result_to_command_result(preprocess_result, panel_size: str = "medium") -> CommandResult:
        items = []
        for error in getattr(preprocess_result, "errors", []) or []:
            detail = getattr(error, "message", "") or getattr(error, "error_code", "")
            suggestion = getattr(error, "suggestion", "")
            if suggestion:
                detail = f"{detail}\n{suggestion}"
            items.append({"title": getattr(error, "field", "validation"), "status": "failed", "detail": detail})
        for warning in getattr(preprocess_result, "warnings", []) or []:
            if not getattr(preprocess_result, "should_block", False) and getattr(warning, "allow_override", False):
                continue
            detail = getattr(warning, "description", "") or getattr(warning, "issue_type", "")
            mitigation = getattr(warning, "mitigation", "")
            if mitigation:
                detail = f"{detail}\n{mitigation}"
            items.append({"title": getattr(warning, "severity", "warning"), "status": "failed", "detail": detail})
        message = "\n".join(f"[{item['status'].upper()}] {item['title']}: {item['detail']}" for item in items)
        return CommandResult(
            success=False,
            message=message or "Command preprocessing failed.",
            display_type="list",
            payload={"items": items, "window_size": panel_size},
            error="Command preprocessing failed",
        )

    @staticmethod
    def _command_param_defs(shortcut: ShortcutItem) -> list[dict]:
        return command_param_defs(shortcut)

    @staticmethod
    def _command_param_values(shortcut: ShortcutItem) -> dict[str, str]:
        return command_param_values(shortcut)

    @staticmethod
    def _chain_values(shortcut: ShortcutItem) -> dict[str, str]:
        return chain_values(shortcut)

    @staticmethod
    def _runtime_env(shortcut: ShortcutItem) -> dict:
        return merge_runtime_env(shortcut, ShortcutExecutor._sanitized_child_env())

    @staticmethod
    def _command_panel_size(shortcut: ShortcutItem) -> str:
        return command_panel_size(shortcut)

    @staticmethod
    def command_requires_confirmation(
        shortcut: ShortcutItem,
        command: str | None = None,
        command_type: str | None = None,
    ) -> list[dict]:
        """Return only the severe destructive risks that must be confirmed before execution."""
        effective_type = ShortcutExecutor._normalize_command_type(
            command_type if command_type is not None else getattr(shortcut, "command_type", "cmd")
        )
        return [
            risk.to_dict()
            for risk in assess_command_risk(shortcut, command=command, command_type=effective_type)
            if risk.requires_confirmation
        ]

    @staticmethod
    def mark_command_confirmed(shortcut: ShortcutItem, confirmed: bool = True) -> None:
        """Mark one shortcut object as confirmed for its next destructive command execution."""
        try:
            setattr(shortcut, CommandExecutionMixin._DESTRUCTIVE_CONFIRMATION_ATTR, bool(confirmed))
        except Exception as exc:
            logger.debug("设置确认属性失败: %s", exc, exc_info=True)

    @staticmethod
    def _consume_command_confirmation(shortcut: ShortcutItem) -> bool:
        try:
            if bool(getattr(shortcut, CommandExecutionMixin._DESTRUCTIVE_CONFIRMATION_ATTR, False)):
                setattr(shortcut, CommandExecutionMixin._DESTRUCTIVE_CONFIRMATION_ATTR, False)
                return True
        except Exception as exc:
            logger.debug("消费确认属性失败: %s", exc, exc_info=True)
        return False

    @staticmethod
    def _destructive_confirmation_result(
        shortcut: ShortcutItem,
        command: str,
        command_type: str,
        *,
        panel_size: str | None = None,
    ) -> CommandResult | None:
        risks = ShortcutExecutor.command_requires_confirmation(shortcut, command=command, command_type=command_type)
        if not risks:
            return None
        if ShortcutExecutor._consume_command_confirmation(shortcut):
            return None
        risk_lines = [f"- {risk.get('message') or risk.get('code')}" for risk in risks]
        detail = "\n".join(risk_lines)
        return CommandResult(
            success=False,
            message="该命令包含不可逆或强破坏性操作，请确认后执行。",
            display_type="confirm",
            error="需要确认",
            payload={
                "window_size": panel_size or ShortcutExecutor._command_panel_size(shortcut),
                "requires_confirmation": True,
                "risks": risks,
                "detail": detail,
                "command_type": command_type,
                "command": command,
                "shortcut": shortcut,
            },
        )

    @staticmethod
    def _decode_bytes(data: bytes, preferred: str = "auto", command_type: str = "") -> tuple[str, str, bool]:
        return decode_command_output(data, preferred, command_type=command_type)

    @staticmethod
    def _preflight_command(
        shortcut: ShortcutItem,
        command: str,
        command_type: str,
        *,
        capture: bool = False,
        preprocess: bool = True,
    ):
        items = []
        command_type = ShortcutExecutor._normalize_command_type(command_type)
        cwd = (getattr(shortcut, "working_dir", "") or "").strip()
        if command_type not in ShortcutExecutor._SUPPORTED_COMMAND_TYPES:
            items.append(
                {
                    "title": "Command type",
                    "status": "failed",
                    "detail": (
                        f"Unsupported command type: {command_type}. "
                        "Supported: cmd, powershell, python, bash, builtin."
                    ),
                }
            )
        if not command:
            items.append({"title": "命令内容", "status": "failed", "detail": "命令内容为空。"})
        if cwd and not os.path.isdir(cwd):
            items.append({"title": "工作目录", "status": "failed", "detail": f"目录不存在: {cwd}"})
        if command_type == "cmd" and not ShortcutExecutor._cmd_launcher():
            items.append({"title": "CMD", "status": "failed", "detail": ShortcutExecutor._cmd_launcher_error()})
        if command_type == "python" and not ShortcutExecutor._python_launcher():
            items.append({"title": "Python", "status": "failed", "detail": ShortcutExecutor._python_launcher_error()})
        if command_type == "powershell" and not ShortcutExecutor._powershell_launcher():
            items.append(
                {"title": "PowerShell", "status": "failed", "detail": ShortcutExecutor._powershell_launcher_error()}
            )
        if command_type == "bash" and not ShortcutExecutor._bash_launcher():
            items.append({"title": "Git Bash", "status": "failed", "detail": ShortcutExecutor._bash_launcher_error()})
        if capture and bool(getattr(shortcut, "show_window", False)):
            items.append({"title": "捕获输出", "status": "failed", "detail": "显示执行窗口时不能捕获输出。"})
        if capture and bool(getattr(shortcut, "run_as_admin", False)):
            items.append({"title": "捕获输出", "status": "failed", "detail": "管理员命令暂不支持捕获输出。"})
        if command_type in ("cmd", "powershell", "bash") and command:
            try:
                if command_type == "cmd":
                    argv = ShortcutExecutor._cmd_argv(
                        command,
                        keep_open=bool(getattr(shortcut, "show_window", False)) and not capture,
                    )
                elif command_type == "powershell":
                    argv = ShortcutExecutor._powershell_argv(
                        command,
                        no_exit=bool(getattr(shortcut, "show_window", False)) and not capture,
                    )
                else:
                    argv = ShortcutExecutor._bash_argv(
                        command,
                        login=bool(getattr(shortcut, "show_window", False)) and not capture,
                    )
                if ShortcutExecutor._direct_command_line_too_long(argv):
                    items.append(
                        {
                            "title": "命令长度",
                            "status": "failed",
                            "detail": ShortcutExecutor._direct_command_line_length_error(command_type, argv),
                        }
                    )
            except FileNotFoundError:
                logger.debug("预检时找不到shell启动器", exc_info=True)
        if command_type in ("cmd", "powershell", "bash") and not bool(getattr(shortcut, "raw_mode", False)):
            unsafe = find_unquoted_external_command_variables(command)
            if unsafe:
                examples = ", ".join("{{" + name + ":q}}" for name in unsafe[:3])
                items.append(
                    {
                        "title": "命令参数引用",
                        "status": "failed",
                        "detail": f"外部输入变量用于 CMD/PowerShell/Bash 时必须使用 :q 引用，例如: {examples}",
                    }
                )
        param_values = ShortcutExecutor._command_param_values(shortcut)
        params = [CommandParam(**param) for param in ShortcutExecutor._command_param_defs(shortcut)]
        for error in validate_param_values(params, param_values):
            items.append({"title": "命令参数", "status": "failed", "detail": error})
        if (
            command_type in ("cmd", "powershell", "bash")
            and not bool(getattr(shortcut, "raw_mode", False))
            and is_value_only_variable_command(command)
        ):
            items.append({"title": "命令内容", "status": "failed", "detail": "命令不能只包含一个变量占位符。"})
        if items:
            message = "\n".join(f"[{item['status'].upper()}] {item['title']}: {item['detail']}" for item in items)
            return CommandResult(
                success=False, message=message, display_type="list", payload={"items": items}, error="预检失败"
            )
        if preprocess:
            preprocess_result = ShortcutExecutor._command_preprocessing_result(shortcut, command, command_type)
            if preprocess_result is not None and (
                getattr(preprocess_result, "should_block", False) or not getattr(preprocess_result, "success", True)
            ):
                return ShortcutExecutor._preprocessing_result_to_command_result(
                    preprocess_result,
                    panel_size=ShortcutExecutor._command_panel_size(shortcut),
                )
        return None

    @staticmethod
    def _python_launcher() -> str | None:
        """Return a Python executable suitable for user scripts."""
        if not ShortcutExecutor._is_packaged_runtime() and sys.executable:
            resolved = ShortcutExecutor._resolve_long_path(sys.executable)
            if os.path.isfile(resolved):
                return resolved
        return ShortcutExecutor._find_system_python_launcher()

    @staticmethod
    def _is_packaged_runtime() -> bool:
        executable = os.path.basename(sys.executable or "").lower()
        return bool(getattr(sys, "frozen", False)) or (executable.endswith(".exe") and "python" not in executable)

    @staticmethod
    def _app_install_dir() -> str:
        if ShortcutExecutor._is_packaged_runtime():
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @staticmethod
    def _probe_python_launcher(candidate: str) -> bool:
        try:
            completed = subprocess.run(
                [candidate, "-c", "import sys; print(sys.version_info[0])"],
                capture_output=True,
                text=True,
                timeout=2.0,
                shell=False,
            )
            return completed.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _resolve_long_path(path: str) -> str:
        """Convert a Windows short (8.3) path to its long form."""
        if os.name != "nt" or not path:
            return path
        try:
            buf = ctypes.create_unicode_buffer(4096)
            result = ctypes.windll.kernel32.GetLongPathNameW(path, buf, 4096)
            if 0 < result < 4096:
                return buf.value
        except Exception as exc:
            logger.debug("获取长路径名失败: %s", exc, exc_info=True)
        # If GetLongPathNameW fails (e.g. 8.3 names disabled on this volume),
        # verify the path actually exists — a stale short-path will break .cmd wrappers.
        if not os.path.exists(path):
            logger.debug("_resolve_long_path: path does not exist after GetLongPathNameW: %s", path)
        return path

    @staticmethod
    def _find_system_python_launcher() -> str | None:
        candidates = [shutil.which("py"), shutil.which("python3"), shutil.which("python")]
        app_dir = os.path.normcase(
            ShortcutExecutor._resolve_long_path(os.path.abspath(ShortcutExecutor._app_install_dir()))
        )
        for candidate in candidates:
            if not candidate:
                continue
            long_path = ShortcutExecutor._resolve_long_path(os.path.abspath(candidate))
            norm = os.path.normcase(long_path)
            candidate_dir = os.path.normcase(os.path.dirname(long_path))
            if "windowsapps" in norm or (ShortcutExecutor._is_packaged_runtime() and candidate_dir == app_dir):
                continue
            if ShortcutExecutor._is_packaged_runtime() and not ShortcutExecutor._probe_python_launcher(long_path):
                continue
            return long_path
        return None

    @staticmethod
    def _python_launcher_error() -> str:
        return (
            "找不到可用的系统 Python。打包版不能直接复用程序目录内的 python312.dll；请安装系统 Python 或 py launcher。"
        )

    @staticmethod
    def _powershell_launcher() -> str | None:
        candidates = [
            shutil.which("powershell.exe"),
            shutil.which("powershell"),
            shutil.which("pwsh.exe"),
            shutil.which("pwsh"),
        ]
        if os.name == "nt":
            system_root = os.environ.get("SystemRoot", r"C:\Windows")
            candidates.extend(
                [
                    os.path.join(system_root, "Sysnative", "WindowsPowerShell", "v1.0", "powershell.exe"),
                    os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
                ]
            )
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return ShortcutExecutor._resolve_long_path(os.path.abspath(candidate))
        return None

    @staticmethod
    def _powershell_launcher_error() -> str:
        return "PowerShell is not available. Install Windows PowerShell or add powershell.exe to PATH."

    @staticmethod
    def _encode_powershell_command(command: str) -> str:
        """Encode PowerShell text for -EncodedCommand without writing a script file."""
        return base64.b64encode(str(command or "").encode("utf-16le")).decode("ascii")

    @staticmethod
    def _powershell_argv(command: str, *, no_exit: bool = False) -> list[str]:
        powershell_exe = ShortcutExecutor._powershell_launcher()
        if not powershell_exe:
            raise FileNotFoundError(ShortcutExecutor._powershell_launcher_error())
        argv = [powershell_exe, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass"]
        if no_exit:
            argv.append("-NoExit")
        argv.extend(["-EncodedCommand", ShortcutExecutor._encode_powershell_command(command)])
        return argv

    @staticmethod
    def _direct_command_line_length(argv: list[str]) -> int:
        try:
            return len(subprocess.list2cmdline([str(part) for part in argv]))
        except Exception:
            return sum(len(str(part)) + 1 for part in argv)

    @staticmethod
    def _direct_command_line_too_long(argv: list[str]) -> bool:
        return (
            os.name == "nt"
            and ShortcutExecutor._direct_command_line_length(argv) > WINDOWS_DIRECT_COMMAND_LINE_MAX_CHARS
        )

    @staticmethod
    def _direct_command_line_length_error(command_type: str, argv: list[str]) -> str:
        label = {"cmd": "CMD", "powershell": "PowerShell", "bash": "Git Bash"}.get(command_type, command_type)
        length = ShortcutExecutor._direct_command_line_length(argv)
        return (
            f"{label} 命令过长，绝不落盘策略下无法直接运行。"
            f"当前命令行长度 {length}，上限 {WINDOWS_DIRECT_COMMAND_LINE_MAX_CHARS}。"
        )

    @staticmethod
    def _bash_launcher() -> str | None:
        """Find Git Bash executable."""
        candidates = []
        # 1. shutil.which
        candidates.append(shutil.which("bash"))
        # 2. Registry: GitForWindows InstallPath
        if os.name == "nt":
            try:
                import winreg

                for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    try:
                        key = winreg.OpenKey(hive, r"SOFTWARE\GitForWindows")
                        install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                        winreg.CloseKey(key)
                        if install_path:
                            candidates.append(os.path.join(install_path, "bin", "bash.exe"))
                    except (OSError, FileNotFoundError):
                        logger.debug("查找GitForWindows注册表项失败", exc_info=True)
            except ImportError:
                logger.debug("winreg模块不可用", exc_info=True)
            # 3. Common install paths
            program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
            program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            candidates.extend(
                [
                    os.path.join(program_files, "Git", "bin", "bash.exe"),
                    os.path.join(program_files_x86, "Git", "bin", "bash.exe"),
                ]
            )
            if local_appdata:
                candidates.append(os.path.join(local_appdata, "Programs", "Git", "bin", "bash.exe"))
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return ShortcutExecutor._resolve_long_path(os.path.abspath(candidate))
        return None

    @staticmethod
    def _bash_launcher_error() -> str:
        return "Git Bash is not available. Install Git for Windows or add bash.exe to PATH."

    @staticmethod
    def _bash_direct_capture_denied(text: str) -> bool:
        lowered = str(text or "").lower()
        return "signal pipe" in lowered or "win32 error 5" in lowered

    @staticmethod
    def _bash_direct_capture_denied_message(detail: str) -> str:
        return "Git Bash 直接捕获启动失败且在回退模式下也失败了。" + (f"\n\n{detail}" if detail else "")

    @staticmethod
    def _bash_write_script(command: str) -> str:
        """Write a bash script file to disk as fallback for pipe capture failures."""
        hash_ = hashlib.md5(command.encode("utf-8")).hexdigest()
        cache_dir = CommandExecutionMixin._get_cmd_cache_dir()
        path = os.path.join(cache_dir, f"{hash_}.sh")
        if not os.path.exists(path):
            _write_atomic(path, "#!/usr/bin/env bash\n" + command + "\n")
        return path

    @staticmethod
    def _bash_capture_via_script(
        command: str,
        cwd: str | None,
        env: dict,
        timeout_value: float,
        start: float,
        max_chars: int,
        panel_size: str,
        command_type: str,
        shortcut,
    ) -> CommandResult | None:
        """Fallback: write temp .sh script, run bash with script path, capture output.

        Simpler than the direct pipe path — uses communicate() without real-time
        streaming so it works around bash.exe console-attachment restrictions.
        Returns a CommandResult on success/failure, or None if the fallback also fails.
        """
        script_path = ShortcutExecutor._bash_write_script(command)
        try:
            bash_exe = ShortcutExecutor._bash_launcher()
            if not bash_exe or not os.path.exists(script_path):
                return None

            process = subprocess.Popen(
                [bash_exe, script_path],
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                shell=False,
                **ShortcutExecutor._capture_popen_platform_kwargs(),
            )

            timed_out = False
            try:
                stdout_bytes, stderr_bytes = process.communicate(timeout=timeout_value)
                returncode = process.returncode
            except subprocess.TimeoutExpired:
                ShortcutExecutor._terminate_process_tree(process)
                stdout_bytes, stderr_bytes = process.communicate()
                returncode = process.returncode
                timed_out = True

            return _bash_fallback_result(
                stdout_bytes,
                stderr_bytes,
                returncode,
                False,
                timed_out,
                shortcut,
                command,
                max_chars,
                panel_size,
                command_type,
                start,
            )
        except Exception:
            logger.error("Bash script fallback also failed", exc_info=True)
            return None
        finally:
            try:
                if os.path.exists(script_path):
                    os.remove(script_path)
            except Exception as exc:
                logger.debug("删除临时脚本失败: %s", exc, exc_info=True)

    @staticmethod
    def _bash_argv(command: str, *, login: bool = False) -> list[str]:
        bash_exe = ShortcutExecutor._bash_launcher()
        if not bash_exe:
            raise FileNotFoundError(ShortcutExecutor._bash_launcher_error())
        argv = [bash_exe]
        if login:
            argv.append("--login")
        argv.extend(["-c", command])
        return argv

    _CMD_CACHE_DIR: str | None = None
    _CMD_CACHE_DIR_LOCK = threading.Lock()

    @classmethod
    def _get_cmd_cache_dir(cls) -> str:
        if cls._CMD_CACHE_DIR is None:
            with cls._CMD_CACHE_DIR_LOCK:
                if cls._CMD_CACHE_DIR is None:
                    cache_dir = os.path.join(tempfile.gettempdir(), "QuickLauncher", "cmd_cache")
                    os.makedirs(cache_dir, exist_ok=True)
                    cls._CMD_CACHE_DIR = cache_dir
        return cls._CMD_CACHE_DIR

    @classmethod
    def _cleanup_cmd_cache(cls) -> None:
        """Clean all cached wrapper scripts. Safe to call multiple times."""
        cache_dir = cls._get_cmd_cache_dir()
        for fname in os.listdir(cache_dir):
            fpath = os.path.join(cache_dir, fname)
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
            except Exception as exc:
                logger.debug("删除缓存文件失败 %s: %s", fpath, exc, exc_info=True)

    @staticmethod
    def _write_temp_python_script(command: str) -> str:
        hash_ = hashlib.md5(command.encode("utf-8")).hexdigest()
        cache_dir = CommandExecutionMixin._get_cmd_cache_dir()
        path = os.path.join(cache_dir, f"{hash_}.py")
        if not os.path.exists(path):
            _write_atomic(path, command)
        return path

    @staticmethod
    def _is_qt_main_thread() -> bool:
        try:
            from qt_compat import QApplication, QThread

            app = QApplication.instance()
            return bool(app and QThread.currentThread() == app.thread())
        except Exception:
            return False

    @staticmethod
    def _cleanup_file_later(process, *paths: str):
        def cleanup():
            try:
                if process is not None:
                    process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                ShortcutExecutor._terminate_process_tree(process)
                try:
                    process.wait(timeout=2.0)
                except Exception as exc:
                    logger.debug("等待进程终止失败: %s", exc, exc_info=True)
            except Exception as exc:
                logger.debug("清理进程失败: %s", exc, exc_info=True)
            for path in paths:
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except Exception as e:
                    logger.debug("临时文件清理失败 %s: %s", path, e)

        threading.Thread(target=cleanup, daemon=True, name="CommandTempCleanup").start()

    @staticmethod
    def _terminate_process_tree(process) -> None:
        """Terminate a process and, on Windows, best-effort terminate children."""
        if process is None:
            return
        pid = getattr(process, "pid", None)
        try:
            process.kill()
        except Exception as exc:
            logger.debug("终止进程失败: %s", exc, exc_info=True)
        if os.name != "nt" or not pid:
            return
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=3,
                check=False,
            )
        except Exception as e:
            logger.debug("Failed to terminate command process tree pid=%s: %s", pid, e)

    @staticmethod
    def _run_silent_output(argv: list[str]) -> str:
        """静默执行命令并获取输出"""
        if os.name != "nt":
            return ""

        try:
            startupinfo = ShortcutExecutor._get_silent_startupinfo()
            creationflags = ShortcutExecutor._get_silent_creationflags()

            # 关键：对于 PowerShell，即使设置了 Hidden WindowStyle，
            # 如果不通过 shell=True 启动，有时仍会短暂显示控制台。
            # 但 shell=True 本身又会引入 cmd.exe 窗口。
            # 最好的办法是直接调用 powershell.exe 并通过 startupinfo 隐藏。

            process = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
                startupinfo=startupinfo,
                shell=False,  # 确保不启动 cmd.exe
            )
            stdout, _ = process.communicate()
            return stdout
        except Exception as e:
            logger.debug(f"静默执行失败: {e}")
            return ""

    @staticmethod
    def _capture_popen_platform_kwargs() -> dict:
        """Windows GUI builds need explicit no-window flags for captured console commands."""
        if os.name != "nt":
            return {}

        kwargs = {}
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = startupinfo
        except Exception as exc:
            logger.debug("设置进程启动信息失败: %s", exc, exc_info=True)

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if creationflags:
            kwargs["creationflags"] = creationflags
        return kwargs

    @staticmethod
    def _execute_command(shortcut: ShortcutItem) -> tuple[bool, str]:
        """执行命令类型快捷方式"""
        command = shortcut.command
        if not command:
            logger.warning("命令为空")
            return False, "命令内容为空"

        command_type = ShortcutExecutor._normalize_command_type(getattr(shortcut, "command_type", "cmd"))
        raw_mode = bool(getattr(shortcut, "raw_mode", False))
        if command_type in ("cmd", "powershell", "bash") and not raw_mode and is_value_only_variable_command(command):
            if ShortcutExecutor._should_expand_command_variables(shortcut):
                return False, f"命令只包含值占位符，不能直接执行。请改为可执行命令，例如: echo {command}"
            return (
                False,
                f"命令只包含变量占位符，但未启用解析变量。请启用解析变量，或改为可执行命令，例如: echo {command}",
            )
        _shell_types = ("cmd", "powershell", "bash")
        if command_type in _shell_types and ShortcutExecutor._should_expand_command_variables(shortcut):
            unsafe_variables = find_unquoted_external_command_variables(command)
            if unsafe_variables:
                examples = ", ".join("{{" + name + ":q}}" for name in unsafe_variables[:3])
                return False, f"外部输入变量用于 CMD/PowerShell/Bash 命令时必须使用 :q 引用，例如: {examples}"
        try:
            if ShortcutExecutor._should_expand_command_variables(shortcut):
                command = ShortcutExecutor._resolve_command_variables(shortcut, command)
        except CommandVariableError as e:
            return False, str(e)

        capture_output = bool(getattr(shortcut, "capture_output", False))
        if not capture_output:
            confirmation = ShortcutExecutor._destructive_confirmation_result(shortcut, command, command_type)
            if confirmation is not None:
                set_pending_command_result(confirmation)
                return False, confirmation.message or confirmation.error
        preflight = ShortcutExecutor._preflight_command(
            shortcut,
            command,
            command_type,
            capture=False,
            preprocess=not capture_output,
        )
        if preflight is not None:
            set_pending_command_result(preflight)
            return False, preflight.message or preflight.error
        if (
            capture_output
            and command_type in ("cmd", "python", "powershell", "bash")
            and not bool(getattr(shortcut, "show_window", False))
            and not bool(getattr(shortcut, "run_as_admin", False))
        ):
            result = ShortcutExecutor.run_command_capture(shortcut)
            set_pending_command_result(result)
            return result.success, result.error

        # PowerShell command execution
        if command_type == "powershell":
            try:
                show_window = getattr(shortcut, "show_window", False)
                run_as_admin = getattr(shortcut, "run_as_admin", False)
                cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
                argv = ShortcutExecutor._powershell_argv(command, no_exit=show_window)
                if ShortcutExecutor._direct_command_line_too_long(argv):
                    return False, ShortcutExecutor._direct_command_line_length_error(command_type, argv)
                show_cmd = 1 if show_window else 0
                if os.name == "nt":
                    launched, launch_error = ShortcutExecutor._launch_with_privilege(
                        argv[0],
                        subprocess.list2cmdline(argv[1:]),
                        cwd,
                        show_cmd=show_cmd,
                        run_as_admin=run_as_admin,
                        admin_failure_message="Administrator launch failed.",
                    )
                    if launched:
                        return True, ""
                    if launch_error:
                        return False, launch_error
                if show_window:
                    subprocess.Popen(argv, cwd=cwd, env=ShortcutExecutor._runtime_env(shortcut), shell=False)
                else:
                    ShortcutExecutor._popen_silent(
                        argv,
                        cwd=cwd,
                        env=ShortcutExecutor._runtime_env(shortcut),
                        shell=False,
                    )
                return True, ""
            except FileNotFoundError:
                return False, ShortcutExecutor._powershell_launcher_error()
            except Exception as e:
                return False, f"PowerShell command launch failed: {e}"

        # Git Bash 命令执行
        if command_type == "bash":
            show_window = getattr(shortcut, "show_window", False)
            run_as_admin = getattr(shortcut, "run_as_admin", False)
            cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
            bash_env = ShortcutExecutor._runtime_env(shortcut)
            bash_env["LANG"] = "en_US.UTF-8"
            if show_window:
                try:
                    bash_exe = ShortcutExecutor._bash_launcher()
                    if not bash_exe:
                        return False, ShortcutExecutor._bash_launcher_error()
                    logger.debug("Bash show-window: launcher=%s, route=shell-execute", bash_exe)
                    bash_cmd = command
                    argv = ShortcutExecutor._bash_argv(bash_cmd, login=True)
                    if ShortcutExecutor._direct_command_line_too_long(argv):
                        return False, ShortcutExecutor._direct_command_line_length_error(command_type, argv)
                    if os.name == "nt":
                        launched, launch_error = ShortcutExecutor._launch_with_privilege(
                            bash_exe,
                            subprocess.list2cmdline(["--login", "-c", bash_cmd]),
                            cwd,
                            show_cmd=1,
                            run_as_admin=run_as_admin,
                            admin_failure_message="Administrator launch failed.",
                        )
                        if launched:
                            return True, ""
                        if launch_error:
                            return False, launch_error
                    argv = ShortcutExecutor._bash_argv(bash_cmd, login=True)
                    process = subprocess.Popen(argv, cwd=cwd, env=bash_env, shell=False)
                    return True, ""
                except FileNotFoundError:
                    return False, ShortcutExecutor._bash_launcher_error()
                except Exception as e:
                    return False, f"Bash command launch failed: {e}"
            # silent mode — use _popen_silent with DETACHED_PROCESS so the
            # console window never appears (ShellExecute show_cmd=0 can flash)
            try:
                bash_exe = ShortcutExecutor._bash_launcher()
                if not bash_exe:
                    return False, ShortcutExecutor._bash_launcher_error()
                logger.debug("Bash silent: launcher=%s, route=popen-silent", bash_exe)
                bash_cmd = command
                argv = ShortcutExecutor._bash_argv(bash_cmd, login=False)
                if ShortcutExecutor._direct_command_line_too_long(argv):
                    return False, ShortcutExecutor._direct_command_line_length_error(command_type, argv)
                ShortcutExecutor._popen_silent(
                    argv,
                    cwd=cwd,
                    env=bash_env,
                    shell=False,
                )
                return True, ""
            except FileNotFoundError:
                return False, ShortcutExecutor._bash_launcher_error()
            except Exception as e:
                return False, f"Bash command launch failed: {e}"

        # Python 代码执行
        if command_type == "python":
            show_window = getattr(shortcut, "show_window", False)
            if show_window:
                tmp_path = None
                try:
                    if not ShortcutExecutor._python_launcher():
                        return False, ShortcutExecutor._python_launcher_error()
                    tmp_path = ShortcutExecutor._write_temp_python_script(command)
                    python_exe = ShortcutExecutor._python_launcher()
                    if not python_exe:
                        return False, ShortcutExecutor._python_launcher_error()
                    run_as_admin = getattr(shortcut, "run_as_admin", False)
                    cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
                    if os.name == "nt":
                        launched, launch_error = ShortcutExecutor._launch_with_privilege(
                            python_exe,
                            subprocess.list2cmdline([tmp_path]),
                            cwd,
                            show_cmd=1,
                            run_as_admin=run_as_admin,
                            admin_failure_message="Administrator launch failed.",
                        )
                        if launched:
                            return True, ""
                        if launch_error:
                            return False, launch_error
                    process = subprocess.Popen(
                        [python_exe, tmp_path],
                        cwd=cwd,
                        env=ShortcutExecutor._runtime_env(shortcut),
                        shell=False,
                    )
                    ShortcutExecutor._cleanup_file_later(process, tmp_path)
                    return True, ""
                except FileNotFoundError:
                    try:
                        if tmp_path and os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception as exc:
                        logger.debug("删除临时Python文件失败: %s", exc, exc_info=True)
                    return False, ShortcutExecutor._python_launcher_error()
                except Exception as e:
                    try:
                        if tmp_path and os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception as exc:
                        logger.debug("删除临时Python文件失败: %s", exc, exc_info=True)
                    return False, f"Python 代码执行失败: {e}"
            try:
                python_exe = ShortcutExecutor._python_launcher()
                if not python_exe:
                    raise FileNotFoundError(ShortcutExecutor._python_launcher_error())

                def _launch_python_stdin():
                    try:
                        si = ShortcutExecutor._get_silent_startupinfo()
                        cf = ShortcutExecutor._get_silent_creationflags(shell=False)
                        cwd_dir = (getattr(shortcut, "working_dir", "") or "").strip() or None
                        env_dict = ShortcutExecutor._runtime_env(shortcut)
                        try:
                            process = subprocess.Popen(
                                [python_exe],
                                stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                cwd=cwd_dir,
                                env=env_dict,
                                startupinfo=si,
                                creationflags=cf,
                            )
                            process.communicate(input=command.encode("utf-8"))
                        except OSError:
                            CREATE_BREAKAWAY_FROM_JOB = 0x01000000
                            if cf and (cf & CREATE_BREAKAWAY_FROM_JOB):
                                cf2 = cf & ~CREATE_BREAKAWAY_FROM_JOB
                                process = subprocess.Popen(
                                    [python_exe],
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    cwd=cwd_dir,
                                    env=env_dict,
                                    startupinfo=si,
                                    creationflags=cf2,
                                )
                                process.communicate(input=command.encode("utf-8"))
                            else:
                                raise
                    except Exception as e:
                        logger.error(f"Python stdin exec failed: {e}")

                threading.Thread(target=_launch_python_stdin, daemon=True, name="PythonStdinExec").start()
                logger.debug("执行命令(Silent Python stdin): %s", command)
                return True, ""
            except FileNotFoundError:
                return False, ShortcutExecutor._python_launcher_error()
            except Exception as e:
                return False, f"Python 代码启动失败: {e}"

        # 内置命令
        elif command_type == "builtin":
            success = ShortcutExecutor._execute_builtin_command(command)
            return success, "" if success else "内置命令执行失败"

        # CMD 命令 (默认为 silent)
        else:
            error_msg = ""
            process = None
            run_as_admin = getattr(shortcut, "run_as_admin", False)
            show_window = getattr(shortcut, "show_window", False)
            show_cmd = 1 if show_window else 0
            if ShortcutExecutor._cmd_has_newline(command) and not show_window and not run_as_admin:
                try:
                    cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
                    argv = ShortcutExecutor._cmd_stdin_argv()
                    process = subprocess.Popen(
                        argv,
                        cwd=cwd,
                        env=ShortcutExecutor._runtime_env(shortcut),
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        shell=False,
                        startupinfo=getattr(ShortcutExecutor, "_get_silent_startupinfo", lambda: None)(),
                        creationflags=getattr(ShortcutExecutor, "_get_silent_creationflags", lambda: 0)(),
                    )
                    stdin_pipe = getattr(process, "stdin", None)
                    if stdin_pipe is not None:
                        stdin_pipe.write(ShortcutExecutor._cmd_stdin_script(command))
                        stdin_pipe.close()
                    logger.debug("执行命令(Silent CMD stdin): %s", command)
                    return True, ""
                except Exception as e:
                    error_msg = f"命令启动失败: {e}"
                    logger.error(error_msg)
                    return False, error_msg

            try:
                # 运行CMD命令
                parsed = ShortcutExecutor._safe_split_args(command)
                exe_path = parsed[0] if parsed else ""

                # 尝试检测是否为直接的可执行文件
                if exe_path and exe_path.lower().endswith(".exe") and os.path.exists(exe_path):
                    if ShortcutExecutor._direct_command_line_too_long(parsed):
                        return False, ShortcutExecutor._direct_command_line_length_error("cmd", parsed)
                    exe_dir = os.path.dirname(os.path.abspath(exe_path))
                    cwd = (getattr(shortcut, "working_dir", "") or "").strip()

                    if os.name == "nt":
                        parameters = subprocess.list2cmdline(parsed[1:]) if len(parsed) > 1 else ""
                        launched, launch_error = ShortcutExecutor._launch_with_privilege(
                            exe_path,
                            parameters or None,
                            cwd or exe_dir or None,
                            show_cmd=show_cmd,
                            run_as_admin=run_as_admin,
                            admin_failure_message="Administrator launch failed.",
                        )
                        if launched:
                            logger.debug(f"Launch via ShellExecute: {exe_path}")
                            return True, ""
                        if launch_error:
                            return False, launch_error
                    if show_window:
                        process = subprocess.Popen(parsed, cwd=cwd or exe_dir or None)
                    else:
                        process = ShortcutExecutor._popen_silent(
                            parsed, cwd=cwd or exe_dir or None, env=ShortcutExecutor._runtime_env(shortcut), shell=False
                        )
                    logger.debug(f"执行程序({'Visible' if show_window else 'Silent'}): {exe_path}")
                else:
                    # 通过 cmd.exe 直接传入原始命令文本；单行/多行都不写临时 .cmd。
                    cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
                    argv = ShortcutExecutor._cmd_argv(command, keep_open=show_window)
                    if ShortcutExecutor._direct_command_line_too_long(argv):
                        return False, ShortcutExecutor._direct_command_line_length_error("cmd", argv)

                    if os.name == "nt":
                        launched, launch_error = ShortcutExecutor._launch_with_privilege(
                            argv[0],
                            subprocess.list2cmdline(argv[1:]),
                            cwd,
                            show_cmd=show_cmd,
                            run_as_admin=run_as_admin,
                            admin_failure_message="Administrator launch failed.",
                        )
                        if launched:
                            logger.debug(f"Command via ShellExecute: {command}")
                            return True, ""
                        if launch_error:
                            return False, launch_error

                    if show_window:
                        process = subprocess.Popen(
                            argv, cwd=cwd, env=ShortcutExecutor._runtime_env(shortcut), shell=False
                        )
                    else:
                        process = ShortcutExecutor._popen_silent(
                            argv, cwd=cwd, env=ShortcutExecutor._runtime_env(shortcut), shell=False
                        )
                    logger.debug(f"执行命令({'Visible' if show_window else 'Silent'} CMD): {command}")

            except Exception as e:
                error_msg = f"命令启动失败: {e}"
                logger.error(error_msg)

            # 焦点恢复移到后台线程，避免主线程阻塞
            if process is not None:

                def _restore_focus(proc=process):
                    try:
                        proc.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        logger.debug("命令进程超时未完成，继续执行焦点恢复")
                    except Exception as e:
                        logger.debug(f"等待命令进程时出错: {e}")
                    time.sleep(0.05)
                    try:
                        ShortcutExecutor.restore_foreground_window()
                        logger.debug("CMD 命令执行后：已恢复焦点")
                    except Exception as e:
                        logger.debug(f"CMD 命令执行后恢复焦点失败: {e}")

                threading.Thread(target=_restore_focus, daemon=True, name="FocusRestore").start()

            return (process is not None), error_msg

    @staticmethod
    def _resolve_command_variables(shortcut: ShortcutItem, command: str) -> str:
        if not ShortcutExecutor._should_expand_command_variables(shortcut):
            return command
        input_values = getattr(shortcut, "_runtime_input_values", None)
        selected_provider = None
        if getattr(shortcut, "trigger_mode", "immediate") == "after_close":
            selected_provider = ShortcutExecutor._capture_selected_text
        command_type = ShortcutExecutor._normalize_command_type(getattr(shortcut, "command_type", "cmd"))
        return resolve_command_variables(
            command,
            input_values=input_values,
            param_values=ShortcutExecutor._command_param_values(shortcut),
            chain_values=ShortcutExecutor._chain_values(shortcut),
            selected_files=getattr(shortcut, "_runtime_selected_files", None),
            clipboard_provider=read_clipboard_text,
            selected_text_provider=selected_provider,
            strict_unknown=True,
            bash_mode=(command_type == "bash"),
            powershell_mode=(command_type == "powershell"),
        )

    @staticmethod
    def _should_expand_command_variables(shortcut: ShortcutItem) -> bool:
        command_type = ShortcutExecutor._normalize_command_type(getattr(shortcut, "command_type", "cmd"))
        if bool(getattr(shortcut, "raw_mode", False)):
            return False
        enabled = getattr(shortcut, "command_variables_enabled", None)
        if ShortcutExecutor._command_param_defs(shortcut) or ShortcutExecutor._chain_values(shortcut):
            return command_type != "builtin"
        return should_expand_command_variables(command_type, enabled)

    @staticmethod
    def _capture_selected_text() -> str:
        """Copy selected text from the previous foreground window and restore clipboard."""
        from .clipboard_service import clipboard_service

        snapshot = clipboard_service.read_snapshot()
        original_text = clipboard_service.read_text_win32()
        original_sequence = clipboard_service.get_sequence_number()
        try:
            try:
                ShortcutExecutor.restore_foreground_window_fast(timeout_ms=300)
            except Exception:
                ShortcutExecutor.restore_foreground_window()
            time.sleep(0.08)
            if hasattr(ShortcutExecutor, "_execute_hotkey_sendinput"):
                ShortcutExecutor._execute_hotkey_sendinput(["ctrl"], "c")
            else:
                return ""
            for _ in range(12):
                time.sleep(0.03)
                if clipboard_service.get_sequence_number() != original_sequence:
                    break
            if clipboard_service.get_sequence_number() == original_sequence:
                return ""
            return clipboard_service.read_text_win32()
        finally:
            if not clipboard_service.restore_snapshot(snapshot):
                try:
                    clipboard_service.write_text(original_text)
                except Exception as exc:
                    logger.debug("恢复剪贴板文本失败: %s", exc, exc_info=True)

    @staticmethod
    def _get_clipboard_sequence_number() -> int:
        from .clipboard_service import clipboard_service

        return clipboard_service.get_sequence_number()

    @staticmethod
    def _snapshot_clipboard():
        from .clipboard_service import clipboard_service

        return clipboard_service.read_snapshot()

    @staticmethod
    def _restore_clipboard_snapshot(snapshot) -> bool:
        from .clipboard_service import clipboard_service

        return clipboard_service.restore_snapshot(snapshot)

    @staticmethod
    def _write_clipboard_text(text: str) -> bool:
        from .clipboard_service import clipboard_service

        return clipboard_service.write_text(text)

    @staticmethod
    def _open_builtin_directory(command: str) -> bool:
        try:
            if command == "open_data_dir":
                path = os.path.join(ShortcutExecutor._app_install_dir(), "config")
            else:
                path = ShortcutExecutor._app_install_dir()
            path = os.path.abspath(path)
            os.makedirs(path, exist_ok=True)
            os.startfile(path)
            logger.info("已打开内置目录: %s", path)
            return True
        except Exception as e:
            logger.error("打开内置目录失败 %s: %s", command, e, exc_info=True)
            return False

    @staticmethod
    def _open_filesystem_target(path: str, create_dir: bool = False, fallback_to_parent: bool = True) -> bool:
        try:
            path = os.path.abspath(path)
            if create_dir:
                os.makedirs(path, exist_ok=True)
            elif not os.path.exists(path):
                if not fallback_to_parent:
                    return False
                parent = os.path.dirname(path)
                os.makedirs(parent, exist_ok=True)
                path = parent

            opener = getattr(os, "startfile", None)
            if callable(opener):
                opener(path)
                logger.debug("Opened built-in filesystem target: %s", path)
                return True
            return ShortcutExecutor._shell_execute_open(path)
        except Exception as e:
            logger.error("Open built-in filesystem target failed %s: %s", path, e, exc_info=True)
            return False

    @staticmethod
    def _open_builtin_text_file(path: str) -> bool:
        path = os.path.abspath(path)
        if not os.path.exists(path):
            return ShortcutExecutor._open_filesystem_target(path, create_dir=False)

        if os.name == "nt":
            try:
                params = subprocess.list2cmdline([path])
                if ShortcutExecutor._shell_execute_open("notepad.exe", params):
                    logger.info("Opened built-in text file via notepad: %s", path)
                    return True
            except Exception:
                logger.debug("Opening built-in text file via notepad failed: %s", path, exc_info=True)

        return ShortcutExecutor._open_filesystem_target(
            path,
            create_dir=False,
            fallback_to_parent=False,
        )

    @staticmethod
    def _open_builtin_filesystem_target(command: str) -> bool:
        install_dir = ShortcutExecutor._app_install_dir()
        config_dir = os.path.join(install_dir, "config")
        targets = {
            "open_data_dir": (config_dir, True),
            "open_install_dir": (install_dir, True),
            "open_config_file": (os.path.join(config_dir, "data.json"), False),
            "open_icons_dir": (os.path.join(install_dir, "icons"), True),
            "open_history_dir": (os.path.join(config_dir, "history"), True),
            "open_auto_backups_dir": (os.path.join(config_dir, "auto_backups"), True),
            "open_error_log": (os.path.join(config_dir, "error.log"), False),
        }
        target = targets.get(command)
        if not target:
            return False
        path, create_dir = target
        if command in {"open_config_file", "open_error_log"}:
            return ShortcutExecutor._open_builtin_text_file(path)
        return ShortcutExecutor._open_filesystem_target(path, create_dir=create_dir)

    @staticmethod
    def _open_windows_system_builtin(command: str) -> bool:
        if command == "open_windows_settings":
            if ShortcutExecutor._shell_execute_open("ms-settings:"):
                return True
            try:
                opener = getattr(os, "startfile", None)
                if callable(opener):
                    opener("ms-settings:")
                    return True
            except Exception:
                logger.debug("os.startfile(ms-settings:) failed", exc_info=True)

        specs = {
            "open_control_panel": ("control.exe", None, ["control.exe"]),
            "open_this_pc": ("explorer.exe", "shell:MyComputerFolder", ["explorer.exe", "shell:MyComputerFolder"]),
            "open_recycle_bin": ("explorer.exe", "shell:RecycleBinFolder", ["explorer.exe", "shell:RecycleBinFolder"]),
            "open_task_manager": ("taskmgr.exe", None, ["taskmgr.exe"]),
            "open_services": ("services.msc", None, ["mmc.exe", "services.msc"]),
            "open_device_manager": ("devmgmt.msc", None, ["mmc.exe", "devmgmt.msc"]),
            "open_disk_management": ("diskmgmt.msc", None, ["mmc.exe", "diskmgmt.msc"]),
            "open_network_connections": ("control.exe", "ncpa.cpl", ["control.exe", "ncpa.cpl"]),
            "open_startup_folder": ("explorer.exe", "shell:startup", ["explorer.exe", "shell:startup"]),
            "open_system_info": ("msinfo32.exe", None, ["msinfo32.exe"]),
        }
        spec = specs.get(command)
        if not spec:
            return False

        target, parameters, fallback_argv = spec
        if ShortcutExecutor._shell_execute_open(target, parameters):
            return True
        try:
            ShortcutExecutor._popen_silent(
                fallback_argv,
                env=ShortcutExecutor._sanitized_child_env(),
            )
            return True
        except Exception as e:
            logger.error("Open Windows built-in command failed %s: %s", command, e)
        return False

    @staticmethod
    def _truncate_output(text: str, max_chars: int) -> tuple[str, bool]:
        return truncate_command_output(text, max_chars)

    @staticmethod
    def run_command_capture(
        shortcut: ShortcutItem,
        timeout: float | None = None,
        cancel_event: threading.Event | None = None,
        on_update=None,
    ) -> CommandResult:
        """Run a CMD/PowerShell/Python/Git Bash/builtin command and return captured output."""
        start = time.monotonic()
        command = shortcut.command or ""
        command_type = ShortcutExecutor._normalize_command_type(getattr(shortcut, "command_type", "cmd"))
        max_chars = getattr(shortcut, "command_output_max_chars", DEFAULT_COMMAND_OUTPUT_MAX_CHARS)
        panel_size = ShortcutExecutor._command_panel_size(shortcut)
        timeout_value = normalize_command_timeout_seconds(
            timeout
            if timeout is not None
            else getattr(shortcut, "command_timeout_seconds", DEFAULT_COMMAND_TIMEOUT_SECONDS)
        )

        raw_mode = bool(getattr(shortcut, "raw_mode", False))
        if command_type in ("cmd", "powershell", "bash") and not raw_mode and is_value_only_variable_command(command):
            if ShortcutExecutor._should_expand_command_variables(shortcut):
                return CommandResult(
                    success=False,
                    message=f"命令只包含值占位符，不能直接执行。请改为可执行命令，例如: echo {command}",
                    display_type="log",
                    error="命令无效",
                    payload={"window_size": panel_size},
                )
            return CommandResult(
                success=False,
                message=(
                    "命令只包含变量占位符，但未启用解析变量。" f"请启用解析变量，或改为可执行命令，例如: echo {command}"
                ),
                display_type="log",
                error="命令无效",
                payload={"window_size": panel_size},
            )
        _shell_types = ("cmd", "powershell", "bash")
        if command_type in _shell_types and ShortcutExecutor._should_expand_command_variables(shortcut):
            unsafe_variables = find_unquoted_external_command_variables(command)
            if unsafe_variables:
                examples = ", ".join("{{" + name + ":q}}" for name in unsafe_variables[:3])
                message = f"外部输入变量用于 CMD/PowerShell/Bash 命令时必须使用 :q 引用，例如: {examples}"
                return CommandResult(
                    success=False,
                    message=message,
                    display_type="log",
                    error=message,
                    payload={"window_size": panel_size},
                )

        try:
            if ShortcutExecutor._should_expand_command_variables(shortcut):
                command = ShortcutExecutor._resolve_command_variables(shortcut, command)
        except CommandVariableError as e:
            return CommandResult(
                success=False,
                message=str(e),
                display_type="log",
                error="变量解析失败",
                payload={"window_size": panel_size},
            )

        cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
        if command_type == "builtin":
            success = ShortcutExecutor._execute_builtin_command(command)
            pending = take_pending_command_result()
            if pending is not None:
                pending.payload.setdefault("window_size", panel_size)
                return pending
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

        preflight = ShortcutExecutor._preflight_command(shortcut, command, command_type, capture=True)
        if preflight is not None:
            if isinstance(getattr(preflight, "payload", None), dict):
                preflight.payload.setdefault("window_size", panel_size)
            return preflight

        confirmation = ShortcutExecutor._destructive_confirmation_result(
            shortcut,
            command,
            command_type,
            panel_size=panel_size,
        )
        if confirmation is not None:
            return confirmation

        tmp_path = None
        stdin_data = None
        try:
            if command_type == "python":
                python_exe = ShortcutExecutor._python_launcher()
                if not python_exe:
                    return CommandResult(
                        success=False,
                        message=ShortcutExecutor._python_launcher_error(),
                        display_type="log",
                        error="Python 不可用",
                        payload={"window_size": panel_size},
                    )
                popen_args = [python_exe, "-u"]
                stdin_data = command.encode("utf-8")
                shell = False
            elif command_type == "powershell":
                popen_args = ShortcutExecutor._powershell_argv(command)
                if ShortcutExecutor._direct_command_line_too_long(popen_args):
                    message = ShortcutExecutor._direct_command_line_length_error(command_type, popen_args)
                    return CommandResult(
                        success=False,
                        message=message,
                        display_type="log",
                        error="命令过长",
                        payload={"window_size": panel_size, "duration": time.monotonic() - start},
                    )
                shell = False
            elif command_type == "bash":
                bash_exe = ShortcutExecutor._bash_launcher()
                if not bash_exe:
                    return CommandResult(
                        success=False,
                        message=ShortcutExecutor._bash_launcher_error(),
                        display_type="log",
                        error="Git Bash 不可用",
                        payload={"window_size": panel_size},
                    )
                logger.debug("Bash capture: launcher=%s, route=capture-direct", bash_exe)
                popen_args = ShortcutExecutor._bash_argv(command)
                if ShortcutExecutor._direct_command_line_too_long(popen_args):
                    message = ShortcutExecutor._direct_command_line_length_error(command_type, popen_args)
                    return CommandResult(
                        success=False,
                        message=message,
                        display_type="log",
                        error="命令过长",
                        payload={"window_size": panel_size, "duration": time.monotonic() - start},
                    )
                shell = False
            elif command_type == "cmd":
                if ShortcutExecutor._cmd_has_newline(command):
                    popen_args = ShortcutExecutor._cmd_stdin_argv()
                    stdin_data = ShortcutExecutor._cmd_stdin_script(command)
                else:
                    popen_args = ShortcutExecutor._cmd_argv(command)
                    if ShortcutExecutor._direct_command_line_too_long(popen_args):
                        message = ShortcutExecutor._direct_command_line_length_error(command_type, popen_args)
                        return CommandResult(
                            success=False,
                            message=message,
                            display_type="log",
                            error="命令过长",
                            payload={"window_size": panel_size, "duration": time.monotonic() - start},
                        )
                shell = False
            else:
                return CommandResult(
                    success=False,
                    message=f"Unsupported command type: {command_type}",
                    display_type="log",
                    error="Unsupported command type",
                    payload={"window_size": panel_size, "duration": time.monotonic() - start},
                )
            try:
                env = ShortcutExecutor._runtime_env(shortcut)
                process = subprocess.Popen(
                    popen_args,
                    cwd=cwd,
                    env=env,
                    stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=False,
                    shell=shell,
                    **ShortcutExecutor._capture_popen_platform_kwargs(),
                )
            except OSError as exc:
                if command_type == "bash" and ShortcutExecutor._bash_direct_capture_denied(str(exc)):
                    fallback = ShortcutExecutor._bash_capture_via_script(
                        command,
                        cwd,
                        env,
                        timeout_value,
                        start,
                        max_chars,
                        panel_size,
                        command_type,
                        shortcut,
                    )
                    if fallback is not None:
                        return fallback
                    message = ShortcutExecutor._bash_direct_capture_denied_message(str(exc))
                    return CommandResult(
                        success=False,
                        message=message,
                        display_type="log",
                        error=str(exc),
                        payload={
                            "window_size": panel_size,
                            "duration": time.monotonic() - start,
                            "command": command,
                        },
                    )
                else:
                    raise

            if on_update is not None:
                stdin_pipe = getattr(process, "stdin", None)
                if stdin_data is not None and stdin_pipe is not None:
                    stdin_pipe.write(stdin_data)
                    stdin_pipe.close()
                output_queue = queue.Queue()

                def _reader(pipe, name):
                    try:
                        while True:
                            chunk = pipe.readline()
                            if not chunk:
                                break
                            output_queue.put((name, chunk))
                    finally:
                        try:
                            pipe.close()
                        except Exception as exc:
                            logger.debug("关闭输出管道失败: %s", exc, exc_info=True)

                executor = ShortcutExecutor._get_executor()
                executor.submit(_reader, process.stdout, "stdout")
                executor.submit(_reader, process.stderr, "stderr")
                stdout_parts = []
                stderr_parts = []
                deadline = time.monotonic() + timeout_value
                last_update = 0.0
                timed_out = False
                cancelled = False

                while process.poll() is None or not output_queue.empty():
                    while True:
                        try:
                            name, chunk = output_queue.get_nowait()
                        except queue.Empty:
                            break
                        if name == "stdout":
                            stdout_parts.append(chunk)
                        else:
                            stderr_parts.append(chunk)

                    now = time.monotonic()
                    if (stdout_parts or stderr_parts) and now - last_update >= COMMAND_CAPTURE_UPDATE_INTERVAL_SECONDS:
                        update_stdout_bytes = b"".join(stdout_parts)
                        update_stderr_bytes = b"".join(stderr_parts)
                        if command_type == "cmd" and stdin_data is not None:
                            update_stdout_bytes = ShortcutExecutor._clean_cmd_stdin_output_bytes(update_stdout_bytes)
                            update_stderr_bytes = ShortcutExecutor._clean_cmd_stdin_output_bytes(update_stderr_bytes)
                        stdout, stdout_encoding, stdout_fallback = ShortcutExecutor._decode_bytes(
                            update_stdout_bytes, getattr(shortcut, "command_encoding", "auto"), command_type
                        )
                        stderr, stderr_encoding, stderr_fallback = ShortcutExecutor._decode_bytes(
                            update_stderr_bytes, getattr(shortcut, "command_encoding", "auto")
                        )
                        update_stdout, stdout_truncated = ShortcutExecutor._truncate_output(stdout or "", max_chars)
                        update_stderr, stderr_truncated = ShortcutExecutor._truncate_output(stderr or "", max_chars)
                        parts = []
                        if update_stdout:
                            parts.append(update_stdout)
                        # stderr 仅在命令最终失败时才显示（在最终结果中处理）
                        on_update(
                            CommandResult(
                                success=True,
                                message="\n".join(parts) or "执行中...",
                                display_type="log",
                                payload={
                                    "window_size": panel_size,
                                    "wrap": False,
                                    "duration": now - start,
                                    "stdout": update_stdout,
                                    "stderr": update_stderr,
                                    "stdout_truncated": stdout_truncated,
                                    "stderr_truncated": stderr_truncated,
                                    "stdout_encoding": stdout_encoding,
                                    "stderr_encoding": stderr_encoding,
                                    "decode_fallback_used": stdout_fallback or stderr_fallback,
                                    "command": command,
                                    "running": True,
                                },
                                cancellable=True,
                            )
                        )
                        last_update = now

                    if cancel_event is not None and cancel_event.is_set():
                        cancelled = True
                        ShortcutExecutor._terminate_process_tree(process)
                        break
                    if time.monotonic() >= deadline:
                        timed_out = True
                        ShortcutExecutor._terminate_process_tree(process)
                        break
                    time.sleep(COMMAND_CAPTURE_POLL_SECONDS)

                try:
                    process.wait(timeout=PROCESS_TERMINATE_WAIT_SECONDS)
                except Exception as exc:
                    logger.debug("等待进程结束失败: %s", exc, exc_info=True)
                while True:
                    try:
                        name, chunk = output_queue.get_nowait()
                    except queue.Empty:
                        break
                    if name == "stdout":
                        stdout_parts.append(chunk)
                    else:
                        stderr_parts.append(chunk)
                stdout_bytes = b"".join(stdout_parts)
                stderr_bytes = b"".join(stderr_parts)
                if command_type == "cmd" and stdin_data is not None:
                    stdout_bytes = ShortcutExecutor._clean_cmd_stdin_output_bytes(stdout_bytes)
                    stderr_bytes = ShortcutExecutor._clean_cmd_stdin_output_bytes(stderr_bytes)
                returncode = process.returncode
                if cancelled:
                    stdout, stdout_encoding, stdout_fallback = ShortcutExecutor._decode_bytes(
                        stdout_bytes or b"", getattr(shortcut, "command_encoding", "auto"), command_type
                    )
                    stderr, stderr_encoding, stderr_fallback = ShortcutExecutor._decode_bytes(
                        stderr_bytes or b"", getattr(shortcut, "command_encoding", "auto"), command_type
                    )
                    stdout, stdout_truncated = ShortcutExecutor._truncate_output(stdout or "", max_chars)
                    stderr, stderr_truncated = ShortcutExecutor._truncate_output(stderr or "", max_chars)
                    message = "\n".join(part for part in ["命令执行已取消。", stdout, stderr] if part)
                    return CommandResult(
                        success=False,
                        message=message,
                        display_type="log",
                        payload={
                            "window_size": panel_size,
                            "wrap": False,
                            "exit_code": returncode,
                            "duration": time.monotonic() - start,
                            "stdout": stdout,
                            "stderr": stderr,
                            "stdout_truncated": stdout_truncated,
                            "stderr_truncated": stderr_truncated,
                            "stdout_encoding": stdout_encoding,
                            "stderr_encoding": stderr_encoding,
                            "decode_fallback_used": stdout_fallback or stderr_fallback,
                            "command": command,
                            "cancelled": True,
                            "timed_out": False,
                        },
                        error="已取消",
                    )
                stdout, stdout_encoding, stdout_fallback = ShortcutExecutor._decode_bytes(
                    stdout_bytes or b"", getattr(shortcut, "command_encoding", "auto")
                )
                stderr, stderr_encoding, stderr_fallback = ShortcutExecutor._decode_bytes(
                    stderr_bytes or b"", getattr(shortcut, "command_encoding", "auto")
                )
                stdout, stdout_truncated = ShortcutExecutor._truncate_output(stdout or "", max_chars)
                stderr, stderr_truncated = ShortcutExecutor._truncate_output(stderr or "", max_chars)
                if command_type == "bash" and ShortcutExecutor._bash_direct_capture_denied(stderr):
                    fallback = ShortcutExecutor._bash_capture_via_script(
                        command,
                        cwd,
                        env,
                        timeout_value,
                        start,
                        max_chars,
                        panel_size,
                        command_type,
                        shortcut,
                    )
                    if fallback is not None:
                        return fallback
                    message = ShortcutExecutor._bash_direct_capture_denied_message(stderr.strip())
                    return CommandResult(
                        success=False,
                        message=message,
                        display_type="log",
                        payload={
                            "window_size": panel_size,
                            "wrap": False,
                            "exit_code": returncode,
                            "duration": time.monotonic() - start,
                            "stdout": stdout,
                            "stderr": stderr,
                            "stdout_truncated": stdout_truncated,
                            "stderr_truncated": stderr_truncated,
                            "stdout_encoding": stdout_encoding,
                            "stderr_encoding": stderr_encoding,
                            "decode_fallback_used": stdout_fallback or stderr_fallback,
                            "command": command,
                            "timed_out": timed_out,
                        },
                        actions=[CommandAction(type="copy", label="复制输出", value=message)],
                        error=stderr.strip().splitlines()[0] if stderr.strip() else "Git Bash 直接捕获启动失败",
                    )
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
                    payload={
                        "window_size": panel_size,
                        "wrap": False,
                        "exit_code": returncode,
                        "duration": time.monotonic() - start,
                        "stdout": stdout,
                        "stderr": stderr,
                        "stdout_truncated": stdout_truncated,
                        "stderr_truncated": stderr_truncated,
                        "stdout_encoding": stdout_encoding,
                        "stderr_encoding": stderr_encoding,
                        "decode_fallback_used": stdout_fallback or stderr_fallback,
                        "command": command,
                        "timed_out": timed_out,
                    },
                    actions=[CommandAction(type="copy", label="复制输出", value=message)],
                    error=error,
                )
            try:
                if cancel_event is None:
                    if stdin_data is None:
                        stdout_bytes, stderr_bytes = process.communicate(timeout=timeout_value)
                    else:
                        stdout_bytes, stderr_bytes = process.communicate(input=stdin_data, timeout=timeout_value)
                else:
                    stdin_pipe = getattr(process, "stdin", None)
                    if stdin_data is not None and stdin_pipe is not None:
                        stdin_pipe.write(stdin_data)
                        stdin_pipe.close()
                    deadline = time.monotonic() + timeout_value
                    while process.poll() is None:
                        if cancel_event.is_set():
                            ShortcutExecutor._terminate_process_tree(process)
                            stdout_bytes, stderr_bytes = process.communicate()
                            stdout, stdout_encoding, stdout_fallback = ShortcutExecutor._decode_bytes(
                                stdout_bytes or b"", getattr(shortcut, "command_encoding", "auto"), command_type
                            )
                            stderr, stderr_encoding, stderr_fallback = ShortcutExecutor._decode_bytes(
                                stderr_bytes or b"", getattr(shortcut, "command_encoding", "auto"), command_type
                            )
                            stdout, stdout_truncated = ShortcutExecutor._truncate_output(stdout or "", max_chars)
                            stderr, stderr_truncated = ShortcutExecutor._truncate_output(stderr or "", max_chars)
                            message = "\n".join(part for part in ["命令执行已取消。", stdout, stderr] if part)
                            return CommandResult(
                                success=False,
                                message=message,
                                display_type="log",
                                payload={
                                    "window_size": panel_size,
                                    "wrap": False,
                                    "exit_code": process.returncode,
                                    "duration": time.monotonic() - start,
                                    "stdout": stdout,
                                    "stderr": stderr,
                                    "stdout_truncated": stdout_truncated,
                                    "stderr_truncated": stderr_truncated,
                                    "stdout_encoding": stdout_encoding,
                                    "stderr_encoding": stderr_encoding,
                                    "decode_fallback_used": stdout_fallback or stderr_fallback,
                                    "command": command,
                                    "cancelled": True,
                                    "timed_out": False,
                                },
                                error="已取消",
                            )
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(popen_args, timeout_value)
                        time.sleep(min(COMMAND_CAPTURE_POLL_SECONDS, remaining))
                    stdout_bytes, stderr_bytes = process.communicate()
                returncode = process.returncode
                timed_out = False
            except subprocess.TimeoutExpired:
                ShortcutExecutor._terminate_process_tree(process)
                stdout_bytes, stderr_bytes = process.communicate()
                returncode = process.returncode
                timed_out = True

            if command_type == "cmd" and stdin_data is not None:
                stdout_bytes = ShortcutExecutor._clean_cmd_stdin_output_bytes(stdout_bytes)
                stderr_bytes = ShortcutExecutor._clean_cmd_stdin_output_bytes(stderr_bytes)

            stdout, stdout_encoding, stdout_fallback = ShortcutExecutor._decode_bytes(
                stdout_bytes or b"", getattr(shortcut, "command_encoding", "auto"), command_type
            )
            stderr, stderr_encoding, stderr_fallback = ShortcutExecutor._decode_bytes(
                stderr_bytes or b"", getattr(shortcut, "command_encoding", "auto"), command_type
            )
            stdout, stdout_truncated = ShortcutExecutor._truncate_output(stdout or "", max_chars)
            stderr, stderr_truncated = ShortcutExecutor._truncate_output(stderr or "", max_chars)
            if command_type == "bash" and ShortcutExecutor._bash_direct_capture_denied(stderr):
                fallback = ShortcutExecutor._bash_capture_via_script(
                    command,
                    cwd,
                    env,
                    timeout_value,
                    start,
                    max_chars,
                    panel_size,
                    command_type,
                    shortcut,
                )
                if fallback is not None:
                    return fallback
                message = ShortcutExecutor._bash_direct_capture_denied_message(stderr.strip())
                return CommandResult(
                    success=False,
                    message=message,
                    display_type="log",
                    payload={
                        "window_size": panel_size,
                        "wrap": False,
                        "exit_code": returncode,
                        "duration": time.monotonic() - start,
                        "stdout": stdout,
                        "stderr": stderr,
                        "stdout_truncated": stdout_truncated,
                        "stderr_truncated": stderr_truncated,
                        "stdout_encoding": stdout_encoding,
                        "stderr_encoding": stderr_encoding,
                        "decode_fallback_used": stdout_fallback or stderr_fallback,
                        "command": command,
                        "timed_out": timed_out,
                    },
                    actions=[CommandAction(type="copy", label="复制输出", value=message)],
                    error=stderr.strip().splitlines()[0] if stderr.strip() else "Git Bash 直接捕获启动失败",
                )
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
                payload={
                    "window_size": panel_size,
                    "wrap": False,
                    "exit_code": returncode,
                    "duration": time.monotonic() - start,
                    "stdout": stdout,
                    "stderr": stderr,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "stdout_encoding": stdout_encoding,
                    "stderr_encoding": stderr_encoding,
                    "decode_fallback_used": stdout_fallback or stderr_fallback,
                    "command": command,
                    "timed_out": timed_out,
                },
                actions=[CommandAction(type="copy", label="复制输出", value=message)],
                error=error,
            )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"命令捕获执行失败: {e}",
                display_type="log",
                error=str(e),
                payload={"window_size": panel_size, "duration": time.monotonic() - start},
            )
        finally:
            for _p in (tmp_path,):
                if _p:
                    try:
                        os.remove(_p)
                    except Exception as exc:
                        logger.debug("删除临时文件失败 %s: %s", _p, exc, exc_info=True)

    @staticmethod
    def test_command(shortcut: ShortcutItem, timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> dict:
        """Run a command shortcut synchronously for the editor test button."""
        old_timeout = getattr(shortcut, "command_timeout_seconds", DEFAULT_COMMAND_TIMEOUT_SECONDS)
        shortcut.command_timeout_seconds = timeout
        try:
            captured = ShortcutExecutor.run_command_capture(shortcut, timeout=timeout)
            payload = captured.payload if isinstance(captured.payload, dict) else {}
            return {
                "success": captured.success,
                "exit_code": payload.get("exit_code"),
                "stdout": payload.get("stdout", captured.message if captured.success else ""),
                "stderr": payload.get("stderr", ""),
                "error": captured.error,
                "duration": payload.get("duration", 0.0),
                "resolved_command": payload.get("command", ""),
            }
        finally:
            shortcut.command_timeout_seconds = old_timeout

    @staticmethod
    def _execute_builtin_command(command: str) -> bool:
        """执行内置命令"""
        from core.builtin_commands import (
            INTERNAL_PATH_BUILTIN_COMMANDS,
            UI_CALLBACK_BUILTIN_COMMANDS,
            WINDOWS_SYSTEM_BUILTIN_COMMANDS,
            canonical_builtin_command,
        )

        parts = command.strip().split(None, 1)
        cmd_name = parts[0].lower() if parts else ""
        args_text = parts[1] if len(parts) > 1 else ""

        # Phase 1/2: try CommandRegistry first for new-style commands
        try:
            from core import registry
            from core.command_registry import (
                _CallbackHandler,
                set_pending_command_result,
            )

            if registry is not None and registry.count() > 0:
                cmd_def = registry.get(cmd_name) or registry.get(canonical_builtin_command(cmd_name))
                if cmd_def is not None and not isinstance(cmd_def.handler, _CallbackHandler):
                    selected_files = []
                    try:
                        from core.file_selection import get_selected_files_for_process

                        selected_files = get_selected_files_for_process() or []
                    except Exception as exc:
                        logger.debug("获取选中文件失败: %s", exc, exc_info=True)

                    clipboard_text = ""
                    clipboard_kind = ""
                    clipboard_files: list[str] = []
                    try:
                        from .clipboard_service import clipboard_service

                        snapshot = clipboard_service.read_snapshot()
                        clipboard_text = snapshot.text or ""
                        clipboard_files = snapshot.file_paths or []
                        if snapshot.text:
                            from .clipboard_classifiers import classify_text

                            kind, _, _ = classify_text(snapshot.text)
                            clipboard_kind = kind
                    except Exception as exc:
                        logger.debug("读取剪贴板快照失败: %s", exc, exc_info=True)

                    ctx = CommandContext(
                        raw_input=command,
                        args_text=args_text,
                        clipboard_text=clipboard_text,
                        clipboard_kind=clipboard_kind,
                        clipboard_files=clipboard_files,
                        selected_files=selected_files,
                        update_callback=lambda r: set_pending_command_result(r),
                    )
                    result = cmd_def.handler(ctx)
                    set_pending_command_result(result)
                    return result.success
        except Exception as exc:
            logger.debug("执行内置命令失败: %s", exc, exc_info=True)

        canonical = canonical_builtin_command(cmd_name)
        command_name = canonical or cmd_name
        filesystem_builtin_commands = {"open_data_dir", "open_install_dir"} | INTERNAL_PATH_BUILTIN_COMMANDS
        if canonical in UI_CALLBACK_BUILTIN_COMMANDS:
            try:
                from core import call_callback, has_callback

                if has_callback(canonical):
                    global _main_thread_invoker
                    if _main_thread_invoker is not None and not ShortcutExecutor._is_qt_main_thread():
                        _main_thread_invoker.execute_signal.emit(lambda: call_callback(canonical))
                        logger.info(f"UI内置命令(通过主线程): {canonical}")
                    elif ShortcutExecutor._is_qt_main_thread():
                        result = call_callback(canonical)
                        if not result:
                            logger.error("UI内置命令回调返回失败: %s", canonical)
                            return False
                    else:
                        logger.warning("MainThreadInvoker未初始化，已跳过跨线程直接执行: %s", canonical)
                    return True
                else:
                    if canonical == "show_config_window":
                        direct = getattr(sys.modules.get("main"), "show_config_window_direct", None)
                        if callable(direct):
                            try:
                                if direct():
                                    return True
                            except Exception as e:
                                logger.debug("配置窗口直接回退失败: %s", e)
                        logger.debug("配置窗口: 回退到 IPC 方式")
                        return ShortcutExecutor._send_ipc_command_deferred("show_config")
                    if canonical in filesystem_builtin_commands:
                        return ShortcutExecutor._open_builtin_filesystem_target(canonical)
                    logger.warning(f"内置命令: 回调未注册: {canonical}")
                    return False
            except Exception as e:
                logger.error(f"内置命令执行失败 ({canonical}): {e}")
                return False

        # 切换置顶（自动判断当前状态）
        if cmd_name in ("topmost", "置顶", "pin", "toggle_topmost"):
            return ShortcutExecutor._toggle_topmost()

        # 强制置顶
        if cmd_name in ("topmost_on", "置顶开", "pin_on"):
            return ShortcutExecutor._set_topmost(True)

        # 强制取消置顶
        if cmd_name in ("topmost_off", "置顶关", "unpin", "pin_off"):
            return ShortcutExecutor._set_topmost(False)

        if command_name in filesystem_builtin_commands:
            return ShortcutExecutor._open_builtin_filesystem_target(command_name)

        if command_name in WINDOWS_SYSTEM_BUILTIN_COMMANDS:
            return ShortcutExecutor._open_windows_system_builtin(command_name)

        return False

    @staticmethod
    def _send_ipc_command_deferred(command: str) -> bool:
        """延迟发送IPC命令，避免主线程阻塞导致的死锁

        当从弹窗点击内置命令时，主线程正在处理执行流程，
        如果直接同步发送 IPC，会因为 waitForConnected() 阻塞事件循环，
        而 QLocalServer 的 newConnection 信号也需要事件循环来触发，
        导致连接永远无法建立（死锁）。

        解决方案：使用 Python threading.Timer 在短暂延迟后发送命令，
        让当前事件处理完成后再发送。
        """
        import threading

        def do_send():
            try:
                # 延迟让 UI 事件处理完成
                # 打包版本首次调用需要更长延迟，Qt网络模块初始化较慢
                import sys
                import time

                is_frozen = getattr(sys, "frozen", False)

                # 打包版本使用更长的初始延迟
                initial_delay = 0.35 if is_frozen else 0.15
                time.sleep(initial_delay)

                # 执行实际的 IPC 发送
                logger.debug(f"开始发送延迟IPC命令: {command} (frozen={is_frozen})")
                result = ShortcutExecutor._send_ipc_command(command)
                if result:
                    logger.debug(f"延迟IPC命令发送成功: {command}")
                else:
                    logger.warning(f"延迟IPC命令发送失败: {command}")
            except Exception:
                logger.exception("延迟IPC命令发送失败")

        try:
            # 使用 Python 线程而不是 QTimer，避免线程亲和性问题
            thread = threading.Thread(target=do_send, name="IPCCommandSender", daemon=True)
            thread.start()
            logger.debug(f"IPC命令已排队到后台线程: {command}")
            return True  # 返回 True 表示命令已排队（不是已执行）

        except Exception as e:
            logger.error(f"排队IPC命令失败: {e}, 尝试直接发送")
            # 回退到直接发送
            return ShortcutExecutor._send_ipc_command(command)

    @staticmethod
    def _send_ipc_command(command: str) -> bool:
        """发送IPC命令

        修复：增加首次连接的等待时间和递增重试延迟，
        解决打包后exe第一次调用时连接失败的问题。

        关键改进：
        1. 首次调用前添加较长延迟，让Qt网络模块和IPC服务器有时间完成初始化
        2. 增加连接等待时间和总超时时间
        3. 添加更详细的状态日志
        4. 优化重试策略，前几次重试更激进
        """
        try:
            # 延迟导入以避免循环引用
            import sys

            from qt_compat import QLocalSocket

            is_frozen = getattr(sys, "frozen", False)

            # 首次调用时给Qt网络模块和IPC服务器更多初始化时间
            # 这对于打包后的exe在首次使用QLocalSocket尤为重要
            if not hasattr(ShortcutExecutor, "_ipc_initialized"):
                ShortcutExecutor._ipc_initialized = True
                # 打包版本需要更长的首次初始化延迟
                # 因为Qt网络模块的DLL加载和初始化需要时间
                init_delay = 0.35 if is_frozen else 0.15
                time.sleep(init_delay)
                logger.debug(f"IPC客户端首次初始化延迟完成 (frozen={is_frozen}, delay={init_delay}s)")

            server_name = "QuickLauncherInstance_v3"
            deadline = time.monotonic() + 4.0  # 增加总超时时间到 4 秒
            last_socket = None
            attempt = 0
            last_error = ""

            while time.monotonic() < deadline:
                socket = QLocalSocket()
                last_socket = socket
                attempt += 1

                try:
                    socket.connectToServer(server_name)
                    # 首次尝试使用更长的等待时间（打包后首次加载可能较慢）
                    # 第一次 1200ms，第二次 800ms，之后 400ms
                    if attempt == 1:
                        wait_time = 1200
                    elif attempt == 2:
                        wait_time = 800
                    else:
                        wait_time = 400

                    if socket.waitForConnected(wait_time):
                        # 连接成功，发送数据
                        data = command.encode("utf-8")
                        bytes_written = socket.write(data)
                        socket.flush()

                        # 等待数据写入完成
                        write_ok = bytes_written == len(data)
                        if not write_ok:
                            write_ok = socket.waitForBytesWritten(800)

                        if write_ok or bytes_written > 0:
                            socket.disconnectFromServer()
                            logger.debug(f"IPC命令发送成功: {command} (尝试 {attempt} 次)")
                            return True

                        # 即使 waitForBytesWritten 返回 False，数据可能已发送
                        socket.disconnectFromServer()
                        logger.debug(f"IPC命令可能已发送: {command} (尝试 {attempt} 次, bytes={bytes_written})")
                        return True
                    else:
                        # 连接失败，记录错误
                        last_error = socket.errorString() or "未知错误"
                        logger.debug(f"IPC连接尝试 {attempt} 失败: {last_error}")

                except Exception as e:
                    last_error = str(e)
                    logger.debug(f"IPC连接尝试 {attempt} 异常: {e}")

                try:
                    socket.disconnectFromServer()
                except Exception as exc:
                    logger.debug("断开IPC套接字连接失败: %s", exc, exc_info=True)

                # 优化重试延迟策略：
                # 前3次快速重试（50-100ms），之后逐渐增加到最大200ms
                if attempt <= 3:
                    retry_delay = 0.05 + attempt * 0.02  # 70ms, 90ms, 110ms
                else:
                    retry_delay = min(0.1 + (attempt - 3) * 0.03, 0.2)
                time.sleep(retry_delay)

            try:
                if last_socket:
                    last_socket.disconnectFromServer()
            except Exception as exc:
                logger.debug("断开最后的IPC套接字连接失败: %s", exc, exc_info=True)

            logger.warning(f"IPC命令发送失败（超时）: {command}, 共尝试 {attempt} 次, 最后错误: {last_error}")
            return False
        except Exception:
            logger.exception("IPC命令发送异常")
            return False
