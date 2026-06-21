"""Platform-specific command executors for W3.2 capture-routing.

The legacy ``CommandExecutionMixin._execute_*_command`` family
(``_execute_powershell_command``, ``_execute_bash_command``,
``_execute_python_command``, ``_execute_cmd_command``) lives in
:mod:`core.shortcut_command_exec` and has the typical mixin host
back-reference pattern: every method reads ``ShortcutExecutor._xxx_launcher()``,
``_runtime_env``, ``_powershell_argv``, etc.  The class grew to 2,213
lines precisely because those mixin-host references forced every new
executor to live next to its helpers.

W3.2 splits the executor side out into module-level functions that
accept the helpers as explicit callables.  This breaks the cycle
between the executor body and the host class while keeping the
historical behaviour intact: the :class:`CommandExecutionMixin`
methods that previously ran the work now just delegate to these
functions and pass the relevant helpers in.

The split is incremental — the original methods on
``CommandExecutionMixin`` remain in place so existing callers and
tests keep working.  New code can import the functions directly.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from infrastructure.process import runtime as process_runtime

if TYPE_CHECKING:
    from core.data_models import ShortcutItem

logger = logging.getLogger(__name__)


LauncherProvider = Callable[[], str | None]
EnvProvider = Callable[["ShortcutItem"], dict[str, str]]
PopenSilent = Callable[..., Any]
PopenLauncher = Callable[[str, list[str], str | None, dict[str, str], int, str, bool], tuple[bool, str]]
DirectTooLong = Callable[[list[str]], bool]
DirectLengthError = Callable[[str, list[str]], str]


class PowershellArgv(Protocol):
    def __call__(self, command: str, *, no_exit: bool = False) -> list[str]: ...


class BashArgv(Protocol):
    def __call__(self, command: str, *, login: bool = False) -> list[str]: ...


BashLauncherError = Callable[[], str]
PythonLauncherError = Callable[[], str]
PowershellLauncherError = Callable[[], str]
WriteTempPython = Callable[[str], str]
CleanupFileLater = Callable[..., None]
RemoveTempPython = Callable[[str | None], None]
GetSilentStartupinfo = Callable[[], Any]
GetSilentCreationflags = Callable[..., int]
RestoreFocus = Callable[[Any], None]


def _safe_get_python_exe(
    python_launcher: LauncherProvider,
    python_launcher_error: PythonLauncherError,
) -> tuple[str | None, str | None]:
    python_exe = python_launcher()
    if not python_exe:
        return None, python_launcher_error()
    return python_exe, None


def execute_powershell_command(
    shortcut: ShortcutItem,
    command: str,
    *,
    powershell_argv: PowershellArgv,
    direct_too_long: DirectTooLong,
    direct_length_error: DirectLengthError,
    runtime_env: EnvProvider,
    launch_with_privilege: Callable[..., tuple[bool, str]],
    popen_silent: PopenSilent,
    powershell_launcher_error: PowershellLauncherError,
) -> tuple[bool, str]:
    """W3.2 platform executor — PowerShell visible / silent / admin.

    Pure function form of ``CommandExecutionMixin._execute_powershell_command``.
    All host-class dependencies are passed in as callables so the
    executor body has no hidden coupling to ``ShortcutExecutor``.
    """
    try:
        show_window = getattr(shortcut, "show_window", False)
        run_as_admin = getattr(shortcut, "run_as_admin", False)
        cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
        argv = powershell_argv(command, no_exit=show_window)
        if direct_too_long(argv):
            return False, direct_length_error("powershell", argv)
        show_cmd = 1 if show_window else 0
        if os.name == "nt" and (show_window or run_as_admin):
            launched, launch_error = launch_with_privilege(
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
            process_runtime.popen(argv, cwd=cwd, env=runtime_env(shortcut), shell=False)
        else:
            popen_silent(argv, cwd=cwd, env=runtime_env(shortcut), shell=False)
        return True, ""
    except FileNotFoundError:
        return False, powershell_launcher_error()
    except Exception as e:
        return False, f"PowerShell command launch failed: {e}"


def execute_bash_command(
    shortcut: ShortcutItem,
    command: str,
    *,
    runtime_env: EnvProvider,
    visible_executor: Callable[[str, str | None, dict[str, str], bool], tuple[bool, str]],
    silent_executor: Callable[[str, str | None, dict[str, str]], tuple[bool, str]],
) -> tuple[bool, str]:
    """W3.2 — dispatch bash to visible or silent executor based on ``show_window``.

    The body itself is small; the helpers used here remain in
    ``ShortcutExecutor`` for now.  Moving the bash-specific launchers
    and the visible/silent helpers is a separate P2 follow-up; this
    function only documents the dispatch boundary.
    """
    show_window = getattr(shortcut, "show_window", False)
    run_as_admin = getattr(shortcut, "run_as_admin", False)
    cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
    bash_env = runtime_env(shortcut)
    bash_env["LANG"] = "en_US.UTF-8"
    if show_window:
        return visible_executor(command, cwd, bash_env, run_as_admin)
    return silent_executor(command, cwd, bash_env)


def execute_visible_bash_command(
    command: str,
    cwd: str | None,
    bash_env: dict[str, str],
    run_as_admin: bool,
    *,
    bash_launcher: LauncherProvider,
    bash_argv: BashArgv,
    direct_too_long: DirectTooLong,
    direct_length_error: DirectLengthError,
    launch_with_privilege: Callable[..., tuple[bool, str]],
    bash_launcher_error: BashLauncherError,
) -> tuple[bool, str]:
    """W3.2 — visible bash launch (windowed) with optional admin elevation."""
    try:
        bash_exe = bash_launcher()
        if not bash_exe:
            return False, bash_launcher_error()
        logger.debug("Bash show-window: launcher=%s, route=shell-execute", bash_exe)
        argv = bash_argv(command, login=True)
        if direct_too_long(argv):
            return False, direct_length_error("bash", argv)
        if os.name == "nt":
            launched, launch_error = launch_with_privilege(
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
        process_runtime.popen(argv, cwd=cwd, env=bash_env, shell=False)
        return True, ""
    except FileNotFoundError:
        return False, bash_launcher_error()
    except Exception as e:
        return False, f"Bash command launch failed: {e}"


def execute_silent_bash_command(
    command: str,
    cwd: str | None,
    bash_env: dict[str, str],
    *,
    bash_launcher: LauncherProvider,
    bash_argv: BashArgv,
    direct_too_long: DirectTooLong,
    direct_length_error: DirectLengthError,
    popen_silent: PopenSilent,
    bash_launcher_error: BashLauncherError,
) -> tuple[bool, str]:
    """W3.2 — silent bash launch (no window) through the debounced popen helper."""
    try:
        bash_exe = bash_launcher()
        if not bash_exe:
            return False, bash_launcher_error()
        logger.debug("Bash silent: launcher=%s, route=popen-silent", bash_exe)
        argv = bash_argv(command, login=False)
        if direct_too_long(argv):
            return False, direct_length_error("bash", argv)
        popen_silent(argv, cwd=cwd, env=bash_env, shell=False)
        return True, ""
    except FileNotFoundError:
        return False, bash_launcher_error()
    except Exception as e:
        return False, f"Bash command launch failed: {e}"


def execute_python_command(
    shortcut: ShortcutItem,
    command: str,
    *,
    python_launcher: LauncherProvider,
    python_launcher_error: PythonLauncherError,
    write_temp_python_script: WriteTempPython,
    runtime_env: EnvProvider,
    launch_with_privilege: Callable[..., tuple[bool, str]],
    cleanup_file_later: CleanupFileLater,
    remove_temp_python_script: RemoveTempPython,
) -> tuple[bool, str]:
    """W3.2 — visible Python launch (windowed) with optional admin elevation.

    Python stdin-mode execution is left to the legacy mixin path; the
    stdin path is short and tightly coupled to background-thread
    submission, so it is not yet split out.
    """
    tmp_path = None
    try:
        python_exe, error = _safe_get_python_exe(python_launcher, python_launcher_error)
        if not python_exe:
            return False, error or "Python 不可用"
        tmp_path = write_temp_python_script(command)
        python_exe = python_launcher()
        if not python_exe:
            return False, python_launcher_error()
        run_as_admin = getattr(shortcut, "run_as_admin", False)
        cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None
        if os.name == "nt":
            launched, launch_error = launch_with_privilege(
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
        process = process_runtime.popen(
            [python_exe, tmp_path],
            cwd=cwd,
            env=runtime_env(shortcut),
            shell=False,
        )
        cleanup_file_later(process, tmp_path)
        return True, ""
    except FileNotFoundError:
        remove_temp_python_script(tmp_path)
        return False, python_launcher_error()
    except Exception as e:
        remove_temp_python_script(tmp_path)
        return False, f"Python 代码执行失败: {e}"


def execute_cmd_command(
    shortcut: ShortcutItem,
    command: str,
    *,
    cmd_has_newline: Callable[[str], bool],
    runtime_env: EnvProvider,
    launch_with_privilege: Callable[..., tuple[bool, str]],
    restore_focus_after_process: RestoreFocus,
    launch_cmd_process: Callable[..., Any],
    execute_cmd_stdin_command: Callable[..., tuple[bool, str]],
) -> tuple[bool, str]:
    """W3.2 — CMD launch with stdin fallback for multi-line scripts.

    The legacy path also dispatches to ``_execute_cmd_stdin_command``
    for multi-line scripts without ``show_window``/``run_as_admin``;
    the function form keeps the same short-circuit semantics.  All
    host-class helpers are passed in as callables so the function is
    independent of the ``ShortcutExecutor`` mixin host.
    """
    process = None
    run_as_admin = getattr(shortcut, "run_as_admin", False)
    show_window = getattr(shortcut, "show_window", False)
    if cmd_has_newline(command) and not show_window and not run_as_admin:
        return execute_cmd_stdin_command(shortcut, command)
    try:
        launch_result = launch_cmd_process(shortcut, command, run_as_admin, show_window)
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
        restore_focus_after_process(process)
    return (process is not None), error_msg


__all__ = [
    "execute_powershell_command",
    "execute_bash_command",
    "execute_visible_bash_command",
    "execute_silent_bash_command",
    "execute_python_command",
    "execute_cmd_command",
]
