"""Auto-start manager.

Strategy:
1. Only the helper path is allowed to elevate.
2. The helper only creates or deletes the Task Scheduler task.
3. The main QuickLauncher process should keep running unelevated.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import winreg
from ctypes import wintypes

logger = logging.getLogger(__name__)

APP_NAME = "QuickLauncher"
TASK_NAME = "QuickLauncherAutoStart"
LEGACY_TASK_NAMES = ("QuickLauncher_AutoStart",)
_REG_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

HELPER_ARG = "--autostart-helper"
AUTOSTART_LAUNCH_ARG = "--autostart-launch"
HELPER_TARGET_ARG = "--target-exe"
HELPER_TARGET_ARGS_ARG = "--target-args"
HELPER_TARGET_CWD_ARG = "--target-cwd"
HELPER_ACTION_ENABLE = "enable"
HELPER_ACTION_DISABLE = "disable"

HELPER_EXIT_SUCCESS = 0
HELPER_EXIT_FAILED = 1
HELPER_EXIT_CANCELLED = 2
HELPER_EXIT_BAD_ARGS = 3

AUTOSTART_FALLBACK_TIMEOUT_SECONDS = 20.0
AUTOSTART_FALLBACK_POLL_SECONDS = 0.25
AUTOSTART_ADMIN_TRIGGER_DELAY = "PT2S"
AUTOSTART_STANDARD_TRIGGER_DELAY = ""

SEE_MASK_NOCLOSEPROCESS = 0x00000040
SW_HIDE = 0
INFINITE = 0xFFFFFFFF
WAIT_TIMEOUT = 0x00000102
AUTOSTART_HELPER_TIMEOUT_MS = 60000
CREATE_UNICODE_ENVIRONMENT = 0x00000400

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_ASSIGN_PRIMARY = 0x0001
TOKEN_DUPLICATE = 0x0002
TOKEN_ADJUST_DEFAULT = 0x0080
TOKEN_ADJUST_SESSIONID = 0x0100
TOKEN_ELEVATION_CLASS = 20
MAXIMUM_ALLOWED = 0x02000000
SecurityImpersonation = 2
TokenPrimary = 1

if os.name == "nt":
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32
    advapi32 = ctypes.windll.advapi32
    userenv = ctypes.windll.userenv
else:
    user32 = None
    shell32 = None
    kernel32 = None
    advapi32 = None
    userenv = None


class SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HANDLE),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class TOKEN_ELEVATION(ctypes.Structure):
    _fields_ = [("TokenIsElevated", wintypes.DWORD)]


if os.name == "nt":
    user32.GetShellWindow.argtypes = []
    user32.GetShellWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.DuplicateTokenEx.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.DuplicateTokenEx.restype = wintypes.BOOL
    # Use raw pointer argtypes for the output structs because this shared DLL
    # function is also configured by shortcut launch helpers.
    advapi32.CreateProcessWithTokenW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    advapi32.CreateProcessWithTokenW.restype = wintypes.BOOL
    userenv.CreateEnvironmentBlock.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        wintypes.BOOL,
    ]
    userenv.CreateEnvironmentBlock.restype = wintypes.BOOL
    userenv.DestroyEnvironmentBlock.argtypes = [ctypes.c_void_p]
    userenv.DestroyEnvironmentBlock.restype = wintypes.BOOL


def _is_frozen() -> bool:
    """Return whether the current runtime is a packaged executable."""
    if getattr(sys, "frozen", False):
        return True
    if "__compiled__" in globals():
        return True

    exe_name = os.path.basename(sys.executable).lower()
    return exe_name not in ("python.exe", "pythonw.exe", "python", "pythonw") and exe_name.endswith(".exe")


def _get_project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_exe_path() -> str:
    """Resolve the app executable path, including Nuitka standalone cases."""
    exe = sys.executable

    if "python" in os.path.basename(exe).lower():
        if sys.argv and sys.argv[0].lower().endswith(".exe"):
            candidate = os.path.abspath(sys.argv[0])
            if os.path.isfile(candidate):
                return candidate

        app_exe = os.path.join(os.path.dirname(os.path.abspath(exe)), f"{APP_NAME}.exe")
        if os.path.isfile(app_exe):
            return app_exe

    if not os.path.isabs(exe):
        exe = os.path.abspath(exe)
    return exe


def _normalize_launch_spec(
    exe_path: str | None = None,
    arguments: str = "",
    working_dir: str = "",
) -> tuple[str, str, str]:
    path = exe_path or _get_exe_path()
    args = arguments or ""
    cwd = working_dir or (os.path.dirname(path) if path else "")
    return path, args, cwd


def _normalize_abs_path(path: str) -> str:
    if not path:
        return ""
    return os.path.normcase(os.path.abspath(path))


def _get_current_user_identity() -> str:
    if os.name == "nt":
        try:
            import win32api

            sam_name = (win32api.GetUserNameEx(2) or "").strip()  # NameSamCompatible
            if sam_name:
                return sam_name
        except Exception as e:
            logger.debug("win32api.GetUserNameEx 调用失败，回退到环境变量: %s", e)

    username = (os.environ.get("USERNAME") or "").strip()
    domain = (os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME") or "").strip()
    if domain and username:
        return f"{domain}\\{username}"
    return username


def _get_current_user_sid() -> str:
    if os.name != "nt":
        return ""

    try:
        import win32api
        import win32security

        account_name = _get_current_user_identity() or win32api.GetUserName()
        if not account_name:
            return ""

        sid_obj, _, _ = win32security.LookupAccountName(None, account_name)
        return win32security.ConvertSidToStringSid(sid_obj) or ""
    except Exception as e:
        logger.debug("获取用户 SID 失败: %s", e)
        return ""


def _get_current_user_identity_variants() -> set[str]:
    variants: set[str] = set()

    full_name = (_get_current_user_identity() or "").strip().lower()
    if full_name:
        variants.add(full_name)
        if "\\" in full_name:
            variants.add(full_name.split("\\", 1)[1])

    username = (os.environ.get("USERNAME") or "").strip().lower()
    if username:
        variants.add(username)

    sid = (_get_current_user_sid() or "").strip().lower()
    if sid:
        variants.add(sid)

    variants.discard("")
    return variants


def _is_current_account_admin() -> bool:
    """Return whether the current logon account has an admin split token."""
    if os.name != "nt":
        return False

    try:
        from core.windows_uipi import get_process_elevation_status

        status = get_process_elevation_status()
        return bool(
            status.get("elevated")
            or status.get("is_user_an_admin")
            or status.get("elevation_type") in ("Limited", "Full")
        )
    except Exception:
        try:
            return bool(shell32.IsUserAnAdmin())
        except Exception as e:
            logger.debug("管理员权限检测失败 (get_process_elevation_status + shell32 均失败): %s", e)
            return False


def _is_current_process_elevated() -> bool:
    if os.name != "nt":
        return False
    try:
        from core.windows_uipi import get_process_elevation_status

        status = get_process_elevation_status()
        return bool(status.get("elevated"))
    except Exception:
        try:
            return bool(shell32.IsUserAnAdmin())
        except Exception as e:
            logger.debug("进程提权检测失败: %s", e)
            return False


def _get_task_trigger_delay(task_mode: str) -> str:
    """Return the logon trigger delay for the selected auto-start path."""
    if task_mode == "admin_launcher":
        return AUTOSTART_ADMIN_TRIGGER_DELAY
    return AUTOSTART_STANDARD_TRIGGER_DELAY


def _build_task_definition(
    scheduler,
    path: str,
    args: str,
    cwd: str,
    user_id: str,
    *,
    set_trigger_user: bool,
    set_principal_user: bool,
):
    task_def = scheduler.NewTask(0)
    task_def.RegistrationInfo.Description = "QuickLauncher 开机自启（helper）"
    task_def.Settings.Enabled = True
    task_def.Settings.StartWhenAvailable = True
    task_def.Settings.DisallowStartIfOnBatteries = False
    task_def.Settings.StopIfGoingOnBatteries = False
    task_def.Settings.ExecutionTimeLimit = "PT0S"
    task_def.Settings.AllowHardTerminate = False
    task_def.Settings.Priority = 4

    task_path, task_args, task_cwd, task_mode = _build_task_action_launch(path, args, cwd)
    trigger_delay = _get_task_trigger_delay(task_mode)

    trigger = task_def.Triggers.Create(9)  # TASK_TRIGGER_LOGON
    trigger.Enabled = True
    trigger.Delay = trigger_delay
    if set_trigger_user and user_id:
        try:
            trigger.UserId = user_id
        except Exception as e:
            logger.debug("设置任务触发器 UserId 失败: %s", e)

    action = task_def.Actions.Create(0)  # TASK_ACTION_EXEC
    action.Path = task_path
    if task_args:
        action.Arguments = task_args
    if task_cwd:
        action.WorkingDirectory = task_cwd

    task_def.Principal.LogonType = 3  # TASK_LOGON_INTERACTIVE_TOKEN
    task_def.Principal.RunLevel = 0  # TASK_RUNLEVEL_LUA
    if set_principal_user and user_id:
        try:
            task_def.Principal.UserId = user_id
        except Exception as e:
            logger.debug("设置任务主体 UserId 失败: %s", e)
    try:
        # Best-effort scheduler hint; admin accounts are actually lowered by the launcher path.
        task_def.Principal.ProcessTokenSidType = 2
    except Exception as e:
        logger.debug("设置 ProcessTokenSidType 失败 (可忽略): %s", e)

    return task_def


def _get_app_launch_spec() -> tuple[str, str, str]:
    """Return the current app launch triple: (path, args, cwd)."""
    if _is_frozen():
        exe_path = _get_exe_path()
        return exe_path, "", os.path.dirname(exe_path)

    main_script = (
        os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else os.path.join(_get_project_root(), "main.py")
    )
    python_exe = sys.executable
    arguments = subprocess.list2cmdline([main_script])
    return python_exe, arguments, os.path.dirname(main_script)


def _build_helper_launch(
    action: str,
    exe_path: str | None = None,
    arguments: str = "",
    working_dir: str = "",
) -> tuple[str, str, str]:
    """Build the helper process launch command."""
    target_path, target_args, target_cwd = _normalize_launch_spec(exe_path, arguments, working_dir)

    if _is_frozen():
        helper_file = _get_exe_path()
        helper_cwd = os.path.dirname(helper_file)
        argv = [HELPER_ARG, action]
    else:
        helper_cwd = _get_project_root()
        helper_file = sys.executable
        argv = [os.path.join(helper_cwd, "main.py"), HELPER_ARG, action]

    if target_path:
        argv.extend([HELPER_TARGET_ARG, target_path])
    if target_args:
        argv.extend([HELPER_TARGET_ARGS_ARG, target_args])
    if target_cwd:
        argv.extend([HELPER_TARGET_CWD_ARG, target_cwd])

    return helper_file, subprocess.list2cmdline(argv), helper_cwd


def _build_autostart_task_launch(
    exe_path: str | None = None,
    arguments: str = "",
    working_dir: str = "",
) -> tuple[str, str, str]:
    """Build the scheduled task action that relaunches the app via Explorer."""
    target_path, target_args, target_cwd = _normalize_launch_spec(exe_path, arguments, working_dir)

    if _is_frozen():
        launcher_file = _get_exe_path()
        launcher_cwd = os.path.dirname(launcher_file)
        argv = [AUTOSTART_LAUNCH_ARG]
    else:
        launcher_cwd = _get_project_root()
        launcher_file = sys.executable
        argv = [os.path.join(launcher_cwd, "main.py"), AUTOSTART_LAUNCH_ARG]

    if target_path:
        argv.extend([HELPER_TARGET_ARG, target_path])
    if target_args:
        argv.extend([HELPER_TARGET_ARGS_ARG, target_args])
    if target_cwd:
        argv.extend([HELPER_TARGET_CWD_ARG, target_cwd])

    return launcher_file, subprocess.list2cmdline(argv), launcher_cwd


def _build_task_action_launch(
    exe_path: str | None = None,
    arguments: str = "",
    working_dir: str = "",
) -> tuple[str, str, str, str]:
    """Return scheduled-task action and mode for the current account type."""
    path, args, cwd = _normalize_launch_spec(exe_path, arguments, working_dir)
    if _is_current_account_admin():
        task_path, task_args, task_cwd = _build_autostart_task_launch(path, args, cwd)
        return task_path, task_args, task_cwd, "admin_launcher"
    return path, args, cwd, "standard_direct"


def _is_allowed_helper_target(
    exe_path: str | None = None,
    arguments: str = "",
    working_dir: str = "",
) -> bool:
    """Only allow the helper to manage this app's own auto-start target."""
    path, args, _ = _normalize_launch_spec(exe_path, arguments, working_dir)
    if not os.path.isfile(path):
        return False

    if _is_frozen():
        return _normalize_abs_path(path) == _normalize_abs_path(_get_exe_path())

    main_script = os.path.abspath(
        sys.argv[0] if sys.argv and sys.argv[0] else os.path.join(_get_project_root(), "main.py")
    )
    expected_args = subprocess.list2cmdline([main_script])
    return _normalize_abs_path(path) == _normalize_abs_path(sys.executable) and (args or "").strip() == expected_args


def _validate_task_launch_spec(
    task,
    exe_path: str | None = None,
    arguments: str = "",
    working_dir: str = "",
) -> tuple[bool, str]:
    """Validate an existing scheduled task and return a diagnostic reason."""
    try:
        path, args, cwd = _normalize_launch_spec(exe_path, arguments, working_dir)
        task_path, task_args, task_cwd, task_mode = _build_task_action_launch(path, args, cwd)
        expected_delay = _get_task_trigger_delay(task_mode)
        expected_users = _get_current_user_identity_variants()

        enabled = bool(getattr(task, "Enabled", False))
        if not enabled:
            return False, "task_disabled"

        definition = task.Definition
        principal = definition.Principal
        actual_runlevel = int(getattr(principal, "RunLevel", 0))
        if actual_runlevel != 0:
            return False, f"runlevel_mismatch: actual={actual_runlevel} expected=0"

        actual_user = (getattr(principal, "UserId", "") or "").strip().lower()
        if expected_users and actual_user and actual_user not in expected_users:
            return False, f"user_mismatch: actual={actual_user} expected={','.join(sorted(expected_users))}"

        actions = definition.Actions
        if int(getattr(actions, "Count", 0)) < 1:
            return False, "actions_missing"

        triggers = definition.Triggers
        if int(getattr(triggers, "Count", 0)) < 1:
            return False, "triggers_missing"

        trigger = triggers.Item(1)
        actual_delay = (getattr(trigger, "Delay", "") or "").strip()
        if actual_delay != expected_delay:
            return (
                False,
                "trigger_delay_mismatch: "
                f"mode={task_mode} actual={actual_delay or 'none'} expected={expected_delay or 'none'}",
            )

        action = actions.Item(1)
        actual_path = _normalize_abs_path(getattr(action, "Path", "") or "")
        actual_args = (getattr(action, "Arguments", "") or "").strip()
        actual_cwd = _normalize_abs_path(getattr(action, "WorkingDirectory", "") or "")

        expected_path = _normalize_abs_path(task_path)
        expected_args = (task_args or "").strip()
        expected_cwd = _normalize_abs_path(task_cwd)
        if actual_path != expected_path:
            return False, f"path_mismatch: actual={actual_path} expected={expected_path}"
        if actual_args != expected_args:
            return False, f"args_mismatch: actual={actual_args} expected={expected_args}"
        if actual_cwd != expected_cwd:
            return False, f"cwd_mismatch: actual={actual_cwd} expected={expected_cwd}"

        return True, f"ok: mode={task_mode} trigger_delay={expected_delay or 'none'}"
    except Exception as exc:
        return False, f"task_definition_read_failed: {exc}"


def _task_matches_launch_spec(task, exe_path: str | None = None, arguments: str = "", working_dir: str = "") -> bool:
    """Validate that an existing scheduled task still points to the current app."""
    valid, reason = _validate_task_launch_spec(task, exe_path, arguments, working_dir)
    if not valid:
        logger.debug("自启动任务定义不匹配: %s", reason)
    return valid


def _run_elevated_helper(
    action: str,
    exe_path: str | None = None,
    arguments: str = "",
    working_dir: str = "",
) -> tuple[bool, str]:
    """Run the helper elevated and wait for completion."""
    if action == HELPER_ACTION_ENABLE and not _is_allowed_helper_target(exe_path, arguments, working_dir):
        logger.error("自启动 helper 拒绝无效目标，已跳过提权")
        return False, "failed"

    if os.name != "nt":
        if action == HELPER_ACTION_ENABLE:
            return _enable_auto_start_direct(exe_path, arguments, working_dir)
        if action == HELPER_ACTION_DISABLE:
            return _disable_auto_start_direct()
        return False, "failed"

    helper_file, helper_params, helper_cwd = _build_helper_launch(action, exe_path, arguments, working_dir)
    if not os.path.isfile(helper_file):
        logger.error("自启动 helper 不存在: %s", helper_file)
        return False, "failed"

    sei = SHELLEXECUTEINFO()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFO)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS
    sei.hwnd = None
    sei.lpVerb = "runas"
    sei.lpFile = helper_file
    sei.lpParameters = helper_params
    sei.lpDirectory = helper_cwd
    sei.nShow = SW_HIDE

    try:
        if not shell32.ShellExecuteExW(ctypes.pointer(sei)):
            error_code = kernel32.GetLastError()
            if error_code == 1223:
                logger.info("用户取消了自启动 helper 的 UAC 授权")
                return False, "cancelled"
            logger.error("启动自启动 helper 失败, error=%s", error_code)
            return False, "failed"

        wait_result = kernel32.WaitForSingleObject(sei.hProcess, AUTOSTART_HELPER_TIMEOUT_MS)
        if wait_result == WAIT_TIMEOUT:
            logger.error("自启动 helper 执行超时，已终止 helper 进程")
            try:
                kernel32.TerminateProcess(sei.hProcess, HELPER_EXIT_FAILED)
            except Exception as e:
                logger.warning("TerminateProcess 失败: %s", e)
            return False, "failed"

        exit_code = wintypes.DWORD(HELPER_EXIT_FAILED)
        kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(exit_code))

        if exit_code.value == HELPER_EXIT_SUCCESS:
            return True, "task_scheduler_helper"
        if exit_code.value == HELPER_EXIT_CANCELLED:
            return False, "cancelled"
        if exit_code.value == HELPER_EXIT_BAD_ARGS:
            logger.error("自启动 helper 参数错误")
            return False, "failed"

        logger.error("自启动 helper 执行失败, exit_code=%s", exit_code.value)
        return False, "failed"
    finally:
        if sei.hProcess:
            try:
                kernel32.CloseHandle(sei.hProcess)
            except Exception as e:
                logger.debug("CloseHandle(hProcess) 失败: %s", e)


def run_autostart_helper(
    action: str,
    exe_path: str | None = None,
    arguments: str = "",
    working_dir: str = "",
) -> int:
    """Helper process entry point."""
    try:
        if action == HELPER_ACTION_ENABLE:
            success, _ = _enable_auto_start_direct(exe_path, arguments, working_dir)
            return HELPER_EXIT_SUCCESS if success else HELPER_EXIT_FAILED
        if action == HELPER_ACTION_DISABLE:
            success, _ = _disable_auto_start_direct()
            return HELPER_EXIT_SUCCESS if success else HELPER_EXIT_FAILED

        logger.error("未知的自启动 helper 动作: %s", action)
        return HELPER_EXIT_BAD_ARGS
    except Exception as exc:
        logger.error("自启动 helper 执行异常: %s", exc)
        logger.exception(exc)
        return HELPER_EXIT_FAILED


def _get_last_error_text() -> str:
    if os.name != "nt":
        return ""
    code = int(kernel32.GetLastError())
    if code <= 0:
        return "error=0"
    try:
        return f"error={code} ({ctypes.FormatError(code).strip()})"
    except Exception:
        return f"error={code}"


def _build_process_command_line(target: str, arguments: str = "") -> str:
    command = subprocess.list2cmdline([target])
    if arguments:
        command = f"{command} {arguments}"
    return command


def _launch_with_current_token(target: str, arguments: str = "", working_dir: str = "") -> bool:
    try:
        subprocess.Popen(_build_process_command_line(target, arguments), cwd=working_dir or None, shell=False)
        logger.info("自启动中转已用当前令牌启动: %s %s", target, arguments or "")
        return True
    except Exception as exc:
        logger.warning("自启动中转当前令牌启动失败: %s", exc)
        return False


def enable_impersonate_privilege() -> bool:
    """Explicitly enable SeImpersonatePrivilege for the current process."""
    if os.name != "nt":
        return False

    try:
        import ctypes
        from ctypes import wintypes

        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32

        TOKEN_ADJUST_PRIVILEGES = 0x0020
        TOKEN_QUERY = 0x0008
        SE_PRIVILEGE_ENABLED = 0x00000002

        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

        class LUID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

        class TOKEN_PRIVILEGES(ctypes.Structure):
            _fields_ = [("PrivilegeCount", wintypes.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]

        # Define function signatures locally to prevent collision
        OpenProcessToken = advapi32.OpenProcessToken
        OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        OpenProcessToken.restype = wintypes.BOOL

        LookupPrivilegeValueW = advapi32.LookupPrivilegeValueW
        LookupPrivilegeValueW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(LUID)]
        LookupPrivilegeValueW.restype = wintypes.BOOL

        AdjustTokenPrivileges = advapi32.AdjustTokenPrivileges
        AdjustTokenPrivileges.argtypes = [
            wintypes.HANDLE,
            wintypes.BOOL,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        AdjustTokenPrivileges.restype = wintypes.BOOL

        h_token = wintypes.HANDLE()
        if not OpenProcessToken(
            kernel32.GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, ctypes.byref(h_token)
        ):
            return False

        try:
            luid = LUID()
            if not LookupPrivilegeValueW(None, "SeImpersonatePrivilege", ctypes.byref(luid)):
                return False

            tp = TOKEN_PRIVILEGES()
            tp.PrivilegeCount = 1
            tp.Privileges[0].Luid = luid
            tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED

            if not AdjustTokenPrivileges(h_token, False, ctypes.byref(tp), 0, None, None):
                logger.warning(
                    "Failed to adjust token privileges for SeImpersonatePrivilege: %s", kernel32.GetLastError()
                )
                return False
            return True
        finally:
            kernel32.CloseHandle(h_token)
    except Exception as exc:
        logger.debug("Failed to enable Impersonate privilege: %s", exc)
        return False


def _create_process_with_token(
    token,
    target: str,
    arguments: str = "",
    working_dir: str = "",
    *,
    token_source: str,
) -> bool:
    # Enable SeImpersonatePrivilege before using CreateProcessWithTokenW
    enable_impersonate_privilege()

    env = ctypes.c_void_p()
    env_created = False
    startup = STARTUPINFO()
    startup.cb = ctypes.sizeof(STARTUPINFO)
    proc_info = PROCESS_INFORMATION()
    command_line = ctypes.create_unicode_buffer(_build_process_command_line(target, arguments))

    try:
        if userenv.CreateEnvironmentBlock(ctypes.byref(env), token, False):
            env_created = True
        else:
            logger.debug("自启动中转创建环境块失败，将使用默认环境: %s", _get_last_error_text())

        creation_flags = CREATE_UNICODE_ENVIRONMENT if env_created else 0
        if not advapi32.CreateProcessWithTokenW(
            token,
            0,
            target,
            command_line,
            creation_flags,
            env if env_created else None,
            working_dir or None,
            ctypes.byref(startup),
            ctypes.byref(proc_info),
        ):
            logger.debug("自启动中转 CreateProcessWithTokenW 失败: %s", _get_last_error_text())
            return False

        logger.info(
            "自启动中转已通过 %s 启动: pid=%s, target=%s %s",
            token_source,
            int(proc_info.dwProcessId),
            target,
            arguments or "",
        )
        return True
    finally:
        if proc_info.hThread:
            try:
                kernel32.CloseHandle(proc_info.hThread)
            except Exception as e:
                logger.debug("CloseHandle(hThread) 失败: %s", e)
        if proc_info.hProcess:
            try:
                kernel32.CloseHandle(proc_info.hProcess)
            except Exception as e:
                logger.debug("CloseHandle(hProcess) 失败: %s", e)
        if env_created and env:
            try:
                userenv.DestroyEnvironmentBlock(env)
            except Exception as e:
                logger.debug("DestroyEnvironmentBlock 失败: %s", e)


def _open_process_token_for_pid(pid: int, desired_access: int):
    process = wintypes.HANDLE()
    token = wintypes.HANDLE()
    try:
        process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not process:
            logger.debug("自启动中转无法打开 Explorer 进程 pid=%s: %s", pid, _get_last_error_text())
            return None

        if not advapi32.OpenProcessToken(process, desired_access, ctypes.byref(token)):
            logger.debug("自启动中转无法读取 Explorer 令牌 pid=%s: %s", pid, _get_last_error_text())
            return None

        opened_token = token
        token = wintypes.HANDLE()
        return opened_token
    finally:
        if token:
            try:
                kernel32.CloseHandle(token)
            except Exception as e:
                logger.debug("CloseHandle(token) 失败: %s", e)
        if process:
            try:
                kernel32.CloseHandle(process)
            except Exception as e:
                logger.debug("CloseHandle(process) 失败: %s", e)


def _is_process_elevated_by_pid(pid: int) -> bool | None:
    token = _open_process_token_for_pid(pid, TOKEN_QUERY)
    if not token:
        return None

    try:
        elevation = TOKEN_ELEVATION()
        size = wintypes.DWORD()
        if not advapi32.GetTokenInformation(
            token,
            TOKEN_ELEVATION_CLASS,
            ctypes.byref(elevation),
            ctypes.sizeof(elevation),
            ctypes.byref(size),
        ):
            logger.debug("自启动中转无法读取 Explorer elevation pid=%s: %s", pid, _get_last_error_text())
            return None

        return bool(elevation.TokenIsElevated)
    finally:
        try:
            kernel32.CloseHandle(token)
        except Exception as e:
            logger.debug("CloseHandle(token) 失败: %s", e)


def _get_shell_explorer_elevation() -> tuple[bool | None, int | None, str]:
    hwnd = user32.GetShellWindow()
    if not hwnd:
        return None, None, "shell_window_missing"

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None, None, "shell_pid_missing"

    elevated = _is_process_elevated_by_pid(int(pid.value))
    if elevated is None:
        return None, int(pid.value), "shell_token_unknown"
    return elevated, int(pid.value), "ok"


def _get_shell_explorer_primary_token() -> tuple[object | None, int | None, str]:
    elevated, pid, reason = _get_shell_explorer_elevation()
    if elevated is None:
        return None, pid, reason
    if elevated:
        return None, pid, "shell_elevated"
    if not pid:
        return None, None, "shell_pid_missing"

    token = _open_process_token_for_pid(
        pid,
        TOKEN_QUERY | TOKEN_DUPLICATE | TOKEN_ASSIGN_PRIMARY | TOKEN_ADJUST_DEFAULT | TOKEN_ADJUST_SESSIONID,
    )
    if not token:
        token = _open_process_token_for_pid(pid, TOKEN_QUERY | TOKEN_DUPLICATE)
    if not token:
        return None, pid, "shell_token_open_failed"

    primary_token = wintypes.HANDLE()
    try:
        if not advapi32.DuplicateTokenEx(
            token,
            MAXIMUM_ALLOWED,
            None,
            SecurityImpersonation,
            TokenPrimary,
            ctypes.byref(primary_token),
        ):
            logger.debug("自启动中转复制 Explorer token 失败: pid=%s %s", pid, _get_last_error_text())
            return None, pid, "shell_token_duplicate_failed"

        opened_token = primary_token
        primary_token = wintypes.HANDLE()
        return opened_token, pid, "ok"
    finally:
        if primary_token:
            try:
                kernel32.CloseHandle(primary_token)
            except Exception as e:
                logger.debug("CloseHandle(primary_token) 失败: %s", e)
        try:
            kernel32.CloseHandle(token)
        except Exception as e:
            logger.debug("CloseHandle(token) 失败: %s", e)


def _launch_via_explorer_token(
    target: str,
    arguments: str = "",
    working_dir: str = "",
    *,
    timeout_seconds: float = AUTOSTART_FALLBACK_TIMEOUT_SECONDS,
    poll_seconds: float = AUTOSTART_FALLBACK_POLL_SECONDS,
) -> bool:
    """Create the real app with Explorer's medium token."""
    if os.name != "nt":
        return _launch_with_current_token(target, arguments, working_dir)

    import time

    last_reason = ""
    last_pid = None
    attempt = 0
    start = time.monotonic()
    timeout_seconds = max(0.05, float(timeout_seconds))
    deadline = start + timeout_seconds
    poll_seconds = max(0.1, min(1.0, poll_seconds))

    while True:
        attempt += 1
        elapsed = time.monotonic() - start
        token, shell_pid, reason = _get_shell_explorer_primary_token()
        last_reason = reason
        last_pid = shell_pid

        if token:
            try:
                if _create_process_with_token(
                    token,
                    target,
                    arguments,
                    working_dir,
                    token_source="Explorer token",
                ):
                    logger.info(
                        "自启动中转已通过 Explorer token 启动: explorer_pid=%s target=%s %s",
                        shell_pid,
                        target,
                        arguments or "",
                    )
                    return True
                reason = "create_process_with_explorer_token_failed"
                last_reason = reason
            finally:
                try:
                    kernel32.CloseHandle(token)
                except Exception as e:
                    logger.debug("CloseHandle(token) 失败: %s", e)

        if reason == "shell_elevated":
            logger.error(
                "自启动中转拒绝使用高权限 Explorer token 启动主程序: pid=%s attempt=%s",
                shell_pid,
                attempt,
            )
            return False

        should_log = attempt == 1 or attempt % max(1, int(round(1.0 / poll_seconds))) == 0
        if should_log:
            logger.info(
                "自启动中转等待 Explorer token 可用: attempt=%s elapsed=%.2fs timeout=%.1fs reason=%s pid=%s",
                attempt,
                elapsed,
                timeout_seconds,
                reason,
                shell_pid,
            )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_seconds, remaining))

    logger.error(
        "自启动中转 Explorer token fallback 失败: attempts=%s timeout=%.1fs last_reason=%s pid=%s",
        attempt,
        timeout_seconds,
        last_reason,
        last_pid,
    )
    return False


def _launch_as_standard_user(target: str, arguments: str = "", working_dir: str = "") -> bool:
    if os.name == "nt":
        if not _is_current_process_elevated():
            logger.info("自启动中转当前已是普通权限，直接启动主程序")
            return _launch_with_current_token(target, arguments, working_dir)

        logger.info("自启动中转当前为高权限，直接使用 Explorer token 降权启动")

    return _launch_via_explorer_token(target, arguments, working_dir)


def run_autostart_launcher(
    exe_path: str | None = None,
    arguments: str = "",
    working_dir: str = "",
) -> int:
    """Scheduled-task entry point that relaunches the real app unelevated."""
    path, args, cwd = _normalize_launch_spec(exe_path, arguments, working_dir)
    if not os.path.isfile(path):
        logger.error("自启动中转目标不存在: %s", path)
        return HELPER_EXIT_FAILED
    if not _is_allowed_helper_target(path, args, cwd):
        logger.error("自启动中转拒绝非当前程序目标: path=%s args=%s cwd=%s", path, args, cwd)
        return HELPER_EXIT_BAD_ARGS

    try:
        from core.windows_uipi import format_process_elevation_status

        logger.info("自启动中转权限状态: %s", format_process_elevation_status())
    except Exception as exc:
        logger.debug("自启动中转权限状态检测失败: %s", exc)

    logger.info("自启动中转准备降权启动: path=%s args=%s cwd=%s", path, args, cwd)
    if _launch_as_standard_user(path, args, cwd):
        return HELPER_EXIT_SUCCESS

    logger.error("自启动中转降权启动全部失败: path=%s args=%s cwd=%s", path, args, cwd)
    return HELPER_EXIT_FAILED


def _get_task_scheduler_service():
    """Return a Task Scheduler COM service instance."""
    try:
        import pythoncom

        pythoncom.CoInitialize()
    except Exception as e:
        logger.debug("CoInitialize 失败 (可能已初始化): %s", e)

    import win32com.client

    scheduler = win32com.client.Dispatch("Schedule.Service")
    scheduler.Connect()
    return scheduler


def _cleanup_legacy_task_scheduler_tasks() -> list[str]:
    """Delete legacy elevated tasks from old versions."""
    if os.name != "nt":
        return []

    removed: list[str] = []
    try:
        scheduler = _get_task_scheduler_service()
        root_folder = scheduler.GetFolder("\\")
        for legacy_name in LEGACY_TASK_NAMES:
            try:
                root_folder.DeleteTask(legacy_name, 0)
                removed.append(legacy_name)
            except Exception as e:
                logger.debug("删除旧版任务 %s 失败 (可能不存在): %s", legacy_name, e)
    except Exception as exc:
        logger.debug("清理旧版计划任务失败: %s", exc)

    if removed:
        logger.info("已清理旧版高权限计划任务: %s", ", ".join(removed))
    return removed


def enable_task_scheduler(exe_path: str | None = None, arguments: str = "", working_dir: str = "") -> bool:
    """Create the helper-only unelevated logon task."""
    if os.name != "nt":
        logger.warning("当前系统不支持 Task Scheduler 自启动")
        return False

    path, args, cwd = _normalize_launch_spec(exe_path, arguments, working_dir)
    if not os.path.isfile(path):
        logger.warning("目标程序不存在，无法创建自启动任务: %s", path)
        return False

    for attempt in range(2):
        try:
            scheduler = _get_task_scheduler_service()
            root_folder = scheduler.GetFolder("\\")
            _cleanup_legacy_task_scheduler_tasks()

            try:
                root_folder.DeleteTask(TASK_NAME, 0)
            except Exception as e:
                logger.debug("删除旧任务失败 (首次注册属正常): %s", e)

            user_id = _get_current_user_identity()
            task_path, task_args, task_cwd, task_mode = _build_task_action_launch(path, args, cwd)
            trigger_delay = _get_task_trigger_delay(task_mode)
            task_def = _build_task_definition(
                scheduler,
                path,
                args,
                cwd,
                user_id,
                set_trigger_user=True,
                set_principal_user=True,
            )

            # TASK_LOGON_INTERACTIVE_TOKEN should not be registered with an empty password.
            # Use the Principal.UserId already stored in task_def and keep credentials empty.
            root_folder.RegisterTaskDefinition(TASK_NAME, task_def, 6, None, None, 3)

            task_valid, task_reason = get_task_scheduler_check_result(path, args, cwd)
            if task_valid:
                logger.info(
                    "Task Scheduler 自启动任务已创建: mode=%s, trigger_delay=%s, task_path=%s, task_args=%s, task_cwd=%s, target=%s %s",
                    task_mode,
                    trigger_delay or "none",
                    task_path,
                    task_args,
                    task_cwd,
                    path,
                    args,
                )
                return True

            logger.warning("Task Scheduler 任务创建后验证失败: %s", task_reason)
        except Exception as exc:
            logger.warning("Task Scheduler 创建失败 (attempt %s): %s", attempt + 1, exc)

        if attempt == 0:
            import time

            time.sleep(0.5)

    return False


def disable_task_scheduler() -> bool:
    """Delete the current and legacy auto-start tasks."""
    if os.name != "nt":
        return False

    try:
        scheduler = _get_task_scheduler_service()
        root_folder = scheduler.GetFolder("\\")
        removed = False

        try:
            root_folder.DeleteTask(TASK_NAME, 0)
            removed = True
        except Exception as e:
            logger.debug("删除自启动任务失败 (可能不存在): %s", e)

        if _cleanup_legacy_task_scheduler_tasks():
            removed = True

        if removed:
            logger.info("Task Scheduler 自启动任务已删除")
        return removed
    except Exception as exc:
        logger.debug("删除 Task Scheduler 任务失败: %s", exc)
        return False


def get_task_scheduler_check_result(
    exe_path: str | None = None,
    arguments: str = "",
    working_dir: str = "",
) -> tuple[bool, str]:
    """Return whether the helper-created task is valid plus a diagnostic reason."""
    if os.name != "nt":
        return False, "unsupported_platform"

    try:
        scheduler = _get_task_scheduler_service()
        root_folder = scheduler.GetFolder("\\")
        task = root_folder.GetTask(TASK_NAME)
        return _validate_task_launch_spec(task, exe_path, arguments, working_dir)
    except Exception as exc:
        return False, f"task_missing_or_inaccessible: {exc}"


def is_task_scheduler_enabled(exe_path: str | None = None, arguments: str = "", working_dir: str = "") -> bool:
    """Return whether the helper-created task exists and is enabled."""
    enabled, reason = get_task_scheduler_check_result(exe_path, arguments, working_dir)
    if not enabled:
        logger.debug("Task Scheduler 自启动任务无效: %s", reason)
    return enabled


def _read_registry_value() -> str | None:
    """Read the legacy Run key if it still exists."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY_PATH, 0, winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return value
        except FileNotFoundError:
            return None
        finally:
            winreg.CloseKey(key)
    except OSError:
        return None


def _delete_registry_value() -> bool:
    """Delete the legacy Run key if present."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY_PATH, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, APP_NAME)
            logger.info("注册表自启动已删除")
        except FileNotFoundError:
            pass
        finally:
            winreg.CloseKey(key)
        return True
    except OSError as exc:
        logger.error("删除注册表自启动失败: %s", exc)
        return False


def _enable_auto_start_direct(
    exe_path: str | None = None,
    arguments: str = "",
    working_dir: str = "",
) -> tuple[bool, str]:
    """Helper-internal direct task creation."""
    path, args, cwd = _normalize_launch_spec(exe_path, arguments, working_dir)
    if not os.path.isfile(path):
        logger.warning("目标程序不存在，无法设置自启动: %s", path)
        return False, "failed"
    if not _is_allowed_helper_target(path, args, cwd):
        logger.error("自启动 helper 拒绝非当前程序目标: path=%s args=%s cwd=%s", path, args, cwd)
        return False, "failed"

    logger.info("自启动 helper 直写任务: path=%s, args=%s, cwd=%s", path, args, cwd)
    if enable_task_scheduler(path, args, cwd):
        logger.info("自启动已启用（Task Scheduler）")
        return True, "task_scheduler"

    logger.error("Task Scheduler 自启动创建失败")
    return False, "failed"


def enable_auto_start(
    exe_path: str | None = None,
    arguments: str = "",
    working_dir: str = "",
) -> tuple[bool, str]:
    """Enable auto-start using the account-appropriate path."""
    if exe_path:
        target_path, target_args, target_cwd = _normalize_launch_spec(exe_path, arguments, working_dir)
    else:
        target_path, target_args, target_cwd = _get_app_launch_spec()

    if not _is_current_account_admin():
        logger.info("非管理员账号启用自启动：直接创建当前用户任务")
        return _enable_auto_start_direct(target_path, target_args, target_cwd)

    logger.info("管理员账号启用自启动：通过 helper 创建中转降权任务")
    return _run_elevated_helper(HELPER_ACTION_ENABLE, target_path, target_args, target_cwd)


def _disable_auto_start_direct() -> tuple[bool, str]:
    """Helper-internal direct task removal and cleanup."""
    task_removed = disable_task_scheduler()
    registry_removed = _delete_registry_value()
    task_still_enabled = is_task_scheduler_enabled()
    registry_still_exists = _read_registry_value() is not None

    if not task_still_enabled and not registry_still_exists:
        if task_removed or registry_removed:
            logger.info("自启动已禁用（Task Scheduler / registry cleanup complete）")
        return True, "task_scheduler"

    logger.error(
        "禁用自启动后仍检测到残留: task_enabled=%s registry_exists=%s",
        task_still_enabled,
        registry_still_exists,
    )
    return False, "failed"


def disable_auto_start() -> tuple[bool, str]:
    """Disable auto-start using the account-appropriate path."""
    if not _is_current_account_admin():
        logger.info("非管理员账号禁用自启动：直接删除当前用户任务")
        return _disable_auto_start_direct()

    logger.info("管理员账号禁用自启动：通过 helper 清理任务")
    return _run_elevated_helper(HELPER_ACTION_DISABLE)


def is_auto_start_enabled() -> bool:
    return is_task_scheduler_enabled()


def get_auto_start_method() -> str:
    return "task_scheduler" if is_task_scheduler_enabled() else "none"


def get_auto_start_check_result() -> tuple[bool, str]:
    """Return current auto-start validity and a reason suitable for logs."""
    return get_task_scheduler_check_result()


def is_auto_start_repair_needed(auto_start_enabled: bool = True) -> bool:
    """Return whether the user wants auto-start but the task is missing or stale."""
    enabled, _ = get_auto_start_check_result()
    return bool(auto_start_enabled) and not enabled


def _has_legacy_tasks() -> bool:
    """Return True if any legacy elevated auto-start tasks still exist."""
    if os.name != "nt":
        return False
    try:
        scheduler = _get_task_scheduler_service()
        root_folder = scheduler.GetFolder("\\")
        for name in LEGACY_TASK_NAMES:
            try:
                root_folder.GetTask(name)
                return True
            except Exception:
                logger.debug("旧版任务 %s 不存在", name)
    except Exception as e:
        logger.debug("检查旧版任务失败: %s", e)
    return False


def _ensure_auto_start(auto_start_enabled: bool = True):
    """Startup check only. Do not recreate tasks inside the main process."""
    if not _is_frozen():
        return

    # Try direct cleanup first; if legacy tasks survive (need elevation), use helper.
    _cleanup_legacy_task_scheduler_tasks()
    if _has_legacy_tasks():
        logger.info("旧版高权限计划任务仍存在，通过 helper 提权清理")
        _run_elevated_helper(HELPER_ACTION_DISABLE)

    if not auto_start_enabled:
        return

    enabled, reason = get_auto_start_check_result()
    if not enabled:
        logger.warning("配置要求开机自启，但任务缺失或定义已过期，需要在设置中重新启用以修复: %s", reason)


def get_exe_path() -> tuple[str, str]:
    """Compatibility helper returning the current launch path and args."""
    path, args, _ = _get_app_launch_spec()
    return path, args
