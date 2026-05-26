"""Command execution helpers for ShortcutExecutor."""

from __future__ import annotations

import ctypes
import locale
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
from typing import List, Optional

from qt_compat import QObject, pyqtSignal

from .command_registry import (
    CommandAction,
    CommandContext,
    CommandResult,
    set_pending_command_result,
    take_pending_command_result,
)
from .command_variables import (
    CommandVariableError,
    find_unquoted_external_command_variables,
    is_value_only_variable_command,
    read_clipboard_text,
    resolve_command_variables,
    should_expand_command_variables,
)
from .data_models import ShortcutItem

logger = logging.getLogger(__name__)
ShortcutExecutor = None


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


class CommandExecutionMixin:
    _PARAM_TOKEN_RE = re.compile(r"(?<!\{)\{param:([^{}\r\n:]+)(?::q)?\}(?!\})")
    _CHAIN_TOKEN_RE = re.compile(r"(?<!\{)\{chain:([^{}\r\n:]+)(?::q)?\}(?!\})")

    @staticmethod
    def _command_param_defs(shortcut: ShortcutItem) -> list[dict]:
        try:
            return ShortcutItem._normalize_command_params(getattr(shortcut, "command_params", []))
        except Exception:
            return []

    @staticmethod
    def _command_param_values(shortcut: ShortcutItem) -> dict[str, str]:
        values = {}
        for param in ShortcutExecutor._command_param_defs(shortcut):
            values[param["name"]] = str(param.get("default") or "")
        runtime = getattr(shortcut, "_runtime_param_values", None)
        if isinstance(runtime, dict):
            values.update({str(k): str(v) for k, v in runtime.items()})
        return values

    @staticmethod
    def _chain_values(shortcut: ShortcutItem) -> dict[str, str]:
        values = getattr(shortcut, "_chain_values", None)
        return dict(values or {}) if isinstance(values, dict) else {}

    @staticmethod
    def _runtime_env(shortcut: ShortcutItem) -> dict:
        env = ShortcutExecutor._sanitized_child_env()
        command_env = getattr(shortcut, "command_env", {}) or {}
        if isinstance(command_env, str):
            command_env = ShortcutItem._normalize_command_env(command_env)
        if isinstance(command_env, dict):
            for key, value in command_env.items():
                key = str(key or "").strip()
                if key:
                    env[key] = str(value)
        return env

    @staticmethod
    def _command_panel_size(shortcut: ShortcutItem) -> str:
        size = str(getattr(shortcut, "command_panel_size", "medium") or "medium").lower().strip()
        return size if size in ("small", "medium", "large") else "medium"

    @staticmethod
    def _decode_bytes(data: bytes, preferred: str = "auto") -> tuple[str, str, bool]:
        if isinstance(data, str):
            return data, "text", False
        data = data or b""
        candidates: list[str] = []
        preferred = str(preferred or "auto").lower().strip()
        if preferred and preferred != "auto":
            candidates.append(preferred)
        candidates.append("utf-8")
        if os.name == "nt":
            try:
                oem_cp = ctypes.windll.kernel32.GetOEMCP()
                if oem_cp:
                    candidates.append(f"cp{oem_cp}")
            except Exception:
                pass
        try:
            pref = locale.getpreferredencoding(False)
            if pref:
                candidates.append(pref)
        except Exception:
            pass
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

    @staticmethod
    def _preflight_command(shortcut: ShortcutItem, command: str, command_type: str, *, capture: bool = False):
        items = []
        cwd = (getattr(shortcut, "working_dir", "") or "").strip()
        if not command:
            items.append({"title": "命令内容", "status": "failed", "detail": "命令内容为空。"})
        if cwd and not os.path.isdir(cwd):
            items.append({"title": "工作目录", "status": "failed", "detail": f"目录不存在: {cwd}"})
        if command_type == "python" and not ShortcutExecutor._python_launcher():
            items.append({"title": "Python", "status": "failed", "detail": ShortcutExecutor._python_launcher_error()})
        if capture and bool(getattr(shortcut, "show_window", False)):
            items.append({"title": "捕获输出", "status": "failed", "detail": "显示执行窗口时不能捕获输出。"})
        if capture and bool(getattr(shortcut, "run_as_admin", False)):
            items.append({"title": "捕获输出", "status": "failed", "detail": "管理员命令暂不支持捕获输出。"})
        if command_type == "cmd":
            unsafe = find_unquoted_external_command_variables(command)
            if unsafe:
                examples = ", ".join(f"{{{name}:q}}" for name in unsafe[:3])
                items.append(
                    {
                        "title": "命令参数引用",
                        "status": "failed",
                        "detail": f"外部输入变量用于 CMD 时必须使用 :q 引用，例如: {examples}",
                    }
                )
        param_values = ShortcutExecutor._command_param_values(shortcut)
        for param in ShortcutExecutor._command_param_defs(shortcut):
            if param.get("required") and not str(param_values.get(param["name"], "")).strip():
                items.append({"title": "命令参数", "status": "failed", "detail": f"缺少必填参数: {param['name']}"})
        if command_type == "cmd" and is_value_only_variable_command(command):
            items.append({"title": "命令内容", "status": "failed", "detail": "命令不能只包含一个变量占位符。"})
        if items:
            message = "\n".join(f"[{item['status'].upper()}] {item['title']}: {item['detail']}" for item in items)
            return CommandResult(success=False, message=message, display_type="list", payload={"items": items}, error="预检失败")
        return None

    @staticmethod
    def _python_launcher() -> Optional[str]:
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
        except Exception:
            pass
        # If GetLongPathNameW fails (e.g. 8.3 names disabled on this volume),
        # verify the path actually exists — a stale short-path will break .cmd wrappers.
        if not os.path.exists(path):
            logger.debug("_resolve_long_path: path does not exist after GetLongPathNameW: %s", path)
        return path

    @staticmethod
    def _find_system_python_launcher() -> Optional[str]:
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
            "找不到可用的系统 Python。打包版不能直接复用程序目录内的 python312.dll；"
            "请安装系统 Python 或 py launcher。"
        )

    @staticmethod
    def _write_temp_python_script(command: str) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(command)
            return f.name

    @staticmethod
    def _write_python_cmd_wrapper(script_path: str) -> str:
        python_exe = ShortcutExecutor._python_launcher()
        if not python_exe:
            raise RuntimeError(ShortcutExecutor._python_launcher_error())
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cmd", delete=False, encoding="utf-8") as f:
            wrapper_path = f.name
            f.write("@echo off\n")
            f.write("chcp 65001 >nul\n")
            f.write(subprocess.list2cmdline([python_exe, script_path]) + "\n")
            f.write("set QL_EXIT=%ERRORLEVEL%\n")
            f.write(f'del /f /q "{script_path}" >nul 2>nul\n')
            f.write("echo.\n")
            f.write("echo [QuickLauncher] Python exited with code %QL_EXIT%.\n")
            f.write('del /f /q "%~f0" >nul 2>nul\n')
            return wrapper_path

    @staticmethod
    def _write_cmd_wrapper(command: str) -> tuple[str, str]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cmd", delete=False, encoding="utf-8") as user_file:
            user_path = user_file.name
            user_file.write("@echo off\n")
            user_file.write("chcp 65001 >nul\n")
            user_file.write(command)
            if not command.endswith(("\n", "\r")):
                user_file.write("\n")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cmd", delete=False, encoding="utf-8") as wrapper_file:
            wrapper_path = wrapper_file.name
            wrapper_file.write("@echo off\n")
            wrapper_file.write("chcp 65001 >nul\n")
            wrapper_file.write(f'call "{user_path}"\n')
            wrapper_file.write("set QL_EXIT=%ERRORLEVEL%\n")
            wrapper_file.write(f'del /f /q "{user_path}" >nul 2>nul\n')
            wrapper_file.write('del /f /q "%~f0" >nul 2>nul\n')
            wrapper_file.write("exit /b %QL_EXIT%\n")
            return user_path, wrapper_path

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
                try:
                    process.kill()
                    process.wait(timeout=2.0)
                except Exception:
                    pass
            except Exception:
                pass
            for path in paths:
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except Exception as e:
                    logger.debug("临时文件清理失败 %s: %s", path, e)

        threading.Thread(target=cleanup, daemon=True, name="CommandTempCleanup").start()

    @staticmethod
    def _run_silent_output(argv: List[str]) -> str:
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
    def _execute_command(shortcut: ShortcutItem) -> tuple[bool, str]:
        """执行命令类型快捷方式"""
        command = shortcut.command
        if not command:
            logger.warning("命令为空")
            return False, "命令内容为空"

        command_type = getattr(shortcut, "command_type", "cmd")
        if command_type == "cmd" and is_value_only_variable_command(command):
            if ShortcutExecutor._should_expand_command_variables(shortcut):
                return False, f"命令只包含值占位符，不能直接执行。请改为可执行命令，例如: echo {command}"
            return (
                False,
                f"命令只包含变量占位符，但未启用解析变量。请启用解析变量，或改为可执行命令，例如: echo {command}",
            )
        if command_type == "cmd" and ShortcutExecutor._should_expand_command_variables(shortcut):
            unsafe_variables = find_unquoted_external_command_variables(command)
            if unsafe_variables:
                examples = ", ".join(f"{{{name}:q}}" for name in unsafe_variables[:3])
                return False, f"外部输入变量用于 CMD 命令时必须使用 :q 引用，例如: {examples}"
        try:
            if ShortcutExecutor._should_expand_command_variables(shortcut):
                command = ShortcutExecutor._resolve_command_variables(shortcut, command)
        except CommandVariableError as e:
            return False, str(e)

        if command_type != "python":
            try:
                from core.builtin_commands import canonical_builtin_command

                parts = command.strip().split(None, 1)
                cmd_word = parts[0] if parts else ""
                canonical = canonical_builtin_command(cmd_word)
                if canonical:
                    args_part = parts[1] if len(parts) > 1 else ""
                    if args_part:
                        command = f"{canonical} {args_part}"
                    else:
                        command = canonical
                    command_type = "builtin"
            except Exception as e:
                logger.debug("内置命令规范化失败（可忽略）: %s", e)

        capture_output = bool(getattr(shortcut, "capture_output", False))
        preflight = ShortcutExecutor._preflight_command(shortcut, command, command_type, capture=False)
        if preflight is not None:
            set_pending_command_result(preflight)
            return False, preflight.message or preflight.error
        if (
            capture_output
            and command_type in ("cmd", "python")
            and not bool(getattr(shortcut, "show_window", False))
            and not bool(getattr(shortcut, "run_as_admin", False))
        ):
            result = ShortcutExecutor.run_command_capture(shortcut)
            set_pending_command_result(result)
            return result.success, result.error

        # Python 代码执行
        if command_type == "python":
            show_window = getattr(shortcut, "show_window", False)
            if show_window:
                tmp_path = None
                try:
                    if not ShortcutExecutor._python_launcher():
                        return False, ShortcutExecutor._python_launcher_error()
                    tmp_path = ShortcutExecutor._write_temp_python_script(command)
                    if os.name == "nt":
                        wrapper_path = ShortcutExecutor._write_python_cmd_wrapper(tmp_path)
                        run_as_admin = getattr(shortcut, "run_as_admin", False)
                        launched, launch_error = ShortcutExecutor._launch_with_privilege(
                            os.environ.get("ComSpec")
                            or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"),
                            subprocess.list2cmdline(["/d", "/s", "/k", wrapper_path]),
                            (getattr(shortcut, "working_dir", "") or "").strip() or None,
                            show_cmd=1,
                            run_as_admin=run_as_admin,
                            admin_failure_message="Administrator launch failed.",
                        )
                        if launched:
                            return True, ""
                        if launch_error:
                            return False, launch_error
                    python_exe = ShortcutExecutor._python_launcher()
                    if not python_exe:
                        return False, ShortcutExecutor._python_launcher_error()
                    process = subprocess.Popen([python_exe, tmp_path], shell=False)
                    ShortcutExecutor._cleanup_file_later(process, tmp_path)
                    return True, ""
                except FileNotFoundError:
                    try:
                        if tmp_path and os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass
                    return False, ShortcutExecutor._python_launcher_error()
                except Exception as e:
                    try:
                        if tmp_path and os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass
                    return False, f"Python 代码执行失败: {e}"
            try:
                python_exe = ShortcutExecutor._python_launcher()
                if not python_exe:
                    raise FileNotFoundError(ShortcutExecutor._python_launcher_error())
                tmp_path = ShortcutExecutor._write_temp_python_script(command)
                process = ShortcutExecutor._popen_silent(
                    [python_exe, tmp_path],
                    cwd=(getattr(shortcut, "working_dir", "") or "").strip() or None,
                    env=ShortcutExecutor._runtime_env(shortcut),
                    shell=False,
                )
                ShortcutExecutor._cleanup_file_later(process, tmp_path)
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
            raw_command = command
            if "\n" in raw_command or "\r" in raw_command:
                try:
                    user_cmd_path, wrapper_path = ShortcutExecutor._write_cmd_wrapper(raw_command)
                    cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
                    comspec = os.environ.get("ComSpec") or os.path.join(
                        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"
                    )
                    if os.name == "nt":
                        launched, launch_error = ShortcutExecutor._launch_with_privilege(
                            comspec,
                            subprocess.list2cmdline(["/d", "/s", "/k" if show_window else "/c", wrapper_path]),
                            cwd,
                            show_cmd=show_cmd,
                            run_as_admin=run_as_admin,
                            admin_failure_message="Administrator launch failed.",
                        )
                        if launched:
                            return True, ""
                        if launch_error:
                            return False, launch_error
                    process = ShortcutExecutor._popen_silent(
                        [comspec, "/d", "/s", "/c", wrapper_path],
                        cwd=cwd,
                        env=ShortcutExecutor._runtime_env(shortcut),
                        shell=False,
                    )
                    ShortcutExecutor._cleanup_file_later(process, user_cmd_path, wrapper_path)
                    return True, ""
                except Exception as e:
                    error_msg = f"命令启动失败: {e}"
                    logger.error(error_msg)
                    return False, error_msg
            # 多行命令合并为单行
            command = " & ".join(line.strip() for line in command.splitlines() if line.strip())

            try:
                # 运行CMD命令
                parsed = ShortcutExecutor._safe_split_args(command)
                exe_path = parsed[0] if parsed else ""

                # 尝试检测是否为直接的可执行文件
                if exe_path and exe_path.lower().endswith(".exe") and os.path.exists(exe_path):
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
                            logger.info(f"Launch via ShellExecute: {exe_path}")
                            return True, ""
                        if launch_error:
                            return False, launch_error
                    if show_window:
                        process = subprocess.Popen(parsed, cwd=cwd or exe_dir or None)
                    else:
                        process = ShortcutExecutor._popen_silent(
                            parsed, cwd=cwd or exe_dir or None, env=ShortcutExecutor._runtime_env(shortcut), shell=False
                        )
                    logger.info(f"执行程序({'Visible' if show_window else 'Silent'}): {exe_path}")
                else:
                    # 对于其他命令，使用 shell=True
                    cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None

                    if os.name == "nt":
                        # show_window 时用 /k 保持窗口，否则用 /c 执行后关闭
                        cmd_flag = "/k" if show_window else "/c"
                        launched, launch_error = ShortcutExecutor._launch_with_privilege(
                            os.environ.get("ComSpec")
                            or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"),
                            subprocess.list2cmdline(["/d", "/s", cmd_flag, command]),
                            cwd,
                            show_cmd=show_cmd,
                            run_as_admin=run_as_admin,
                            admin_failure_message="Administrator launch failed.",
                        )
                        if launched:
                            logger.info(f"Command via ShellExecute: {command}")
                            return True, ""
                        if launch_error:
                            return False, launch_error

                    if show_window:
                        process = subprocess.Popen(command, cwd=cwd, shell=True)
                    else:
                        process = ShortcutExecutor._popen_silent(
                            command, cwd=cwd, env=ShortcutExecutor._runtime_env(shortcut), shell=True
                        )
                    logger.info(f"执行命令({'Visible' if show_window else 'Silent'} Shell): {command}")

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
        return resolve_command_variables(
            command,
            input_values=input_values,
            param_values=ShortcutExecutor._command_param_values(shortcut),
            chain_values=ShortcutExecutor._chain_values(shortcut),
            clipboard_provider=read_clipboard_text,
            selected_text_provider=selected_provider,
            strict_unknown=True,
        )

    @staticmethod
    def _should_expand_command_variables(shortcut: ShortcutItem) -> bool:
        command_type = getattr(shortcut, "command_type", "cmd")
        enabled = getattr(shortcut, "command_variables_enabled", None)
        if ShortcutExecutor._command_param_defs(shortcut) or ShortcutExecutor._chain_values(shortcut):
            return command_type != "builtin"
        return should_expand_command_variables(command_type, enabled)

    @staticmethod
    def _capture_selected_text() -> str:
        """Copy selected text from the previous foreground window and restore clipboard."""
        snapshot = ShortcutExecutor._snapshot_clipboard()
        original_text = read_clipboard_text()
        original_sequence = ShortcutExecutor._get_clipboard_sequence_number()
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
                if ShortcutExecutor._get_clipboard_sequence_number() != original_sequence:
                    break
            if ShortcutExecutor._get_clipboard_sequence_number() == original_sequence:
                return ""
            return read_clipboard_text()
        finally:
            if not ShortcutExecutor._restore_clipboard_snapshot(snapshot):
                try:
                    ShortcutExecutor._write_clipboard_text(original_text)
                except Exception:
                    pass

    @staticmethod
    def _get_clipboard_sequence_number() -> int:
        if os.name != "nt":
            return 0
        try:
            return int(ctypes.windll.user32.GetClipboardSequenceNumber())
        except Exception:
            return 0

    @staticmethod
    def _snapshot_clipboard():
        if os.name != "nt":
            return None
        try:
            import win32clipboard
            import win32con

            supported = {win32con.CF_UNICODETEXT, win32con.CF_TEXT}
            if hasattr(win32con, "CF_HDROP"):
                supported.add(win32con.CF_HDROP)

            snapshot = []
            win32clipboard.OpenClipboard()
            try:
                fmt = 0
                while True:
                    fmt = win32clipboard.EnumClipboardFormats(fmt)
                    if not fmt:
                        break
                    try:
                        data = win32clipboard.GetClipboardData(fmt)
                    except Exception:
                        continue
                    if fmt in supported or isinstance(data, (bytes, bytearray, str, tuple)):
                        snapshot.append((fmt, data))
            finally:
                win32clipboard.CloseClipboard()
            return snapshot
        except Exception as e:
            logger.debug("clipboard snapshot failed: %s", e)
            return None

    @staticmethod
    def _restore_clipboard_snapshot(snapshot) -> bool:
        if snapshot is None or os.name != "nt":
            return False
        try:
            import win32clipboard

            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                ok = True
                for fmt, data in snapshot:
                    try:
                        win32clipboard.SetClipboardData(fmt, data)
                    except Exception as e:
                        ok = False
                        logger.debug("clipboard format restore failed %s: %s", fmt, e)
                return ok
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            logger.debug("clipboard restore failed: %s", e)
            return False

    @staticmethod
    def _write_clipboard_text(text: str) -> bool:
        try:
            import win32clipboard
            import win32con

            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text or "")
                return True
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            logger.debug("写入剪贴板失败: %s", e)
            return False

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
                logger.info("Opened built-in filesystem target: %s", path)
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
        text = text or ""
        max_chars = max(1000, int(max_chars or 20000))
        if len(text) <= max_chars:
            return text, False
        return text[:max_chars] + "\n\n[输出过长，已截断]", True

    @staticmethod
    def run_command_capture(
        shortcut: ShortcutItem,
        timeout: float | None = None,
        cancel_event: threading.Event | None = None,
        on_update=None,
    ) -> CommandResult:
        """Run a CMD/Python/builtin command and return a CommandResult with captured output."""
        start = time.monotonic()
        command = shortcut.command or ""
        command_type = getattr(shortcut, "command_type", "cmd")
        max_chars = getattr(shortcut, "command_output_max_chars", 20000)
        panel_size = ShortcutExecutor._command_panel_size(shortcut)
        timeout_value = float(
            timeout if timeout is not None else getattr(shortcut, "command_timeout_seconds", 10.0) or 10.0
        )

        if command_type == "cmd" and is_value_only_variable_command(command):
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
                message=f"命令只包含变量占位符，但未启用解析变量。请启用解析变量，或改为可执行命令，例如: echo {command}",
                display_type="log",
                error="命令无效",
                payload={"window_size": panel_size},
            )
        if command_type == "cmd" and ShortcutExecutor._should_expand_command_variables(shortcut):
            unsafe_variables = find_unquoted_external_command_variables(command)
            if unsafe_variables:
                examples = ", ".join(f"{{{name}:q}}" for name in unsafe_variables[:3])
                message = f"外部输入变量用于 CMD 命令时必须使用 :q 引用，例如: {examples}"
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
        if command_type != "python":
            try:
                from core.builtin_commands import canonical_builtin_command

                parts = command.strip().split(None, 1)
                cmd_word = parts[0] if parts else ""
                canonical = canonical_builtin_command(cmd_word)
                if canonical:
                    args_part = parts[1] if len(parts) > 1 else ""
                    command = f"{canonical} {args_part}".strip()
                    command_type = "builtin"
            except Exception:
                pass

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

        tmp_path = None
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
                tmp_path = ShortcutExecutor._write_temp_python_script(command)
                popen_args = [python_exe, "-u", tmp_path]
                shell = False
            else:
                popen_args = command
                shell = True

            process = subprocess.Popen(
                popen_args,
                cwd=cwd,
                env=ShortcutExecutor._runtime_env(shortcut),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                shell=shell,
            )
            if on_update is not None:
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
                        except Exception:
                            pass

                threading.Thread(target=_reader, args=(process.stdout, "stdout"), daemon=True).start()
                threading.Thread(target=_reader, args=(process.stderr, "stderr"), daemon=True).start()
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
                    if (stdout_parts or stderr_parts) and now - last_update >= 0.15:
                        stdout, stdout_encoding, stdout_fallback = ShortcutExecutor._decode_bytes(
                            b"".join(stdout_parts), getattr(shortcut, "command_encoding", "auto")
                        )
                        stderr, stderr_encoding, stderr_fallback = ShortcutExecutor._decode_bytes(
                            b"".join(stderr_parts), getattr(shortcut, "command_encoding", "auto")
                        )
                        update_stdout, stdout_truncated = ShortcutExecutor._truncate_output(stdout or "", max_chars)
                        update_stderr, stderr_truncated = ShortcutExecutor._truncate_output(stderr or "", max_chars)
                        parts = []
                        if update_stdout:
                            parts.extend(["stdout:", update_stdout])
                        if update_stderr:
                            parts.extend(["stderr:", update_stderr])
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
                        try:
                            process.kill()
                        except Exception:
                            pass
                        break
                    if time.monotonic() >= deadline:
                        timed_out = True
                        try:
                            process.kill()
                        except Exception:
                            pass
                        break
                    time.sleep(0.03)

                try:
                    process.wait(timeout=2.0)
                except Exception:
                    pass
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
                returncode = process.returncode
                if cancelled:
                    stdout, stdout_encoding, stdout_fallback = ShortcutExecutor._decode_bytes(
                        stdout_bytes or b"", getattr(shortcut, "command_encoding", "auto")
                    )
                    stderr, stderr_encoding, stderr_fallback = ShortcutExecutor._decode_bytes(
                        stderr_bytes or b"", getattr(shortcut, "command_encoding", "auto")
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
                parts = []
                if stdout:
                    parts.extend(["stdout:", stdout])
                if stderr:
                    parts.extend(["stderr:", stderr])
                if not parts:
                    parts.append("(无输出)")
                message = "\n".join(parts)
                if timed_out:
                    message = f"命令执行超时 ({timeout_value:g}s)，已终止。\n\n{message}"
                success = (returncode == 0) and not timed_out
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
                    stdout_bytes, stderr_bytes = process.communicate(timeout=timeout_value)
                else:
                    deadline = time.monotonic() + timeout_value
                    while process.poll() is None:
                        if cancel_event.is_set():
                            try:
                                process.kill()
                            except Exception:
                                pass
                            stdout_bytes, stderr_bytes = process.communicate()
                            stdout, stdout_encoding, stdout_fallback = ShortcutExecutor._decode_bytes(
                                stdout_bytes or b"", getattr(shortcut, "command_encoding", "auto")
                            )
                            stderr, stderr_encoding, stderr_fallback = ShortcutExecutor._decode_bytes(
                                stderr_bytes or b"", getattr(shortcut, "command_encoding", "auto")
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
                                },
                                error="已取消",
                            )
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(popen_args, timeout_value)
                        time.sleep(min(0.05, remaining))
                    stdout_bytes, stderr_bytes = process.communicate()
                returncode = process.returncode
                timed_out = False
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except Exception:
                    pass
                stdout_bytes, stderr_bytes = process.communicate()
                returncode = process.returncode
                timed_out = True

            stdout, stdout_encoding, stdout_fallback = ShortcutExecutor._decode_bytes(
                stdout_bytes or b"", getattr(shortcut, "command_encoding", "auto")
            )
            stderr, stderr_encoding, stderr_fallback = ShortcutExecutor._decode_bytes(
                stderr_bytes or b"", getattr(shortcut, "command_encoding", "auto")
            )
            stdout, stdout_truncated = ShortcutExecutor._truncate_output(stdout or "", max_chars)
            stderr, stderr_truncated = ShortcutExecutor._truncate_output(stderr or "", max_chars)
            parts = []
            if stdout:
                parts.extend(["stdout:", stdout])
            if stderr:
                parts.extend(["stderr:", stderr])
            if not parts:
                parts.append("(无输出)")
            message = "\n".join(parts)
            if timed_out:
                message = f"命令执行超时 ({timeout_value:g}s)，已终止。\n\n{message}"
            success = (returncode == 0) and not timed_out
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
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    @staticmethod
    def test_command(shortcut: ShortcutItem, timeout: float = 10.0) -> dict:
        """Run a command shortcut synchronously for the editor test button."""
        old_timeout = getattr(shortcut, "command_timeout_seconds", 10.0)
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
                        from ui.launcher_popup.file_selection import get_selected_files_for_process

                        selected_files = get_selected_files_for_process() or []
                    except Exception:
                        pass

                    clipboard_text = ""
                    try:
                        from qt_compat import QApplication

                        cb = QApplication.clipboard()
                        clipboard_text = cb.text() or ""
                    except Exception:
                        pass

                    ctx = CommandContext(
                        raw_input=command,
                        args_text=args_text,
                        clipboard_text=clipboard_text,
                        selected_files=selected_files,
                        update_callback=lambda r: set_pending_command_result(r),
                    )
                    result = cmd_def.handler(ctx)
                    set_pending_command_result(result)
                    return result.success
        except Exception:
            pass

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
                        if result is False:
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

        if cmd_name == "open_control_panel":
            if ShortcutExecutor._shell_execute_open("control.exe"):
                return True
            try:
                ShortcutExecutor._popen_silent(["control.exe"], env=ShortcutExecutor._sanitized_child_env())
                return True
            except Exception as e:
                logger.error(f"打开控制面板失败: {e}")
                return False

        if cmd_name == "open_this_pc":
            if ShortcutExecutor._shell_execute_open("explorer.exe", "shell:MyComputerFolder"):
                return True
            try:
                ShortcutExecutor._popen_silent(
                    ["explorer.exe", "shell:MyComputerFolder"], env=ShortcutExecutor._sanitized_child_env()
                )
                return True
            except Exception as e:
                logger.error(f"打开此电脑失败: {e}")
                return False

        if cmd_name == "open_recycle_bin":
            if ShortcutExecutor._shell_execute_open("explorer.exe", "shell:RecycleBinFolder"):
                return True
            try:
                ShortcutExecutor._popen_silent(
                    ["explorer.exe", "shell:RecycleBinFolder"], env=ShortcutExecutor._sanitized_child_env()
                )
                return True
            except Exception as e:
                logger.error(f"打开回收站失败: {e}")
                return False

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
                    logger.info(f"延迟IPC命令发送成功: {command}")
                else:
                    logger.warning(f"延迟IPC命令发送失败: {command}")
            except Exception as e:
                logger.error(f"延迟IPC命令异常: {e}")
                import traceback

                logger.error(traceback.format_exc())

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
                            logger.info(f"IPC命令发送成功: {command} (尝试 {attempt} 次)")
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
                except Exception:
                    pass

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
            except Exception:
                pass

            logger.warning(f"IPC命令发送失败（超时）: {command}, 共尝试 {attempt} 次, 最后错误: {last_error}")
            return False
        except Exception as e:
            logger.error(f"发送IPC命令失败: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return False
