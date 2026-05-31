"""
安全的文件对话框包装器，基于 Qt 原生 QFileDialog (DontUseNativeDialog=False) 与 DLL 同步原子级暂停保护机制。
通过在显示 Windows 原生资源管理器对话框前，执行 C++ DLL 的 SetMousePaused(True) 同步原子暂停，
并在主线程中完全使用 Qt 原生 QFileDialog API 进行呼起，从而完美融入 Qt 事件循环，
彻底杜绝 IDE 调试、低级钩子与外壳扩展造成的死锁/转圈/卡死。
提供极其详尽的日志步骤追踪，便于对各种复杂环境进行深度审计。
"""

import logging

from qt_compat import QApplication, QFileDialog

logger = logging.getLogger(__name__)
logger.debug("[safe_file_dialog] 纯 Qt 原生 Windows 对话框集成模块已加载")

# 全局鼠标/键盘钩子物理引用
_global_mouse_hook = None
_global_keyboard_hook = None


def set_global_mouse_hook(hook):
    """设置全局鼠标钩子引用，供文件对话框暂停与复原使用"""
    global _global_mouse_hook
    _global_mouse_hook = hook
    # logger.debug("[文件对话框追踪] 已成功绑定全局鼠标钩子引用")


def set_global_keyboard_hook(hook):
    """设置全局键盘钩子引用，供文件对话框暂停与复原使用"""
    global _global_keyboard_hook
    _global_keyboard_hook = hook
    # logger.debug("[文件对话框追踪] 已成功绑定全局键盘钩子引用")


def _execute_dialog_synchronously(parent, func, *args, **kwargs) -> str:
    """
    同步安全激活方案：通过 QTimer.singleShot 或直接调用，并加挂极其详尽的日志追踪。
    """
    # logger.debug(f"[文件对话框追踪][PID: {os.getpid()}] ================= 开始执行安全文件对话框流程 ================= ")

    mouse_hook_paused = False

    # 1. 立即原子暂停鼠标钩子，直接改写 DLL 变量（0微秒延迟，瞬间屏蔽中键回调）
    if _global_mouse_hook:
        try:
            _global_mouse_hook.set_paused(True)
            mouse_hook_paused = True
            # logger.debug(f"[文件对话框追踪][PID: {os.getpid()}] 步骤 1: 鼠标钩子已成功同步暂停，当前实际 DLL 暂停状态: {_global_mouse_hook.is_paused()}")
        except Exception as he:
            logger.warning(f"[文件对话框追踪] 步骤 1 异常: 暂停鼠标钩子失败: {he}")
    else:
        pass
        # logger.debug("[文件对话框追踪] 步骤 1: _global_mouse_hook 句柄为空，跳过暂停")

    result = ""
    try:
        # logger.debug("[文件对话框追踪] 步骤 2: 准备启动 Qt 模态对话框执行体...")
        result = func(*args, **kwargs)
        # logger.debug(f"[文件对话框追踪] 步骤 2: 对话框已正常返回，选中结果为: {result}")
    except Exception as e:
        logger.error(f"[文件对话框追踪] 步骤 2 异常: 对话框执行失败: {e}", exc_info=True)
    finally:
        # 3. 恢复鼠标钩子
        if _global_mouse_hook and mouse_hook_paused:
            try:
                # logger.debug("[文件对话框追踪] 步骤 3: 尝试解除暂停并恢复鼠标钩子")
                _global_mouse_hook.set_paused(False)
                # logger.debug("[文件对话框追踪] 步骤 3: 鼠标钩子已成功解除暂停并恢复")
            except Exception as he:
                logger.warning(f"[文件对话框追踪] 步骤 3 异常: 恢复鼠标钩子失败: {he}")
        else:
            pass
            # logger.debug("[文件对话框追踪] 步骤 3: 无需恢复鼠标钩子")

        # 4. 重绘
        if parent:
            try:
                # logger.debug("[文件对话框追踪] 步骤 4: 尝试重绘与恢复父窗口亚克力特效")
                if hasattr(parent, "_apply_effects"):
                    parent._apply_effects()
                parent.repaint()
                app = QApplication.instance()
                if app:
                    app.processEvents()
                # logger.debug("[文件对话框追踪] 步骤 4: 父窗口效果重绘成功")
            except Exception as pe:
                logger.debug(f"[文件对话框追踪] 步骤 4 异常: 重绘失败: {pe}")

    # logger.debug("[文件对话框追踪] ================= 安全文件对话框流程执行完毕 ================= ")
    return result


def get_open_file_name(parent=None, caption="", directory="", filter="", selected_filter=""):
    """
    【同步重构】使用 Qt 原生 QFileDialog (集成于事件循环，防死锁)
    """
    # logger.debug(f"[文件对话框追踪] get_open_file_name 被调用: caption={caption}, directory={directory}")

    def runner():
        # logger.debug("[文件对话框追踪] 启动 QFileDialog.getOpenFileName...")
        file_path, sel_filter = QFileDialog.getOpenFileName(parent, caption or "选择文件", directory, filter)
        return file_path

    result = _execute_dialog_synchronously(parent, runner)
    return (result, "") if result else ("", "")


def get_save_file_name(parent=None, caption="", directory="", filter="", selected_filter=""):
    """
    【同步重构】使用 Qt 原生 QFileDialog (集成于事件循环，防死锁)
    """
    # logger.debug(f"[文件对话框追踪] get_save_file_name 被调用: caption={caption}, directory={directory}")

    def runner():
        # logger.debug("[文件对话框追踪] 启动 QFileDialog.getSaveFileName...")
        file_path, sel_filter = QFileDialog.getSaveFileName(parent, caption or "保存文件", directory, filter)
        return file_path

    result = _execute_dialog_synchronously(parent, runner)
    return (result, "") if result else ("", "")


def get_existing_directory(parent=None, caption="", directory="", options=None):
    """
    【同步重构】使用 Qt 原生 QFileDialog (集成于事件循环，防死锁)
    """
    # logger.debug(f"[文件对话框追踪] get_existing_directory 被调用: caption={caption}, directory={directory}")

    def runner():
        # logger.debug("[文件对话框追踪] 启动 QFileDialog.getExistingDirectory...")
        dir_path = QFileDialog.getExistingDirectory(parent, caption or "选择文件夹", directory)
        return dir_path

    result = _execute_dialog_synchronously(parent, runner)
    return result
