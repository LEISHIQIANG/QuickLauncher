"""核心模块"""

APP_VERSION = "1.5.6.0"

from .data_models import (
    ShortcutType, ShortcutItem, Folder, AppSettings, AppData,
    DEFAULT_SPECIAL_APPS  # 添加这个
)
from .data_manager import DataManager

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
