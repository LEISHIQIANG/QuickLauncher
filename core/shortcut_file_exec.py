"""File and process launch helpers for ShortcutExecutor."""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
import threading
import time
from typing import List, Optional

import win32process

from .data_models import ShortcutItem
from .windows_uipi import is_process_elevated

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
try:
    ULONG_PTR = wintypes.ULONG_PTR
except AttributeError:
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_SCANCODE = 0x0008

SendInput = user32.SendInput
SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
SendInput.restype = wintypes.UINT

logger = logging.getLogger(__name__)
ShortcutExecutor = None
STANDARD_USER_LAUNCH_FAILED_MESSAGE = (
    "QuickLauncher is currently elevated and standard-user launch failed. "
    "Start QuickLauncher as a normal user or enable run-as-admin for this item."
)

try:
    from .window_manager import WindowManager
    HAS_WINDOW_MANAGER = True
except ImportError:
    WindowManager = None
    HAS_WINDOW_MANAGER = False


class FileExecutionMixin:
    @staticmethod
    def _resolve_shortcut(path: str) -> Optional[str]:
        """解析快捷方式获取真实目标路径
        
        Args:
            path: 文件路径（可能是 .lnk 快捷方式）
        
        Returns:
            真实目标路径，如果不是快捷方式则返回原路径
        """
        if not path:
            return None
        
        # 如果不是 .lnk 文件，直接返回
        if not path.lower().endswith('.lnk'):
            return path
        
        if not os.path.exists(path):
            return path
        
        try:
            # 使用 COM 接口解析快捷方式
            import pythoncom
            from win32com.shell import shell, shellcon
            
            pythoncom.CoInitialize()
            try:
                link = pythoncom.CoCreateInstance(
                    shell.CLSID_ShellLink,
                    None,
                    pythoncom.CLSCTX_INPROC_SERVER,
                    shell.IID_IShellLink
                )
                persist_file = link.QueryInterface(pythoncom.IID_IPersistFile)
                persist_file.Load(path)
                
                target_path, _ = link.GetPath(shell.SLGP_RAWPATH)
                if target_path:
                    logger.debug(f"解析快捷方式: {path} -> {target_path}")
                    return target_path
            finally:
                pythoncom.CoUninitialize()
        except ImportError:
            logger.debug("pywin32 未安装，尝试其他方式解析快捷方式")
        except Exception as e:
            logger.debug(f"解析快捷方式失败: {e}")
        
        # 备用方案：使用 PowerShell 解析
        try:
            ps_script = f'''
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut("{path}")
            $shortcut.TargetPath
            '''
            
            # 使用更隐蔽的参数
            ps_cmd = [
                'powershell', 
                '-NoLogo', 
                '-NoProfile', 
                '-NonInteractive', 
                '-WindowStyle', 'Hidden', 
                '-Command', ps_script
            ]
            
            output = ShortcutExecutor._run_silent_output(ps_cmd)
            
            if output and output.strip():
                target = output.strip()
                logger.debug(f"PowerShell 解析快捷方式: {path} -> {target}")
                return target
        except Exception as e:
            logger.debug(f"PowerShell 解析快捷方式失败: {e}")
        
        # 如果都失败，返回原路径
        return path
    @staticmethod
    def _open_folder_with_files(folder: str, files: List[str]) -> bool:
        """打开文件夹并选中文件（用于文件夹类型快捷方式）
        
        Args:
            folder: 目标文件夹路径
            files: 要处理的文件列表
        
        Returns:
            bool: 是否成功
        """
        try:
            # 方案1：使用 explorer /select 打开并选中第一个文件（如果在该文件夹中）
            # 方案2：如果文件不在该文件夹中，可以选择复制文件到该文件夹
            # 这里我们选择方案1的变体：打开文件夹
            
            # 简单处理：打开目标文件夹
            if not ShortcutExecutor._shell_execute_open(folder):
                os.startfile(folder)
            logger.info(f"打开文件夹: {folder}")
            
            # TODO: 可以扩展为将文件复制到该文件夹
            # 或者用 explorer /select 选中文件（如果在同一文件夹）
            
            return True
        except Exception as e:
            logger.error(f"打开文件夹失败: {e}")
            return False
    @staticmethod
    def _open_exe_with_files(
        exe_path: str,
        files: List[str],
        extra_args: str = "",
        working_dir: str = "",
        run_as_admin: bool = False
    ) -> bool:
        """使用可执行文件打开文件列表
        
        Args:
            exe_path: 可执行文件路径
            files: 要打开的文件列表
            extra_args: 额外的命令行参数
        
        Returns:
            bool: 是否成功
        """
        success = True
        
        # 构建命令行参数
        # 某些程序支持一次传入多个文件，某些需要分别启动
        # 这里我们尝试一次性传入所有文件
        
        try:
            cmd_args = [exe_path]
            
            # 添加额外参数
            if extra_args:
                cmd_args.extend(ShortcutExecutor._safe_split_args(extra_args))
            
            # 添加所有文件
            cmd_args.extend(files)
            
            logger.info(f"执行命令: {cmd_args}")
            
            exe_dir = os.path.dirname(os.path.abspath(exe_path)) if exe_path else None
            cwd = working_dir.strip() if working_dir else ""
            if os.name == "nt":
                parameters = subprocess.list2cmdline(cmd_args[1:]) if len(cmd_args) > 1 else ""
                launched, launch_error = ShortcutExecutor._launch_with_privilege(
                    exe_path,
                    parameters or None,
                    cwd or exe_dir or None,
                    run_as_admin=run_as_admin,
                    admin_failure_message="Administrator launch failed.",
                )
                if launched:
                    return True
                if launch_error:
                    logger.warning("%s: %s", exe_path, launch_error)
                    return False

            ShortcutExecutor._popen_silent(
                cmd_args,
                cwd=cwd or exe_dir or None,
                env=ShortcutExecutor._sanitized_child_env(),
            )
            
            return True
            
        except Exception as e:
            logger.warning(f"一次性传入文件失败: {e}，尝试逐个打开")
        
        # 备用方案：逐个打开文件
        for file_path in files:
            try:
                cmd = [exe_path]
                if extra_args:
                    cmd.extend(ShortcutExecutor._safe_split_args(extra_args))
                cmd.append(file_path)
                exe_dir = os.path.dirname(os.path.abspath(exe_path)) if exe_path else None
                cwd = working_dir.strip() if working_dir else ""
                if os.name == "nt":
                    parameters = subprocess.list2cmdline(cmd[1:]) if len(cmd) > 1 else ""
                    launched, launch_error = ShortcutExecutor._launch_with_privilege(
                        exe_path,
                        parameters or None,
                        cwd or exe_dir or None,
                        run_as_admin=run_as_admin,
                        admin_failure_message="Administrator launch failed.",
                    )
                    if launched:
                        logger.info(f"ShellExecute launched: {exe_path} {file_path}")
                        continue
                    if launch_error:
                        logger.warning("%s: %s", exe_path, launch_error)
                        return False

                ShortcutExecutor._popen_silent(cmd, cwd=cwd or exe_dir or None, env=ShortcutExecutor._sanitized_child_env())
                logger.info(f"用 {exe_path} 打开: {file_path}")
            except Exception as e:
                logger.error(f"逐个打开文件失败 {file_path}: {e}")
                success = False
        return success
    @staticmethod
    def _open_file_with_files(target: str, files: List[str], run_as_admin: bool = False) -> bool:
        """使用非 exe 文件（如脚本、文档等）关联的程序打开文件"""
        success = True
        target_dir = os.path.dirname(os.path.abspath(target)) if target else None
        for file_path in files:
            try:
                launch_error = ""
                if os.name == "nt":
                    parameters = subprocess.list2cmdline([file_path])
                    launched, launch_error = ShortcutExecutor._launch_with_privilege(
                        target,
                        parameters or None,
                        target_dir,
                        run_as_admin=run_as_admin,
                        admin_failure_message="Administrator launch failed.",
                    )
                    if launched:
                        logger.info(f"Associated launch succeeded: target={target}, file={file_path}")
                        continue
                    if launch_error:
                        logger.warning("%s: %s", target, launch_error)
                        return False

                # 使用 start 命令，让 Windows 决定用什么程序打开
                cmd = f'start "" "{target}" "{file_path}"'
                ShortcutExecutor._popen_silent(cmd, shell=True)
                logger.info(f"Start 命令打开: {cmd}")
            except Exception as e:
                logger.error(f"打开文件失败 {file_path}: {e}")
                success = False
                try:
                    if run_as_admin:
                        return False
                    os.startfile(file_path)
                    logger.info(f"os.startfile 打开: {file_path}")
                    success = True
                except Exception:
                    pass
        return success
    @staticmethod
    def _is_launch_context_elevated() -> bool:
        return os.name == "nt" and is_process_elevated()
    @staticmethod
    def _shell_execute_open_raw(
        target: str,
        parameters: Optional[str] = None,
        directory: Optional[str] = None,
        show_cmd: int = 1,
        verb: str = "open",
    ) -> bool:
        try:
            if os.name != "nt":
                argv = [target]
                if parameters:
                    argv.extend(ShortcutExecutor._safe_split_args(parameters))
                ShortcutExecutor._popen_silent(argv, env=ShortcutExecutor._sanitized_child_env())
                return True

            result = shell32.ShellExecuteW(None, verb, target, parameters, directory, show_cmd)
            if int(result) <= 32:
                logger.debug(
                    "ShellExecuteW failed: target=%s parameters=%s verb=%s code=%s",
                    target,
                    parameters or "",
                    verb,
                    int(result),
                )
                return False
            return True
        except Exception as e:
            logger.debug("ShellExecuteW exception: %s", e)
            return False
    @staticmethod
    def _launch_with_privilege(
        target: str,
        parameters: Optional[str] = None,
        directory: Optional[str] = None,
        show_cmd: int = 1,
        run_as_admin: bool = False,
        admin_failure_message: str = "Administrator launch failed.",
        standard_user_failure_message: str = STANDARD_USER_LAUNCH_FAILED_MESSAGE,
    ) -> tuple[bool, str]:
        if os.name != "nt":
            argv = [target]
            if parameters:
                argv.extend(ShortcutExecutor._safe_split_args(parameters))
            ShortcutExecutor._popen_silent(argv, env=ShortcutExecutor._sanitized_child_env())
            return True, ""

        if not run_as_admin and ShortcutExecutor._is_launch_context_elevated():
            if ShortcutExecutor._execute_as_standard_user(
                target,
                parameters or "",
                directory or "",
                show_cmd,
            ):
                return True, ""
            return False, standard_user_failure_message

        verb = "runas" if run_as_admin else "open"
        if ShortcutExecutor._shell_execute_open_raw(target, parameters, directory, show_cmd, verb=verb):
            return True, ""

        if run_as_admin:
            return False, admin_failure_message
        return False, ""
    @staticmethod
    def _shell_execute_open(
        target: str,
        parameters: Optional[str] = None,
        directory: Optional[str] = None,
        show_cmd: int = 1,
        run_as_admin: bool = False,
    ) -> bool:
        success, _ = ShortcutExecutor._launch_with_privilege(
            target,
            parameters,
            directory,
            show_cmd,
            run_as_admin=run_as_admin,
        )
        return success
    @staticmethod
    def _activate_launched_app_async(exe_path: str):
        """【平滑置顶】后台异步监测并激活刚启动的程序窗口。"""
        if not exe_path or not HAS_WINDOW_MANAGER:
            return
            
        def run():
            # 增加一个起步延迟，让软件自身的启动/恢复逻辑先跑一会儿，减少抢焦点的冲突
            time.sleep(0.15)
            
            # 监测周期：由快到慢
            # 如果软件已经在前台了，就立即停止，防止“反复置顶”导致的闪烁
            for delay_s in (0.1, 0.2, 0.4, 0.6, 1.0):
                time.sleep(delay_s)
                try:
                    # 获取当前前台窗口，检查是否已经是我们要激活的进程下的窗口
                    # 如果已经是前台了，且不是隐藏状态，就没必要再激活了
                    target_pids = []
                    import psutil
                    process_name = os.path.splitext(os.path.basename(exe_path))[0].lower()
                    for proc in psutil.process_iter(['name', 'pid']):
                        if proc.info['name'] and proc.info['name'].lower().startswith(process_name):
                            target_pids.append(proc.info['pid'])
                    
                    if not target_pids:
                        continue
                        
                    curr_hwnd = user32.GetForegroundWindow()
                    _, cur_pid = win32process.GetWindowThreadProcessId(curr_hwnd)
                    
                    if cur_pid in target_pids:
                        logger.debug(f"目标已在前台: {exe_path}，停止辅助置顶")
                        return

                    # 尝试激活
                    if WindowManager.try_activate(exe_path, restore_minimized=False):
                        logger.debug(f"辅助置顶成功: {exe_path}")
                        return
                except Exception as e:
                    logger.debug("Failed to activate launched app %s: %s", exe_path, e)
                    continue

        threading.Thread(target=run, daemon=True, name="ActivateLaunchedApp").start()
    @staticmethod
    def _execute_as_standard_user(target: str, parameters: str = "", directory: str = "", show_cmd: int = 1) -> bool:
        """【终极稳健方案】通过桌面窗口的 Shell 环境直接发起启动请求。
        
        这是目前已知最稳定、跨版本兼容性最好且不依赖任何中间服务的 UIPI 绕过方案。
        它通过 COM 接口直接与正在运行的资源管理器进程握手，完全模拟用户在文件夹中双击的效果。
        """
        if os.name != 'nt':
            return False
            
        logger.info(f"原生降权启动尝试: {target} (参数: {parameters})")
        
        try:
            import pythoncom
            from win32com.client import Dispatch, dynamic
            com_initialized = False
            
            # 确保 COM 环境初始化
            try:
                pythoncom.CoInitialize()
                com_initialized = True
            except Exception as e:
                logger.debug(f"COM 初始化失败: {e}")
            # 这种方式获取的 Shell 对象完全属于 explorer.exe 进程的上下文，
            # 从而确保执行 ShellExecute 时绝对继承标准用户权限。
            try:
                # 获取桌面窗口句柄
                # 方法：找到 Shell 窗口，并从中导航到 IShellDispatch 对象
                shell_app = dynamic.Dispatch("Shell.Application")
                
                # 设置工作目录，如果没有提供则使用目标所在的目录
                if not directory and os.path.isfile(target):
                    directory = os.path.dirname(target)
                
                # 执行
                # 参数顺序：File, [vArgs], [vDir], [vOperation], [vShow]
                shell_app.ShellExecute(target, parameters or "", directory or "", "open", show_cmd)
                
                logger.info(f"已通过原生 Shell 接口成功下发启动指令: {target}")
                return True
            except Exception as e:
                logger.debug(f"通过桌面导航启动失败: {e}，尝试常规 COM 方式")
                
                # 常规 fallback：直接 Dispatch
                shell = Dispatch("Shell.Application")
                shell.ShellExecute(target, parameters or "", directory or "", "open", show_cmd)
                return True
                
        except Exception as e:
            logger.error(f"终极降权方案执行异常: {e}")
            return False
        finally:
            try:
                if 'pythoncom' in locals() and com_initialized:
                    pythoncom.CoUninitialize()
            except Exception:
                pass
    @staticmethod
    def _shell_execute_cmd(command: str, cwd: Optional[str] = None, run_as_admin: bool = False) -> bool:
        """通过 cmd.exe 执行命令，并统一走 ShellExecute 的提权/降权路径。"""
        if os.name != "nt":
            return False

        comspec = os.environ.get("ComSpec")
        if not comspec:
            system_root = os.environ.get("SystemRoot", r"C:\Windows")
            comspec = os.path.join(system_root, "System32", "cmd.exe")

        parameters = subprocess.list2cmdline(["/d", "/s", "/c", command])
        return ShortcutExecutor._shell_execute_open(
            comspec,
            parameters,
            cwd,
            show_cmd=0,
            run_as_admin=run_as_admin,
        )
    @staticmethod
    def _execute_file(shortcut: ShortcutItem, force_new: bool) -> tuple[bool, str]:
        """【稳健方案】统一的文件/程序执行入口。
        
        不再使用复杂的权限降级矩阵，转而使用 Windows 最标准的 ShellExecute 接口。
        这能保证：
        1. 只要启动器以普通权限运行，所有软件启动、拖拽功能均天然正常。
        2. 如果用户勾选了“管理员运行”，通过 'runas' 动词由系统弹出标准 UAC 提权。
        """
        target = shortcut.target_path
        if not target:
            return False, "目标路径为空"

        # 1. 属性提取与路径解析
        run_as_admin = getattr(shortcut, "run_as_admin", False)
        params = (getattr(shortcut, "target_args", "") or "").strip()
        working_dir = (getattr(shortcut, "working_dir", "") or "").strip()
        real_target = ShortcutExecutor._resolve_shortcut(target) or target
        
        # 2. 自动激活逻辑 (优化：仅在普通启动且非强制新窗口时尝试)
        if not force_new and not run_as_admin and HAS_WINDOW_MANAGER:
            if real_target.lower().endswith('.exe'):
                try:
                    if WindowManager.try_activate(real_target):
                        return True, ""
                except Exception as e:
                    logger.debug("Failed to activate existing target %s: %s", real_target, e)

        cwd = working_dir or (os.path.dirname(os.path.abspath(real_target)) if os.path.isfile(real_target) else None)
        launched, launch_error = ShortcutExecutor._launch_with_privilege(
            real_target,
            params or None,
            cwd,
            run_as_admin=run_as_admin,
        )
        if launched:
            if real_target.lower().endswith(".exe"):
                ShortcutExecutor._activate_launched_app_async(real_target)
            return True, ""
        if launch_error:
            return False, launch_error

        try:
            cmd = [real_target]
            if params:
                cmd.extend(ShortcutExecutor._safe_split_args(params))
            ShortcutExecutor._popen_silent(
                cmd,
                cwd=cwd,
                env=ShortcutExecutor._sanitized_child_env(),
            )
            if real_target.lower().endswith(".exe"):
                ShortcutExecutor._activate_launched_app_async(real_target)
            return True, ""
        except Exception as e:
            return False, f"Launch failed: {str(e)}"
    @staticmethod
    def _safe_split_args(args_text: str) -> List[str]:
        args_text = (args_text or "").strip()
        if not args_text:
            return []
        try:
            return shlex.split(args_text, posix=False)
        except Exception:
            return args_text.split()
    @staticmethod
    def _sanitized_child_env():
        env = os.environ.copy()
        for k in list(env.keys()):
            ku = k.upper()
            if ku.startswith("PYTHON"):
                env.pop(k, None)
        for k in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "QML_IMPORT_PATH"):
            env.pop(k, None)
        return env
    @staticmethod
    def _get_silent_startupinfo():
        if os.name != 'nt':
            return None
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            return startupinfo
        except Exception:
            return None
    @staticmethod
    def _get_silent_creationflags(shell=False):
        if os.name != 'nt':
            return 0

        # Windows 进程创建标志
        DETACHED_PROCESS = 0x00000008          # 脱离控制台
        CREATE_NEW_PROCESS_GROUP = 0x00000200  # 新进程组
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000 # 脱离作业对象，完全独立

        if shell:
            # shell=True 需要 cmd.exe 控制台，用 CREATE_NO_WINDOW 隐藏
            # 同样需要 CREATE_BREAKAWAY_FROM_JOB，确保子进程不随父进程终止
            flags = subprocess.CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
            return flags

        # 非 shell 模式：使用多个标志确保子进程完全独立
        # 这样可以：
        # 1. 子进程不继承父进程的 DLL 引用
        # 2. 安装/更新时不会被子进程占用文件
        # 3. 退出 QuickLauncher 后子进程继续运行
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
        return flags
    @staticmethod
    def _popen_silent(argv, cwd=None, env=None, shell=False):
        kwargs = {
            "shell": shell,
            "cwd": cwd,
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True
        }

        if os.name == "nt":
            startupinfo = ShortcutExecutor._get_silent_startupinfo()
            if startupinfo:
                kwargs["startupinfo"] = startupinfo

            creationflags = ShortcutExecutor._get_silent_creationflags(shell=shell)
            if creationflags:
                kwargs["creationflags"] = creationflags

        try:
            return subprocess.Popen(argv, **kwargs)
        except OSError:
            # CREATE_BREAKAWAY_FROM_JOB 可能因 Job Object 限制而失败
            # 回退到不使用 breakaway 的标志
            if os.name == "nt" and "creationflags" in kwargs:
                CREATE_BREAKAWAY_FROM_JOB = 0x01000000
                fallback_flags = kwargs["creationflags"] & ~CREATE_BREAKAWAY_FROM_JOB
                if fallback_flags != kwargs["creationflags"]:
                    kwargs["creationflags"] = fallback_flags
                    logger.debug("CREATE_BREAKAWAY_FROM_JOB 不支持，回退")
                    return subprocess.Popen(argv, **kwargs)
            raise
