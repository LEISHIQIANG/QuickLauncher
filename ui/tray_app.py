"""
托盘应用
"""

import logging
import os
import sys
import time

# 导入兼容层
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.i18n import tr
from qt_compat import (
    QApplication,
    QIcon,
    QObject,
    QSystemTrayIcon,
    QtCompat,
    QThread,
    QTimer,
    get_standard_icon,
    pyqtSignal,
)
from ui.styles.style import PopupMenu
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.tray_mixins import HooksMixin, PopupMixin, SleepMixin, StartupMixin, UpdateMixin, WindowsMixin

logger = logging.getLogger(__name__)

# Lazy import cache for performance
_ShortcutExecutor = None


def _get_shortcut_executor():
    global _ShortcutExecutor
    if _ShortcutExecutor is None:
        from core import ShortcutExecutor

        _ShortcutExecutor = ShortcutExecutor
    return _ShortcutExecutor


class IconCacheCleanThread(QThread):
    finished_signal = pyqtSignal(dict, str)

    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager

    def run(self):
        try:
            try:
                from core import IconExtractor

                if hasattr(IconExtractor, "clear_cache"):
                    IconExtractor.clear_cache()
            except Exception as exc:
                logger.debug("清理图标提取器缓存: %s", exc, exc_info=True)
            self.finished_signal.emit(self.data_manager.clean_icon_cache(dry_run=False), "")
        except Exception as exc:
            self.finished_signal.emit({}, str(exc))


class TrayApp(UpdateMixin, HooksMixin, SleepMixin, PopupMixin, StartupMixin, WindowsMixin, QObject):
    """托盘应用"""

    # 信号定义
    show_popup_signal = pyqtSignal(int, int)
    show_config_signal = pyqtSignal()  # 用于跨线程安全地请求显示配置窗口
    # Alt 双击信号 (从钩子线程发到主线程)
    _alt_double_tap_signal = pyqtSignal()
    # 键盘钩子热键信号 (从钩子线程发到主线程)
    _hook_hotkey_signal = pyqtSignal()
    _update_event_signal = pyqtSignal(str, object)
    _download_event_signal = pyqtSignal(str, object)
    _install_event_signal = pyqtSignal(str, object)

    def __init__(self):
        init_start = time.perf_counter()
        super().__init__()
        logger.info("TrayApp 初始化...")

        # 初始化数据管理器
        logger.info("初始化数据管理器...")
        from core import DataManager

        self.data_manager = DataManager()
        logger.info("数据管理器初始化成功")

        # 注册 data_manager 引用到 core 模块
        from core import set_data_manager

        set_data_manager(self.data_manager)

        # 初始化命令注册中心
        import core

        core.ensure_registry_initialized()

        # Check plugin degrade switch before initializing plugin manager
        _safe_mode = bool(os.environ.get("QL_SAFE_MODE"))
        _plugins_enabled = True
        try:
            _plugins_enabled = self.data_manager.get_settings().enable_plugins
        except Exception as exc:
            logger.debug("获取设置: %s", exc, exc_info=True)
        if _safe_mode:
            logger.info("安全模式：插件系统已禁用")
        elif _plugins_enabled:
            core.ensure_plugin_manager_initialized()
        else:
            logger.info("插件系统已通过功能开关禁用")

        plugin_manager = core.plugin_manager
        if plugin_manager is not None:

            def _save_enabled_plugins(enabled_ids: list[str]):
                self.data_manager.update_settings(enabled_plugins=list(enabled_ids or []))

            plugin_manager.set_save_callback(_save_enabled_plugins)

            def _confirm_high_risk(info) -> bool:
                from ui.styles.themed_messagebox import ThemedMessageBox

                manifest = getattr(info, "manifest", None)
                name = getattr(manifest, "name", str(info))
                permissions = list(getattr(manifest, "permissions", []) or [])
                from core.plugin_manager import HIGH_RISK_PERMISSIONS

                high_risk = [p for p in permissions if p in HIGH_RISK_PERMISSIONS]
                risk_line = f"\n高风险权限: {', '.join(high_risk)}\n" if high_risk else "\n"
                parent = getattr(self, "config_window", None) or QApplication.activeWindow()
                reply = ThemedMessageBox.question(
                    parent,
                    "启用插件",
                    f"插件「{name}」将与 QuickLauncher 主程序同权限运行。"
                    f"{risk_line}\n仅启用您信任的插件。确定要启用吗？",
                    ThemedMessageBox.Yes | ThemedMessageBox.No,
                )
                return reply == ThemedMessageBox.Yes

            plugin_manager.set_confirm_high_risk_callback(_confirm_high_risk)
            enabled = list(self.data_manager.get_settings().enabled_plugins)
            if enabled:
                plugin_manager.auto_enable(enabled)

        self.config_window = None
        self.popup_window = None
        self._extra_popup_windows = []
        self._max_extra_popup_windows = 2
        self._toast = None  # Toast 通知实例

        # 创建托盘图标
        logger.info("创建托盘图标...")
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self._load_icon())
        self.tray_icon.setToolTip(tr("QuickLauncher\n左键=设置 | 中键=启动器"))
        self.tray_icon.activated.connect(self._on_tray_activated)

        # 日志窗口实例
        self.log_window = None
        self.diagnostics_window = None
        self.shortcut_health_window = None
        self.config_history_window = None
        self.slash_help_window = None
        self.command_panel_window = None
        try:
            from core.command_results import CommandResultStore

            self.command_result_store = CommandResultStore()
        except Exception:
            logger.exception("初始化命令结果存储失败")
            self.command_result_store = None
        self._icon_cache_clean_thread = None

        # 创建菜单
        self.tray_menu = None
        self._create_menu()

        # Show the tray icon before any deferred startup work. Silent startup
        # must not create hidden top-level windows that can appear in taskbar.
        self._apply_initial_settings()

        # 连接信号
        self.show_popup_signal.connect(self._on_show_popup)
        self.show_config_signal.connect(self._show_config)  # 跨线程安全的配置窗口显示
        self._alt_double_tap_signal.connect(self._on_alt_double_tap)
        self._update_event_signal.connect(self._on_update_event)
        self._download_event_signal.connect(self._on_download_event)
        self._install_event_signal.connect(self._on_install_event)

        # 安装鼠标钩子（延迟到事件循环启动后，让托盘图标先显示）
        self.mouse_hook = None
        self._mouse_paused_state = False
        self._special_app_monitors_active = False
        self._hook_reinstall_cooldown_until = 0.0
        if not _safe_mode:
            logger.info("安装鼠标钩子...")
            QTimer.singleShot(0, self._install_hook)
        else:
            logger.info("安全模式：鼠标钩子已禁用")

        # 安装键盘钩子 (Alt双击检测 + Alt按住状态跟踪)
        self.keyboard_hook = None
        if not _safe_mode:
            logger.info("安装键盘钩子...")
            QTimer.singleShot(0, self._install_keyboard_hook_and_hotkey)
        else:
            logger.info("安全模式：键盘钩子已禁用")

        # 快捷键管理器（钩子安装后再共享DLL）
        from hooks.hotkey_manager import HotkeyManager

        self.hotkey_manager = HotkeyManager()
        self._quitting = False
        self._last_synced_settings_snapshot = self._make_settings_snapshot()
        self._pending_settings_sync = False
        self._settings_sync_timer = QTimer(self)
        self._settings_sync_timer.setSingleShot(True)
        self._settings_sync_timer.setInterval(120)
        self._settings_sync_timer.timeout.connect(self._apply_pending_settings_changes)

        self._sleeping = False
        self._sleep_was_hw_accel = False
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self._enter_light_sleep)

        self._has_shown_popup = False
        self._icon_preload_started = False
        self._deferred_startup_timer = QTimer(self)
        self._deferred_startup_timer.setSingleShot(True)
        self._deferred_startup_timer.setInterval(10)  # 极速启动预加载
        self._deferred_startup_timer.timeout.connect(self._run_deferred_startup_tasks)
        self._deferred_startup_timer.start()

        # 内存保护
        from core.memory_guard import MemoryGuard

        self.memory_guard = MemoryGuard(critical_mb=200)  # 提高阈值到200MB
        self.memory_guard.register_cleanup_callback(self._cleanup_icon_cache)
        self.memory_guard.register_cleanup_callback(
            lambda level: (
                None
                if level == "light"
                else (
                    __import__(
                        "core.shortcut_command_exec", fromlist=["CommandExecutionMixin"]
                    ).CommandExecutionMixin._cleanup_cmd_cache()
                )
            )
        )
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

        self._update_checker = None
        self._update_downloader = None
        self._update_installer = None
        self._pending_update_info = None
        self._pending_update_installer = ""
        self._update_dialog_parent = None
        if not _safe_mode:
            try:
                if getattr(self.data_manager.get_settings(), "auto_update_enabled", False):
                    QTimer.singleShot(5000, self._init_update_system)
            except Exception as exc:
                logger.debug("获取设置: %s", exc, exc_info=True)
        else:
            logger.info("安全模式：自动更新检查已禁用")

        self._mark_activity("startup")

        logger.info("TrayApp 初始化完成，耗时 %.1f ms", (time.perf_counter() - init_start) * 1000)

    def _make_settings_snapshot(self) -> dict:
        settings = self.data_manager.get_settings()
        try:
            special_apps = tuple(getattr(settings, "special_apps", []) or [])
        except Exception:
            special_apps = ()

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
                self.popup_window.refresh_data(pos.x(), pos.y(), refresh_selection=False, reposition=False)
            except Exception as e:
                logger.error(f"刷新弹窗失败: {e}")

    def _apply_initial_settings(self):
        """应用初始设置"""
        settings = self.data_manager.get_settings()

        # 1. 托盘图标可见性
        if getattr(settings, "hide_tray_icon", False):
            self.tray_icon.hide()
        else:
            self.tray_icon.show()

        # 2. 硬件加速 (进程优先级)
        self._apply_hardware_acceleration(getattr(settings, "hardware_acceleration", False))

        # 3. 双击间隔
        self._apply_double_click_interval(getattr(settings, "double_click_interval", 300))

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
            import os

            import psutil

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

    def _show_toast(self, text: str, theme: str = "dark"):
        """显示 Toast 通知"""
        try:
            if self._toast is None:
                from ui.toast_notification import ToastNotification

                self._toast = ToastNotification()
            self._toast.show_toast(text, theme=theme, duration_ms=1500)
        except Exception as e:
            logger.error(f"显示Toast失败: {e}")

    def _load_icon(self) -> QIcon:
        """加载图标"""
        possible_paths = [
            os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "app.ico"),  # exe所在目录
            os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "assets", "app.ico"),  # exe/assets
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "app.ico"
            ),  # 根目录/assets/app.ico
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.ico"),  # 根目录 app.ico
            os.path.join(os.path.dirname(__file__), "..", "resources", "app.ico"),
            os.path.join(os.path.dirname(__file__), "resources", "app.ico"),
            "assets/app.ico",
            "resources/app.ico",
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

        return get_standard_icon(QApplication.instance(), "SP_ComputerIcon")

    def _create_menu(self):
        """创建托盘菜单"""
        # 使用 PopupMenu 实现磨砂质感（模糊效果在 popup() 中自动应用）
        theme = self.data_manager.get_settings().theme
        self.tray_menu = PopupMenu(theme=theme, radius=12)

        # 添加菜单项
        self.tray_menu.add_action("设置", self._show_config)
        self.tray_menu.add_action("重新启动", self._restart)
        self.tray_menu.add_action("运行日志", self._show_log)
        self.tray_menu.add_action("诊断中心", self._show_diagnostics)
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
            except Exception as exc:
                logger.debug("停止定时器失败: %s", exc, exc_info=True)

    def _close_widget_if_present(self, attr_name):
        widget = getattr(self, attr_name, None)
        if widget is None:
            return
        try:
            widget.close()
        except Exception as exc:
            logger.debug("关闭窗口组件: %s", exc, exc_info=True)
        try:
            setattr(self, attr_name, None)
        except Exception as exc:
            logger.debug("清除窗口引用失败: %s", exc, exc_info=True)

    def _shutdown_runtime_components(self):
        # 停止后台线程
        try:
            _thread = self._icon_cache_clean_thread
        except Exception:
            _thread = None
        if _thread is not None:
            try:
                _thread.quit()
                _thread.wait(2000)
            except Exception as exc:
                logger.debug("退出图标缓存清理线程失败: %s", exc, exc_info=True)

        for timer_name in (
            "_settings_sync_timer",
            "_sleep_timer",
            "_deferred_startup_timer",
            "_memory_check_timer",
            "_process_check_timer",
        ):
            self._stop_timer_if_active(timer_name)

        try:
            if self._update_checker:
                self._update_checker.stop()
        except Exception as e:
            logger.debug(f"stop update checker failed: {e}")

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
            except Exception as exc:
                logger.debug("卸载鼠标钩子: %s", exc, exc_info=True)

        keyboard_hook = self.keyboard_hook
        self.keyboard_hook = None
        if keyboard_hook:
            try:
                keyboard_hook.uninstall()
            except Exception as exc:
                logger.debug("卸载键盘钩子: %s", exc, exc_info=True)

        try:
            self.tray_icon.hide()
        except Exception as exc:
            logger.debug("隐藏托盘图标: %s", exc, exc_info=True)

        for attr_name in (
            "config_window",
            "popup_window",
            "log_window",
            "diagnostics_window",
            "shortcut_health_window",
            "config_history_window",
            "slash_help_window",
            "_toast",
        ):
            self._close_widget_if_present(attr_name)
        self._close_extra_popup_windows()

    def _close_extra_popup_windows(self):
        for popup in list(getattr(self, "_extra_popup_windows", []) or []):
            try:
                popup.close()
            except Exception as exc:
                logger.debug("关闭弹窗: %s", exc, exc_info=True)
        self._extra_popup_windows = []

    def _restart(self):
        """重新启动应用"""
        logger.info("重新启动应用...")

        # 卸载钩子
        self._shutdown_runtime_components()
        if self.mouse_hook:
            try:
                self.mouse_hook.uninstall()
            except Exception as exc:
                logger.debug("卸载鼠标钩子: %s", exc, exc_info=True)

        if self.keyboard_hook:
            try:
                self.keyboard_hook.uninstall()
            except Exception as exc:
                logger.debug("卸载键盘钩子: %s", exc, exc_info=True)

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
            is_frozen = getattr(sys, "frozen", False)

            # 如果是打包版本，查找真正的 QuickLauncher.exe
            if not is_frozen and "python" in os.path.basename(exe).lower():
                # 可能是 Nuitka 打包，检查 sys.argv[0]
                if sys.argv[0].lower().endswith(".exe"):
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
                vbs_file = os.path.join(tempfile.gettempdir(), "quicklauncher_restart.vbs")
                with open(vbs_file, "w", encoding="utf-8") as f:
                    f.write(vbs_content)

                logger.info(f"打包模式重启: exe={exe}, vbs={vbs_file}")

                # 启动 VBScript（无窗口）
                subprocess.Popen(["wscript.exe", vbs_file], cwd=cwd, creationflags=0x08000000, shell=False)

            else:
                # 开发模式：使用 VBScript 无窗口延迟启动
                cwd = os.path.dirname(os.path.abspath(__file__))
                while cwd and not os.path.exists(os.path.join(cwd, "main.py")):
                    parent = os.path.dirname(cwd)
                    if parent == cwd:
                        break
                    cwd = parent

                main_py = os.path.join(cwd, "main.py")
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
                vbs_file = os.path.join(tempfile.gettempdir(), "quicklauncher_restart.vbs")
                with open(vbs_file, "w", encoding="utf-8") as f:
                    f.write(vbs_content)

                logger.info(f"开发模式重启: exe={exe}, main_py={main_py}, vbs={vbs_file}")

                # 启动 VBScript（无窗口）
                subprocess.Popen(["wscript.exe", vbs_file], cwd=cwd, creationflags=0x08000000, shell=False)

            # 立即退出当前进程
            logger.info("准备退出当前进程...")
            QTimer.singleShot(100, QApplication.quit)

        except Exception as e:
            logger.exception("重新启动失败")
            # TrayApp 是 QObject，不能作为 QDialog 的 parent
            # 尝试使用配置窗口作为 parent，如果没有则使用 None
            parent = self.config_window if self.config_window else None
            ThemedMessageBox.critical(parent, tr("重启失败"), tr("无法重新启动程序\n\n{error}", error=str(e)))

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

    def _clean_icon_cache_now(self):
        """立即执行图标缓存维护。"""
        self._wake_from_sleep("clean_icon_cache")
        try:
            if self._icon_cache_clean_thread and self._icon_cache_clean_thread.isRunning():
                self._show_toast(tr("图标缓存正在清理中"), self.data_manager.get_settings().theme)
                return True

            self._cleanup_icon_cache()

            if self.popup_window:
                try:
                    self.popup_window._icon_pixmap_cache.clear()
                    self.popup_window._icon_miss_cache.clear()
                    self.popup_window._default_icon_cache.clear()
                except Exception:
                    logger.debug("清理弹窗图标缓存失败", exc_info=True)
            for popup in list(getattr(self, "_extra_popup_windows", []) or []):
                try:
                    popup._icon_pixmap_cache.clear()
                    popup._icon_miss_cache.clear()
                    popup._default_icon_cache.clear()
                except Exception:
                    logger.debug("清理固定多开弹窗图标缓存失败", exc_info=True)

            theme = self.data_manager.get_settings().theme
            self._show_toast(tr("正在清理图标缓存..."), theme)
            self._icon_cache_clean_thread = IconCacheCleanThread(self.data_manager)
            self._icon_cache_clean_thread.finished_signal.connect(self._on_icon_cache_clean_finished)
            self._icon_cache_clean_thread.finished.connect(lambda: setattr(self, "_icon_cache_clean_thread", None))
            self._icon_cache_clean_thread.finished.connect(self._icon_cache_clean_thread.deleteLater)
            self._icon_cache_clean_thread.start()
            return True
        except Exception as e:
            logger.error("手动图标缓存清理失败: %s", e, exc_info=True)
            return False

    def _on_icon_cache_clean_finished(self, stats: dict, error: str):
        theme = self.data_manager.get_settings().theme
        if error:
            logger.error("手动图标缓存清理失败: %s", error)
            self._show_toast(tr("图标缓存清理失败，请查看日志"), theme)
            return
        removed = int(stats.get("total_removed", 0) or 0)
        freed = float(stats.get("total_size_freed_mb", 0) or 0)
        logger.info("手动图标缓存清理完成: removed=%s freed=%.2fMB", removed, freed)
        self._show_toast(
            tr("图标缓存已清理：{removed} 个文件，释放 {freed:.1f} MB", removed=removed, freed=freed), theme
        )

    def _reload_hooks_now(self):
        """手动重装鼠标、键盘钩子。"""
        self._wake_from_sleep("reload_hooks")
        try:
            self._hook_reinstall_cooldown_until = 0.0
            self._reinstall_hooks()

            if not self.mouse_hook:
                self._install_hook()
            if not self.keyboard_hook:
                self._install_keyboard_hook_and_hotkey()
            else:
                try:
                    self.hotkey_manager.start()
                except Exception as exc:
                    logger.debug("启动热键管理器: %s", exc, exc_info=True)

            self._sync_special_apps_to_hook()
            theme = self.data_manager.get_settings().theme
            self._show_toast(tr("全局钩子已重装"), theme)
            logger.info("手动重装全局钩子完成")
            return True
        except Exception as e:
            logger.error("手动重装全局钩子失败: %s", e, exc_info=True)
            return False

    def _open_data_dir(self):
        """打开 QuickLauncher 配置数据目录。"""
        self._wake_from_sleep("open_data_dir")
        try:
            path = os.path.abspath(str(self.data_manager.app_dir))
            os.makedirs(path, exist_ok=True)
            os.startfile(path)
            logger.info("已打开配置数据目录: %s", path)
            return True
        except Exception as e:
            logger.error("打开配置数据目录失败: %s", e, exc_info=True)
            return False

    def _open_install_dir(self):
        """打开 QuickLauncher 软件安装目录。"""
        self._wake_from_sleep("open_install_dir")
        try:
            path = _get_shortcut_executor()._app_install_dir()
            os.makedirs(path, exist_ok=True)
            os.startfile(path)
            logger.info("已打开软件安装目录: %s", path)
            return True
        except Exception as e:
            logger.error("打开软件安装目录失败: %s", e, exc_info=True)
            return False

    def _quit(self):
        if self._quitting:
            return
        self._quitting = True
        self._shutdown_runtime_components()
        app = QApplication.instance()
        if app is not None:
            app.quit()
