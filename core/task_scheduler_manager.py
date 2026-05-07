"""
任务计划程序自启动管理器

使用 Windows 任务计划程序实现快速开机自启，比注册表 Run 键快 5-10 秒。

优势：
- 启动时机更早（用户登录时立即触发，不等桌面加载）
- 可设置延迟启动（避免开机卡顿）
- 可设置最高权限运行
- 用户可在任务计划程序中查看和管理
"""

from __future__ import annotations

import sys
import os
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "QuickLauncher"
TASK_NAME = f"{APP_NAME}_AutoStart"


def _is_frozen() -> bool:
    """是否为打包后的 exe 环境（支持 PyInstaller 和 Nuitka）"""
    if getattr(sys, 'frozen', False):
        return True
    if "__compiled__" in globals():
        return True
    exe_name = os.path.basename(sys.executable).lower()
    if exe_name not in ('python.exe', 'pythonw.exe', 'python', 'pythonw') and exe_name.endswith('.exe'):
        return True
    return False


def _get_exe_path() -> str:
    """Nuitka standalone 下 sys.executable 可能是内嵌 python.exe，需要修正"""
    exe = sys.executable

    if 'python' in os.path.basename(exe).lower():
        if sys.argv and sys.argv[0].lower().endswith('.exe'):
            candidate = os.path.abspath(sys.argv[0])
            if os.path.isfile(candidate):
                return candidate
        app_exe = os.path.join(os.path.dirname(os.path.abspath(exe)), f'{APP_NAME}.exe')
        if os.path.isfile(app_exe):
            return app_exe

    if not os.path.isabs(exe):
        exe = os.path.abspath(exe)
    return exe


def _run_schtasks(args: list[str]) -> tuple[bool, str]:
    """执行 schtasks 命令"""
    try:
        result = subprocess.run(
            ["schtasks"] + args,
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore',
            timeout=5
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def enable_task_scheduler(delay_seconds: int = 3) -> bool:
    """启用任务计划程序自启动

    Args:
        delay_seconds: 登录后延迟启动秒数（0-10秒，避免开机卡顿）
    """
    if not _is_frozen():
        logger.debug("开发模式，跳过任务计划程序设置")
        return False

    exe_path = _get_exe_path()
    if not os.path.isfile(exe_path):
        logger.warning(f"exe 不存在: {exe_path}")
        return False

    # 先删除旧任务
    _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"])

    # 创建新任务
    delay = max(0, min(10, delay_seconds))
    args = [
        "/Create",
        "/TN", TASK_NAME,
        "/TR", f'"{exe_path}"',
        "/SC", "ONLOGON",  # 登录时触发
        "/DELAY", f"0000:00:{delay:02d}",  # 延迟 N 秒
        "/RL", "HIGHEST",  # 最高权限
        "/F"  # 强制创建
    ]

    success, output = _run_schtasks(args)
    if success:
        logger.info(f"任务计划程序自启动已创建（延迟 {delay}s）")
        return True
    else:
        logger.error(f"创建任务失败: {output}")
        return False


def disable_task_scheduler() -> bool:
    """禁用任务计划程序自启动"""
    success, output = _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    if success or "找不到" in output or "not found" in output.lower():
        logger.info("任务计划程序自启动已删除")
        return True
    logger.error(f"删除任务失败: {output}")
    return False


def is_task_scheduler_enabled() -> bool:
    """检查任务计划程序自启动是否启用"""
    success, output = _run_schtasks(["/Query", "/TN", TASK_NAME])
    return success and TASK_NAME in output
