"""
安全的文件对话框包装器，基于原生系统文件选择对话框与钩子暂停保护机制。

显示文件对话框前会暂停全局鼠标钩子，退出后恢复并重绘父窗口。文件选择本身使用
系统原生资源管理器对话框，避免配置导入/导出等入口出现 Qt 自绘文件框。
"""

import logging

from hooks.hook_pause import mouse_hook_paused
from qt_compat import QApplication, QFileDialog

logger = logging.getLogger(__name__)
logger.debug("[safe_file_dialog] 原生系统文件对话框集成模块已加载")

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


def _execute_dialog_synchronously(parent, func, *args, **kwargs):
    """
    同步安全激活方案：通过 QTimer.singleShot 或直接调用，并加挂极其详尽的日志追踪。
    """
    # logger.debug(f"[文件对话框追踪][PID: {os.getpid()}] ================= 开始执行安全文件对话框流程 ================= ")

    result = ""
    with mouse_hook_paused(_global_mouse_hook, log_label="文件对话框鼠标钩子"):
        try:
            # logger.debug("[文件对话框追踪] 步骤 2: 准备启动 Qt 模态对话框执行体...")
            result = func(*args, **kwargs)
            # logger.debug(f"[文件对话框追踪] 步骤 2: 对话框已正常返回，选中结果为: {result}")
        except Exception as e:
            logger.error(f"[文件对话框追踪] 步骤 2 异常: 对话框执行失败: {e}", exc_info=True)

    if parent:
        try:
            # logger.debug("[文件对话框追踪] 步骤 4: 尝试重绘与恢复父窗口亚克力特效")
            if hasattr(parent, "_apply_effects"):
                parent._apply_effects()
            parent.update()
            app = QApplication.instance()
            if app:
                app.processEvents()
            # logger.debug("[文件对话框追踪] 步骤 4: 父窗口效果重绘成功")
        except Exception as pe:
            logger.debug(f"[文件对话框追踪] 步骤 4 异常: 重绘失败: {pe}")

    # logger.debug("[文件对话框追踪] ================= 安全文件对话框流程执行完毕 ================= ")
    return result


def _native_dialog_options(options=None):
    """返回不含 DontUseNativeDialog 的 QFileDialog 选项。"""
    if options is None:
        return QFileDialog.Options()
    try:
        return QFileDialog.Options(options & ~QFileDialog.DontUseNativeDialog)
    except Exception as exc:
        logger.debug("清理文件对话框选项失败: %s", exc, exc_info=True)
        return QFileDialog.Options()


def get_open_file_name(parent=None, caption="", directory="", filter="", selected_filter=""):
    """
    使用原生系统打开文件对话框，并在显示期间暂停全局鼠标钩子。
    """
    # logger.debug(f"[文件对话框追踪] get_open_file_name 被调用: caption={caption}, directory={directory}")

    def runner():
        return QFileDialog.getOpenFileName(
            parent,
            caption or "选择文件",
            directory,
            filter,
            selected_filter,
            _native_dialog_options(),
        )

    result = _execute_dialog_synchronously(parent, runner)
    return result if isinstance(result, tuple) else ("", "")


def get_save_file_name(parent=None, caption="", directory="", filter="", selected_filter=""):
    """
    使用原生系统保存文件对话框，并在显示期间暂停全局鼠标钩子。
    """
    # logger.debug(f"[文件对话框追踪] get_save_file_name 被调用: caption={caption}, directory={directory}")

    def runner():
        return QFileDialog.getSaveFileName(
            parent,
            caption or "保存文件",
            directory,
            filter,
            selected_filter,
            _native_dialog_options(),
        )

    result = _execute_dialog_synchronously(parent, runner)
    return result if isinstance(result, tuple) else ("", "")


def get_existing_directory(parent=None, caption="", directory="", options=None):
    """
    使用原生系统选择文件夹对话框，并在显示期间暂停全局鼠标钩子。
    """
    # logger.debug(f"[文件对话框追踪] get_existing_directory 被调用: caption={caption}, directory={directory}")

    def runner():
        dialog_options = _native_dialog_options(options) | QFileDialog.ShowDirsOnly
        return QFileDialog.getExistingDirectory(
            parent,
            caption or "选择文件夹",
            directory,
            dialog_options,
        )

    result = _execute_dialog_synchronously(parent, runner)
    return result
