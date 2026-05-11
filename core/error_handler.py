"""
统一异常处理工具
提供安全执行函数和装饰器，避免静默忽略异常
"""

import logging
from typing import Callable, TypeVar, Optional, Type, Tuple
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


def safe_execute(
    func: Callable[[], T],
    error_msg: str,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    default: Optional[T] = None,
    log_level: str = "warning"
) -> T:
    """安全执行函数，捕获特定异常

    Args:
        func: 要执行的函数
        error_msg: 错误消息
        exceptions: 要捕获的异常类型
        default: 异常时返回的默认值
        log_level: 日志级别 (debug/info/warning/error)

    Returns:
        函数执行结果或默认值
    """
    try:
        return func()
    except exceptions as e:
        log_func = getattr(logger, log_level)
        log_func(f"{error_msg}: {e}", exc_info=True)
        return default


def safe_method(error_msg: str, default=None, exceptions=(Exception,)):
    """装饰器：安全执行方法

    Args:
        error_msg: 错误消息
        default: 异常时返回的默认值
        exceptions: 要捕获的异常类型
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                logger.warning(f"{error_msg}: {e}", exc_info=True)
                return default
        return wrapper
    return decorator
