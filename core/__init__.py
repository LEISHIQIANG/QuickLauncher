"""核心模块"""

import importlib
import logging

from .clipboard_classifiers import classify_clipboard as classify_clipboard
from .clipboard_classifiers import classify_text as classify_text
from .data_manager import DataManager as DataManager
from .data_models import DEFAULT_SPECIAL_APPS as DEFAULT_SPECIAL_APPS  # 添加这个
from .data_models import AppData as AppData
from .data_models import AppSettings as AppSettings
from .data_models import Folder as Folder
from .data_models import ShortcutItem as ShortcutItem
from .data_models import ShortcutType as ShortcutType
from .version import APP_VERSION as APP_VERSION

_LAZY_EXPORTS = {
    "ClipboardClassification": ("clipboard_service", "ClipboardClassification"),
    "ClipboardService": ("clipboard_service", "ClipboardService"),
    "clipboard_service": ("clipboard_service", "clipboard_service"),
    "InteractionContext": ("interaction_context", "InteractionContext"),
    "TriggerContext": ("interaction_context", "TriggerContext"),
    "SelectedTextResult": ("selected_text_service", "SelectedTextResult"),
    "SelectedTextService": ("selected_text_service", "SelectedTextService"),
    "selected_text_service": ("selected_text_service", "selected_text_service"),
    "IconExtractor": ("icon_extractor", "IconExtractor"),
    "ShortcutParser": ("shortcut_parser", "ShortcutParser"),
    "ShortcutExecutor": ("shortcut_executor", "ShortcutExecutor"),
    "WindowManager": ("window_manager", "WindowManager"),
    "auto_start_manager": ("auto_start_manager", None),
    "registry": ("command_registry", "CommandRegistry"),
}


def __getattr__(name: str):
    """Lazy: avoids circular import chains through core.__init__."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    # Lazy registry: deferred construction to avoid import-time side effect.
    # IMPORTANT: the singleton registry may be replaced via set_command_registry()
    # by the composition root.  If plugin_manager already owns a registry, prefer it
    # so that plugin-registered commands are visible to settings pages.
    if name == "registry":
        return _get_registry()
    module_name, attr_name = _LAZY_EXPORTS[name]
    try:
        module = importlib.import_module(f".{module_name}", __name__)
        value = module if attr_name is None else getattr(module, attr_name)
    except ImportError:
        value = None
    globals()[name] = value
    return value


# ============================================================
# 命令注册中心 & 全局管理器
# ============================================================
#
# W1 收尾(2026-06-19):全局字符串 callback 字典已删除。
# UI 动作改走 application/ports/ui_actions.UIActions,数据访问改走
# bootstrap.composition_root.build_app_context() 注入的服务。
# 本模块仍保留命令注册中心(registry)与惰性 _LAZY_EXPORTS。
# get_data_manager() / get_plugin_manager() 仅作迁移垫片保留接口,
# 新代码应通过 AppContext 取依赖。

from .command_registry import CommandRegistry

logger = logging.getLogger(__name__)

_registry = None


def set_command_registry(reg: CommandRegistry) -> None:
    """Replace the singleton registry.  Called by the composition root so
    that plugin-registered commands become visible to all consumers of
    ``from core import registry``.

    Also marks the registry as initialized so that
    ``ensure_registry_initialized()`` does not re-register the same
    builtin commands a second time.
    """
    global _registry, _registry_ready
    _registry = reg
    _registry_ready = True


def _get_registry():
    """Internal accessor: returns the lazily-initialized CommandRegistry.
    If plugin_manager has already been injected with its own registry,
    that instance takes priority."""
    global _registry
    if _registry is not None:
        return _registry
    # Fallback: create a standalone instance (used before composition root wires up)
    _registry = CommandRegistry()
    return _registry


plugin_manager = None
data_manager = None


def get_plugin_manager():
    """迁移垫片:新代码应通过 AppContext.plugin_manager 取依赖。"""
    logger.debug("service locator accessed: get_plugin_manager() — prefer AppContext")
    if plugin_manager is None:
        raise RuntimeError("PluginManager 尚未初始化，请先调用 ensure_plugin_manager_initialized()")
    return plugin_manager


def get_data_manager():
    """迁移垫片:新代码应通过 AppContext.data_manager 取依赖。"""
    logger.debug("service locator accessed: get_data_manager() — prefer AppContext")
    if data_manager is None:
        raise RuntimeError("DataManager 尚未初始化，请先调用 set_data_manager()")
    return data_manager


_registry_ready = False


def ensure_registry_initialized():
    """初始化命令注册中心（只执行一次）。"""
    global _registry_ready
    if _registry_ready:
        return
    try:
        reg = _get_registry()
        _register_builtin_commands()
        c1 = reg.migrate_slash_commands()
        c2 = reg.migrate_builtin_aliases()
        total = reg.count()
        _registry_ready = True
        logger.info(
            "命令注册中心初始化完成: %d 条命令 (%d 旧, %d 新)",
            total,
            c1 + c2,
            total - c1 - c2,
        )
    except Exception as e:
        logger.warning("命令注册中心初始化失败：%s", e, exc_info=True)


def ensure_plugin_manager_initialized():
    """初始化插件管理器（只执行一次）。

    Service-locator rationale: PluginManager is constructed here (rather than
    injected from bootstrap) because it must register itself into the command
    registry before bootstrap's composition root finishes wiring the app
    context.  Moving construction to bootstrap would create a circular
    dependency between bootstrap and core.plugin_manager.  New code should
    prefer AppContext.plugin_manager over this module-level accessor.
    """
    global plugin_manager
    if plugin_manager is not None:
        return
    try:
        # Lazy: avoids circular import via core.__init__.
        from .plugin_manager import PluginManager

        plugin_manager = PluginManager(_get_registry())
        plugin_manager.scan_plugins()
        logger.info("插件管理器初始化完成")
    except Exception as e:
        logger.warning("插件管理器初始化失败: %s", e)


def set_data_manager(dm):
    """设置全局 DataManager 实例（仅迁移垫片）。"""
    global data_manager
    data_manager = dm


def _register_builtin_commands():
    """注册所有 Phase 2/3 内置命令到 registry。"""
    # Lazy: avoids circular import via core.__init__.
    from .builtin_command_catalog import PANEL_COMMAND_IDS, build_builtin_command_definitions
    from .command_registry import (
        COMMAND_INTERACTION_DIRECT,
        COMMAND_INTERACTION_PANEL,
        builtin_command_metadata,
    )

    reg = _get_registry()
    count = 0
    for cmd_def in build_builtin_command_definitions():
        cmd_def.metadata = builtin_command_metadata(cmd_def.id, cmd_def.category)
        cmd_def.interaction_mode = (
            COMMAND_INTERACTION_PANEL if cmd_def.id in PANEL_COMMAND_IDS else COMMAND_INTERACTION_DIRECT
        )
        if reg.register(cmd_def):
            count += 1
    if count:
        logger.info("已注册 %d 个 Phase 2/3 内置命令", count)
