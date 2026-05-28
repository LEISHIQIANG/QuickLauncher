"""核心模块"""

from .data_manager import DataManager as DataManager
from .data_models import DEFAULT_SPECIAL_APPS as DEFAULT_SPECIAL_APPS  # 添加这个
from .data_models import AppData as AppData
from .data_models import AppSettings as AppSettings
from .data_models import Folder as Folder
from .data_models import ShortcutItem as ShortcutItem
from .data_models import ShortcutType as ShortcutType
from .clipboard_classifiers import classify_clipboard as classify_clipboard
from .clipboard_classifiers import classify_text as classify_text
from .clipboard_service import (
    ClipboardClassification as ClipboardClassification,
    ClipboardService as ClipboardService,
    clipboard_service as clipboard_service,
)
from .interaction_context import InteractionContext as InteractionContext
from .interaction_context import TriggerContext as TriggerContext
from .selected_text_service import SelectedTextResult as SelectedTextResult
from .selected_text_service import SelectedTextService as SelectedTextService
from .selected_text_service import selected_text_service as selected_text_service
from .version import APP_VERSION as APP_VERSION

# 可选模块
try:
    from .icon_extractor import IconExtractor
except ImportError:
    IconExtractor = None

try:
    from .shortcut_parser import ShortcutParser
except ImportError:
    ShortcutParser = None

try:
    from .shortcut_executor import ShortcutExecutor
except ImportError:
    ShortcutExecutor = None

try:
    from .window_manager import WindowManager
except ImportError:
    WindowManager = None


# 自启动管理器（优化开机启动速度）
try:
    from . import auto_start_manager
except ImportError:
    auto_start_manager = None


# ============================================================
# 全局回调注册机制
# 用于跨模块通信，解决打包版本中模块导入问题
# ============================================================

# 全局回调存储
_callbacks = {}


def register_callback(name: str, callback):
    """注册全局回调函数

    Args:
        name: 回调名称，如 'show_config_window'
        callback: 回调函数
    """
    _callbacks[name] = callback


def call_callback(name: str, *args, **kwargs):
    """调用已注册的回调函数

    Args:
        name: 回调名称
        *args, **kwargs: 传递给回调函数的参数

    Returns:
        回调函数的返回值，如果回调不存在则返回 None
    """
    import logging

    logger = logging.getLogger(__name__)

    callback = _callbacks.get(name)
    if callback is not None:
        try:
            logger.debug(f"执行回调: {name}")
            result = callback(*args, **kwargs)
            logger.debug(f"回调执行完成: {name}")
            return result
        except Exception as e:
            logger.error(f"回调执行失败 {name}: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return None
    else:
        logger.warning(f"回调未找到: {name}")
    return None


def has_callback(name: str) -> bool:
    """检查回调是否已注册

    Args:
        name: 回调名称

    Returns:
        bool: 回调是否存在
    """
    return name in _callbacks


# ============================================================
# 命令注册中心 & 全局管理器
# ============================================================

from .command_registry import CommandRegistry

logger = __import__("logging").getLogger(__name__)

registry = CommandRegistry()
_registry_initialized = False

plugin_manager = None
data_manager = None


def ensure_registry_initialized():
    """初始化命令注册中心（只执行一次）。"""
    global _registry_initialized
    if _registry_initialized:
        return
    try:
        _register_builtin_commands()
        c1 = registry.migrate_slash_commands()
        c2 = registry.migrate_builtin_aliases()
        total = registry.count()
        _registry_initialized = True
        logger.info(
            "命令注册中心初始化完成: %d 条命令 (%d 旧, %d 新)",
            total,
            c1 + c2,
            total - c1 - c2,
        )
    except Exception as e:
        logger.warning("命令注册中心初始化失败：%s", e, exc_info=True)


def ensure_plugin_manager_initialized():
    """初始化插件管理器（只执行一次）。"""
    global plugin_manager
    if plugin_manager is not None:
        return
    try:
        from .plugin_manager import PluginManager

        plugin_manager = PluginManager(registry)
        plugin_manager.scan_plugins()
        logger.info("插件管理器初始化完成")
    except Exception as e:
        logger.warning("插件管理器初始化失败: %s", e)


def set_data_manager(dm):
    """设置全局 DataManager 实例。"""
    global data_manager
    data_manager = dm


def _register_builtin_commands():
    """注册所有 Phase 2/3 内置命令到 registry。"""
    from .builtin_command_catalog import PANEL_COMMAND_IDS, build_builtin_command_definitions
    from .command_registry import (
        COMMAND_INTERACTION_DIRECT,
        COMMAND_INTERACTION_PANEL,
        builtin_command_metadata,
    )

    count = 0
    for cmd_def in build_builtin_command_definitions():
        cmd_def.metadata = builtin_command_metadata(cmd_def.id, cmd_def.category)
        cmd_def.interaction_mode = (
            COMMAND_INTERACTION_PANEL if cmd_def.id in PANEL_COMMAND_IDS else COMMAND_INTERACTION_DIRECT
        )
        if registry.register(cmd_def):
            count += 1
    if count:
        logger.info("已注册 %d 个 Phase 2/3 内置命令", count)
