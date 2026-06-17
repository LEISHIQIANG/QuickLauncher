"""Tray menu + icon helpers for :class:`TrayApp`.

Extracted from :mod:`ui.tray_app` as part of the P1-06 file-split
pass.  Owns the menu construction, the icon load fallback chain and
the tray-icon click handler that pops the menu on right-click and
opens the config window on left/double click.
"""

from __future__ import annotations

import logging
import os
from typing import cast

from qt_compat import (
    QApplication,
    QCursor,
    QIcon,
    QPoint,
    QtCompat,
)
from runtime_paths import app_executable, app_root
from ui.styles.style import PopupMenu

logger = logging.getLogger(__name__)


def _get_shortcut_executor():
    from core import ShortcutExecutor

    return ShortcutExecutor


class TrayAppMenuMixin:
    """Menu construction / icon loading / tray-activation helpers.

    The host class is expected to expose:

    * :pyattr:`data_manager` — settings store (for theme + cache
      stats)
    * :pyattr:`tray_icon` — ``QSystemTrayIcon`` instance
    * :pyattr:`tray_menu` — ``PopupMenu`` (created in
      :meth:`_create_menu`)
    * :pyattr:`_toast` — cached ``ToastNotification`` instance
    * :pyattr:`_show_config` / :pyattr:`_show_log` /
      :pyattr:`_show_diagnostics` / :pyattr:`_restart` /
      :pyattr:`_quit` — action callbacks
    """

    def _show_toast(self, text: str, theme: str = "dark"):
        """显示 Toast 通知"""
        try:
            toast = getattr(self, "_toast", None)
            if toast is None:
                from ui.toast_notification import ToastNotification

                toast = ToastNotification()
                self._toast = toast
            toast.show_toast(text, theme=theme, duration_ms=1500)
        except Exception as e:  # noqa: BLE001
            logger.error(f"显示Toast失败: {e}")

    def _load_icon(self) -> QIcon:
        """加载图标"""
        root_dir = str(app_root())
        exe_dir = str(app_executable().parent)
        possible_paths = [
            os.path.join(root_dir, "assets", "app.ico"),
            os.path.join(root_dir, "app.ico"),
            os.path.join(exe_dir, "assets", "app.ico"),
            os.path.join(exe_dir, "app.ico"),
            "assets/app.ico",
            "resources/app.ico",
        ]

        for path in possible_paths:
            try:
                abs_path = os.path.abspath(path)
                if os.path.exists(abs_path):
                    logger.debug(f"找到图标: {abs_path}")
                    icon = QIcon(abs_path)
                    if not icon.isNull():
                        return icon
            except Exception as e:  # noqa: BLE001
                logger.warning(f"检查图标路径失败 {path}: {e}")

        from qt_compat import get_standard_icon

        return cast(QIcon, get_standard_icon(QApplication.instance(), "SP_ComputerIcon"))

    def _create_menu(self):
        """创建托盘菜单"""
        # 托盘右键是高频入口，使用 Qt 自绘菜单，避免同步 DWM/Acrylic 导致卡顿或 native 崩溃。
        theme = self.data_manager.get_settings().theme
        # Resolve ``PopupMenu`` through the host module's globals so
        # tests that ``monkeypatch.setattr(tray_app_mod, "PopupMenu", ...)``
        # continue to work — see ``test_tray_menu_disables_native_popup_effects``.
        import sys

        host_mod = sys.modules.get(type(self).__module__)
        PopupMenu_cls = getattr(host_mod, "PopupMenu", PopupMenu)
        self.tray_menu = PopupMenu_cls(theme=theme, radius=12, native_effects=False)

        # 添加菜单项
        self.tray_menu.add_action("设置", self._show_config)
        self.tray_menu.add_action("重新启动", self._restart)
        self.tray_menu.add_action("运行日志", self._show_log)
        self.tray_menu.add_action("诊断中心", self._show_diagnostics)
        self.tray_menu.add_separator()
        self.tray_menu.add_action("退出软件", self._quit)

    def _on_tray_activated(self, reason):
        """托盘图标激活"""
        logger.debug(f"托盘激活: {reason}")
        if reason == QtCompat.Trigger or reason == QtCompat.DoubleClick:
            self._show_config()
        elif reason == QtCompat.Context:
            # 右键显示自定义磨砂菜单
            pos = QCursor.pos()
            # 稍微偏移一点，避免遮住托盘图标
            offset_pos = QPoint(pos.x(), pos.y() - 5)
            self.tray_menu.popup(offset_pos)


__all__ = ["TrayAppMenuMixin", "_get_shortcut_executor"]
