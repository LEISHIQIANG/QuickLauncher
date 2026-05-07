"""Tooltip 辅助函数 - 为所有控件添加完美圆角 Tooltip"""

from qt_compat import QWidget, Qt, QCursor, QTimer


def install_tooltip(widget: QWidget, text: str):
    """为控件安装自定义 Tooltip"""
    if not text:
        return

    widget.setToolTip("")  # 禁用默认 tooltip
    widget._tooltip_timer = None

    def on_enter(event):
        # 取消之前的定时器
        if widget._tooltip_timer:
            widget._tooltip_timer.stop()

        # 延迟500ms显示
        widget._tooltip_timer = QTimer()
        widget._tooltip_timer.setSingleShot(True)
        widget._tooltip_timer.timeout.connect(lambda: show_tooltip())
        widget._tooltip_timer.start(500)

        return widget.__class__.enterEvent(widget, event)

    def show_tooltip():
        from ui.custom_tooltip import CustomToolTip
        try:
            from core import DataManager
            dm = DataManager()
            theme = dm.get_settings().theme
        except:
            theme = "dark"

        # 显示时获取当前鼠标位置
        mouse_pos = QCursor.pos()
        CustomToolTip.showToolTip(text, theme, mouse_pos)

    def on_leave(event):
        # 取消定时器
        if widget._tooltip_timer:
            widget._tooltip_timer.stop()

        from ui.custom_tooltip import CustomToolTip
        CustomToolTip.hideToolTip()
        return widget.__class__.leaveEvent(widget, event)

    widget.enterEvent = on_enter
    widget.leaveEvent = on_leave
