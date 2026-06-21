"""
延迟启动、预加载、图标缓存清理相关方法。
"""

import atexit
import logging
import os
import time

from core.background_tasks import join_background_tasks, start_background_thread
from runtime_paths import is_packaged_runtime

logger = logging.getLogger(__name__)


def _join_startup_threads():
    """进程退出时 join 所有启动线程，防止文件操作被中断"""
    join_background_tasks("startup", timeout=9.0)


atexit.register(_join_startup_threads)


class StartupMixin:
    """延迟启动、预加载、图标缓存清理相关方法。"""

    def _enable_next_startup_plugin(self):
        pending = getattr(self, "_pending_startup_plugin_ids", None)
        if not pending:
            self._stop_timer_if_active("_plugin_startup_timer")
            return

        plugin_id = pending.pop(0)
        plugin_manager = None
        load_start = time.perf_counter()
        try:
            plugin_manager = getattr(self, "plugin_manager", None)
            if plugin_manager is None:
                pending.clear()
                return
            loaded = plugin_manager.load_plugin(plugin_id)
            logger.info(
                "启动插件%s: %s，耗时 %.1f ms",
                "加载完成" if loaded else "加载失败",
                plugin_id,
                (time.perf_counter() - load_start) * 1000,
            )
        except Exception:
            logger.exception("启动插件加载失败: %s", plugin_id)

        if pending:
            return

        self._stop_timer_if_active("_plugin_startup_timer")
        try:
            if plugin_manager is not None:
                plugin_manager.save_enabled_state()
        except Exception:
            logger.exception("保存启动插件状态失败")

    def _run_deferred_startup_tasks(self):
        if self._sleeping:
            return
        if self._has_shown_popup:
            return
        config_window = getattr(self, "config_window", None)
        try:
            if config_window is not None and config_window.isVisible():
                self._deferred_startup_timer.start(1000)
                return
        except (AttributeError, RuntimeError):
            logger.debug("config_window visibility check skipped", exc_info=True)

        self._preinit_popup()
        self._preload_icons()

        from qt_compat import QTimer

        QTimer.singleShot(500, self._preinit_watcher_manager)
        QTimer.singleShot(800, self._preimport_config_modules)

        QTimer.singleShot(3000, self._clean_icon_cache_async)

    def _clean_icon_cache_async(self):
        """Audit icon cache state without deleting user icon files on startup."""
        if self._sleeping:
            return

        def do_clean():
            if self._sleeping:
                return
            try:
                from core import APP_VERSION

                marker_file = self.data_manager.app_dir / ".icon_cache_cleaned"

                last_cleaned_version = ""

                if marker_file.exists():
                    try:
                        last_cleaned_version = marker_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        logger.debug("读取图标缓存清理标记失败", exc_info=True)

                if last_cleaned_version != APP_VERSION:
                    logger.info(
                        "检测到版本升级 (%s -> %s)，跳过自动图标缓存清理以保留用户图标目录",
                        last_cleaned_version or "未知",
                        APP_VERSION,
                    )

                cache_stats = self.data_manager.get_icon_cache_stats()

                if cache_stats.get("invalid_size_mb", 0) > 10:
                    logger.info(
                        "检测到 %.1f MB 无效图标缓存文件；自动启动不清理用户图标目录，可手动执行清理图标缓存",
                        cache_stats["invalid_size_mb"],
                    )

                try:
                    marker_file.write_text(APP_VERSION, encoding="utf-8")
                except Exception as e:
                    logger.debug(f"无法写入版本标记: {e}")

            except Exception as e:
                logger.debug(f"图标缓存清理失败: {e}")

        start_background_thread(name="IconCacheCleaner", target=do_clean, owner="startup")

    def _preinit_popup(self):
        if self._sleeping:
            return
        if self._has_shown_popup:
            return
        if self.popup_window:
            return
        preinit_start = time.perf_counter()
        logger.info("预初始化弹窗...")
        try:
            from ui.launcher_popup import LauncherPopup

            self.popup_window = LauncherPopup(self.data_manager, -10000, -10000, self, capture_selection=False)
            self.popup_window.refresh_data(refresh_selection=False, reposition=False)
            if not os.environ.get("QL_SAFE_MODE"):
                self.popup_window.preload_background()
            self.popup_window.preload_visible_icons(force=True, all_pages=True)
            self.popup_window.prepare_first_show(create_native_window=is_packaged_runtime())
            logger.info("预初始化弹窗完成，耗时 %.1f ms", (time.perf_counter() - preinit_start) * 1000)
        except Exception as e:
            logger.error(f"  预初始化弹窗失败: {e}")

    def _preinit_watcher_manager(self):
        """预初始化文件夹监听管理器（在后台线程中创建 watchdog Observer）"""
        if self._sleeping:
            return

        def do_init():
            if self._sleeping:
                return
            try:
                from core.folder_watcher import get_watcher_manager

                get_watcher_manager()
                logger.info("预初始化文件夹监听管理器完成")
            except Exception as e:
                logger.debug(f"  预初始化文件夹监听管理器失败: {e}")

        start_background_thread(name="PreinitWatcher", target=do_init, owner="startup")

    def _preimport_config_modules(self):
        """后台线程预导入配置窗口相关模块"""
        if self._sleeping:
            return

        def do_import():
            if self._sleeping:
                return
            import_start = time.perf_counter()
            try:
                import ui.config_window.folder_panel  # noqa: F401
                import ui.config_window.icon_grid  # noqa: F401
                import ui.config_window.main_window  # noqa: F401
                import ui.config_window.theme_helper  # noqa: F401

                logger.info("后台预导入配置窗口模块完成，耗时 %.1f ms", (time.perf_counter() - import_start) * 1000)
            except Exception as e:
                logger.debug(f"  后台预导入配置窗口模块失败: {e}")

        start_background_thread(name="PreimportConfigModules", target=do_import, owner="startup")

    def _preload_icons(self):
        """预加载图标（在主线程分批执行，避免跨线程 Qt 对象风险）"""
        if self._sleeping:
            self._icon_preload_started = False
            return
        if self._icon_preload_started:
            return
        self._icon_preload_started = True
        logger.info("开始预加载图标...")

        try:
            from core import IconExtractor
        except Exception:
            return

        from core.shortcut_icon_helpers import default_folder_icon_path, shortcut_uses_folder_icon

        settings = self.data_manager.get_settings()
        # 使用与弹窗 _get_icon() 完全一致的 DPI 缩放后 source_size，
        # 确保预加载的缓存 key 能被弹窗命中，避免重复提取图标
        from ui.utils.ui_scale import sp as _sp

        scaled_icon_size = _sp(settings.icon_size)
        source_size = max(48, scaled_icon_size * 2)

        tasks = []

        pages = self.data_manager.data.get_pages()
        for page in pages:
            for item in getattr(page, "items", []) or []:
                tasks.append(item)

        dock = self.data_manager.data.get_dock()
        if dock:
            for item in getattr(dock, "items", []) or []:
                tasks.append(item)

        state = {"i": 0, "count": 0}

        def step():
            if self._sleeping:
                self._icon_preload_started = False
                return
            i = state["i"]
            if i >= len(tasks):
                logger.info(f"预加载图标完成: {state['count']} 个")
                return

            from qt_compat import QTimer

            # Shell icon extraction can take several milliseconds per item.
            # Keep each GUI-thread slice small so background warming never
            # turns into a visible input stall.
            end = min(len(tasks), i + 4)
            for idx in range(i, end):
                item = tasks[idx]
                try:
                    icon_path = getattr(item, "icon_path", None)
                    target_path = getattr(item, "target_path", None)
                    item_type = getattr(item, "type", None)

                    if not icon_path and shortcut_uses_folder_icon(item_type, target_path):
                        icon_path = default_folder_icon_path()
                        if icon_path:
                            target_path = None

                    if icon_path:
                        IconExtractor.from_file(icon_path, source_size)
                        state["count"] += 1
                    elif target_path:
                        IconExtractor.extract(
                            target_path,
                            target_path,
                            source_size,
                            fallback_to_default=False,
                        )
                        state["count"] += 1
                except Exception:
                    continue

            state["i"] = end
            QTimer.singleShot(8, step)

        from qt_compat import QTimer

        QTimer.singleShot(10, step)
