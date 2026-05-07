"""
Autostart compatibility facade.

The old Windows-service based autostart path is deprecated.  This module keeps
the historical public functions used by CLI flags and older callers, while
delegating current behavior to ``auto_start_manager``.
"""

import logging

logger = logging.getLogger(__name__)


def enable_service_autostart():
    """Enable autostart using the current autostart manager."""
    try:
        from core.auto_start_manager import enable_auto_start

        success, method = enable_auto_start()
        if success:
            return True, f"自启动已启用（{method}）"
        return False, "自启动启用失败"
    except Exception as e:
        logger.debug("enable_service_autostart failed: %s", e)
        return False, f"启用失败: {e}"


def disable_service_autostart():
    """Disable autostart and clean up any legacy Windows service."""
    try:
        from core.auto_start_manager import disable_auto_start

        disable_auto_start()
        _cleanup_legacy_service()
        return True, "自启动已禁用"
    except Exception as e:
        logger.debug("disable_service_autostart failed: %s", e)
        return False, f"禁用失败: {e}"


def is_service_enabled():
    """Return whether autostart is enabled."""
    try:
        from core.auto_start_manager import is_auto_start_enabled

        return is_auto_start_enabled()
    except Exception as e:
        logger.debug("is_service_enabled failed: %s", e)
        return False


def get_autostart_status():
    """Return normalized autostart status for settings and diagnostics."""
    status = {
        "enabled": False,
        "method": "none",
        "task_scheduler_enabled": False,
        "registry_enabled": False,
        "service_installed": False,
        "service_running": False,
    }

    try:
        from core.auto_start_manager import (
            get_auto_start_method,
            is_auto_start_enabled,
            is_task_scheduler_enabled,
        )
        from core.auto_start_manager import _read_registry_value

        status["enabled"] = bool(is_auto_start_enabled())
        status["method"] = get_auto_start_method()
        status["task_scheduler_enabled"] = bool(is_task_scheduler_enabled())
        status["registry_enabled"] = _read_registry_value() is not None
    except Exception as e:
        logger.debug("get_autostart_status current manager check failed: %s", e)

    try:
        from core.windows_service import is_service_installed, is_service_running

        status["service_installed"] = bool(is_service_installed())
        status["service_running"] = bool(is_service_running())
    except Exception as e:
        logger.debug("get_autostart_status legacy service check failed: %s", e)

    return status


def _cleanup_legacy_service():
    """Silently remove the deprecated Windows service if it still exists."""
    try:
        from core.windows_service import is_service_installed, stop_service, uninstall_service

        if is_service_installed():
            logger.info("Detected legacy Windows service, cleaning up")
            stop_service()
            uninstall_service()
            logger.info("Legacy Windows service cleaned up")
    except Exception as e:
        logger.debug("cleanup legacy service failed: %s", e)
