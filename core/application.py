"""
应用程序主类
封装全局状态和生命周期管理
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Application:
    """应用程序主类，管理应用生命周期和全局状态"""

    def __init__(self):
        self.tray_app = None
        self.server = None
        self.pending_show_config = False
        self.data_manager = None
        self.qt_app = None

    def get_tray_app(self):
        """获取托盘应用实例"""
        return self.tray_app

    def show_config_window(self) -> bool:
        """显示配置窗口"""
        if self.tray_app is not None:
            try:
                from qt_compat import QTimer
                QTimer.singleShot(0, self.tray_app._show_config)
                return True
            except Exception as e:
                logger.error(f"显示配置窗口失败: {e}")
        return False
