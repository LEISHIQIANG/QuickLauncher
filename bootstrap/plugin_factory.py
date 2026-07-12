"""Plugin manager factory owned by the composition root."""

from __future__ import annotations

import logging

from core.command_registry import CommandRegistry
from core.plugin_manager import PluginManager

logger = logging.getLogger(__name__)


def create_plugin_manager(registry: CommandRegistry, data_manager=None, module_registry=None) -> PluginManager | None:
    """Create and initialise the plugin manager.

    ``data_manager`` and ``module_registry`` are accepted for API compatibility
    with earlier versions; PluginManager currently resolves its own plugin
    directory path.  Do NOT remove them — callers in composition_root.py pass
    them unconditionally.

    Returns ``None`` only when the plugin directory is entirely absent (no
    ``plugins/`` on disk).  Individual per-plugin errors during
    ``scan_plugins()`` are logged and skipped — a single bad manifest will NEVER
    take down the entire plugin system.
    """
    try:
        manager = PluginManager(registry)
    except Exception as exc:
        # P0 FIX: PluginManager constructor failure is a hard error — escalate
        # from warning to error so it appears in diagnostics and log viewers.
        logger.error(
            "插件管理器构造失败 — 所有插件将不可用: %s",
            exc,
            exc_info=True,
        )
        return None

    try:
        manager.scan_plugins()
    except Exception as exc:
        # P0 FIX: per-plugin errors are already handled inside scan_plugins(),
        # so a top-level exception here means the plugin directory itself is
        # corrupt or inaccessible.  Log at error level and return a manager
        # with an empty plugin set — this is better than returning None and
        # silently disabling ALL functionality that depends on plugin_manager
        # being not-None (e.g. slash commands registered by plugins).
        logger.error(
            "插件扫描失败 — 插件管理器将以空列表继续运行: %s",
            exc,
            exc_info=True,
        )
        # Return the manager anyway; it is still useful for future
        # install/uninstall operations that repopulate the plugin set.

    logger.info("插件管理器初始化完成 (%d 个插件)", len(getattr(manager, "_plugins", {})))
    return manager
