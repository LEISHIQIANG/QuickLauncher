"""Command execution helpers for ShortcutExecutor."""

from __future__ import annotations

import hashlib
import logging
import os
import queue
import shutil  # noqa: F401 — kept for test monkeypatch access
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from qt_compat import QObject, pyqtSignal
from runtime_paths import is_packaged_runtime

from .background_tasks import start_background_thread
from .command_exec import (
    SUPPORTED_COMMAND_TYPES,
    build_bash_fallback_result,
    chain_values,
    command_panel_size,
    command_param_defs,
    command_param_values,
    decode_command_output,
    merge_runtime_env,
    truncate_command_output,
)
from .command_exec.launcher_mixin import CommandLauncherMixin
from .command_exec.standalone import _write_atomic
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
_TOPMOST_TARGET_UNSET = object()
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


class CommandExecutionMixin(CommandLauncherMixin):
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
                    param_values=ShortcutExecutor._command_param_values(shortcut),  # type: ignore[attr-defined]
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
    def _capture_error_result(
        message: str,
        error: str,
        panel_size: str,
        *,
        start: float | None = None,
        command: str | None = None,
    ) -> CommandResult:
        payload = {"window_size": panel_size}
        if start is not None:
            payload["duration"] = time.monotonic() - start  # type: ignore[assignment]
        if command is not None:
            payload["command"] = command
        return CommandResult(
            success=False,
            message=message,
            display_type="log",
            error=error,
            payload=payload,
        )

    @staticmethod
    def _capture_builtin_result(success: bool, panel_size: str, start: float) -> CommandResult:
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

    @staticmethod
    def _decode_capture_output(
        stdout_bytes: bytes,
        stderr_bytes: bytes,
        shortcut: ShortcutItem,
        command_type: str,
        max_chars: int,
    ) -> tuple[str, str, bool, str, bool]:
        """Decode and truncate captured stdout/stderr bytes.

        Returns a 7-element tuple:
        (stdout, stderr, stdout_truncated, stderr_truncated,
         stdout_encoding, stderr_encoding, decode_fallback_used)
        """
        encoding = getattr(shortcut, "command_encoding", "auto")
        stdout, stdout_encoding, stdout_fallback = ShortcutExecutor._decode_bytes(  # type: ignore[attr-defined]
            stdout_bytes or b"", encoding, command_type
        )
        stderr, stderr_encoding, stderr_fallback = ShortcutExecutor._decode_bytes(  # type: ignore[attr-defined]
            stderr_bytes or b"", encoding, command_type
        )
        stdout, stdout_truncated = ShortcutExecutor._truncate_output(stdout or "", max_chars)  # type: ignore[attr-defined]
        stderr, stderr_truncated = ShortcutExecutor._truncate_output(stderr or "", max_chars)  # type: ignore[attr-defined]
        return (  # type: ignore[return-value]
            stdout,
            stderr,
            stdout_truncated,
            stderr_truncated,
            stdout_encoding,
            stderr_encoding,
            stdout_fallback or stderr_fallback,
        )

    @staticmethod
    def _build_capture_payload(
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
        """Build the common payload dict for capture results."""
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

    @staticmethod
    def _build_capture_cancel_result(
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
        """Build a CommandResult for a cancelled capture."""
        message = "\n".join(part for part in ["命令执行已取消。", stdout, stderr] if part)
        return CommandResult(
            success=False,
            message=message,
            display_type="log",
            payload=ShortcutExecutor._build_capture_payload(  # type: ignore[attr-defined]
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

    @staticmethod
    def _build_capture_success_result(
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
        """Build a CommandResult for a completed (success/failure/timeout) capture."""
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
            payload=ShortcutExecutor._build_capture_payload(  # type: ignore[attr-defined]
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

    @staticmethod
    def _build_bash_fallback_result(
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
        """Build a CommandResult when bash direct capture is denied."""
        message = ShortcutExecutor._bash_direct_capture_denied_message(stderr.strip())  # type: ignore[attr-defined]
        return CommandResult(
            success=False,
            message=message,
            display_type="log",
            payload=ShortcutExecutor._build_capture_payload(  # type: ignore[attr-defined]
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
            error=stderr.strip().splitlines()[0] if stderr.strip() else "Git Bash 直接捕获启动失败",
        )

    @staticmethod
    def _prepare_command_for_execution(
        shortcut: ShortcutItem,
        command: str,
        command_type: str,
        *,
        panel_size: str | None = None,
        display_type: str = "text",
    ) -> tuple[str, CommandResult | None]:
        payload = {"window_size": panel_size} if panel_size else {}

        def _invalid(message: str, error: str | None = None) -> tuple[str, CommandResult]:
            return command, CommandResult(
                success=False,
                message=message,
                display_type=display_type,
                error=error if error is not None else message,
                payload=dict(payload),
            )

        raw_mode = bool(getattr(shortcut, "raw_mode", False))
        expand_variables = ShortcutExecutor._should_expand_command_variables(shortcut)  # type: ignore[attr-defined]
        if command_type in ("cmd", "powershell", "bash") and not raw_mode and is_value_only_variable_command(command):
            if expand_variables:
                return _invalid(
                    f"命令只包含值占位符，不能直接执行。请改为可执行命令，例如: echo {command}",
                    "命令无效",
                )
            return _invalid(
                f"命令只包含变量占位符，但未启用解析变量。请启用解析变量，或改为可执行命令，例如: echo {command}",
                "命令无效",
            )
        if command_type in ("cmd", "powershell", "bash") and expand_variables:
            unsafe_variables = find_unquoted_external_command_variables(command)
            if unsafe_variables:
                examples = ", ".join("{{" + name + ":q}}" for name in unsafe_variables[:3])
                message = f"外部输入变量用于 CMD/PowerShell/Bash 命令时必须使用 :q 引用，例如: {examples}"
                return _invalid(message)
        try:
            if expand_variables:
                command = ShortcutExecutor._resolve_command_variables(shortcut, command)  # type: ignore[attr-defined]
        except CommandVariableError as e:
            return _invalid(str(e), "变量解析失败")
        return command, None

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
        return merge_runtime_env(shortcut, ShortcutExecutor._sanitized_child_env())  # type: ignore[attr-defined]

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
        effective_type = ShortcutExecutor._normalize_command_type(  # type: ignore[attr-defined]
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
        risks = ShortcutExecutor.command_requires_confirmation(shortcut, command=command, command_type=command_type)  # type: ignore[attr-defined]
        if not risks:
            return None
        if ShortcutExecutor._consume_command_confirmation(shortcut):  # type: ignore[attr-defined]
            return None
        risk_lines = [f"- {risk.get('message') or risk.get('code')}" for risk in risks]
        detail = "\n".join(risk_lines)
        return CommandResult(
            success=False,
            message="该命令包含不可逆或强破坏性操作，请确认后执行。",
            display_type="confirm",
            error="需要确认",
            payload={
                "window_size": panel_size or ShortcutExecutor._command_panel_size(shortcut),  # type: ignore[attr-defined]
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
        command_type = ShortcutExecutor._normalize_command_type(command_type)  # type: ignore[attr-defined]
        cwd = (getattr(shortcut, "working_dir", "") or "").strip()
        if command_type not in ShortcutExecutor._SUPPORTED_COMMAND_TYPES:  # type: ignore[attr-defined]
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
        if command_type == "cmd" and not ShortcutExecutor._cmd_launcher():  # type: ignore[attr-defined]
            items.append({"title": "CMD", "status": "failed", "detail": ShortcutExecutor._cmd_launcher_error()})  # type: ignore[attr-defined]
        if command_type == "python" and not ShortcutExecutor._python_launcher():  # type: ignore[attr-defined]
            items.append({"title": "Python", "status": "failed", "detail": ShortcutExecutor._python_launcher_error()})  # type: ignore[attr-defined]
        if command_type == "powershell" and not ShortcutExecutor._powershell_launcher():  # type: ignore[attr-defined]
            items.append(
                {"title": "PowerShell", "status": "failed", "detail": ShortcutExecutor._powershell_launcher_error()}  # type: ignore[attr-defined]
            )
        if command_type == "bash" and not ShortcutExecutor._bash_launcher():  # type: ignore[attr-defined]
            items.append({"title": "Git Bash", "status": "failed", "detail": ShortcutExecutor._bash_launcher_error()})  # type: ignore[attr-defined]
        if capture and bool(getattr(shortcut, "show_window", False)):
            items.append({"title": "捕获输出", "status": "failed", "detail": "显示执行窗口时不能捕获输出。"})
        if capture and bool(getattr(shortcut, "run_as_admin", False)):
            items.append({"title": "捕获输出", "status": "failed", "detail": "管理员命令暂不支持捕获输出。"})
        if command_type in ("cmd", "powershell", "bash") and command:
            try:
                if command_type == "cmd":
                    argv = ShortcutExecutor._cmd_argv(  # type: ignore[attr-defined]
                        command,
                        keep_open=bool(getattr(shortcut, "show_window", False)) and not capture,
                    )
                elif command_type == "powershell":
                    argv = ShortcutExecutor._powershell_argv(  # type: ignore[attr-defined]
                        command,
                        no_exit=bool(getattr(shortcut, "show_window", False)) and not capture,
                    )
                else:
                    argv = ShortcutExecutor._bash_argv(  # type: ignore[attr-defined]
                        command,
                        login=bool(getattr(shortcut, "show_window", False)) and not capture,
                    )
                if ShortcutExecutor._direct_command_line_too_long(argv):  # type: ignore[attr-defined]
                    items.append(
                        {
                            "title": "命令长度",
                            "status": "failed",
                            "detail": ShortcutExecutor._direct_command_line_length_error(command_type, argv),  # type: ignore[attr-defined]
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
        param_values = ShortcutExecutor._command_param_values(shortcut)  # type: ignore[attr-defined]
        params = [CommandParam(**param) for param in ShortcutExecutor._command_param_defs(shortcut)]  # type: ignore[attr-defined]
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
            preprocess_result = ShortcutExecutor._command_preprocessing_result(shortcut, command, command_type)  # type: ignore[attr-defined]
            if preprocess_result is not None and (
                getattr(preprocess_result, "should_block", False) or not getattr(preprocess_result, "success", True)
            ):
                return ShortcutExecutor._preprocessing_result_to_command_result(  # type: ignore[attr-defined]
                    preprocess_result,
                    panel_size=ShortcutExecutor._command_panel_size(shortcut),  # type: ignore[attr-defined]
                )
        return None

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
        script_path = ShortcutExecutor._bash_write_script(command)  # type: ignore[attr-defined]
        try:
            bash_exe = ShortcutExecutor._bash_launcher()  # type: ignore[attr-defined]
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
                **ShortcutExecutor._capture_popen_platform_kwargs(),  # type: ignore[attr-defined]
            )

            timed_out = False
            try:
                stdout_bytes, stderr_bytes = process.communicate(timeout=timeout_value)
                returncode = process.returncode
            except subprocess.TimeoutExpired:
                ShortcutExecutor._terminate_process_tree(process)  # type: ignore[attr-defined]
                stdout_bytes, stderr_bytes = process.communicate()
                returncode = process.returncode
                timed_out = True

            return build_bash_fallback_result(  # type: ignore[no-any-return]
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
            logger.debug("_is_qt_main_thread check failed", exc_info=True)
            return False

    @staticmethod
    def _cleanup_file_later(process, *paths: str):
        def cleanup():
            try:
                if process is not None:
                    process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                ShortcutExecutor._terminate_process_tree(process)  # type: ignore[attr-defined]
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

        start_background_thread(
            name="CommandTempCleanup",
            target=cleanup,
            owner="shortcut-command-exec",
        )

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
            startupinfo = ShortcutExecutor._get_silent_startupinfo()  # type: ignore[attr-defined]
            creationflags = ShortcutExecutor._get_silent_creationflags()  # type: ignore[attr-defined]

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
            kwargs["creationflags"] = creationflags  # type: ignore[assignment]
        return kwargs

    @staticmethod
    def _execute_command(shortcut: ShortcutItem) -> tuple[bool, str]:
        """执行命令类型快捷方式"""
        command = shortcut.command
        if not command:
            logger.warning("命令为空")
            return False, "命令内容为空"

        command_type = ShortcutExecutor._normalize_command_type(getattr(shortcut, "command_type", "cmd"))  # type: ignore[attr-defined]
        command, prepare_error = ShortcutExecutor._prepare_command_for_execution(  # type: ignore[attr-defined]
            shortcut,
            command,
            command_type,
        )
        if prepare_error is not None:
            return False, prepare_error.message or prepare_error.error

        capture_output = bool(getattr(shortcut, "capture_output", False))
        if not capture_output:
            confirmation = ShortcutExecutor._destructive_confirmation_result(shortcut, command, command_type)  # type: ignore[attr-defined]
            if confirmation is not None:
                set_pending_command_result(confirmation)
                return False, confirmation.message or confirmation.error
        preflight = ShortcutExecutor._preflight_command(  # type: ignore[attr-defined]
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
            result = ShortcutExecutor.run_command_capture(shortcut)  # type: ignore[attr-defined]
            set_pending_command_result(result)
            return result.success, result.error

        if command_type == "powershell":
            return ShortcutExecutor._execute_powershell_command(shortcut, command)  # type: ignore[attr-defined, no-any-return]
        if command_type == "bash":
            return ShortcutExecutor._execute_bash_command(shortcut, command)  # type: ignore[attr-defined, no-any-return]
        if command_type == "python":
            return ShortcutExecutor._execute_python_command(shortcut, command)  # type: ignore[attr-defined, no-any-return]
        if command_type == "builtin":
            success = ShortcutExecutor._execute_builtin_for_shortcut(shortcut, command)  # type: ignore[attr-defined]
            return success, "" if success else "内置命令执行失败"
        return ShortcutExecutor._execute_cmd_command(shortcut, command)  # type: ignore[attr-defined, no-any-return]

    @staticmethod
    def _execute_powershell_command(shortcut: ShortcutItem, command: str) -> tuple[bool, str]:
        try:
            show_window = getattr(shortcut, "show_window", False)
            run_as_admin = getattr(shortcut, "run_as_admin", False)
            cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
            argv = ShortcutExecutor._powershell_argv(command, no_exit=show_window)  # type: ignore[attr-defined]
            if ShortcutExecutor._direct_command_line_too_long(argv):  # type: ignore[attr-defined]
                return False, ShortcutExecutor._direct_command_line_length_error("powershell", argv)  # type: ignore[attr-defined]
            show_cmd = 1 if show_window else 0
            if os.name == "nt" and (show_window or run_as_admin):
                launched, launch_error = ShortcutExecutor._launch_with_privilege(  # type: ignore[attr-defined]
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
                subprocess.Popen(argv, cwd=cwd, env=ShortcutExecutor._runtime_env(shortcut), shell=False)  # type: ignore[attr-defined]
            else:
                ShortcutExecutor._popen_silent(  # type: ignore[attr-defined]
                    argv,
                    cwd=cwd,
                    env=ShortcutExecutor._runtime_env(shortcut),  # type: ignore[attr-defined]
                    shell=False,
                )
            return True, ""
        except FileNotFoundError:
            return False, ShortcutExecutor._powershell_launcher_error()  # type: ignore[attr-defined]
        except Exception as e:
            return False, f"PowerShell command launch failed: {e}"

    @staticmethod
    def _execute_bash_command(shortcut: ShortcutItem, command: str) -> tuple[bool, str]:
        show_window = getattr(shortcut, "show_window", False)
        run_as_admin = getattr(shortcut, "run_as_admin", False)
        cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
        bash_env = ShortcutExecutor._runtime_env(shortcut)  # type: ignore[attr-defined]
        bash_env["LANG"] = "en_US.UTF-8"
        if show_window:
            return ShortcutExecutor._execute_visible_bash_command(command, cwd, bash_env, run_as_admin)  # type: ignore[attr-defined, no-any-return]
        return ShortcutExecutor._execute_silent_bash_command(command, cwd, bash_env)  # type: ignore[attr-defined, no-any-return]

    @staticmethod
    def _execute_visible_bash_command(
        command: str,
        cwd: str | None,
        bash_env: dict[str, str],
        run_as_admin: bool,
    ) -> tuple[bool, str]:
        try:
            bash_exe = ShortcutExecutor._bash_launcher()  # type: ignore[attr-defined]
            if not bash_exe:
                return False, ShortcutExecutor._bash_launcher_error()  # type: ignore[attr-defined]
            logger.debug("Bash show-window: launcher=%s, route=shell-execute", bash_exe)
            argv = ShortcutExecutor._bash_argv(command, login=True)  # type: ignore[attr-defined]
            if ShortcutExecutor._direct_command_line_too_long(argv):  # type: ignore[attr-defined]
                return False, ShortcutExecutor._direct_command_line_length_error("bash", argv)  # type: ignore[attr-defined]
            if os.name == "nt":
                launched, launch_error = ShortcutExecutor._launch_with_privilege(  # type: ignore[attr-defined]
                    bash_exe,
                    subprocess.list2cmdline(["--login", "-c", command]),
                    cwd,
                    show_cmd=1,
                    run_as_admin=run_as_admin,
                    admin_failure_message="Administrator launch failed.",
                )
                if launched:
                    return True, ""
                if launch_error:
                    return False, launch_error
            subprocess.Popen(argv, cwd=cwd, env=bash_env, shell=False)
            return True, ""
        except FileNotFoundError:
            return False, ShortcutExecutor._bash_launcher_error()  # type: ignore[attr-defined]
        except Exception as e:
            return False, f"Bash command launch failed: {e}"

    @staticmethod
    def _execute_silent_bash_command(
        command: str,
        cwd: str | None,
        bash_env: dict[str, str],
    ) -> tuple[bool, str]:
        try:
            bash_exe = ShortcutExecutor._bash_launcher()  # type: ignore[attr-defined]
            if not bash_exe:
                return False, ShortcutExecutor._bash_launcher_error()  # type: ignore[attr-defined]
            logger.debug("Bash silent: launcher=%s, route=popen-silent", bash_exe)
            argv = ShortcutExecutor._bash_argv(command, login=False)  # type: ignore[attr-defined]
            if ShortcutExecutor._direct_command_line_too_long(argv):  # type: ignore[attr-defined]
                return False, ShortcutExecutor._direct_command_line_length_error("bash", argv)  # type: ignore[attr-defined]
            ShortcutExecutor._popen_silent(  # type: ignore[attr-defined]
                argv,
                cwd=cwd,
                env=bash_env,
                shell=False,
            )
            return True, ""
        except FileNotFoundError:
            return False, ShortcutExecutor._bash_launcher_error()  # type: ignore[attr-defined]
        except Exception as e:
            return False, f"Bash command launch failed: {e}"

    @staticmethod
    def _execute_python_command(shortcut: ShortcutItem, command: str) -> tuple[bool, str]:
        if getattr(shortcut, "show_window", False):
            return ShortcutExecutor._execute_visible_python_command(shortcut, command)  # type: ignore[attr-defined, no-any-return]
        return ShortcutExecutor._execute_silent_python_command(shortcut, command)  # type: ignore[attr-defined, no-any-return]

    @staticmethod
    def _execute_visible_python_command(shortcut: ShortcutItem, command: str) -> tuple[bool, str]:
        tmp_path = None
        try:
            if not ShortcutExecutor._python_launcher():  # type: ignore[attr-defined]
                return False, ShortcutExecutor._python_launcher_error()  # type: ignore[attr-defined]
            tmp_path = ShortcutExecutor._write_temp_python_script(command)  # type: ignore[attr-defined]
            python_exe = ShortcutExecutor._python_launcher()  # type: ignore[attr-defined]
            if not python_exe:
                return False, ShortcutExecutor._python_launcher_error()  # type: ignore[attr-defined]
            run_as_admin = getattr(shortcut, "run_as_admin", False)
            cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
            if os.name == "nt":
                launched, launch_error = ShortcutExecutor._launch_with_privilege(  # type: ignore[attr-defined]
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
                env=ShortcutExecutor._runtime_env(shortcut),  # type: ignore[attr-defined]
                shell=False,
            )
            ShortcutExecutor._cleanup_file_later(process, tmp_path)  # type: ignore[attr-defined]
            return True, ""
        except FileNotFoundError:
            ShortcutExecutor._remove_temp_python_script(tmp_path)  # type: ignore[attr-defined]
            return False, ShortcutExecutor._python_launcher_error()  # type: ignore[attr-defined]
        except Exception as e:
            ShortcutExecutor._remove_temp_python_script(tmp_path)  # type: ignore[attr-defined]
            return False, f"Python 代码执行失败: {e}"

    @staticmethod
    def _remove_temp_python_script(tmp_path: str | None) -> None:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception as exc:
            logger.debug("删除临时Python文件失败: %s", exc, exc_info=True)

    @staticmethod
    def _execute_silent_python_command(shortcut: ShortcutItem, command: str) -> tuple[bool, str]:
        try:
            python_exe = ShortcutExecutor._python_launcher()  # type: ignore[attr-defined]
            if not python_exe:
                raise FileNotFoundError(ShortcutExecutor._python_launcher_error())  # type: ignore[attr-defined]

            def _launch_python_stdin():
                try:
                    si = ShortcutExecutor._get_silent_startupinfo()  # type: ignore[attr-defined]
                    cf = ShortcutExecutor._get_silent_creationflags(shell=False)  # type: ignore[attr-defined]
                    cwd_dir = (getattr(shortcut, "working_dir", "") or "").strip() or None
                    env_dict = ShortcutExecutor._runtime_env(shortcut)  # type: ignore[attr-defined]
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
                            shell=False,
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
                                shell=False,
                            )
                            process.communicate(input=command.encode("utf-8"))
                        else:
                            raise
                except Exception as e:
                    logger.error(f"Python stdin exec failed: {e}")

            start_background_thread(
                name="PythonStdinExec",
                target=_launch_python_stdin,
                owner="shortcut-command-exec",
            )
            logger.debug("执行命令(Silent Python stdin): %s", command)
            return True, ""
        except FileNotFoundError:
            return False, ShortcutExecutor._python_launcher_error()  # type: ignore[attr-defined]
        except Exception as e:
            return False, f"Python 代码启动失败: {e}"

    @staticmethod
    def _execute_cmd_command(shortcut: ShortcutItem, command: str) -> tuple[bool, str]:
        process = None
        run_as_admin = getattr(shortcut, "run_as_admin", False)
        show_window = getattr(shortcut, "show_window", False)
        if ShortcutExecutor._cmd_has_newline(command) and not show_window and not run_as_admin:  # type: ignore[attr-defined]
            return ShortcutExecutor._execute_cmd_stdin_command(shortcut, command)  # type: ignore[attr-defined, no-any-return]
        try:
            launch_result = ShortcutExecutor._launch_cmd_process(shortcut, command, run_as_admin, show_window)  # type: ignore[attr-defined]
            if launch_result is True:
                return True, ""
            process = launch_result
            error_msg = ""
        except (ValueError, RuntimeError) as e:
            return False, str(e)
        except Exception as e:
            error_msg = f"命令启动失败: {e}"
            logger.error(error_msg)
        if process is not None:
            ShortcutExecutor._restore_focus_after_process(process)  # type: ignore[attr-defined]
        return (process is not None), error_msg

    @staticmethod
    def _execute_cmd_stdin_command(shortcut: ShortcutItem, command: str) -> tuple[bool, str]:
        try:
            cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
            argv = ShortcutExecutor._cmd_stdin_argv()  # type: ignore[attr-defined]
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=ShortcutExecutor._runtime_env(shortcut),  # type: ignore[attr-defined]
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                startupinfo=getattr(ShortcutExecutor, "_get_silent_startupinfo", lambda: None)(),
                creationflags=getattr(ShortcutExecutor, "_get_silent_creationflags", lambda: 0)(),
            )
            stdin_pipe = getattr(process, "stdin", None)
            if stdin_pipe is not None:
                stdin_pipe.write(ShortcutExecutor._cmd_stdin_script(command))  # type: ignore[attr-defined]
                stdin_pipe.close()
            logger.debug("执行命令(Silent CMD stdin): %s", command)
            return True, ""
        except Exception as e:
            error_msg = f"命令启动失败: {e}"
            logger.error(error_msg)
            return False, error_msg

    @staticmethod
    def _launch_cmd_process(
        shortcut: ShortcutItem,
        command: str,
        run_as_admin: bool,
        show_window: bool,
    ):
        parsed = ShortcutExecutor._safe_split_args(command)  # type: ignore[attr-defined]
        exe_path = parsed[0] if parsed else ""
        if exe_path and exe_path.lower().endswith(".exe") and os.path.exists(exe_path):
            return ShortcutExecutor._launch_direct_exe_command(shortcut, parsed, exe_path, run_as_admin, show_window)  # type: ignore[attr-defined]
        return ShortcutExecutor._launch_cmd_text_command(shortcut, command, run_as_admin, show_window)  # type: ignore[attr-defined]

    @staticmethod
    def _launch_direct_exe_command(
        shortcut: ShortcutItem,
        parsed: list[str],
        exe_path: str,
        run_as_admin: bool,
        show_window: bool,
    ):
        if ShortcutExecutor._direct_command_line_too_long(parsed):  # type: ignore[attr-defined]
            raise ValueError(ShortcutExecutor._direct_command_line_length_error("cmd", parsed))  # type: ignore[attr-defined]
        exe_dir = os.path.dirname(os.path.abspath(exe_path))
        cwd = (getattr(shortcut, "working_dir", "") or "").strip()
        show_cmd = 1 if show_window else 0

        if os.name == "nt" and (show_window or run_as_admin):
            parameters = subprocess.list2cmdline(parsed[1:]) if len(parsed) > 1 else ""
            launched, launch_error = ShortcutExecutor._launch_with_privilege(  # type: ignore[attr-defined]
                exe_path,
                parameters or None,
                cwd or exe_dir or None,
                show_cmd=show_cmd,
                run_as_admin=run_as_admin,
                admin_failure_message="Administrator launch failed.",
            )
            if launched:
                logger.debug(f"Launch via ShellExecute: {exe_path}")
                return True
            if launch_error:
                raise RuntimeError(launch_error)
        if show_window:
            process = subprocess.Popen(parsed, cwd=cwd or exe_dir or None)
        else:
            process = ShortcutExecutor._popen_silent(  # type: ignore[attr-defined]
                parsed, cwd=cwd or exe_dir or None, env=ShortcutExecutor._runtime_env(shortcut), shell=False  # type: ignore[attr-defined]
            )
        logger.debug(f"执行程序({'Visible' if show_window else 'Silent'}): {exe_path}")
        return process

    @staticmethod
    def _launch_cmd_text_command(
        shortcut: ShortcutItem,
        command: str,
        run_as_admin: bool,
        show_window: bool,
    ):
        cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
        argv = ShortcutExecutor._cmd_argv(command, keep_open=show_window)  # type: ignore[attr-defined]
        if ShortcutExecutor._direct_command_line_too_long(argv):  # type: ignore[attr-defined]
            raise ValueError(ShortcutExecutor._direct_command_line_length_error("cmd", argv))  # type: ignore[attr-defined]

        show_cmd = 1 if show_window else 0
        if os.name == "nt" and (show_window or run_as_admin):
            launched, launch_error = ShortcutExecutor._launch_with_privilege(  # type: ignore[attr-defined]
                argv[0],
                subprocess.list2cmdline(argv[1:]),
                cwd,
                show_cmd=show_cmd,
                run_as_admin=run_as_admin,
                admin_failure_message="Administrator launch failed.",
            )
            if launched:
                logger.debug(f"Command via ShellExecute: {command}")
                return True
            if launch_error:
                raise RuntimeError(launch_error)

        if show_window:
            process = subprocess.Popen(argv, cwd=cwd, env=ShortcutExecutor._runtime_env(shortcut), shell=False)  # type: ignore[attr-defined]
        else:
            process = ShortcutExecutor._popen_silent(  # type: ignore[attr-defined]
                argv, cwd=cwd, env=ShortcutExecutor._runtime_env(shortcut), shell=False  # type: ignore[attr-defined]
            )
        logger.debug(f"执行命令({'Visible' if show_window else 'Silent'} CMD): {command}")
        return process

    @staticmethod
    def _restore_focus_after_process(process) -> None:
        def _restore_focus(proc=process):
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                logger.debug("命令进程超时未完成，继续执行焦点恢复")
            except Exception as e:
                logger.debug(f"等待命令进程时出错: {e}")
            time.sleep(0.05)
            try:
                ShortcutExecutor.restore_foreground_window()  # type: ignore[attr-defined]
                logger.debug("CMD 命令执行后：已恢复焦点")
            except Exception as e:
                logger.debug(f"CMD 命令执行后恢复焦点失败: {e}")

        start_background_thread(
            name="FocusRestore",
            target=_restore_focus,
            owner="shortcut-command-exec",
        )

    @staticmethod
    def _resolve_command_variables(shortcut: ShortcutItem, command: str) -> str:
        if not ShortcutExecutor._should_expand_command_variables(shortcut):  # type: ignore[attr-defined]
            return command
        input_values = getattr(shortcut, "_runtime_input_values", None)
        selected_provider = None
        if getattr(shortcut, "trigger_mode", "immediate") == "after_close":
            selected_provider = ShortcutExecutor._capture_selected_text  # type: ignore[attr-defined]
        command_type = ShortcutExecutor._normalize_command_type(getattr(shortcut, "command_type", "cmd"))  # type: ignore[attr-defined]
        return resolve_command_variables(
            command,
            input_values=input_values,
            param_values=ShortcutExecutor._command_param_values(shortcut),  # type: ignore[attr-defined]
            chain_values=ShortcutExecutor._chain_values(shortcut),  # type: ignore[attr-defined]
            selected_files=getattr(shortcut, "_runtime_selected_files", None),
            clipboard_provider=read_clipboard_text,
            selected_text_provider=selected_provider,
            strict_unknown=True,
            bash_mode=(command_type == "bash"),
            powershell_mode=(command_type == "powershell"),
        )

    @staticmethod
    def _should_expand_command_variables(shortcut: ShortcutItem) -> bool:
        command_type = ShortcutExecutor._normalize_command_type(getattr(shortcut, "command_type", "cmd"))  # type: ignore[attr-defined]
        if bool(getattr(shortcut, "raw_mode", False)):
            return False
        enabled = getattr(shortcut, "command_variables_enabled", None)
        if ShortcutExecutor._command_param_defs(shortcut) or ShortcutExecutor._chain_values(shortcut):  # type: ignore[attr-defined]
            return command_type != "builtin"  # type: ignore[no-any-return]
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
                ShortcutExecutor.restore_foreground_window_fast(timeout_ms=300)  # type: ignore[attr-defined]
            except Exception:
                ShortcutExecutor.restore_foreground_window()  # type: ignore[attr-defined]
            time.sleep(0.08)
            if hasattr(ShortcutExecutor, "_execute_hotkey_sendinput"):
                ShortcutExecutor._execute_hotkey_sendinput(["ctrl"], "c")  # type: ignore[attr-defined]
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
                path = os.path.join(ShortcutExecutor._app_install_dir(), "config")  # type: ignore[attr-defined]
            else:
                path = ShortcutExecutor._app_install_dir()  # type: ignore[attr-defined]
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
            return ShortcutExecutor._shell_execute_open(path)  # type: ignore[attr-defined, no-any-return]
        except Exception as e:
            logger.error("Open built-in filesystem target failed %s: %s", path, e, exc_info=True)
            return False

    @staticmethod
    def _open_builtin_text_file(path: str) -> bool:
        path = os.path.abspath(path)
        if not os.path.exists(path):
            return ShortcutExecutor._open_filesystem_target(path, create_dir=False)  # type: ignore[attr-defined, no-any-return]

        if os.name == "nt":
            try:
                params = subprocess.list2cmdline([path])
                if ShortcutExecutor._shell_execute_open("notepad.exe", params):  # type: ignore[attr-defined]
                    logger.info("Opened built-in text file via notepad: %s", path)
                    return True
            except Exception:
                logger.debug("Opening built-in text file via notepad failed: %s", path, exc_info=True)

        return ShortcutExecutor._open_filesystem_target(  # type: ignore[attr-defined, no-any-return]
            path,
            create_dir=False,
            fallback_to_parent=False,
        )

    @staticmethod
    def _open_builtin_filesystem_target(command: str) -> bool:
        install_dir = ShortcutExecutor._app_install_dir()  # type: ignore[attr-defined]
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
            return ShortcutExecutor._open_builtin_text_file(path)  # type: ignore[attr-defined, no-any-return]
        return ShortcutExecutor._open_filesystem_target(path, create_dir=create_dir)  # type: ignore[attr-defined, no-any-return]

    @staticmethod
    def _open_windows_system_builtin(command: str) -> bool:
        if command == "open_windows_settings":
            if ShortcutExecutor._shell_execute_open("ms-settings:"):  # type: ignore[attr-defined]
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
        if ShortcutExecutor._shell_execute_open(target, parameters):  # type: ignore[attr-defined]
            return True
        try:
            ShortcutExecutor._popen_silent(  # type: ignore[attr-defined]
                fallback_argv,
                env=ShortcutExecutor._sanitized_child_env(),  # type: ignore[attr-defined]
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
        command_type = ShortcutExecutor._normalize_command_type(getattr(shortcut, "command_type", "cmd"))  # type: ignore[attr-defined]
        max_chars = getattr(shortcut, "command_output_max_chars", DEFAULT_COMMAND_OUTPUT_MAX_CHARS)
        panel_size = ShortcutExecutor._command_panel_size(shortcut)  # type: ignore[attr-defined]
        timeout_value = normalize_command_timeout_seconds(
            timeout
            if timeout is not None
            else getattr(shortcut, "command_timeout_seconds", DEFAULT_COMMAND_TIMEOUT_SECONDS)
        )

        command, prepare_error = ShortcutExecutor._prepare_command_for_execution(  # type: ignore[attr-defined]
            shortcut,
            command,
            command_type,
            panel_size=panel_size,
            display_type="log",
        )
        if prepare_error is not None:
            return prepare_error  # type: ignore[no-any-return]

        cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
        if command_type == "builtin":
            success = ShortcutExecutor._execute_builtin_for_shortcut(shortcut, command)  # type: ignore[attr-defined]
            pending = take_pending_command_result()
            if pending is not None:
                pending.payload.setdefault("window_size", panel_size)
                return pending
            return ShortcutExecutor._capture_builtin_result(success, panel_size, start)  # type: ignore[attr-defined, no-any-return]

        preflight = ShortcutExecutor._preflight_command(shortcut, command, command_type, capture=True)  # type: ignore[attr-defined]
        if preflight is not None:
            if isinstance(getattr(preflight, "payload", None), dict):
                preflight.payload.setdefault("window_size", panel_size)
            return preflight  # type: ignore[no-any-return]

        confirmation = ShortcutExecutor._destructive_confirmation_result(  # type: ignore[attr-defined]
            shortcut,
            command,
            command_type,
            panel_size=panel_size,
        )
        if confirmation is not None:
            return confirmation  # type: ignore[no-any-return]

        try:
            launch_spec = ShortcutExecutor._capture_launch_spec(command, command_type, panel_size, start)  # type: ignore[attr-defined]
            if isinstance(launch_spec, CommandResult):
                return launch_spec
            popen_args, stdin_data, shell = launch_spec
            try:
                env = ShortcutExecutor._runtime_env(shortcut)  # type: ignore[attr-defined]
                process = subprocess.Popen(
                    popen_args,
                    cwd=cwd,
                    env=env,
                    stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=False,
                    shell=shell,
                    **ShortcutExecutor._capture_popen_platform_kwargs(),  # type: ignore[attr-defined]
                )
            except OSError as exc:
                if command_type == "bash" and ShortcutExecutor._bash_direct_capture_denied(str(exc)):  # type: ignore[attr-defined]
                    fallback = ShortcutExecutor._bash_capture_via_script(  # type: ignore[attr-defined]
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
                        return fallback  # type: ignore[no-any-return]
                    message = ShortcutExecutor._bash_direct_capture_denied_message(str(exc))  # type: ignore[attr-defined]
                    return ShortcutExecutor._capture_error_result(  # type: ignore[attr-defined, no-any-return]
                        message,
                        str(exc),
                        panel_size,
                        start=start,
                        command=command,
                    )
                else:
                    raise

            if on_update is not None:
                return ShortcutExecutor._run_command_capture_streaming(  # type: ignore[attr-defined, no-any-return]
                    process=process,
                    stdin_data=stdin_data,
                    timeout_value=timeout_value,
                    start=start,
                    max_chars=max_chars,
                    panel_size=panel_size,
                    command_type=command_type,
                    shortcut=shortcut,
                    command=command,
                    cwd=cwd,
                    env=env,
                    cancel_event=cancel_event,
                    on_update=on_update,
                )
            return ShortcutExecutor._run_command_capture_blocking(  # type: ignore[attr-defined, no-any-return]
                process=process,
                stdin_data=stdin_data,
                timeout_value=timeout_value,
                start=start,
                max_chars=max_chars,
                panel_size=panel_size,
                command_type=command_type,
                shortcut=shortcut,
                command=command,
                cwd=cwd,
                env=env,
                cancel_event=cancel_event,
                popen_args=popen_args,
            )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"命令捕获执行失败: {e}",
                display_type="log",
                error=str(e),
                payload={"window_size": panel_size, "duration": time.monotonic() - start},
            )

    @staticmethod
    def _capture_launch_spec(
        command: str,
        command_type: str,
        panel_size: str,
        start: float,
    ) -> tuple[list[str], bytes | None, bool] | CommandResult:
        stdin_data = None
        if command_type == "python":
            python_exe = ShortcutExecutor._python_launcher()  # type: ignore[attr-defined]
            if not python_exe:
                return ShortcutExecutor._capture_error_result(  # type: ignore[attr-defined, no-any-return]
                    ShortcutExecutor._python_launcher_error(),  # type: ignore[attr-defined]
                    "Python 不可用",
                    panel_size,
                )
            return [python_exe, "-u"], command.encode("utf-8"), False
        if command_type == "powershell":
            popen_args = ShortcutExecutor._powershell_argv(command)  # type: ignore[attr-defined]
            if ShortcutExecutor._direct_command_line_too_long(popen_args):  # type: ignore[attr-defined]
                message = ShortcutExecutor._direct_command_line_length_error(command_type, popen_args)  # type: ignore[attr-defined]
                return ShortcutExecutor._capture_error_result(message, "命令过长", panel_size, start=start)  # type: ignore[attr-defined, no-any-return]
            return popen_args, stdin_data, False
        if command_type == "bash":
            bash_exe = ShortcutExecutor._bash_launcher()  # type: ignore[attr-defined]
            if not bash_exe:
                return ShortcutExecutor._capture_error_result(  # type: ignore[attr-defined, no-any-return]
                    ShortcutExecutor._bash_launcher_error(),  # type: ignore[attr-defined]
                    "Git Bash 不可用",
                    panel_size,
                )
            logger.debug("Bash capture: launcher=%s, route=capture-direct", bash_exe)
            popen_args = ShortcutExecutor._bash_argv(command)  # type: ignore[attr-defined]
            if ShortcutExecutor._direct_command_line_too_long(popen_args):  # type: ignore[attr-defined]
                message = ShortcutExecutor._direct_command_line_length_error(command_type, popen_args)  # type: ignore[attr-defined]
                return ShortcutExecutor._capture_error_result(message, "命令过长", panel_size, start=start)  # type: ignore[attr-defined, no-any-return]
            return popen_args, stdin_data, False
        if command_type == "cmd":
            if ShortcutExecutor._cmd_has_newline(command):  # type: ignore[attr-defined]
                return ShortcutExecutor._cmd_stdin_argv(), ShortcutExecutor._cmd_stdin_script(command), False  # type: ignore[attr-defined]
            popen_args = ShortcutExecutor._cmd_argv(command)  # type: ignore[attr-defined]
            if ShortcutExecutor._direct_command_line_too_long(popen_args):  # type: ignore[attr-defined]
                message = ShortcutExecutor._direct_command_line_length_error(command_type, popen_args)  # type: ignore[attr-defined]
                return ShortcutExecutor._capture_error_result(message, "命令过长", panel_size, start=start)  # type: ignore[attr-defined, no-any-return]
            return popen_args, stdin_data, False
        return ShortcutExecutor._capture_error_result(  # type: ignore[attr-defined, no-any-return]
            f"Unsupported command type: {command_type}",
            "Unsupported command type",
            panel_size,
            start=start,
        )

    @staticmethod
    def _run_command_capture_streaming(
        *,
        process,
        stdin_data,
        timeout_value: float,
        start: float,
        max_chars: int,
        panel_size: str,
        command_type: str,
        shortcut: ShortcutItem,
        command: str,
        cwd: str | None,
        env: dict[str, str],
        cancel_event: threading.Event | None,
        on_update,
    ) -> CommandResult:
        stdin_pipe = getattr(process, "stdin", None)
        if stdin_data is not None and stdin_pipe is not None:
            stdin_pipe.write(stdin_data)
            stdin_pipe.close()
        output_queue = queue.Queue()  # type: ignore[var-annotated]

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

        executor = ShortcutExecutor._get_executor()  # type: ignore[attr-defined]
        executor.submit(_reader, process.stdout, "stdout")
        executor.submit(_reader, process.stderr, "stderr")
        stdout_parts = []  # type: ignore[var-annotated]
        stderr_parts = []  # type: ignore[var-annotated]
        deadline = time.monotonic() + timeout_value
        last_update = 0.0
        timed_out = False
        cancelled = False

        while process.poll() is None or not output_queue.empty():
            ShortcutExecutor._drain_capture_queue(output_queue, stdout_parts, stderr_parts)  # type: ignore[attr-defined]
            now = time.monotonic()
            if (stdout_parts or stderr_parts) and now - last_update >= COMMAND_CAPTURE_UPDATE_INTERVAL_SECONDS:
                ShortcutExecutor._emit_capture_update(  # type: ignore[attr-defined]
                    stdout_parts=stdout_parts,
                    stderr_parts=stderr_parts,
                    stdin_data=stdin_data,
                    max_chars=max_chars,
                    panel_size=panel_size,
                    command_type=command_type,
                    shortcut=shortcut,
                    command=command,
                    start=start,
                    now=now,
                    on_update=on_update,
                )
                last_update = now

            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                ShortcutExecutor._terminate_process_tree(process)  # type: ignore[attr-defined]
                break
            if time.monotonic() >= deadline:
                timed_out = True
                ShortcutExecutor._terminate_process_tree(process)  # type: ignore[attr-defined]
                break
            time.sleep(COMMAND_CAPTURE_POLL_SECONDS)

        try:
            process.wait(timeout=PROCESS_TERMINATE_WAIT_SECONDS)
        except Exception as exc:
            logger.debug("等待进程结束失败: %s", exc, exc_info=True)
        ShortcutExecutor._drain_capture_queue(output_queue, stdout_parts, stderr_parts)  # type: ignore[attr-defined]
        return ShortcutExecutor._finalize_capture_bytes(  # type: ignore[attr-defined, no-any-return]
            stdout_bytes=b"".join(stdout_parts),
            stderr_bytes=b"".join(stderr_parts),
            returncode=process.returncode,
            cancelled=cancelled,
            timed_out=timed_out,
            stdin_data=stdin_data,
            max_chars=max_chars,
            panel_size=panel_size,
            command_type=command_type,
            shortcut=shortcut,
            command=command,
            cwd=cwd,
            env=env,
            timeout_value=timeout_value,
            start=start,
        )

    @staticmethod
    def _drain_capture_queue(output_queue: queue.Queue, stdout_parts: list[bytes], stderr_parts: list[bytes]) -> None:
        while True:
            try:
                name, chunk = output_queue.get_nowait()
            except queue.Empty:
                break
            if name == "stdout":
                stdout_parts.append(chunk)
            else:
                stderr_parts.append(chunk)

    @staticmethod
    def _emit_capture_update(
        *,
        stdout_parts: list[bytes],
        stderr_parts: list[bytes],
        stdin_data,
        max_chars: int,
        panel_size: str,
        command_type: str,
        shortcut: ShortcutItem,
        command: str,
        start: float,
        now: float,
        on_update,
    ) -> None:
        update_stdout_bytes = b"".join(stdout_parts)
        update_stderr_bytes = b"".join(stderr_parts)
        if command_type == "cmd" and stdin_data is not None:
            update_stdout_bytes = ShortcutExecutor._clean_cmd_stdin_output_bytes(update_stdout_bytes)  # type: ignore[attr-defined]
            update_stderr_bytes = ShortcutExecutor._clean_cmd_stdin_output_bytes(update_stderr_bytes)  # type: ignore[attr-defined]
        stdout, stdout_encoding, stdout_fallback = ShortcutExecutor._decode_bytes(  # type: ignore[attr-defined]
            update_stdout_bytes, getattr(shortcut, "command_encoding", "auto"), command_type
        )
        stderr, stderr_encoding, stderr_fallback = ShortcutExecutor._decode_bytes(  # type: ignore[attr-defined]
            update_stderr_bytes, getattr(shortcut, "command_encoding", "auto")
        )
        update_stdout, stdout_truncated = ShortcutExecutor._truncate_output(stdout or "", max_chars)  # type: ignore[attr-defined]
        update_stderr, stderr_truncated = ShortcutExecutor._truncate_output(stderr or "", max_chars)  # type: ignore[attr-defined]
        parts = []
        if update_stdout:
            parts.append(update_stdout)
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

    @staticmethod
    def _run_command_capture_blocking(
        *,
        process,
        stdin_data,
        timeout_value: float,
        start: float,
        max_chars: int,
        panel_size: str,
        command_type: str,
        shortcut: ShortcutItem,
        command: str,
        cwd: str | None,
        env: dict[str, str],
        cancel_event: threading.Event | None,
        popen_args: list[str],
    ) -> CommandResult:
        try:
            if cancel_event is None:
                if stdin_data is None:
                    stdout_bytes, stderr_bytes = process.communicate(timeout=timeout_value)
                else:
                    stdout_bytes, stderr_bytes = process.communicate(input=stdin_data, timeout=timeout_value)
            else:
                cancel_result = ShortcutExecutor._wait_capture_with_cancel(  # type: ignore[attr-defined]
                    process=process,
                    stdin_data=stdin_data,
                    timeout_value=timeout_value,
                    start=start,
                    max_chars=max_chars,
                    panel_size=panel_size,
                    command_type=command_type,
                    shortcut=shortcut,
                    command=command,
                    popen_args=popen_args,
                    cancel_event=cancel_event,
                )
                if isinstance(cancel_result, CommandResult):
                    return cancel_result
                stdout_bytes, stderr_bytes = cancel_result
            returncode = process.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            ShortcutExecutor._terminate_process_tree(process)  # type: ignore[attr-defined]
            stdout_bytes, stderr_bytes = process.communicate()
            returncode = process.returncode
            timed_out = True

        return ShortcutExecutor._finalize_capture_bytes(  # type: ignore[attr-defined, no-any-return]
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            returncode=returncode,
            cancelled=False,
            timed_out=timed_out,
            stdin_data=stdin_data,
            max_chars=max_chars,
            panel_size=panel_size,
            command_type=command_type,
            shortcut=shortcut,
            command=command,
            cwd=cwd,
            env=env,
            timeout_value=timeout_value,
            start=start,
        )

    @staticmethod
    def _wait_capture_with_cancel(
        *,
        process,
        stdin_data,
        timeout_value: float,
        start: float,
        max_chars: int,
        panel_size: str,
        command_type: str,
        shortcut: ShortcutItem,
        command: str,
        popen_args: list[str],
        cancel_event: threading.Event,
    ):
        stdin_pipe = getattr(process, "stdin", None)
        if stdin_data is not None and stdin_pipe is not None:
            stdin_pipe.write(stdin_data)
            stdin_pipe.close()
        deadline = time.monotonic() + timeout_value
        while process.poll() is None:
            if cancel_event.is_set():
                ShortcutExecutor._terminate_process_tree(process)  # type: ignore[attr-defined]
                stdout_bytes, stderr_bytes = process.communicate()
                return ShortcutExecutor._build_cancel_result_from_bytes(  # type: ignore[attr-defined]
                    stdout_bytes=stdout_bytes,
                    stderr_bytes=stderr_bytes,
                    process=process,
                    max_chars=max_chars,
                    panel_size=panel_size,
                    command_type=command_type,
                    shortcut=shortcut,
                    command=command,
                    start=start,
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(popen_args, timeout_value)
            time.sleep(min(COMMAND_CAPTURE_POLL_SECONDS, remaining))
        return process.communicate()

    @staticmethod
    def _build_cancel_result_from_bytes(
        *,
        stdout_bytes: bytes,
        stderr_bytes: bytes,
        process,
        max_chars: int,
        panel_size: str,
        command_type: str,
        shortcut: ShortcutItem,
        command: str,
        start: float,
    ) -> CommandResult:
        stdout, stderr, stdout_truncated, stderr_truncated, stdout_encoding, stderr_encoding, decode_fallback_used = (
            ShortcutExecutor._decode_capture_output(stdout_bytes, stderr_bytes, shortcut, command_type, max_chars)  # type: ignore[attr-defined]
        )
        return ShortcutExecutor._build_capture_cancel_result(  # type: ignore[attr-defined, no-any-return]
            panel_size=panel_size,
            returncode=process.returncode,
            start=start,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            stdout_encoding=stdout_encoding,
            stderr_encoding=stderr_encoding,
            decode_fallback_used=decode_fallback_used,
            command=command,
        )

    @staticmethod
    def _finalize_capture_bytes(
        *,
        stdout_bytes: bytes,
        stderr_bytes: bytes,
        returncode: int | None,
        cancelled: bool,
        timed_out: bool,
        stdin_data,
        max_chars: int,
        panel_size: str,
        command_type: str,
        shortcut: ShortcutItem,
        command: str,
        cwd: str | None,
        env: dict[str, str],
        timeout_value: float,
        start: float,
    ) -> CommandResult:
        if command_type == "cmd" and stdin_data is not None:
            stdout_bytes = ShortcutExecutor._clean_cmd_stdin_output_bytes(stdout_bytes)  # type: ignore[attr-defined]
            stderr_bytes = ShortcutExecutor._clean_cmd_stdin_output_bytes(stderr_bytes)  # type: ignore[attr-defined]
        stdout, stderr, stdout_truncated, stderr_truncated, stdout_encoding, stderr_encoding, decode_fallback_used = (
            ShortcutExecutor._decode_capture_output(stdout_bytes, stderr_bytes, shortcut, command_type, max_chars)  # type: ignore[attr-defined]
        )
        if cancelled:
            return ShortcutExecutor._build_capture_cancel_result(  # type: ignore[attr-defined, no-any-return]
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
            )
        if command_type == "bash" and ShortcutExecutor._bash_direct_capture_denied(stderr):  # type: ignore[attr-defined]
            fallback = ShortcutExecutor._bash_capture_via_script(  # type: ignore[attr-defined]
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
                return fallback  # type: ignore[no-any-return]
            return ShortcutExecutor._build_bash_fallback_result(  # type: ignore[attr-defined, no-any-return]
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
            )
        return ShortcutExecutor._build_capture_success_result(  # type: ignore[attr-defined, no-any-return]
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
            timeout_value=timeout_value,
        )

    @staticmethod
    def test_command(
        shortcut: ShortcutItem,
        timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
        cancel_event: threading.Event | None = None,
    ) -> dict:
        """Run a command shortcut synchronously for the editor test button."""
        captured = ShortcutExecutor.run_command_capture(shortcut, timeout=timeout, cancel_event=cancel_event)  # type: ignore[attr-defined]
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

    @staticmethod
    def _execute_builtin_for_shortcut(shortcut: ShortcutItem, command: str) -> bool:
        if bool(getattr(shortcut, "_topmost_target_captured", False)):
            return ShortcutExecutor._execute_builtin_command(  # type: ignore[attr-defined, no-any-return]
                command,
                topmost_target=getattr(shortcut, "_topmost_target", None),
            )
        return ShortcutExecutor._execute_builtin_command(command)  # type: ignore[attr-defined, no-any-return]

    @staticmethod
    def _execute_builtin_command(command: str, *, topmost_target=_TOPMOST_TARGET_UNSET) -> bool:
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
                    payload = result.payload if isinstance(getattr(result, "payload", {}), dict) else {}
                    if not payload.get("_suppress_result_panel"):
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
                    if _main_thread_invoker is not None and not ShortcutExecutor._is_qt_main_thread():  # type: ignore[attr-defined]
                        _main_thread_invoker.execute_signal.emit(lambda: call_callback(canonical))
                        logger.info(f"UI内置命令(通过主线程): {canonical}")
                    elif ShortcutExecutor._is_qt_main_thread():  # type: ignore[attr-defined]
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
                        return ShortcutExecutor._send_ipc_command_deferred("show_config")  # type: ignore[attr-defined, no-any-return]
                    if canonical in filesystem_builtin_commands:
                        return ShortcutExecutor._open_builtin_filesystem_target(canonical)  # type: ignore[attr-defined, no-any-return]
                    logger.warning(f"内置命令: 回调未注册: {canonical}")
                    return False
            except Exception as e:
                logger.error(f"内置命令执行失败 ({canonical}): {e}")
                return False

        if command_name == "toggle_topmost":
            if topmost_target is not _TOPMOST_TARGET_UNSET:
                return ShortcutExecutor._toggle_topmost(topmost_target)  # type: ignore[attr-defined, no-any-return]
            return ShortcutExecutor._toggle_topmost()  # type: ignore[attr-defined, no-any-return]

        # 旧版强制开关命令继续兼容已有配置，但主界面只推荐状态切换入口。
        if command_name == "pin_on":
            if topmost_target is not _TOPMOST_TARGET_UNSET:
                return ShortcutExecutor._set_topmost(True, topmost_target)  # type: ignore[attr-defined, no-any-return]
            return ShortcutExecutor._set_topmost(True)  # type: ignore[attr-defined, no-any-return]

        if command_name == "pin_off":
            if topmost_target is not _TOPMOST_TARGET_UNSET:
                return ShortcutExecutor._set_topmost(False, topmost_target)  # type: ignore[attr-defined, no-any-return]
            return ShortcutExecutor._set_topmost(False)  # type: ignore[attr-defined, no-any-return]

        if command_name in filesystem_builtin_commands:
            return ShortcutExecutor._open_builtin_filesystem_target(command_name)  # type: ignore[attr-defined, no-any-return]

        if command_name in WINDOWS_SYSTEM_BUILTIN_COMMANDS:
            return ShortcutExecutor._open_windows_system_builtin(command_name)  # type: ignore[attr-defined, no-any-return]

        return False

    @staticmethod
    def _send_ipc_command_deferred(command: str) -> bool:
        """延迟发送IPC命令，避免主线程阻塞导致的死锁

        当从弹窗点击内置命令时，主线程正在处理执行流程，
        如果直接同步发送 IPC，会因为 waitForConnected() 阻塞事件循环，
        而 QLocalServer 的 newConnection 信号也需要事件循环来触发，
        导致连接永远无法建立（死锁）。

        解决方案：使用注册后台任务在短暂延迟后发送命令，
        让当前事件处理完成后再发送。
        """

        def do_send():
            try:
                # 延迟让 UI 事件处理完成
                # 打包版本首次调用需要更长延迟，Qt网络模块初始化较慢
                import time

                is_frozen = is_packaged_runtime()

                # 打包版本使用更长的初始延迟
                initial_delay = 0.35 if is_frozen else 0.15
                time.sleep(initial_delay)

                # 执行实际的 IPC 发送
                logger.debug(f"开始发送延迟IPC命令: {command} (frozen={is_frozen})")
                result = ShortcutExecutor._send_ipc_command(command)  # type: ignore[attr-defined]
                if result:
                    logger.debug(f"延迟IPC命令发送成功: {command}")
                else:
                    logger.warning(f"延迟IPC命令发送失败: {command}")
            except Exception:
                logger.exception("延迟IPC命令发送失败")

        try:
            # 使用 Python 线程而不是 QTimer，避免线程亲和性问题
            start_background_thread(
                name="IPCCommandSender",
                target=do_send,
                owner="shortcut-command-exec",
            )
            logger.debug(f"IPC命令已排队到后台线程: {command}")
            return True  # 返回 True 表示命令已排队（不是已执行）

        except Exception as e:
            logger.error(f"排队IPC命令失败: {e}, 尝试直接发送")
            # 回退到直接发送
            return ShortcutExecutor._send_ipc_command(command)  # type: ignore[attr-defined, no-any-return]

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
            from qt_compat import QLocalSocket

            is_frozen = is_packaged_runtime()

            # 首次调用时给Qt网络模块和IPC服务器更多初始化时间
            # 这对于打包后的exe在首次使用QLocalSocket尤为重要
            if not hasattr(ShortcutExecutor, "_ipc_initialized"):
                ShortcutExecutor._ipc_initialized = True  # type: ignore[attr-defined]
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
