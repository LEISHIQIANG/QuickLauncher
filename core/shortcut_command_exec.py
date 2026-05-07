"""Command execution helpers for ShortcutExecutor."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import threading
from typing import List

from .data_models import ShortcutItem

logger = logging.getLogger(__name__)
ShortcutExecutor = None


class CommandExecutionMixin:
    @staticmethod
    def _run_silent_output(argv: List[str]) -> str:
        """静默执行命令并获取输出"""
        if os.name != 'nt':
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
                shell=False # 确保不启动 cmd.exe
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
            
        command_type = getattr(shortcut, 'command_type', 'cmd')
        
        # Python 代码执行
        if command_type == 'python':
            show_window = getattr(shortcut, "show_window", False)
            if show_window:
                # 写入临时脚本，用可见窗口的 cmd.exe 运行
                import tempfile
                try:
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                        f.write(command)
                        tmp_path = f.name
                    if os.name == "nt":
                        run_as_admin = getattr(shortcut, "run_as_admin", False)
                        launched, launch_error = ShortcutExecutor._launch_with_privilege(
                            os.environ.get("ComSpec") or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"),
                            subprocess.list2cmdline(["/d", "/s", "/k", f'python "{tmp_path}" & del /f "{tmp_path}"']),
                            None,
                            show_cmd=1,
                            run_as_admin=run_as_admin,
                            admin_failure_message="Administrator launch failed.",
                        )
                        if launched:
                            return True, ""
                        if launch_error:
                            return False, launch_error
                    subprocess.Popen(["python", tmp_path], shell=False)
                    return True, ""
                except Exception as e:
                    return False, f"Python 代码执行失败: {e}"
            try:
                # 提供一些常用的上下文
                context = {
                    'os': os,
                    'sys': sys,
                    'subprocess': subprocess,
                    'time': time,
                    'ctypes': ctypes,
                    'ShortcutExecutor': ShortcutExecutor,
                    'logger': logger,
                    'run_silent': lambda cmd, shell=False: ShortcutExecutor._popen_silent(cmd, shell=shell)
                }
                exec(command, context)
                logger.info("执行Python代码成功")
                return True, ""
            except Exception as e:
                error_msg = f"Python 代码执行失败: {e}"
                logger.error(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                return False, error_msg
                
        # 内置命令
        elif command_type == 'builtin':
            success = ShortcutExecutor._execute_builtin_command(command)
            return success, "" if success else "内置命令执行失败"
            
        # CMD 命令 (默认为 silent)
        else:
            # 兼容旧版本，检查是否是内置命令关键字
            if command_type == 'cmd':
                cmd_lower = command.strip().lower()
                if cmd_lower in ('topmost', '置顶', 'pin', 'toggle_topmost',
                               'topmost_on', '置顶开', 'pin_on',
                               'topmost_off', '置顶关', 'unpin', 'pin_off'):
                    success = ShortcutExecutor._execute_builtin_command(command)
                    return success, "" if success else "内置命令执行失败"

            error_msg = ""
            process = None
            run_as_admin = getattr(shortcut, "run_as_admin", False)
            show_window = getattr(shortcut, "show_window", False)
            show_cmd = 1 if show_window else 0
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
                            parsed,
                            cwd=cwd or exe_dir or None,
                            env=ShortcutExecutor._sanitized_child_env(),
                            shell=False
                        )
                    logger.info(f"执行程序({'Visible' if show_window else 'Silent'}): {exe_path}")
                else:
                    # 对于其他命令，使用 shell=True
                    cwd = (getattr(shortcut, "working_dir", "") or "").strip() or None

                    if os.name == "nt":
                        # show_window 时用 /k 保持窗口，否则用 /c 执行后关闭
                        cmd_flag = "/k" if show_window else "/c"
                        launched, launch_error = ShortcutExecutor._launch_with_privilege(
                            os.environ.get("ComSpec") or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"),
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
                            command,
                            cwd=cwd,
                            env=ShortcutExecutor._sanitized_child_env(),
                            shell=True
                        )
                    logger.info(f"执行命令({'Visible' if show_window else 'Silent'} Shell): {command}")
                    
            except Exception as e:
                error_msg = f"命令启动失败: {e}"
                logger.error(error_msg)
            
            # ===== v2.6.6.0 关键修复：命令执行后恢复焦点 =====
            # 等待命令进程完成或超时（最多等待 2 秒）
            if process is not None:
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    logger.debug("命令进程超时未完成，继续执行焦点恢复")
                except Exception as e:
                    logger.debug(f"等待命令进程时出错: {e}")
            
            # 短暂等待，让系统处理进程结束后的状态变化
            time.sleep(0.05)
            
            # 恢复焦点
            try:
                ShortcutExecutor.restore_foreground_window()
                logger.debug("CMD 命令执行后：已恢复焦点")
            except Exception as e:
                logger.debug(f"CMD 命令执行后恢复焦点失败: {e}")
            
            return (process is not None), error_msg
    @staticmethod
    def _execute_builtin_command(command: str) -> bool:
        """执行内置命令"""
        cmd_lower = command.strip().lower()
        
        # 切换置顶（自动判断当前状态）
        if cmd_lower in ('topmost', '置顶', 'pin', 'toggle_topmost'):
            return ShortcutExecutor._toggle_topmost()
        
        # 强制置顶
        if cmd_lower in ('topmost_on', '置顶开', 'pin_on'):
            return ShortcutExecutor._set_topmost(True)
        
        # 强制取消置顶
        if cmd_lower in ('topmost_off', '置顶关', 'unpin', 'pin_off'):
            return ShortcutExecutor._set_topmost(False)
            
        if cmd_lower in ('show_config', 'show_config_window', 'config_window', '配置窗口'):
            # 使用全局回调机制打开配置窗口
            # 回调绑定到 TrayApp.show_config_signal.emit()
            # Qt 的信号机制保证了跨线程安全，所以可以从任何线程调用
            try:
                from core import has_callback, call_callback
                if has_callback('show_config_window'):
                    call_callback('show_config_window')
                    logger.info("配置窗口: 通过全局回调打开")
                    return True
                else:
                    logger.warning("配置窗口: 回调未注册")
            except Exception as e:
                logger.error(f"配置窗口: 回调调用失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
            
            # 回退到 IPC 方式
            logger.debug("配置窗口: 回退到 IPC 方式")
            return ShortcutExecutor._send_ipc_command_deferred('show_config')


        if cmd_lower == 'open_control_panel':
            if ShortcutExecutor._shell_execute_open("control.exe"):
                return True
            try:
                ShortcutExecutor._popen_silent(["control.exe"], env=ShortcutExecutor._sanitized_child_env())
                return True
            except Exception as e:
                logger.error(f"打开控制面板失败: {e}")
                return False
            
        if cmd_lower == 'open_this_pc':
            if ShortcutExecutor._shell_execute_open("explorer.exe", "shell:MyComputerFolder"):
                return True
            try:
                ShortcutExecutor._popen_silent(
                    ["explorer.exe", "shell:MyComputerFolder"],
                    env=ShortcutExecutor._sanitized_child_env()
                )
                return True
            except Exception as e:
                logger.error(f"打开此电脑失败: {e}")
                return False

        if cmd_lower == 'open_recycle_bin':
            if ShortcutExecutor._shell_execute_open("explorer.exe", "shell:RecycleBinFolder"):
                return True
            try:
                ShortcutExecutor._popen_silent(
                    ["explorer.exe", "shell:RecycleBinFolder"],
                    env=ShortcutExecutor._sanitized_child_env()
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
                import time
                import sys
                is_frozen = getattr(sys, 'frozen', False)
                
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
            from qt_compat import QLocalSocket, QApplication
            import sys
            is_frozen = getattr(sys, 'frozen', False)
            
            # 首次调用时给Qt网络模块和IPC服务器更多初始化时间
            # 这对于打包后的exe在首次使用QLocalSocket尤为重要
            if not hasattr(ShortcutExecutor, '_ipc_initialized'):
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
            success = False
            
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
                        data = command.encode('utf-8')
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
