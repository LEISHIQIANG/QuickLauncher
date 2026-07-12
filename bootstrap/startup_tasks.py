"""Startup helper tasks that can be tested without importing main.py."""

from __future__ import annotations

import json
import os

from runtime_paths import is_packaged_runtime


def cleanup_stale_command_cache(logger) -> None:
    try:
        from core.shortcut_command_exec import CommandExecutionMixin

        CommandExecutionMixin._cleanup_cmd_cache()
        logger.debug("已清理命令缓存目录")
    except ImportError:
        logger.warning("命令缓存清理模块导入失败", exc_info=True)
    except OSError:
        logger.warning("清理命令缓存目录失败", exc_info=True)


def sync_frozen_autostart_from_config(root_dir: str, logger) -> None:
    if not is_packaged_runtime():
        return

    cfg_path = os.path.join(root_dir, "config", "data.json")
    auto_start = False
    try:
        if os.path.isfile(cfg_path):
            with open(cfg_path, encoding="utf-8") as fh:
                auto_start = json.load(fh).get("settings", {}).get("auto_start", False)
    except (OSError, json.JSONDecodeError):
        logger.warning("读取自启动配置失败: %s", cfg_path, exc_info=True)
        return

    try:
        from core.auto_start_manager import _ensure_auto_start

        _ensure_auto_start(bool(auto_start))
    except (ImportError, OSError, RuntimeError):
        logger.warning("自启动检查失败", exc_info=True)


def process_startup_events(app, logger) -> None:
    try:
        app.processEvents()
        if is_packaged_runtime():
            import time

            time.sleep(0.05)
            app.processEvents()
    except RuntimeError as exc:
        logger.debug("启动事件处理失败: %s", exc, exc_info=True)


def merge_default_special_apps(tray_app, logger) -> None:
    try:
        from core import APP_VERSION
        from core.data_models import DEFAULT_SPECIAL_APPS
    except ImportError:
        logger.warning("导入默认特殊应用配置失败", exc_info=True)
        return

    version_marker = tray_app.data_manager.app_dir / ".special_apps_merged_version"
    last_merged = ""
    try:
        if version_marker.exists():
            last_merged = version_marker.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("读取特殊应用版本标记失败: %s", version_marker, exc_info=True)

    if last_merged == APP_VERSION:
        return

    try:
        settings = tray_app.data_manager.get_settings()
        user_apps = list(settings.special_apps or [])
        added = [app for app in DEFAULT_SPECIAL_APPS if app not in user_apps]
        if added:
            tray_app.data_manager.update_settings(special_apps=user_apps + added)
            logger.info("新版本合并特殊应用列表，新增: %s", added)
    except (AttributeError, OSError, ValueError):
        logger.warning("合并特殊应用列表失败", exc_info=True)
        return

    try:
        version_marker.write_text(APP_VERSION, encoding="utf-8")
    except OSError:
        logger.warning("写入特殊应用版本标记失败: %s", version_marker, exc_info=True)


def sync_autostart_setting_from_task(tray_app, logger) -> None:
    if not is_packaged_runtime():
        return

    try:
        from core.auto_start_manager import get_auto_start_check_result

        task_enabled, task_reason = get_auto_start_check_result()
        settings = tray_app.data_manager.get_settings()
        config_auto_start = bool(getattr(settings, "auto_start", False))
        if task_enabled and not config_auto_start:
            tray_app.data_manager.update_settings(auto_start=True)
            logger.info("检测到有效自启动任务，已同步配置为开启: %s", task_reason)
        elif config_auto_start and not task_enabled:
            tray_app.data_manager.update_settings(auto_start=False)
            logger.warning(
                "配置要求开机自启，但任务缺失或定义已过期；已同步配置为关闭，避免误导用户: %s",
                task_reason,
            )
    except (ImportError, OSError, RuntimeError, AttributeError, ValueError):
        logger.warning("同步自启动状态失败", exc_info=True)
