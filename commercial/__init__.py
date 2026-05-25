"""QuickLauncher 商业功能模块。"""

import logging

_initialized = False


def init_commercial():
    global _initialized
    if _initialized:
        return
    _initialized = True
    logger = logging.getLogger(__name__)
    logger.debug("商业模块初始化完成")
