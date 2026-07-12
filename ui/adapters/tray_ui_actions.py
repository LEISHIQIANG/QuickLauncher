"""Tray-backed implementation of the application UIActions port."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from application.ports.ui_actions import UIAction

logger = logging.getLogger(__name__)


class TrayUIActions:
    def __init__(self, tray: Any) -> None:
        self._callbacks: dict[UIAction, Callable[[], Any]] = {
            UIAction.SHOW_CONFIG_WINDOW: tray.show_config_signal.emit,
            UIAction.QUIT_APP: tray._quit,
            UIAction.RESTART_APP: tray._restart,
            UIAction.SHOW_LOG: tray._show_log,
            UIAction.SHOW_ABOUT: tray._show_about,
            UIAction.SHOW_HELP: tray._show_slash_help,
            UIAction.SHOW_DIAGNOSTICS: tray._show_diagnostics,
            UIAction.SHOW_SHORTCUT_HEALTH: tray._show_shortcut_health,
            UIAction.SHOW_CONFIG_HISTORY: tray._show_config_history,
            UIAction.CLEAN_ICON_CACHE: tray._clean_icon_cache_now,
            UIAction.RELOAD_HOOKS: tray._reload_hooks_now,
            UIAction.OPEN_DATA_DIR: tray._open_data_dir,
            UIAction.OPEN_INSTALL_DIR: tray._open_install_dir,
        }

    def execute(self, action: UIAction) -> bool:
        callback = self._callbacks.get(action)
        if callback is None:
            logger.error("unsupported UI action: %s", action.value)
            return False
        result = callback()
        return result is not False

    def execute_named(self, name: str) -> bool:
        try:
            return self.execute(UIAction(str(name)))
        except ValueError:
            logger.error("unsupported UI action name: %s", name)
            return False
