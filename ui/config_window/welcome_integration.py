"""
新手引导集成模块
"""

import logging
from qt_compat import QTimer

logger = logging.getLogger(__name__)

APP_VERSION = "1.5.6.7"


def show_welcome_if_first_run(parent, data_manager):
    """根据版本号和配置决定是否显示新手引导

    逻辑：
    1. 如果版本号变化（新安装或升级），强制显示欢迎页面
    2. 如果版本号未变化，根据 show_welcome_guide 配置决定
    """
    try:
        settings = data_manager.get_settings()
        current_version = APP_VERSION
        last_version = getattr(settings, 'last_version', '')
        show_welcome = getattr(settings, 'show_welcome_guide', True)

        # 版本变化时强制显示，并重置 show_welcome_guide 为 True
        if last_version != current_version:
            logger.info(f"版本变化: {last_version} -> {current_version}，显示欢迎页面")
            data_manager.update_settings(show_welcome_guide=True, last_version=current_version)
            QTimer.singleShot(300, lambda: _show_welcome(parent, data_manager))
        elif show_welcome:
            logger.info("根据配置显示欢迎页面")
            QTimer.singleShot(300, lambda: _show_welcome(parent, data_manager))
        else:
            logger.info("用户已选择不再显示欢迎页面")
    except Exception as e:
        logger.error(f"显示新手引导失败: {e}")


def _show_welcome(parent, data_manager):
    """显示新手引导对话框"""
    try:
        from ui.welcome_guide import WelcomeGuide
        settings = data_manager.get_settings()
        theme = getattr(settings, 'theme', 'dark')

        guide = WelcomeGuide(parent, theme)
        result = guide.exec_()

        # 保存用户的"不再显示"选择
        show_again = guide.should_show_again()
        data_manager.update_settings(show_welcome_guide=show_again, first_run=False)

        logger.info(f"新手引导完成，用户{'完成' if result else '跳过'}了教程，{'将' if show_again else '不'}再显示")
    except Exception as e:
        logger.error(f"新手引导执行失败: {e}")
