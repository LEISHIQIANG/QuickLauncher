"""Public style functions — delegates to :mod:`ui.styles.qss`.

All three functions produce byte-for-byte identical output to the original
inline implementations.
"""

from __future__ import annotations

import logging

from ui.utils.ui_scale import scale_qss

from .qss import dialog as _dialog
from .qss import menu as _menu
from .qss.button import get_plain_style as _get_plain_button

logger = logging.getLogger(__name__)


def get_menu_stylesheet(theme: str) -> str:
    """获取菜单样式表"""
    return scale_qss(_menu.get_plain_style(theme))


def get_dialog_stylesheet(theme: str, settings=None) -> str:
    """获取对话框完整样式表"""
    return _dialog.get_dialog_stylesheet(theme, settings=settings)


def get_button_stylesheet(theme: str, settings=None) -> str:
    """获取按钮样式表"""
    base = _get_plain_button(theme)
    return scale_qss(base)
