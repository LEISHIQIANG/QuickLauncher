"""HWND registration / focus restoration helpers for :class:`LauncherPopup`.

Extracted from :mod:`ui.launcher_popup.popup_window` as part of the
P1-06 file-split pass.  Owns the ``_register_popup_hwnd`` /
``_unregister_popup_hwnd`` calls that ``showEvent`` / ``hideEvent``
need, plus the focus / modifier-key cleanup.

The mixin relies on the ``HAS_EXECUTOR`` flag and ``ShortcutExecutor``
class that the host module (``ui.launcher_popup.popup_window``)
defines as module-level globals.  They are resolved lazily via
:func:`_get_executor` so the mixin does not need to duplicate the
conditional import logic and stays importable in isolation.
"""

from __future__ import annotations

import logging
from typing import Any, cast

logger = logging.getLogger(__name__)


def _get_executor():
    """Return ``(has_executor, executor_class)`` or ``(False, None)``.

    The lookup mirrors the conditional import in
    :mod:`ui.launcher_popup.popup_window` so the mixin stays
    functional on hosts where the native executor is unavailable.
    """
    try:
        from core import ShortcutExecutor

        return True, ShortcutExecutor
    except ImportError:  # noqa: BLE001
        return False, None


class PopupWindowHwndMixin:
    """Owns the popup HWND registration / focus restoration plumbing.

    The host class is expected to expose the
    ``HAS_EXECUTOR`` / ``ShortcutExecutor`` module-level symbols —
    the actual implementation gates on ``HAS_EXECUTOR`` so the
    helpers are no-ops on platforms / build configs that lack the
    native executor.
    """

    def _restore_focus_safe(self):
        """安全地恢复之前的前台窗口焦点"""
        try:
            has_executor, executor_cls = _get_executor()
            if has_executor and executor_cls is not None:
                executor_cls.restore_foreground_window()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"恢复焦点失败: {e}")

    def _current_popup_hwnd(self) -> int:
        """获取当前弹窗的 Win32 HWND（若尚未创建则返回 0）"""
        try:
            has_executor, _ = _get_executor()
            if not has_executor:
                return 0
            return int(cast(Any, self).winId() or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _register_popup_hwnd(self) -> None:
        """在 showEvent 中调用：将自身 HWND 注册到 ShortcutExecutor 的弹窗注册表。"""
        has_executor, executor_cls = _get_executor()
        if not has_executor or executor_cls is None:
            return
        try:
            hwnd = self._current_popup_hwnd()
            if hwnd:
                executor_cls.register_popup_hwnd(hwnd)
        except Exception as exc:  # noqa: BLE001
            logger.debug("注册弹窗HWND失败: %s", exc, exc_info=True)

    def _unregister_popup_hwnd(self) -> None:
        """在 hideEvent/closeEvent 中调用：从注册表中移除自身 HWND。"""
        has_executor, executor_cls = _get_executor()
        if not has_executor or executor_cls is None:
            return
        try:
            hwnd = self._current_popup_hwnd()
            if hwnd:
                executor_cls.unregister_popup_hwnd(hwnd)
        except Exception as exc:  # noqa: BLE001
            logger.debug("取消注册弹窗HWND失败: %s", exc, exc_info=True)

    def _release_residual_modifiers(self):
        """释放残留的修饰键

        v2.6.6.0 新增：
        弹窗显示时调用，释放可能由全局热键遗留的修饰键状态
        """
        try:
            has_executor, executor_cls = _get_executor()
            if has_executor and executor_cls is not None:
                executor_cls._pre_execution_cleanup()
                logger.debug("弹窗显示：已清理残留修饰键")
        except Exception as e:  # noqa: BLE001
            logger.debug(f"释放残留修饰键失败: {e}")


__all__ = ["PopupWindowHwndMixin"]
