"""Narrow protocols implemented by infrastructure and presentation adapters."""

from .persistence import (
    BackupStore,
    Clock,
    ConfigRepository,
    ConfigStatePort,
    HistoryStore,
    SaveScheduler,
)
from .platform import AutoStartPort, GlobalHotkeyPort, IconProvider, WindowPort
from .search import SearchPort
from .shell import ShellOpenerPort
from .ui_actions import UIAction, UIActions

__all__ = [
    "AutoStartPort",
    "BackupStore",
    "Clock",
    "ConfigRepository",
    "ConfigStatePort",
    "GlobalHotkeyPort",
    "HistoryStore",
    "IconProvider",
    "SaveScheduler",
    "SearchPort",
    "ShellOpenerPort",
    "UIAction",
    "UIActions",
    "WindowPort",
]
