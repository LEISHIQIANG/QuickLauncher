"""Plugin manager factory owned by the composition root."""

from __future__ import annotations

import logging

from core.command_registry import CommandRegistry
from core.plugin_manager import PluginManager

logger = logging.getLogger(__name__)


def create_plugin_manager(registry: CommandRegistry, data_manager, module_registry=None) -> PluginManager | None:
    try:
        manager = PluginManager(
            registry,
        )
        manager.scan_plugins()
        logger.info("插件管理器初始化完成")
        return manager
    except Exception as exc:
        logger.warning("插件管理器初始化失败: %s", exc, exc_info=True)
        return None
