"""URL execution helpers for ShortcutExecutor."""

from __future__ import annotations

import logging
import webbrowser

from .data_models import ShortcutItem

logger = logging.getLogger(__name__)
ShortcutExecutor = None


class UrlExecutionMixin:
    @staticmethod
    def _execute_url(shortcut: ShortcutItem) -> tuple[bool, str]:
        """执行URL类型快捷方式"""
        url = shortcut.url
        if not url:
            logger.warning("URL为空")
            return False, "URL为空"
        
        # 确保URL有协议前缀
        if not url.startswith(('http://', 'https://', 'file://')):
            url = 'https://' + url
        
        try:
            launched, launch_error = ShortcutExecutor._launch_with_privilege(url)
            if launched:
                logger.info(f"打开URL: {url}")
                return True, ""

            if launch_error:
                return False, launch_error

            import webbrowser
            webbrowser.open(url)
            logger.info(f"打开URL: {url}")
            return True, ""
        except Exception as e:
            error_msg = f"打开URL失败: {e}"
            logger.error(error_msg)
            return False, error_msg
