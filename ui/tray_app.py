"""
托盘应用
"""

import os
import sys
import logging
import time
import ctypes

# 导入兼容层
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qt_compat import (
    QSystemTrayIcon, QMenu, QApplication, QMessageBox, QAction,
    QObject, pyqtSignal, QTimer, QIcon, QPainter, QColor, QRectF, QPainterPath,
    QtCompat, PYQT_VERSION, get_standard_icon
)
from ui.styles.style import PopupMenu
from ui.utils.window_effect import WindowEffect, is_win11
from ui.styles.themed_messagebox import ThemedMessageBox

logger = logging.getLogger(__name__)

# Lazy import cache for performance
_ShortcutExecutor = None

def _get_shortcut_executor():
    global _ShortcutExecutor
    if _ShortcutExecutor is None:
        from core import ShortcutExecutor
        _ShortcutExecutor = ShortcutExecutor
    return _ShortcutExecutor


class TrayApp(QObject):
    """托盘应用"""
    
    # 信号定义
    show_popup_signal = pyqtSignal(int, int)
    show_config_signal = pyqtSignal()  # 用于跨线程安全地请求显示配置窗口
    # Alt 双击信号 (从钩子线程发到主线程)
    _alt_double_tap_signal = pyqtSignal()
    # 键盘钩子热键信号 (从钩子线程发到主线程)
    _hook_hotkey_signal = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        logger.info("TrayApp 初始化...")
        
        # 初始化数据管理器
        logger.info("初始化数据管理器...")
        from core import DataManager
        self.data_manager = DataManager()
        logger.info("数据管理器初始化成功")


        self.config_window = None
        self.popup_window = None
        self._toast = None  # Toast 通知实例
        
        # 创建托盘图标
        logger.info("创建托盘图标...")
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self._load_icon())
        self.tray_icon.setToolTip("QuickLauncher\n左键=设置 | 中键=启动器")
        self.tray_icon.activated.connect(self._on_tray_activated)
        
        # 日志窗口实例
        self.log_window = None
        
        # 创建菜单
        self.tray_menu = None
        self._create_menu()
        
        # 连接信号
        self.show_popup_signal.connect(self._on_show_popup)
        self.show_config_signal.connect(self._show_config)  # 跨线程安全的配置窗口显示
        self._alt_double_tap_signal.connect(self._on_alt_double_tap)
        
        # 安装鼠标钩子（延迟到事件循环启动后，让托盘图标先显示）
        logger.info("安装鼠标钩子...")
        self.mouse_hook = None
        self._mouse_paused_state = False
        self._special_app_monitors_active = False
        self._hook_reinstall_cooldown_until = 0.0
        QTimer.singleShot(0, self._install_hook)

        # 安装键盘钩子 (Alt双击检测 + Alt按住状态跟踪)
        logger.info("安装键盘钩子...")
        self.keyboard_hook = None
        QTimer.singleShot(0, self._install_keyboard_hook_and_hotkey)
        
        # 快捷键管理器（钩子安装后再共享DLL）
        from hooks.hotkey_manager import HotkeyManager
        self.hotkey_manager = HotkeyManager()
        self._quitting = False
        # 应用设置
        self._apply_initial_settings()
        self._last_synced_settings_snapshot = self._make_settings_snapshot()
        self._pending_settings_sync = False
        self._settings_sync_timer = QTimer(self)
        self._settings_sync_timer.setSingleShot(True)
        self._settings_sync_timer.setInterval(120)
        self._settings_sync_timer.timeout.connect(self._apply_pending_settings_changes)
        
        self._has_shown_popup = False
        self._icon_preload_started = False
        self._preinit_popup()
        self._deferred_startup_timer = QTimer(self)
        self._deferred_startup_timer.setSingleShot(True)
        self._deferred_startup_timer.setInterval(10)  # 极速启动预加载
        self._deferred_startup_timer.timeout.connect(self._run_deferred_startup_tasks)
        self._deferred_startup_timer.start()

        # 内存保护
        from core.memory_guard import MemoryGuard
        self.memory_guard = MemoryGuard(critical_mb=200)  # 提高阈值到200MB
        self.memory_guard.register_cleanup_callback(self._cleanup_icon_cache)
        self._memory_check_timer = QTimer(self)
        self._memory_check_timer.setInterval(120000)  # 改为每120秒检查
        self._memory_check_timer.timeout.connect(self._check_memory)
        self._memory_check_timer.start()

        # hook.dll 模式下，仅在特殊进程启动时尝试重装一次钩子
        self._known_processes = set()
        self._process_check_timer = QTimer(self)
        self._process_check_timer.setInterval(10000)
        self._process_check_timer.timeout.connect(self._check_new_processes)

        self._update_special_app_monitors(reset_state=True)

        logger.info("TrayApp 初始化完成")


    def _make_settings_snapshot(self) -> dict:
        settings = self.data_manager.get_settings()
        try:
            special_apps = tuple(getattr(settings, "special_apps", []) or [])
        except Exception:
            special_apps = tuple()

        return {
            "hide_tray_icon": bool(getattr(settings, "hide_tray_icon", False)),
            "hardware_acceleration": bool(getattr(settings, "hardware_acceleration", False)),
            "special_apps": special_apps,
            "theme": str(getattr(settings, "theme", "dark") or "dark"),
            "bg_mode": str(getattr(settings, "bg_mode", "theme") or "theme"),
            "bg_alpha": int(getattr(settings, "bg_alpha", 90) or 90),
            "bg_blur_radius": int(getattr(settings, "bg_blur_radius", 0) or 0),
            "custom_bg_path": str(getattr(settings, "custom_bg_path", "") or ""),
            "bg_solid_color": str(getattr(settings, "bg_solid_color", "#2b2b2b") or ""),
            "corner_radius": int(getattr(settings, "corner_radius", 10) or 10),
            "dock_bg_alpha": int(getattr(settings, "dock_bg_alpha", 90) or 90),
            "dock_corner_radius": int(getattr(settings, "corner_radius", 10) or 10),  # 使用窗口圆角值
            "icon_alpha": float(getattr(settings, "icon_alpha", 1.0) or 1.0),
            "shadow_size": int(getattr(settings, "shadow_size", 0) or 0),
            "shadow_distance": int(getattr(settings, "shadow_distance", 0) or 0),
            "edge_highlight_color": str(getattr(settings, "edge_highlight_color", "#ffffff") or "#ffffff"),
            "edge_highlight_opacity": float(getattr(settings, "edge_highlight_opacity", 0.0) or 0.0),
            "double_click_interval": int(getattr(settings, "double_click_interval", 300) or 300),
            # 布局参数（用于检测变更后刷新弹窗）
            "cols": int(getattr(settings, "cols", 4) or 4),
            "cell_size": int(getattr(settings, "cell_size", 72) or 72),
            "icon_size": int(getattr(settings, "icon_size", 48) or 48),
        }

    def _apply_pending_settings_changes(self):
        if not self._pending_settings_sync:
            return
        self._pending_settings_sync = False

        prev = self._last_synced_settings_snapshot or {}
        cur = self._make_settings_snapshot()
        self._last_synced_settings_snapshot = cur

        if cur.get("special_apps") != prev.get("special_apps"):
            self._sync_special_apps_to_hook()

        if cur.get("hide_tray_icon") != prev.get("hide_tray_icon"):
            if cur.get("hide_tray_icon"):
                self.tray_icon.hide()
            else:
                self.tray_icon.show()

        if cur.get("hardware_acceleration") != prev.get("hardware_acceleration"):
            self._apply_hardware_acceleration(bool(cur.get("hardware_acceleration")))

        if cur.get("double_click_interval") != prev.get("double_click_interval"):
            self._apply_double_click_interval(cur.get("double_click_interval"))

        if cur.get("theme") != prev.get("theme"):
            self._create_menu()  # 重建托盘菜单以应用新主题

        if self.popup_window:
            try:
                # 如果窗口对象已被销毁，置为 None
                try:
                    _ = self.popup_window.width()
                except RuntimeError:
                    self.popup_window = None
            except Exception:
                self.popup_window = None
        
        if self.popup_window:
            try:
                pos = self.popup_window.geometry().center()
                self.popup_window.refresh_data(
                    pos.x(),
                    pos.y(),
                    refresh_selection=False,
                    reposition=False
                )
            except Exception as e:
                logger.error(f"刷新弹窗失败: {e}")

    def _apply_initial_settings(self):
        """应用初始设置"""
        settings = self.data_manager.get_settings()
        
        # 1. 托盘图标可见性
        if getattr(settings, 'hide_tray_icon', False):
            self.tray_icon.hide()
        else:
            self.tray_icon.show()
            
        # 2. 硬件加速 (进程优先级)
        self._apply_hardware_acceleration(getattr(settings, 'hardware_acceleration', False))
        
        # 3. 双击间隔
        self._apply_double_click_interval(getattr(settings, 'double_click_interval', 300))

    def _apply_double_click_interval(self, interval_ms: int):
        """同步 Qt 原生双击间隔设置"""
        app = QApplication.instance()
        if not app:
            return
        try:
            interval = max(100, int(interval_ms or 300))
        except Exception:
            interval = 300
        app.setDoubleClickInterval(interval)

    def _apply_hardware_acceleration(self, enable: bool):
        """应用硬件加速设置"""
        try:
            import psutil
            import os
            p = psutil.Process(os.getpid())
            if enable:
                # 设置为高于正常优先级 (High 可能导致鼠标卡顿，Above Normal 比较安全)
                # Windows: ABOVE_NORMAL_PRIORITY_CLASS (0x00008000)
                p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
                logger.info("硬件加速已启用: 进程优先级设为 ABOVE_NORMAL")
            else:
                p.nice(psutil.NORMAL_PRIORITY_CLASS)
                logger.info("硬件加速已禁用: 进程优先级设为 NORMAL")
        except Exception as e:
            logger.warning(f"设置进程优先级失败: {e}")

    def _run_deferred_startup_tasks(self):
        if self._has_shown_popup:
            return
        
        # 优先极速预初始化弹窗和加载图标，满足"一两秒内显示完整"的要求
        self._preinit_popup()
        self._preload_icons()
        
        # 后台线程预导入配置窗口和其它不紧急的模块
        QTimer.singleShot(500, self._preinit_watcher_manager)
        QTimer.singleShot(800, self._preimport_config_modules)
        
        # 清理图标缓存放到最后执行
        QTimer.singleShot(3000, self._clean_icon_cache_async)
    
    def _clean_icon_cache_async(self):
        """异步清理图标缓存
        
        首次升级清理机制：
        - 使用版本标记文件记录上次清理使用的版本
        - 如果版本升级了，执行一次完整清理
        - 日常启动只做轻量级检查（跳过孤儿文件检测以提高性能）
        """
        import threading
        
        def do_clean():
            try:
                from core import APP_VERSION
                
                # 版本标记文件路径
                marker_file = self.data_manager.app_dir / ".icon_cache_cleaned"
                
                # 检查是否需要深度清理（首次升级）
                need_deep_clean = False
                last_cleaned_version = ""
                
                if marker_file.exists():
                    try:
                        last_cleaned_version = marker_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        pass
                
                # 如果版本不同或标记文件不存在，执行深度清理
                if last_cleaned_version != APP_VERSION:
                    need_deep_clean = True
                    logger.info(f"检测到版本升级 ({last_cleaned_version or '未知'} -> {APP_VERSION})，执行图标缓存深度清理...")
                
                # 先获取缓存状态，判断是否需要清理
                cache_stats = self.data_manager.get_icon_cache_stats()
                
                # 如果有大量无效文件（exe/dll 或过大文件），一定要清理
                if cache_stats.get("invalid_size_mb", 0) > 10:  # 超过 10MB 的无效文件
                    need_deep_clean = True
                    logger.info(f"检测到 {cache_stats['invalid_size_mb']:.1f} MB 无效缓存文件，执行清理...")
                
                if need_deep_clean:
                    # 深度清理：清理所有类型的问题文件
                    stats = self.data_manager.clean_icon_cache(dry_run=False)
                    
                    if stats["total_removed"] > 0:
                        # 构建清理报告
                        parts = []
                        if stats["exe_files_removed"] > 0:
                            parts.append(f"可执行文件 {stats['exe_files_removed']} 个 ({stats['exe_files_size_mb']:.1f} MB)")
                        if stats["large_files_removed"] > 0:
                            parts.append(f"过大文件 {stats['large_files_removed']} 个 ({stats['large_files_size_mb']:.1f} MB)")
                        if stats["orphan_files_removed"] > 0:
                            parts.append(f"孤儿文件 {stats['orphan_files_removed']} 个 ({stats['orphan_files_size_mb']:.1f} MB)")
                        if stats["duplicate_files_removed"] > 0:
                            parts.append(f"重复文件 {stats['duplicate_files_removed']} 个 ({stats['duplicate_files_size_mb']:.1f} MB)")
                        
                        logger.info(
                            f"图标缓存升级清理完成: 共删除 {stats['total_removed']} 个文件, "
                            f"释放 {stats['total_size_freed_mb']:.1f} MB\n  - " + "\n  - ".join(parts)
                        )
                    else:
                        logger.info("图标缓存已是最新，无需清理")
                    
                    # 更新版本标记
                    try:
                        marker_file.write_text(APP_VERSION, encoding="utf-8")
                    except Exception as e:
                        logger.debug(f"无法写入版本标记: {e}")
                        
            except Exception as e:
                logger.debug(f"图标缓存清理失败: {e}")
        
        threading.Thread(target=do_clean, name="IconCacheCleaner", daemon=True).start()
    
    def _preinit_popup(self):
        if self._has_shown_popup:
            return
        if self.popup_window:
            return
        logger.info("预初始化弹窗...")
        try:
            from ui.launcher_popup import LauncherPopup
            self.popup_window = LauncherPopup(self.data_manager, -10000, -10000, self)
            self.popup_window.refresh_data(refresh_selection=False, reposition=False)
            self.popup_window.preload_background()
            self.popup_window.preload_visible_icons()
            self.popup_window.prepare_first_show()
        except Exception as e:
            logger.error(f"  预初始化弹窗失败: {e}")


    def _preinit_watcher_manager(self):
        """预初始化文件夹监听管理器（在后台线程中创建 watchdog Observer）"""
        import threading
        def do_init():
            try:
                from core.folder_watcher import get_watcher_manager
                get_watcher_manager()  # 触发单例创建和 Observer 线程启动
                logger.info("预初始化文件夹监听管理器完成")
            except Exception as e:
                logger.debug(f"  预初始化文件夹监听管理器失败: {e}")
        threading.Thread(target=do_init, name="PreinitWatcher", daemon=True).start()

    def _preimport_config_modules(self):
        """后台线程预导入配置窗口相关模块
        
        模块导入可以在后台线程执行（不涉及 QWidget 创建），
        这样当用户打开配置窗口时，模块已在 sys.modules 缓存中，
        QWidget 创建只需很短的时间。
        """
        import threading
        def do_import():
            try:
                # 预导入配置窗口的核心模块（最重的部分）
                import ui.config_window.main_window  # noqa: F401
                import ui.config_window.folder_panel  # noqa: F401
                import ui.config_window.icon_grid  # noqa: F401
                import ui.config_window.theme_helper  # noqa: F401
                logger.info("后台预导入配置窗口模块完成")
            except Exception as e:
                logger.debug(f"  后台预导入配置窗口模块失败: {e}")
        threading.Thread(target=do_import, name="PreimportConfigModules", daemon=True).start()

    def _preload_icons(self):
        """预加载图标（在主线程分批执行，避免跨线程 Qt 对象风险）"""
        if self._icon_preload_started:
            return
        self._icon_preload_started = True
        logger.info("开始预加载图标...")

        try:
            from core import IconExtractor
        except Exception:
            return

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
            i = state["i"]
            if i >= len(tasks):
                logger.info(f"预加载图标完成: {state['count']} 个")
                return

            end = min(len(tasks), i + 24)  # Increase batch size massively for instant start
            for idx in range(i, end):
                item = tasks[idx]
                try:
                    icon_path = getattr(item, "icon_path", None)
                    target_path = getattr(item, "target_path", None)
                    item_type = getattr(item, "type", None)

                    import os, sys
                    is_folder_type = item_type == ShortcutType.FOLDER
                    if item_type == ShortcutType.FILE and target_path and os.path.isdir(target_path):
                        is_folder_type = True

                    if not icon_path and is_folder_type:
                        possible_paths = [
                            os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'assets', 'Folder.ico'),
                            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'Folder.ico')
                        ]
                        import sys
                        if hasattr(sys, '_MEIPASS'):
                            possible_paths.insert(0, os.path.join(sys._MEIPASS, 'assets', 'Folder.ico'))
                        for p in possible_paths:
                            if os.path.exists(p):
                                icon_path = p
                                target_path = None
                                break

                    if icon_path:
                        IconExtractor.from_file(icon_path, icon_size)
                        state["count"] += 1
                    elif target_path:
                        IconExtractor.extract(target_path, target_path, icon_size)
                        state["count"] += 1
                except Exception:
                    continue

            state["i"] = end
            QTimer.singleShot(1, step)

        QTimer.singleShot(10, step)

    def _install_hook(self):
        """安装鼠标钩子"""
        if not self._install_mouse_backend():
            logger.error("鼠标钩子安装失败")

    def _install_mouse_backend(self) -> bool:
        """安装 DLL 鼠标后端。hooks.dll 是全局单例，必须按单实例方式重装。"""
        try:
            from hooks.mouse_hook_dll import MouseHook
            if self.mouse_hook:
                try:
                    self.mouse_hook.uninstall()
                except Exception:
                    pass
                self.mouse_hook = None

            hook = MouseHook()
            success = hook.install(self._on_middle_click_from_hook)
            if not success:
                return False

            if self.keyboard_hook:
                try:
                    hook.set_keyboard_hook(self.keyboard_hook)
                except Exception:
                    pass

            try:
                hook.set_paused(self._mouse_paused_state)
            except Exception:
                pass

            self.mouse_hook = hook
            self._apply_mouse_hook_settings()

            logger.info("鼠标触发已切换到 DLL Hook")
            return True
        except Exception as e:
            logger.error(f"安装鼠标后端失败 [dll_hook]: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.mouse_hook = None
            return False

    def _install_keyboard_hook(self):
        """安装键盘钩子 (Alt双击检测 + Alt按住状态)"""
        try:
            from hooks.keyboard_hook_dll import KeyboardHook
            self.keyboard_hook = KeyboardHook()

            success = self.keyboard_hook.install(
                on_alt_double_tap=self._on_alt_double_tap_from_hook
            )

            if success:
                logger.info("键盘钩子安装成功")
                # 将键盘钩子传给鼠标钩子（用于检测 Alt 按住状态）
                if self.mouse_hook:
                    self.mouse_hook.set_keyboard_hook(self.keyboard_hook)
            else:
                logger.warning("  键盘钩子安装失败")

        except Exception as e:
            logger.error(f"  键盘钩子异常: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _install_keyboard_hook_and_hotkey(self):
        """安装键盘钩子并启动热键管理器（延迟执行）"""
        self._install_keyboard_hook()
        # 共享键盘钩子的DLL实例
        if self.keyboard_hook and hasattr(self.keyboard_hook, '_dll'):
            self.hotkey_manager._dll = self.keyboard_hook._dll
        self.hotkey_manager.start()

    def _reinstall_hooks(self):
        """重装钩子以保持优先级（轻量级，仅卸载重装）"""
        try:
            now = time.monotonic()
            if now < self._hook_reinstall_cooldown_until:
                return
            self._hook_reinstall_cooldown_until = now + 2.0

            if not self._install_mouse_backend():
                return

            if self.keyboard_hook:
                self.keyboard_hook.uninstall()
                self.keyboard_hook.install(self._on_alt_double_tap_from_hook)
        except Exception:
            pass

    def _check_new_processes(self):
        """检测特定软件启动时重装钩子（仅监测可能有钩子冲突的软件）"""
        try:
            import psutil

            # 需要监测的软件关键词（可能有钩子冲突的专业软件）
            target_apps = set(self._get_special_apps())

            if not target_apps:
                self._known_processes = set()
                return

            current_pids = set()
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    name = proc.info['name'].lower()
                    if any(app in name for app in target_apps):
                        current_pids.add(proc.info['pid'])
                except:
                    pass

            if not self._known_processes:
                self._known_processes = current_pids
                return

            new_pids = current_pids - self._known_processes
            if new_pids:
                logger.info(f"检测到目标软件启动，重装钩子以保持优先级")
                self._reinstall_hooks()

            self._known_processes = current_pids
        except Exception:
            pass

    def _on_alt_double_tap_from_hook(self):
        """Alt双击回调 (从键盘钩子线程调用，必须极快返回)"""
        try:
            self._alt_double_tap_signal.emit()
        except Exception:
            pass
    
    def _on_hook_hotkey_from_hook(self):
        """键盘钩子热键回调 (从钩子线程调用，必须极快返回)"""
        try:
            self._hook_hotkey_signal.emit()
        except Exception:
            pass
    
    def _on_alt_double_tap(self):
        """处理 Alt 双击 - 切换鼠标中键钩子暂停状态 (主线程)"""
        try:
            if not self.mouse_hook:
                return
            
            # 切换暂停状态
            new_paused = not self.mouse_hook.is_paused()
            self._mouse_paused_state = new_paused
            self.mouse_hook.set_paused(new_paused)
            
            # 获取当前主题
            theme = "dark"
            try:
                settings = self.data_manager.get_settings()
                theme = getattr(settings, "theme", "dark") or "dark"
            except Exception:
                pass
            
            # 显示 Toast 通知
            if new_paused:
                text = "已关闭鼠标中键"
            else:
                text = "已开启鼠标中键"
            
            self._show_toast(text, theme)
            logger.info(f"Alt双击: 鼠标中键钩子 {'已暂停' if new_paused else '已恢复'}")
            
        except Exception as e:
            logger.error(f"处理Alt双击失败: {e}")
    
    def _show_toast(self, text: str, theme: str = "dark"):
        """显示 Toast 通知"""
        try:
            if self._toast is None:
                from ui.toast_notification import ToastNotification
                self._toast = ToastNotification()
            self._toast.show_toast(text, theme=theme, duration_ms=1500)
        except Exception as e:
            logger.error(f"显示Toast失败: {e}")

    def _get_special_apps(self):
        try:
            settings = self.data_manager.get_settings()
            return [str(app or "").strip().lower() for app in (getattr(settings, 'special_apps', []) or []) if str(app or "").strip()]
        except Exception:
            return []

    def _get_special_apps_for_hook(self):
        expanded_apps = []
        seen = set()

        for app in self._get_special_apps():
            candidates = [app]
            if app.endswith(".exe"):
                base_name = app[:-4].strip()
                if base_name:
                    candidates.append(base_name)
            else:
                candidates.append(f"{app}.exe")

            for candidate in candidates:
                normalized = str(candidate or "").strip().lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    expanded_apps.append(normalized)

        return expanded_apps

    def _reset_special_app_monitor_state(self):
        self._known_processes = set()

    def _update_special_app_monitors(self, reset_state: bool = False):
        special_apps = self._get_special_apps()

        if reset_state:
            self._reset_special_app_monitor_state()

        if not special_apps:
            if self._process_check_timer.isActive():
                self._process_check_timer.stop()
            self._special_app_monitors_active = False
            return

        if not self._special_app_monitors_active:
            self._process_check_timer.start()
            self._special_app_monitors_active = True

    def _apply_mouse_hook_settings(self):
        """将特殊应用配置同步到 DLL 鼠标钩子"""
        if not self.mouse_hook:
            return

        special_apps = self._get_special_apps_for_hook()
        self.mouse_hook.set_special_apps(special_apps)
        logger.info(f"已同步特殊应用列表[dll_hook]: {special_apps}")

    def _sync_special_apps_to_hook(self):
        """同步特殊应用设置到鼠标钩子"""
        try:
            self._update_special_app_monitors(reset_state=True)
            if self.mouse_hook:
                self._apply_mouse_hook_settings()
            
        except Exception as e:
            logger.error(f"同步特殊应用设置失败: {e}")
    
    def _on_middle_click_from_hook(self, x: int, y: int):
        """从钩子线程接收中键点击（在钩子线程中调用）

        v2.6.6.0: 降低防抖动阈值从 180ms 到 80ms，
        与钩子层的 40ms 配合，总共约 120ms 有效防抖动
        """
        # 使用Windows API直接获取鼠标位置，避免DPI转换问题
        import ctypes
        try:
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            x, y = pt.x, pt.y
        except Exception:
            pass

        logger.debug(f"钩子回调: ({x}, {y})")

        # 简单的防抖动 (Debounce) - 降低阈值以支持更快的连续点击
        current_time = time.monotonic()
        if hasattr(self, '_last_click_time') and (current_time - self._last_click_time < 0.08):
            logger.debug("点击过快，已忽略")
            return
        self._last_click_time = current_time

        # 通过信号传递到主线程
        self.show_popup_signal.emit(x, y)
    
    def _on_show_popup(self, x: int, y: int):
        """显示弹出窗口（在主线程中执行）"""
        current_time = time.monotonic()
        if hasattr(self, '_last_show_popup_time') and (current_time - self._last_show_popup_time < 0.3):
            return
        self._last_show_popup_time = current_time
        x, y = self._normalize_popup_pos(x, y)
        logger.info(f"显示弹出窗口: ({x}, {y})")
        

        try:
            _get_shortcut_executor().save_foreground_window()
        except Exception:
            pass

        self._has_shown_popup = True
        try:
            if self._deferred_startup_timer and self._deferred_startup_timer.isActive():
                self._deferred_startup_timer.stop()
        except Exception:
            pass

        if not self._icon_preload_started:
            QTimer.singleShot(0, self._preload_icons)
        
        try:
            # 1. 如果窗口已存在
            if self.popup_window:
                # 检查是否在不同屏幕上点击
                if self.popup_window.isVisible():
                    from qt_compat import QApplication, QPoint
                    current_screen = QApplication.screenAt(QPoint(x, y))
                    window_screen = QApplication.screenAt(self.popup_window.pos())

                    # 如果在同一屏幕上点击，则隐藏（Toggle功能）
                    if current_screen == window_screen:
                        self.popup_window.hide()
                        return
                    # 如果在不同屏幕上点击，继续显示（重新定位）

                # 如果窗口对象已被销毁（C++对象已删除），则置为 None
                try:
                    _ = self.popup_window.width()
                except RuntimeError:
                    self.popup_window = None
            
            # 移除每次显示的重载，提高响应速度
            # self.data_manager.reload()
            
            # 2. 复用或新建窗口
            if self.popup_window:
                # 复用现有窗口：先刷新数据和位置，再显示
                self.popup_window.refresh_data(x, y)
                self.popup_window.preload_visible_icons()
                self.popup_window.prepare_first_show()
                self.popup_window.show()
                self.popup_window.activateWindow()
                self.popup_window.raise_()
                logger.info("弹出窗口已复用并显示")
            else:
                # 创建新弹窗（在屏幕外创建，设置好后再移动显示）
                from ui.launcher_popup import LauncherPopup
                self.popup_window = LauncherPopup(self.data_manager, x, y, self)
                self.popup_window.preload_background()
                self.popup_window.preload_visible_icons()
                self.popup_window.prepare_first_show()
                self.popup_window.show()
                self.popup_window.activateWindow()
                self.popup_window.raise_()
                logger.info("弹出窗口已创建并显示")
            
        except Exception as e:
            logger.error(f"显示弹出窗口失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _normalize_popup_pos(self, x: int, y: int):
        # 直接使用QCursor.pos()获取当前鼠标位置
        try:
            from qt_compat import QCursor
            cursor = QCursor.pos()
            return (cursor.x(), cursor.y())
        except Exception:
            pass
        return (int(x), int(y))

    def _is_point_in_any_qt_screen(self, x: int, y: int) -> bool:
        try:
            from qt_compat import QApplication, QPoint
            pt = QPoint(int(x), int(y))
            for s in QApplication.screens() or []:
                if s.geometry().contains(pt):
                    return True
        except Exception:
            return True
        return False

    def _try_convert_win_physical_to_qt(self, x: int, y: int):
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32

            class POINT(ctypes.Structure):
                _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", wintypes.LONG),
                    ("top", wintypes.LONG),
                    ("right", wintypes.LONG),
                    ("bottom", wintypes.LONG),
                ]

            class MONITORINFOEXW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", wintypes.DWORD),
                    ("szDevice", wintypes.WCHAR * 32),
                ]

            MONITOR_DEFAULTTONEAREST = 2

            monitor_from_point = user32.MonitorFromPoint
            monitor_from_point.argtypes = [POINT, wintypes.DWORD]
            monitor_from_point.restype = wintypes.HMONITOR

            get_monitor_info = user32.GetMonitorInfoW
            get_monitor_info.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
            get_monitor_info.restype = wintypes.BOOL

            hmon = monitor_from_point(POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST)
            if not hmon:
                return None

            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if not get_monitor_info(hmon, ctypes.byref(info)):
                return None

            device = (info.szDevice or "").strip()
            from qt_compat import QApplication, QCursor

            screen = None
            for s in QApplication.screens() or []:
                try:
                    if s.name() == device:
                        screen = s
                        break
                except Exception:
                    continue

            if not screen:
                screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
            if not screen:
                return None

            try:
                dpr = float(screen.devicePixelRatio())
            except Exception:
                dpr = 1.0
            if dpr <= 0:
                dpr = 1.0

            geo = screen.geometry()
            left = geo.left() + int(round((int(x) - int(info.rcMonitor.left)) / dpr))
            top = geo.top() + int(round((int(y) - int(info.rcMonitor.top)) / dpr))
            return (left, top)
        except Exception:
            return None
    
    def _load_icon(self) -> QIcon:
        """加载图标"""
        possible_paths = [
            os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'app.ico'),  # exe所在目录
            os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'assets', 'app.ico'),  # exe/assets
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'app.ico'),  # 根目录/assets/app.ico
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.ico'),  # 根目录 app.ico
            os.path.join(os.path.dirname(__file__), '..', 'resources', 'app.ico'),
            os.path.join(os.path.dirname(__file__), 'resources', 'app.ico'),
            'assets/app.ico',
            'resources/app.ico',
        ]
        
        for path in possible_paths:
            try:
                abs_path = os.path.abspath(path)
                if os.path.exists(abs_path):
                    logger.debug(f"找到图标: {abs_path}")
                    icon = QIcon(abs_path)
                    if not icon.isNull():
                        return icon
            except Exception as e:
                logger.warning(f"检查图标路径失败 {path}: {e}")
        
        return get_standard_icon(QApplication.instance(), 'SP_ComputerIcon')
    
    def _create_menu(self):
        """创建托盘菜单"""
        # 使用 PopupMenu 实现磨砂质感（模糊效果在 popup() 中自动应用）
        theme = self.data_manager.get_settings().theme
        self.tray_menu = PopupMenu(theme=theme, radius=12)

        # 添加菜单项
        self.tray_menu.add_action("设置", self._show_config)
        self.tray_menu.add_action("重新启动", self._restart)
        self.tray_menu.add_action("运行日志", self._show_log)
        self.tray_menu.add_separator()
        self.tray_menu.add_action("退出软件", self._quit)

    def _stop_timer_if_active(self, attr_name):
        timer = getattr(self, attr_name, None)
        if timer is None:
            return
        try:
            if timer.isActive():
                timer.stop()
        except Exception:
            try:
                timer.stop()
            except Exception:
                pass

    def _close_widget_if_present(self, attr_name):
        widget = getattr(self, attr_name, None)
        if widget is None:
            return
        try:
            widget.close()
        except Exception:
            pass
        try:
            setattr(self, attr_name, None)
        except Exception:
            pass

    def _shutdown_runtime_components(self):
        for timer_name in (
            "_settings_sync_timer",
            "_deferred_startup_timer",
            "_memory_check_timer",
            "_process_check_timer",
        ):
            self._stop_timer_if_active(timer_name)

        try:
            self.hotkey_manager.stop()
        except Exception as e:
            logger.debug(f"stop hotkey manager failed: {e}")

        try:
            from core.folder_watcher import shutdown_watcher_manager
            shutdown_watcher_manager()
        except Exception as e:
            logger.debug(f"stop folder watcher failed: {e}")

        mouse_hook = self.mouse_hook
        self.mouse_hook = None
        if mouse_hook:
            try:
                mouse_hook.uninstall()
            except Exception:
                pass

        keyboard_hook = self.keyboard_hook
        self.keyboard_hook = None
        if keyboard_hook:
            try:
                keyboard_hook.uninstall()
            except Exception:
                pass

        try:
            self.tray_icon.hide()
        except Exception:
            pass

        for attr_name in (
            "config_window",
            "popup_window",
            "log_window",
            "_toast",
        ):
            self._close_widget_if_present(attr_name)

    def _restart(self):
        """重新启动应用"""
        logger.info("重新启动应用...")

        # 卸载钩子
        self._shutdown_runtime_components()
        if self.mouse_hook:
            try:
                self.mouse_hook.uninstall()
            except:
                pass

        if self.keyboard_hook:
            try:
                self.keyboard_hook.uninstall()
            except:
                pass

        # 隐藏托盘
        self.tray_icon.hide()

        # 执行重新启动
        try:
            import subprocess
            import tempfile

            # 获取当前进程的可执行文件路径
            # 对于 Nuitka 打包，需要查找 QuickLauncher.exe
            exe = sys.executable
            logger.info(f"sys.executable = {exe}")
            logger.info(f"sys.frozen = {getattr(sys, 'frozen', False)}")
            logger.info(f"sys.argv[0] = {sys.argv[0]}")

            # 判断是否为打包版本
            is_frozen = getattr(sys, 'frozen', False)

            # 如果是打包版本，查找真正的 QuickLauncher.exe
            if not is_frozen and 'python' in os.path.basename(exe).lower():
                # 可能是 Nuitka 打包，检查 sys.argv[0]
                if sys.argv[0].lower().endswith('.exe'):
                    exe = os.path.abspath(sys.argv[0])
                    is_frozen = True
                    logger.info(f"从 sys.argv[0] 检测到打包版本: {exe}")

            logger.info(f"最终检测: is_frozen={is_frozen}, exe={exe}")

            if is_frozen:
                # 打包模式：使用 VBScript 无窗口延迟启动
                if not os.path.isabs(exe):
                    exe = os.path.abspath(exe)

                cwd = os.path.dirname(exe)

                # 创建临时 VBScript 脚本（无窗口）
                vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WScript.Sleep 2000
WshShell.Run """{exe}""", 0, False
Set fso = CreateObject("Scripting.FileSystemObject")
fso.DeleteFile WScript.ScriptFullName
'''
                vbs_file = os.path.join(tempfile.gettempdir(), 'quicklauncher_restart.vbs')
                with open(vbs_file, 'w', encoding='utf-8') as f:
                    f.write(vbs_content)

                logger.info(f"打包模式重启: exe={exe}, vbs={vbs_file}")

                # 启动 VBScript（无窗口）
                subprocess.Popen(['wscript.exe', vbs_file],
                               cwd=cwd,
                               creationflags=0x08000000,
                               shell=False)

            else:
                # 开发模式：使用 VBScript 无窗口延迟启动
                cwd = os.path.dirname(os.path.abspath(__file__))
                while cwd and not os.path.exists(os.path.join(cwd, 'main.py')):
                    parent = os.path.dirname(cwd)
                    if parent == cwd:
                        break
                    cwd = parent

                main_py = os.path.join(cwd, 'main.py')
                if not os.path.exists(main_py):
                    logger.error(f"找不到 main.py: {main_py}")
                    raise FileNotFoundError(f"找不到 main.py: {main_py}")

                # 创建临时 VBScript 脚本（无窗口）
                vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WScript.Sleep 2000
WshShell.Run """{exe}"" ""{main_py}""", 0, False
Set fso = CreateObject("Scripting.FileSystemObject")
fso.DeleteFile WScript.ScriptFullName
'''
                vbs_file = os.path.join(tempfile.gettempdir(), 'quicklauncher_restart.vbs')
                with open(vbs_file, 'w', encoding='utf-8') as f:
                    f.write(vbs_content)

                logger.info(f"开发模式重启: exe={exe}, main_py={main_py}, vbs={vbs_file}")

                # 启动 VBScript（无窗口）
                subprocess.Popen(['wscript.exe', vbs_file],
                               cwd=cwd,
                               creationflags=0x08000000,
                               shell=False)

            # 立即退出当前进程
            logger.info("准备退出当前进程...")
            QTimer.singleShot(100, QApplication.quit)

        except Exception as e:
            logger.error(f"重新启动失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # TrayApp 是 QObject，不能作为 QDialog 的 parent
            # 尝试使用配置窗口作为 parent，如果没有则使用 None
            parent = self.config_window if self.config_window else None
            ThemedMessageBox.critical(parent, "重启失败", f"无法重新启动程序\n\n{str(e)}")
    
    def _test_popup(self):
        """测试弹窗（用于调试）"""
        # 获取鼠标位置
        from qt_compat import QCursor
        pos = QCursor.pos()
        self._on_show_popup(pos.x(), pos.y())
    
    def _on_tray_activated(self, reason):
        """托盘图标激活"""
        logger.debug(f"托盘激活: {reason}")
        if reason == QtCompat.Trigger or reason == QtCompat.DoubleClick:
            self._show_config()
        elif reason == QtCompat.Context:
            # 右键显示自定义磨砂菜单
            from qt_compat import QCursor, QPoint
            pos = QCursor.pos()
            # 稍微偏移一点，避免遮住托盘图标
            offset_pos = QPoint(pos.x(), pos.y() - 5)
            self.tray_menu.popup(offset_pos)
    
    def _show_config(self):
        """显示配置窗口"""
        logger.info("显示配置窗口...")
        try:
            if self.config_window is None:
                from ui.config_window import ConfigWindow
                self.config_window = ConfigWindow(self.data_manager)
                # 连接设置变更信号
                self.config_window.settings_changed.connect(self._on_settings_changed)

            # 延迟连接 hotkey_recording_changed（settings_panel 是延迟创建的）
            if not getattr(self, '_hotkey_signal_connected', False):
                try:
                    panel = getattr(self.config_window, "settings_panel", None)
                    if panel and hasattr(panel, "hotkey_recording_changed"):
                        panel.hotkey_recording_changed.connect(self._on_hotkey_recording_changed)
                        self._hotkey_signal_connected = True
                except Exception:
                    pass

            # 连接特殊应用变更信号
            if not getattr(self, '_special_apps_signal_connected', False):
                try:
                    panel = getattr(self.config_window, "settings_panel", None)
                    if panel and hasattr(panel, "special_apps_changed"):
                        panel.special_apps_changed.connect(self._sync_special_apps_to_hook)
                        self._special_apps_signal_connected = True
                except Exception:
                    pass
            
            self.config_window.show()
            
            # 使用强力激活方案 (多阶段尝试，应对系统焦点竞争)
            try:
                hwnd = int(self.config_window.winId())
                from ui.utils.window_effect import force_activate_window
                from qt_compat import QTimer
                
                force_activate_window(hwnd)
                QTimer.singleShot(100, lambda: force_activate_window(hwnd))
                
            except Exception:
                # 最后的兜底
                self.config_window.raise_()
                self.config_window.activateWindow()
                
            logger.info("配置窗口已显示并进入四段式强力激活流程")
        except Exception as e:
            logger.error(f"显示配置窗口失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            ThemedMessageBox.critical(None, "错误", f"无法打开设置窗口:\n{e}")
    
    def _on_settings_changed(self):
        """设置变更时的回调"""
        self._pending_settings_sync = True
        if not self._settings_sync_timer.isActive():
            self._settings_sync_timer.start()

    def _on_hotkey_recording_changed(self, recording: bool):
        try:
            self._is_hotkey_recording = bool(recording)
            if recording:
                self.hotkey_manager.stop()
                # 录制时也暂停键盘钩子热键检测
                if self.keyboard_hook:
                    self.keyboard_hook.set_hotkey("", None)
                return
            pass
        except Exception:
            pass
    
    def _show_log(self):
        """显示日志窗口"""
        logger.info("_show_log 方法被调用")
        try:
            theme = self.data_manager.get_settings().theme
            logger.debug(f"log_window 状态: {self.log_window}")
            if self.log_window is None:
                logger.info("创建新的日志窗口")
                from ui.log_window import LogWindow
                log_dir = self.data_manager.app_dir
                log_file = os.path.join(log_dir, 'error.log')
                self.log_window = LogWindow(log_file, theme=theme)
                logger.info("日志窗口创建完成")

            # 检查窗口是否已被删除
            try:
                logger.debug("检查窗口是否有效")
                _ = self.log_window.isVisible()
                logger.debug("窗口有效")
                # 同步主题
                self.log_window.set_theme(theme)
            except RuntimeError as e:
                logger.warning(f"窗口已被删除，重新创建: {e}")
                from ui.log_window import LogWindow
                log_dir = self.data_manager.app_dir
                log_file = os.path.join(log_dir, 'error.log')
                self.log_window = LogWindow(log_file, theme=theme)
                logger.info("日志窗口重新创建完成")

            logger.info("显示日志窗口")
            self.log_window.show()
            self.log_window.raise_()
            self.log_window.activateWindow()

            # 强制激活窗口
            try:
                hwnd = int(self.log_window.winId())
                from ui.utils.window_effect import force_activate_window
                force_activate_window(hwnd)
                logger.debug("已强制激活日志窗口")
            except Exception as e:
                logger.warning(f"强制激活失败: {e}")

            logger.debug("窗口已显示，准备加载日志")
            from qt_compat import QTimer
            QTimer.singleShot(100, self.log_window.load_log)
            logger.info("日志窗口显示完成")
        except Exception as e:
            logger.error(f"显示日志窗口失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _force_unload_dlls(self):
        """强制卸载当前进程加载的 DLL，特别是 msvcp140.dll"""
        try:
            import ctypes
            import sys

            # 获取当前进程句柄
            kernel32 = ctypes.windll.kernel32

            # 需要释放的 DLL 列表
            dlls_to_free = [
                'msvcp140.dll',
                'vcruntime140.dll',
                'vcruntime140_1.dll'
            ]

            logger.info("开始释放 DLL 引用...")

            for dll_name in dlls_to_free:
                try:
                    # 获取 DLL 模块句柄
                    h_module = kernel32.GetModuleHandleW(dll_name)
                    if h_module:
                        # 多次调用 FreeLibrary 来减少引用计数
                        # 注意：不能完全卸载，只是减少引用计数
                        for _ in range(10):  # 尝试多次释放
                            result = kernel32.FreeLibrary(h_module)
                            if not result:
                                break
                        logger.info(f"已释放 {dll_name} 的引用")
                    else:
                        logger.debug(f"{dll_name} 未加载")
                except Exception as e:
                    logger.debug(f"释放 {dll_name} 失败: {e}")

            logger.info("DLL 引用释放完成")
        except Exception as e:
            logger.error(f"释放 DLL 时出错: {e}")

    def _quit(self):
        if self._quitting:
            return
        self._quitting = True
        self._shutdown_runtime_components()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _check_memory(self):
        """定期检查内存并优化"""
        try:
            self.memory_guard.check_and_optimize()
        except Exception:
            pass

    def _cleanup_icon_cache(self):
        """清理图标缓存以释放内存"""
        try:
            from core import IconExtractor
            if hasattr(IconExtractor, '_cache'):
                cache_size = len(IconExtractor._cache)
                if cache_size > 50:
                    items = list(IconExtractor._cache.items())
                    IconExtractor._cache.clear()
                    for k, v in items[-50:]:
                        IconExtractor._cache[k] = v
                    logger.info(f"清理图标缓存: {cache_size} -> 50")
        except Exception as e:
            logger.debug(f"清理图标缓存失败: {e}")
