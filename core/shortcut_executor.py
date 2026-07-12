"""
快捷方式执行器
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
from ctypes import wintypes

from .data_models import ShortcutItem, ShortcutType
from .shortcut_command_exec import CommandExecutionMixin
from .shortcut_file_exec import FileExecutionMixin
from .shortcut_hotkey import HotkeyExecutionMixin
from .shortcut_types import (
    shell32,
    user32,
)
from .shortcut_url_exec import UrlExecutionMixin
from .shortcut_window_control import WindowControlMixin

logger = logging.getLogger(__name__)
STANDARD_USER_LAUNCH_FAILED_MESSAGE = (
    "QuickLauncher 当前以管理员权限运行，且降权启动失败。"
    "请先以普通权限启动 QuickLauncher，或为该项目显式勾选“以管理员身份运行”。"
)

# ===== 配置 user32 函数签名（仅限本模块特有的函数） =====
user32.SetWindowPos.argtypes = [
    wintypes.HWND,  # hWnd
    wintypes.HWND,  # hWndInsertAfter
    ctypes.c_int,  # X
    ctypes.c_int,  # Y
    ctypes.c_int,  # cx
    ctypes.c_int,  # cy
    ctypes.c_uint,  # uFlags
]
user32.SetWindowPos.restype = wintypes.BOOL

user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL

user32.GetDesktopWindow.argtypes = []
user32.GetDesktopWindow.restype = wintypes.HWND

user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND

shell32.ShellExecuteW.argtypes = [
    wintypes.HWND,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    ctypes.c_int,
]
shell32.ShellExecuteW.restype = wintypes.HINSTANCE


class ShortcutExecutor(
    HotkeyExecutionMixin, FileExecutionMixin, UrlExecutionMixin, CommandExecutionMixin, WindowControlMixin
):
    """快捷方式执行器"""

    # 记录弹窗显示前的前台窗口
    _previous_hwnd = None
    _previous_hwnd_process_id = None
    _foreground_window_lock = threading.RLock()
    _hotkey_lock = threading.Lock()
    _hotkey_lock_timeout = 2.0

    # 当前活跃的 LauncherPopup HWND 集合，用于在 save_foreground_window 中
    # 精确区分弹窗自身与配置窗口等其他 QuickLauncher 窗口，避免配置窗口
    # 被错误地排除在"恢复目标"之外。
    _popup_hwnds: set[int] = set()

    _ui_actions = None

    @classmethod
    def configure_services(cls, *, data_manager=None, ui_actions=None) -> None:
        """Inject process-owned execution dependencies from the composition root."""
        if data_manager is not None:
            from core import set_data_manager

            set_data_manager(data_manager)
        cls._ui_actions = ui_actions

    @classmethod
    def resolve_ui_actions(cls):
        """Return the injected UIActions port, or None if not yet wired."""
        return cls._ui_actions

    # ===== POINT 结构体（用于获取鼠标位置）=====
    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    @staticmethod
    def execute(shortcut: ShortcutItem, force_new: bool = False) -> tuple[bool, str]:
        """执行快捷方式

        Returns:
            tuple[bool, str]: (是否成功, 错误消息)
        """
        try:
            if getattr(shortcut, "run_as_admin", False):
                logger.info(
                    "Shortcut admin audit: shortcut=%s type=%s target=%s",
                    getattr(shortcut, "name", "") or getattr(shortcut, "id", ""),
                    getattr(getattr(shortcut, "type", ""), "value", getattr(shortcut, "type", "")),
                    getattr(shortcut, "target_path", "")
                    or getattr(shortcut, "url", "")
                    or getattr(shortcut, "command", ""),
                )
            if shortcut.type == ShortcutType.HOTKEY:
                # 快捷键执行：已经在内部处理了线程，这里返回状态
                # 注意：快捷键执行通常是异步的，错误可能无法立即捕获
                success = ShortcutExecutor._execute_hotkey_safe(shortcut)
                return success, "" if success else "快捷键执行失败"

            elif shortcut.type == ShortcutType.URL:
                return ShortcutExecutor._execute_url(shortcut)

            elif shortcut.type == ShortcutType.COMMAND:
                # 命令执行：有些是内置命令，有些是系统命令
                return ShortcutExecutor._execute_command(shortcut)

            elif shortcut.type == ShortcutType.BATCH_LAUNCH:
                from core.batch_launch_exec import execute_batch_launch

                try:
                    from core import data_manager as global_data_manager
                except Exception:
                    global_data_manager = None
                result = execute_batch_launch(shortcut, global_data_manager)
                return bool(result.success), result.error or ""

            elif shortcut.type == ShortcutType.MACRO:
                return ShortcutExecutor._execute_macro(shortcut)

            else:
                # 文件/文件夹执行
                return ShortcutExecutor._execute_file(shortcut, force_new)

        except Exception as e:
            error_msg = str(e)
            logger.exception("执行快捷方式失败")
            return False, error_msg

    @staticmethod
    def execute_with_files(shortcut: ShortcutItem, files: list[str]) -> bool:
        """使用快捷方式打开指定文件列表

        将拖放的文件作为参数传递给快捷方式对应的程序打开。

        Args:
            shortcut: 快捷方式项（必须是 FILE 或 FOLDER 类型）
            files: 要打开的文件路径列表

        Returns:
            bool: 是否执行成功
        """
        if not files:
            logger.warning("没有要打开的文件")
            return False

        if shortcut.type not in (ShortcutType.FILE, ShortcutType.FOLDER):
            logger.warning(f"不支持的快捷方式类型用于拖放: {shortcut.type}")
            return False

        target = shortcut.target_path

        if not target:
            logger.warning("目标路径为空")
            return False

        # 解析快捷方式文件获取真实目标
        real_target = ShortcutExecutor._resolve_shortcut(target)

        if not real_target or not os.path.exists(real_target):
            logger.warning(f"目标不存在: {target} -> {real_target}")
            return False

        logger.info(f"拖放执行: {shortcut.name}, 目标: {real_target}, 文件数: {len(files)}")

        success = True
        run_as_admin = getattr(shortcut, "run_as_admin", False)

        # 判断目标类型
        if os.path.isdir(real_target):
            # 目标是文件夹：在资源管理器中打开并选中文件，或复制文件到该文件夹
            success = ShortcutExecutor._open_folder_with_files(real_target, files, run_as_admin=run_as_admin)
        elif real_target.lower().endswith(".exe"):
            # 目标是可执行文件：将所有文件作为参数传递
            success = ShortcutExecutor._open_exe_with_files(
                real_target,
                files,
                shortcut.target_args,
                getattr(shortcut, "working_dir", "") or "",
                run_as_admin=run_as_admin,
            )
        else:
            # 其他文件类型（如 .lnk 快捷方式本身指向程序）
            success = ShortcutExecutor._open_file_with_files(real_target, files, run_as_admin=run_as_admin)

        return success

    @staticmethod
    def _execute_macro(shortcut: ShortcutItem) -> tuple[bool, str]:
        """执行宏录制：将已录制的事件回放到系统。

        使用统一的 InputMacroBackend，确保与诊断、测试播放使用同一套回放通道。

        P0 FIX (2026-06-26):  The previous implementation always returned
        ``(True, "")`` regardless of the macro outcome.  The background
        thread's return value was silently discarded by
        ``start_background_thread()``.  We now capture the result via a
        shared container + ``threading.Event`` and join the thread with a
        generous timeout, so the caller receives the real success/failure
        status and error message.
        """
        events = list(getattr(shortcut, "macro_events", []) or [])
        if not events:
            return False, "宏内容为空"

        try:
            from hooks.input_macro import InputMacroBackend
        except Exception as exc:
            logger.error("宏回放失败：无法导入 InputMacroBackend: %s", exc)
            return False, f"宏回放模块不可用: {exc}"

        speed = float(getattr(shortcut, "macro_speed", 1.0) or 1.0)
        if speed <= 0:
            speed = 1.0

        trigger_mode = getattr(shortcut, "trigger_mode", "immediate")

        result_container: list[tuple[bool, str]] = []
        done_event = threading.Event()

        def _do():
            try:
                if trigger_mode == "after_close":
                    target_hwnd = ShortcutExecutor._previous_hwnd
                    time.sleep(0.150)
                    ShortcutExecutor.restore_foreground_window_fast(timeout_ms=300)
                    if target_hwnd:
                        for attempt in range(6):
                            try:
                                if user32.GetForegroundWindow() == target_hwnd:
                                    break
                            except Exception as exc:
                                logger.debug("宏回放前检测前台窗口失败: %s", exc, exc_info=True)
                                break
                            if attempt < 5:
                                time.sleep(0.050)
                    # Give the restored target one more message-pump turn before the first macro event.
                    time.sleep(0.250)
                backend = InputMacroBackend()
                ok = backend.play(events=events, speed=speed)
                result_container.append((bool(ok), "" if ok else "宏播放失败"))
            except Exception as exc:
                logger.exception("宏播放异常")
                result_container.append((False, str(exc)))
            finally:
                done_event.set()

        from .background_tasks import start_background_thread

        start_background_thread(
            name=f"ShortcutExecutor.macro.{shortcut.id}",
            target=_do,
            owner="ShortcutExecutor.macro",
        )

        # Calculate a reasonable timeout: base 5s + 1s per 100 events
        timeout = max(5.0, 5.0 + len(events) / 100.0 * speed)
        if not done_event.wait(timeout=timeout):
            logger.error(
                "宏播放超时: shortcut=%s events=%d speed=%.1f timeout=%.1fs",
                getattr(shortcut, "id", shortcut.name),
                len(events),
                speed,
                timeout,
            )
            return False, "宏播放超时"

        if not result_container:
            return False, "宏播放未返回结果"
        return result_container[0]

    # ===== 窗口置顶功能（已修复）=====


def _bind_shortcut_executor_mixins():
    from . import shortcut_command_exec, shortcut_file_exec, shortcut_hotkey, shortcut_url_exec, shortcut_window_control

    for module in (
        shortcut_command_exec,
        shortcut_file_exec,
        shortcut_hotkey,
        shortcut_url_exec,
        shortcut_window_control,
    ):
        module.ShortcutExecutor = ShortcutExecutor  # type: ignore[attr-defined]


_bind_shortcut_executor_mixins()
