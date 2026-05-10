"""性能监控模块"""

import time
import functools
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


def performance_monitor(threshold_ms: float = 100) -> Callable:
    """性能监控装饰器

    Args:
        threshold_ms: 性能阈值（毫秒），超过此值将记录警告
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed = (time.perf_counter() - start) * 1000
            if elapsed > threshold_ms:
                logger.warning(f"{func.__name__} took {elapsed:.2f}ms (threshold: {threshold_ms}ms)")
            return result
        return wrapper
    return decorator
