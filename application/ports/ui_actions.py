"""Strongly typed presentation actions requested by application commands."""

from __future__ import annotations

from enum import Enum
from typing import Protocol


class UIAction(str, Enum):
    SHOW_CONFIG_WINDOW = "show_config_window"
    QUIT_APP = "quit_app"
    RESTART_APP = "restart_app"
    SHOW_LOG = "show_log"
    SHOW_ABOUT = "show_about"
    SHOW_HELP = "show_help"
    SHOW_DIAGNOSTICS = "show_diagnostics"
    SHOW_SHORTCUT_HEALTH = "show_shortcut_health"
    SHOW_CONFIG_HISTORY = "show_config_history"
    CLEAN_ICON_CACHE = "clean_icon_cache"
    RELOAD_HOOKS = "reload_hooks"
    OPEN_DATA_DIR = "open_data_dir"
    OPEN_INSTALL_DIR = "open_install_dir"

    @classmethod
    def parse(cls, value: str) -> UIAction | None:
        try:
            return cls(value)
        except ValueError:
            return None


class UIActions(Protocol):
    def execute(self, action: UIAction) -> bool: ...
