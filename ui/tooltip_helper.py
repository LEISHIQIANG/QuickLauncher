"""Tooltip 辅助函数 - 为所有控件添加完美圆角 Tooltip"""

import logging

from qt_compat import QCursor, QTimer, QWidget

logger = logging.getLogger(__name__)
_cached_theme = "dark"
_theme_initialized = False


def update_tooltip_theme(theme: str):
    global _cached_theme, _theme_initialized
    _cached_theme = str(theme or "dark")
    _theme_initialized = True


def _get_tooltip_theme() -> str:
    global _cached_theme, _theme_initialized
    if _theme_initialized:
        return _cached_theme
    try:
        from core import DataManager

        _cached_theme = getattr(DataManager().get_settings(), "theme", "dark") or "dark"
    except Exception as exc:
        logger.debug("读取 tooltip 主题失败: %s", exc, exc_info=True)
        _cached_theme = "dark"
    _theme_initialized = True
    return _cached_theme


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
        widget._tooltip_timer = QTimer(widget)
        widget._tooltip_timer.setSingleShot(True)
        widget._tooltip_timer.timeout.connect(lambda: show_tooltip())
        widget._tooltip_timer.start(500)

        return widget.__class__.enterEvent(widget, event)

    def show_tooltip():
        from ui.custom_tooltip import CustomToolTip

        theme = _get_tooltip_theme()

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

    widget.enterEvent = on_enter  # type: ignore[unused-ignore, method-assign]
    widget.leaveEvent = on_leave  # type: ignore[unused-ignore, method-assign]
