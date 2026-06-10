"""Unified custom window chrome helpers."""

from __future__ import annotations

import logging

from qt_compat import QtCompat

logger = logging.getLogger(__name__)


def apply_custom_window_chrome(
    widget,
    *,
    kind: str = "dialog",
    topmost: bool = False,
    translucent: bool = True,
    delete_on_close: bool = False,
    no_shadow: bool = False,
    extra_flags=0,
):
    """Apply the QuickLauncher frameless custom-window contract."""
    try:
        kind_key = str(kind or "dialog").lower()
        if kind_key == "popup":
            flags = QtCompat.Popup
        elif kind_key == "tooltip":
            flags = QtCompat.ToolTip
        elif kind_key == "tool":
            flags = QtCompat.Tool
        elif kind_key == "window":
            flags = QtCompat.Window
        else:
            flags = QtCompat.Dialog
        flags |= QtCompat.FramelessWindowHint
        if topmost:
            flags |= QtCompat.WindowStaysOnTopHint
        if no_shadow:
            flags |= QtCompat.NoDropShadowWindowHint
        if extra_flags:
            flags |= extra_flags
        widget.setWindowFlags(flags)
        if translucent:
            widget.setAttribute(QtCompat.WA_TranslucentBackground, True)
        if delete_on_close:
            widget.setAttribute(QtCompat.WA_DeleteOnClose, True)
        try:
            widget.setAutoFillBackground(False)
        except Exception as exc:
            logger.debug("禁用窗口自动填充背景失败: %s", exc, exc_info=True)
        if not no_shadow:
            try:
                from ui.utils.window_effect import install_win10_window_shadow, is_win10, remove_win10_window_shadow

                if is_win10():
                    install_win10_window_shadow(widget, radius=8)
                else:
                    remove_win10_window_shadow(widget)
            except Exception as exc:
                logger.debug("安装 Win10 自绘窗口阴影失败: %s", exc, exc_info=True)
        return flags
    except Exception as exc:
        logger.debug("应用自定义窗口壳失败: %s", exc, exc_info=True)
        return None
