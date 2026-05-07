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
HELPER_TARGET_ARG = "--target-exe"
HELPER_TARGET_ARGS_ARG = "--target-args"
HELPER_TARGET_CWD_ARG = "--target-cwd"
HELPER_ACTION_ENABLE = "enable"
HELPER_ACTION_DISABLE = "disable"

HELPER_EXIT_SUCCESS = 0
HELPER_EXIT_FAILED = 1
HELPER_EXIT_CANCELLED = 2
HELPER_EXIT_BAD_ARGS = 3

SEE_MASK_NOCLOSEPROCESS = 0x00000040
SW_HIDE = 0
INFINITE = 0xFFFFFFFF

if os.name == "nt":
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32
else:
    shell32 = None
    kernel32 = None


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


if os.name == "nt":
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFO)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL


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
        except Exception:
            pass

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
    except Exception:
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


def _extract_task_scheduler_win32_error(exc: Exception) -> int | None:
    """Extract the nested Win32 error from a pywin32 COM exception when available."""
    try:
        details = exc.args[2] if len(exc.args) > 2 else None
        if isinstance(details, tuple) and len(details) > 5 and isinstance(details[5], int):
            return int(details[5])
    except Exception:
        pass
    return None


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

    trigger = task_def.Triggers.Create(9)  # TASK_TRIGGER_LOGON
    trigger.Enabled = True
    trigger.Delay = ""
    if set_trigger_user and user_id:
        try:
            trigger.UserId = user_id
        except Exception:
            pass

    action = task_def.Actions.Create(0)  # TASK_ACTION_EXEC
    action.Path = path
    if args:
        action.Arguments = args
    if cwd:
        action.WorkingDirectory = cwd

    task_def.Principal.LogonType = 3  # TASK_LOGON_INTERACTIVE_TOKEN
    task_def.Principal.RunLevel = 0  # TASK_RUNLEVEL_LUA
    if set_principal_user and user_id:
        try:
            task_def.Principal.UserId = user_id
        except Exception:
            pass
    try:
        # Filter the admin token so the main app still starts unelevated.
        task_def.Principal.ProcessTokenSidType = 2
    except Exception:
        pass

    return task_def


def _get_app_launch_spec() -> tuple[str, str, str]:
    """Return the current app launch triple: (path, args, cwd)."""
    if _is_frozen():
        exe_path = _get_exe_path()
        return exe_path, "", os.path.dirname(exe_path)

    main_script = (
        os.path.abspath(sys.argv[0])
        if sys.argv and sys.argv[0]
        else os.path.join(_get_project_root(), "main.py")
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
    return (
        _normalize_abs_path(path) == _normalize_abs_path(sys.executable)
        and (args or "").strip() == expected_args
    )


def _task_matches_launch_spec(task, exe_path: str | None = None, arguments: str = "", working_dir: str = "") -> bool:
    """Validate that an existing scheduled task still points to the current app."""
    try:
        path, args, cwd = _normalize_launch_spec(exe_path, arguments, working_dir)
        expected_users = _get_current_user_identity_variants()

        enabled = bool(getattr(task, "Enabled", False))
        if not enabled:
            return False

        definition = task.Definition
        principal = definition.Principal
        if int(getattr(principal, "RunLevel", 0)) != 0:
            return False

        actual_user = (getattr(principal, "UserId", "") or "").strip().lower()
        if expected_users and actual_user and actual_user not in expected_users:
            return False

        actions = definition.Actions
        if int(getattr(actions, "Count", 0)) < 1:
            return False

        action = actions.Item(1)
        actual_path = _normalize_abs_path(getattr(action, "Path", "") or "")
        actual_args = (getattr(action, "Arguments", "") or "").strip()
        actual_cwd = _normalize_abs_path(getattr(action, "WorkingDirectory", "") or "")

        return (
            actual_path == _normalize_abs_path(path)
            and actual_args == (args or "").strip()
            and actual_cwd == _normalize_abs_path(cwd)
        )
    except Exception as exc:
        logger.debug("读取自启动任务定义失败: %s", exc)
        return False


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
        if not shell32.ShellExecuteExW(ctypes.byref(sei)):
            error_code = kernel32.GetLastError()
            if error_code == 1223:
                logger.info("用户取消了自启动 helper 的 UAC 授权")
                return False, "cancelled"
            logger.error("启动自启动 helper 失败, error=%s", error_code)
            return False, "failed"

        kernel32.WaitForSingleObject(sei.hProcess, INFINITE)
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
            except Exception:
                pass


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


def _get_task_scheduler_service():
    """Return a Task Scheduler COM service instance."""
    try:
        import pythoncom

        pythoncom.CoInitialize()
    except Exception:
        pass

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
            except Exception:
                pass
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
            except Exception:
                pass

            task_def = scheduler.NewTask(0)
            task_def.RegistrationInfo.Description = "QuickLauncher 开机自启（helper）"
            task_def.Settings.Enabled = True
            task_def.Settings.StartWhenAvailable = True
            task_def.Settings.DisallowStartIfOnBatteries = False
            task_def.Settings.StopIfGoingOnBatteries = False
            task_def.Settings.ExecutionTimeLimit = "PT0S"
            task_def.Settings.AllowHardTerminate = False
            task_def.Settings.Priority = 4

            trigger = task_def.Triggers.Create(9)  # TASK_TRIGGER_LOGON
            trigger.Enabled = True
            trigger.Delay = ""
            user_id = _get_current_user_identity()
            try:
                if user_id:
                    trigger.UserId = user_id
            except Exception:
                pass

            action = task_def.Actions.Create(0)  # TASK_ACTION_EXEC
            action.Path = path
            if args:
                action.Arguments = args
            if cwd:
                action.WorkingDirectory = cwd

            task_def.Principal.LogonType = 3  # TASK_LOGON_INTERACTIVE_TOKEN
            task_def.Principal.RunLevel = 0  # TASK_RUNLEVEL_LUA
            try:
                if user_id:
                    task_def.Principal.UserId = user_id
            except Exception:
                pass
            try:
                # Filter the admin token so the main app still starts unelevated.
                task_def.Principal.ProcessTokenSidType = 2
            except Exception:
                pass

            # TASK_LOGON_INTERACTIVE_TOKEN should not be registered with an empty password.
            # Use the Principal.UserId already stored in task_def and keep credentials empty.
            root_folder.RegisterTaskDefinition(TASK_NAME, task_def, 6, None, None, 3)

            if is_task_scheduler_enabled(path, args, cwd):
                logger.info(
                    "Task Scheduler 自启动任务已创建: path=%s, args=%s, cwd=%s",
                    path,
                    args,
                    cwd,
                )
                return True

            logger.warning("Task Scheduler 任务创建后验证失败")
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
        except Exception:
            pass

        if _cleanup_legacy_task_scheduler_tasks():
            removed = True

        if removed:
            logger.info("Task Scheduler 自启动任务已删除")
        return removed
    except Exception as exc:
        logger.debug("删除 Task Scheduler 任务失败: %s", exc)
        return False


def is_task_scheduler_enabled(exe_path: str | None = None, arguments: str = "", working_dir: str = "") -> bool:
    """Return whether the helper-created task exists and is enabled."""
    if os.name != "nt":
        return False

    try:
        scheduler = _get_task_scheduler_service()
        root_folder = scheduler.GetFolder("\\")
        task = root_folder.GetTask(TASK_NAME)
        return _task_matches_launch_spec(task, exe_path, arguments, working_dir)
    except Exception:
        return False


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


def _write_registry_value(exe_path: str) -> bool:
    """Legacy compatibility helper. No longer used for normal creation."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY_PATH, 0, winreg.KEY_SET_VALUE)
        cmd = f'"{exe_path}"'
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        logger.info("注册表自启动已写入: %s", cmd)
        return True
    except OSError as exc:
        logger.error("写入注册表自启动失败: %s", exc)
        return False


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
    """Enable auto-start via the elevated helper."""
    if exe_path:
        target_path, target_args, target_cwd = _normalize_launch_spec(exe_path, arguments, working_dir)
    else:
        target_path, target_args, target_cwd = _get_app_launch_spec()

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
    """Disable auto-start via the elevated helper."""
    return _run_elevated_helper(HELPER_ACTION_DISABLE)


def is_auto_start_enabled() -> bool:
    return is_task_scheduler_enabled()


def get_auto_start_method() -> str:
    return "task_scheduler" if is_task_scheduler_enabled() else "none"


def fix_auto_start() -> tuple[bool, str]:
    """Rebuild the helper-only auto-start task."""
    target_path, target_args, target_cwd = _get_app_launch_spec()
    if not os.path.isfile(target_path):
        return False, f"目标文件不存在: {target_path}"

    disable_task_scheduler()
    _delete_registry_value()

    success, _ = enable_auto_start(target_path, target_args, target_cwd)
    if success:
        command_text = target_path if not target_args else f"{target_path} {target_args}"
        return True, (
            "开机自启动已修复\n\n"
            "方式: helper + 任务计划\n"
            f"命令: {command_text}\n"
            f"工作目录: {target_cwd}"
        )

    return False, (
        "修复失败\n\n"
        "可能原因:\n"
        "1. 杀毒软件拦截\n"
        "2. 系统策略禁止修改启动项\n\n"
        "建议将程序添加到杀毒软件白名单后重试"
    )


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
                pass
    except Exception:
        pass
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

    if not is_task_scheduler_enabled():
        logger.info("配置要求开机自启，但 helper 创建的任务当前缺失")


def get_exe_path() -> tuple[str, str]:
    """Compatibility helper returning the current launch path and args."""
    path, args, _ = _get_app_launch_spec()
    return path, args


def migrate_to_fast_startup() -> bool:
    """Deprecated compatibility stub."""
    return False
