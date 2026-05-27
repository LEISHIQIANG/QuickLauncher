"""
延迟启动、预加载、图标缓存清理相关方法。
"""

import logging
import os
import sys
import time

logger = logging.getLogger(__name__)


class StartupMixin:
    """延迟启动、预加载、图标缓存清理相关方法。"""

    def _run_deferred_startup_tasks(self):
        if self._sleeping:
            return
        if self._has_shown_popup:
            return

        self._preinit_popup()
        self._preload_icons()

        from qt_compat import QTimer

        QTimer.singleShot(500, self._preinit_watcher_manager)
        QTimer.singleShot(800, self._preimport_config_modules)

        QTimer.singleShot(3000, self._clean_icon_cache_async)

    def _clean_icon_cache_async(self):
        """异步清理图标缓存"""
        if self._sleeping:
            return
        import threading

        def do_clean():
            if self._sleeping:
                return
            try:
                from core import APP_VERSION

                marker_file = self.data_manager.app_dir / ".icon_cache_cleaned"

                need_deep_clean = False
                last_cleaned_version = ""

                if marker_file.exists():
                    try:
                        last_cleaned_version = marker_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        pass

                if last_cleaned_version != APP_VERSION:
                    need_deep_clean = True
                    logger.info(
                        f"检测到版本升级 ({last_cleaned_version or '未知'} -> {APP_VERSION})，执行图标缓存深度清理..."
                    )

                cache_stats = self.data_manager.get_icon_cache_stats()

                if cache_stats.get("invalid_size_mb", 0) > 10:
                    need_deep_clean = True
                    logger.info(f"检测到 {cache_stats['invalid_size_mb']:.1f} MB 无效缓存文件，执行清理...")

                if need_deep_clean:
                    stats = self.data_manager.clean_icon_cache(dry_run=False)

                    if stats["total_removed"] > 0:
                        parts = []
                        if stats["exe_files_removed"] > 0:
                            parts.append(
                                f"可执行文件 {stats['exe_files_removed']} 个 ({stats['exe_files_size_mb']:.1f} MB)"
                            )
                        if stats["large_files_removed"] > 0:
                            parts.append(
                                f"过大文件 {stats['large_files_removed']} 个 ({stats['large_files_size_mb']:.1f} MB)"
                            )
                        if stats["orphan_files_removed"] > 0:
                            parts.append(
                                f"孤儿文件 {stats['orphan_files_removed']} 个 ({stats['orphan_files_size_mb']:.1f} MB)"
                            )
                        if stats["duplicate_files_removed"] > 0:
                            parts.append(
                                f"重复文件 {stats['duplicate_files_removed']} 个 ({stats['duplicate_files_size_mb']:.1f} MB)"
                            )

                        logger.info(
                            f"图标缓存升级清理完成: 共删除 {stats['total_removed']} 个文件, "
                            f"释放 {stats['total_size_freed_mb']:.1f} MB\n  - " + "\n  - ".join(parts)
                        )
                    else:
                        logger.info("图标缓存已是最新，无需清理")

                    try:
                        marker_file.write_text(APP_VERSION, encoding="utf-8")
                    except Exception as e:
                        logger.debug(f"无法写入版本标记: {e}")

            except Exception as e:
                logger.debug(f"图标缓存清理失败: {e}")

        threading.Thread(target=do_clean, name="IconCacheCleaner", daemon=True).start()

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
            self.popup_window.preload_visible_icons()
            packaged_runtime = (
                bool(getattr(sys, "frozen", False))
                or "__compiled__" in dir(__builtins__)
                or os.path.basename(sys.executable).lower() == "quicklauncher.exe"
            )
            self.popup_window.prepare_first_show(create_native_window=packaged_runtime)
            logger.info("预初始化弹窗完成，耗时 %.1f ms", (time.perf_counter() - preinit_start) * 1000)
        except Exception as e:
            logger.error(f"  预初始化弹窗失败: {e}")

    def _preinit_watcher_manager(self):
        """预初始化文件夹监听管理器（在后台线程中创建 watchdog Observer）"""
        if self._sleeping:
            return
        import threading

        def do_init():
            if self._sleeping:
                return
            try:
                from core.folder_watcher import get_watcher_manager

                get_watcher_manager()
                logger.info("预初始化文件夹监听管理器完成")
            except Exception as e:
                logger.debug(f"  预初始化文件夹监听管理器失败: {e}")

        threading.Thread(target=do_init, name="PreinitWatcher", daemon=True).start()

    def _preimport_config_modules(self):
        """后台线程预导入配置窗口相关模块"""
        if self._sleeping:
            return
        import threading

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

        threading.Thread(target=do_import, name="PreimportConfigModules", daemon=True).start()

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

        from core.data_models import ShortcutType

        settings = self.data_manager.get_settings()
        icon_size = settings.icon_size

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

            end = min(len(tasks), i + 24)
            for idx in range(i, end):
                item = tasks[idx]
                try:
                    icon_path = getattr(item, "icon_path", None)
                    target_path = getattr(item, "target_path", None)
                    item_type = getattr(item, "type", None)

                    is_folder_type = item_type == ShortcutType.FOLDER
                    if item_type == ShortcutType.FILE and target_path and os.path.isdir(target_path):
                        is_folder_type = True

                    if not icon_path and is_folder_type:
                        possible_paths = [
                            os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "assets", "Folder.ico"),
                            os.path.join(
                                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "Folder.ico"
                            ),
                        ]
                        if hasattr(sys, "_MEIPASS"):
                            possible_paths.insert(0, os.path.join(sys._MEIPASS, "assets", "Folder.ico"))
                        for p in possible_paths:
                            if os.path.exists(p):
                                icon_path = p
                                target_path = None
                                break

                    if icon_path:
                        IconExtractor.from_file(icon_path, icon_size)
                        state["count"] += 1
                    elif target_path:
                        IconExtractor.extract(
                            target_path,
                            target_path,
                            icon_size,
                            fallback_to_default=False,
                        )
                        state["count"] += 1
                except Exception:
                    continue

            state["i"] = end
            QTimer.singleShot(1, step)

        from qt_compat import QTimer

        QTimer.singleShot(10, step)
