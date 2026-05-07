"""
对话框居中辅助函数
确保所有对话框都居中在主窗口（ConfigWindow）中
"""

from qt_compat import QWidget


def center_dialog_on_main_window(dialog: QWidget):
    """
    将对话框居中在主窗口（ConfigWindow）中

    Args:
        dialog: 要居中的对话框
    """
    if not dialog:
        return

    parent = dialog.parent()
    if not parent:
        return

    # 找到顶级窗口（ConfigWindow）
    # window() 方法会返回顶级窗口，即使 parent 是子组件
    top_window = parent.window()
    if not top_window:
        return

    # 获取主窗口的几何信息
    main_geo = top_window.geometry()
    dialog_size = dialog.size()

    # 计算居中位置
    x = main_geo.x() + (main_geo.width() - dialog_size.width()) // 2
    y = main_geo.y() + (main_geo.height() - dialog_size.height()) // 2

    # 移动对话框到居中位置
    dialog.move(int(x), int(y))


def get_main_window(widget: QWidget):
    """
    获取主窗口（ConfigWindow）

    Args:
        widget: 任意子组件

    Returns:
        主窗口对象，如果找不到则返回 None
    """
    if not widget:
        return None

    parent = widget.parent()
    if not parent:
        return None

    return parent.window()
