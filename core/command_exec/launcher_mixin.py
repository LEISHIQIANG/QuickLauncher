"""Launcher detection mixin — finds cmd, python, powershell, git-bash on Windows."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading

from runtime_paths import app_root, is_packaged_runtime

from .runtime import normalize_command_type

logger = logging.getLogger(__name__)


class _ShortcutExecutorProxy:
    """Delegates all attribute access to core.shortcut_command_exec.ShortcutExecutor,
    so tests can monkeypatch the canonical location and the mixin sees it."""

    def __getattr__(self, name):
        from .. import shortcut_command_exec

        return getattr(shortcut_command_exec.ShortcutExecutor, name)


ShortcutExecutor = _ShortcutExecutorProxy()

WINDOWS_DIRECT_COMMAND_LINE_MAX_CHARS = 30000


class CommandLauncherMixin:
    _CMD_CACHE_DIR = None
    _CMD_CACHE_DIR_LOCK = threading.Lock()

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
                return ShortcutExecutor._resolve_long_path(os.path.abspath(candidate))  # type: ignore[no-any-return]
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
    def _python_launcher() -> str | None:
        if not ShortcutExecutor._is_packaged_runtime() and sys.executable:
            resolved = ShortcutExecutor._resolve_long_path(sys.executable)
            if os.path.isfile(resolved):
                return resolved  # type: ignore[no-any-return]
        return ShortcutExecutor._find_system_python_launcher()  # type: ignore[no-any-return]

    @staticmethod
    def _is_packaged_runtime() -> bool:
        return is_packaged_runtime()

    @staticmethod
    def _app_install_dir() -> str:
        return str(app_root())

    @staticmethod
    def _probe_python_launcher(candidate: str) -> bool:
        try:
            completed = subprocess.run(
                [candidate, "-c", "import sys; print(sys.version_info[0])"],
                capture_output=True,
                text=True,
                timeout=2.0,
                shell=False,
                **ShortcutExecutor._capture_popen_platform_kwargs(),
            )
            return completed.returncode == 0
        except Exception:
            logger.debug("_probe_python_launcher check failed", exc_info=True)
            return False

    @staticmethod
    def _resolve_long_path(path: str) -> str:
        if os.name != "nt" or not path:
            return path
        try:
            buf = ctypes.create_unicode_buffer(4096)
            result = ctypes.windll.kernel32.GetLongPathNameW(path, buf, 4096)
            if 0 < result < 4096:
                return buf.value
        except Exception as exc:
            logger.debug("获取长路径名失败: %s", exc, exc_info=True)
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
            return long_path  # type: ignore[no-any-return]
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
                return ShortcutExecutor._resolve_long_path(os.path.abspath(candidate))  # type: ignore[no-any-return]
        return None

    @staticmethod
    def _powershell_launcher_error() -> str:
        return "PowerShell is not available. Install Windows PowerShell or add powershell.exe to PATH."

    @staticmethod
    def _encode_powershell_command(command: str) -> str:
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
            logger.debug("_direct_command_line_length failed", exc_info=True)
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
        candidates = []
        candidates.append(shutil.which("bash"))
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
                return ShortcutExecutor._resolve_long_path(os.path.abspath(candidate))  # type: ignore[no-any-return]
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
        hash_ = hashlib.md5(command.encode("utf-8")).hexdigest()
        cache_dir = CommandLauncherMixin._get_cmd_cache_dir()
        path = os.path.join(cache_dir, f"{hash_}.sh")
        if not os.path.exists(path):
            from .standalone import _write_atomic

            _write_atomic(path, "#!/usr/bin/env bash\n" + command + "\n")
        return path

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
        cache_dir = cls._get_cmd_cache_dir()
        for fname in os.listdir(cache_dir):
            fpath = os.path.join(cache_dir, fname)
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
            except Exception as exc:
                logger.debug("删除缓存文件失败 %s: %s", fpath, exc, exc_info=True)

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
