"""
托盘应用
"""

import atexit
import logging
import os
import sys
import time

from core.i18n import tr
from infrastructure.process import runtime as process_runtime
from qt_compat import (
    QApplication,
    QObject,
    QSystemTrayIcon,
    QtCompat,
    QThread,
    QTimer,
    pyqtSignal,
)
from runtime_paths import app_executable, app_root, is_packaged_runtime
from ui.styles.style import PopupMenu  # noqa: F401 - re-exported for legacy monkey-patches
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.tray_mixins import HooksMixin, PopupMixin, SleepMixin, StartupMixin, UpdateMixin, WindowsMixin
from ui.tray_mixins.menu_mixin import TrayAppMenuMixin
from ui.tray_mixins.shutdown_mixin import TrayAppShutdownMixin

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


class TrayApp(
    TrayAppMenuMixin,
    TrayAppShutdownMixin,
    UpdateMixin,
    HooksMixin,
    SleepMixin,
    PopupMixin,
    StartupMixin,
    WindowsMixin,
    QObject,
):
    """托盘应用"""

    # 信号定义
    show_popup_signal = pyqtSignal(int, int)
    show_config_signal = pyqtSignal()  # 用于跨线程安全地请求显示配置窗口
    # Alt 双击信号 (从钩子线程发到主线程)
    _alt_double_tap_signal = pyqtSignal()
    # 任务栏双击信号 (从钩子线程发到主线程)
    _taskbar_double_click_signal = pyqtSignal(int, int)
    _update_event_signal = pyqtSignal(str, object)
    _download_event_signal = pyqtSignal(str, object)
    _install_event_signal = pyqtSignal(str, object)
    _process_check_done_signal = pyqtSignal(object)
    _config_saved_signal = pyqtSignal(object)

    def __init__(self, data_manager, command_registry=None, plugin_manager=None, module_registry=None):
        init_start = time.perf_counter()
        super().__init__()
        logger.info("TrayApp 初始化...")

        # 初始化数据管理器
        logger.info("初始化数据管理器...")
        self.data_manager = data_manager
        logger.info("数据管理器初始化成功")

        # 初始化 UI 缩放（从配置中读取，在创建任何 UI 之前设置）
        from ui.utils.ui_scale import (
            DEFAULT_SCALE_PERCENT,
            detect_system_ui_scale,
        )
        from ui.utils.ui_scale import (
            set_scale as _set_ui_scale,
        )

        _init_scale = getattr(self.data_manager.get_settings(), "ui_scale_percent", DEFAULT_SCALE_PERCENT)

        # 首次运行自动检测：配置值仍为默认 100 时，根据主显示器 DPI 自动设置
        if _init_scale == DEFAULT_SCALE_PERCENT:
            detected = detect_system_ui_scale()
            if detected != DEFAULT_SCALE_PERCENT:
                logger.info("首次运行 → 自动检测系统 DPI: %d%%", detected)
                _init_scale = detected
                # 持久化自动检测值，后续运行沿用此值
                self.data_manager.update_settings(ui_scale_percent=detected)

        _set_ui_scale(_init_scale)
        from ui.styles.theme_controller import set_app_theme
        from ui.tooltip_helper import update_tooltip_theme

        _initial_theme = getattr(self.data_manager.get_settings(), "theme", "dark")
        set_app_theme(_initial_theme)
        update_tooltip_theme(_initial_theme)
        try:
            from ui.utils.font_manager import apply_app_font

            apply_app_font(13)
        except Exception as exc:
            logger.debug("应用启动 UI 缩放字体失败: %s", exc, exc_info=True)

        # 安装 WM_DPICHANGED 事件过滤器（PerMonitorV2 模式下跨 DPI 显示器自适应）
        try:
            from ui.utils.dpi_event_filter import install_dpi_filter

            self._dpi_filter = install_dpi_filter(self._on_system_dpi_changed)
            self._last_auto_detected: int | None = _init_scale if _init_scale != DEFAULT_SCALE_PERCENT else None
        except Exception as exc:
            logger.debug("安装 DPI 事件过滤器失败: %s", exc, exc_info=True)
            self._dpi_filter = None
            self._last_auto_detected = None

        # 兼容旧入口；标准 GUI 入口由 composition root 显式注入依赖。
        import core

        if command_registry is None:
            core.ensure_registry_initialized()
            command_registry = core.registry
        self.command_registry = command_registry

        # Check plugin degrade switch before initializing plugin manager
        _safe_mode = bool(os.environ.get("QL_SAFE_MODE"))
        self._safe_mode = _safe_mode
        self._started = False
        _plugins_enabled = True
        try:
            _plugins_enabled = self.data_manager.get_settings().enable_plugins
        except Exception as exc:
            logger.debug("获取设置: %s", exc, exc_info=True)
        if _safe_mode:
            logger.info("安全模式：插件系统已禁用")
        elif not _plugins_enabled:
            logger.info("插件系统已通过功能开关禁用")

        self.plugin_manager = plugin_manager
        self.module_registry = module_registry
        self._pending_startup_plugin_ids = []
        if plugin_manager is not None:

            def _save_enabled_plugins(enabled_ids: list[str]):
                self.data_manager.update_settings(enabled_plugins=list(enabled_ids or []))

            plugin_manager.set_save_callback(_save_enabled_plugins)

            def _confirm_high_risk(info) -> bool:
                from ui.styles.themed_messagebox import ThemedMessageBox

                manifest = getattr(info, "manifest", None)
                name = getattr(manifest, "name", str(info))
                permissions = list(getattr(manifest, "permissions", []) or [])
                trust_level = str(getattr(manifest, "trust_level", "community-unverified") or "")
                install_source = str(getattr(manifest, "install_source", "") or "")
                from core.plugin_manager import HIGH_RISK_PERMISSIONS

                high_risk = [p for p in permissions if p in HIGH_RISK_PERMISSIONS]
                risk_line = f"\n高风险权限: {', '.join(high_risk)}\n" if high_risk else "\n"
                source_label = "官方插件包" if install_source == "builtin" else "第三方或未知来源"
                trust_label = {
                    "builtin": "官方可信",
                    "local-trusted": "本地开发",
                    "community-unverified": "社区未验证",
                }.get(trust_level, "社区未验证")
                parent = getattr(self, "config_window", None) or QApplication.activeWindow()
                reply = ThemedMessageBox.question(
                    parent,
                    "启用插件",
                    f"插件「{name}」将与 QuickLauncher 主程序同权限运行。"
                    f"\n来源: {source_label}\n信任等级: {trust_label}"
                    f"{risk_line}\n仅启用您信任的插件。确定要启用吗？",
                    ThemedMessageBox.Yes | ThemedMessageBox.No,
                )
                return reply == ThemedMessageBox.Yes  # type: ignore[no-any-return]

            plugin_manager.set_confirm_high_risk_callback(_confirm_high_risk)
            self._pending_startup_plugin_ids = list(self.data_manager.get_settings().enabled_plugins)

            # Auto-discover builtin plugins from .plugins/ repository that were
            # installed after the last session.  Skip plugins the user explicitly
            # disabled (status "disabled" or "error" in plugin_state.json).
            _state = getattr(plugin_manager, "_plugin_state", {})
            _plugins_section = _state.get("plugins", {}) if isinstance(_state, dict) else {}
            for _info in plugin_manager.list_plugins():
                _pid = _info.manifest.id
                if _pid in self._pending_startup_plugin_ids:
                    continue
                if _info.manifest.trust_level != "builtin":
                    continue
                _persisted = _plugins_section.get(_pid, {})
                _ps = str(_persisted.get("status", "") or "")
                if _ps in ("disabled", "error"):
                    continue  # user explicitly disabled or previously failed
                self._pending_startup_plugin_ids.append(_pid)
                logger.info("发现新的内置插件，将自动启用: %s", _pid)

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
        self._taskbar_double_click_signal.connect(self._on_taskbar_double_click)
        self._update_event_signal.connect(self._on_update_event, QtCompat.QueuedConnection)
        self._download_event_signal.connect(self._on_download_event, QtCompat.QueuedConnection)
        self._install_event_signal.connect(self._on_install_event, QtCompat.QueuedConnection)
        self._config_saved_signal.connect(self._on_config_saved_event, QtCompat.QueuedConnection)
        self._config_saved_listener = self._emit_config_saved_event
        try:
            from application.events import ConfigSaved, event_bus

            event_bus.subscribe(ConfigSaved, self._config_saved_listener)
        except Exception as exc:
            logger.debug("注册配置保存事件监听失败: %s", exc, exc_info=True)

        # 安装鼠标钩子（延迟到事件循环启动后，让托盘图标先显示）
        self.mouse_hook = None
        self._mouse_paused_state = False
        self._special_app_monitors_active = False
        self._hook_reinstall_cooldown_until = 0.0
        self._hook_reinstall_failures = 0
        self._hook_reinstall_in_progress = False
        self._last_hook_runtime_stats = {}

        # 安装键盘钩子 (Alt双击检测 + Alt按住状态跟踪)
        self.keyboard_hook = None

        self._quitting = False
        self._runtime_shutdown_started = False
        self._atexit_shutdown_registered = False
        try:
            app = QApplication.instance()
            if app is not None:
                app.aboutToQuit.connect(self._shutdown_runtime_components)
        except Exception as exc:
            logger.debug("注册 Qt 退出清理失败: %s", exc, exc_info=True)
        try:
            atexit.register(self._shutdown_runtime_components)
            self._atexit_shutdown_registered = True
        except Exception as exc:
            logger.debug("注册退出清理失败: %s", exc, exc_info=True)
        self._last_synced_settings_snapshot = self._make_settings_snapshot()
        self._last_synced_popup_model_snapshot = self._make_popup_model_snapshot()
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
        self._deferred_startup_timer.setInterval(750)
        self._deferred_startup_timer.timeout.connect(self._run_deferred_startup_tasks)
        self._plugin_startup_timer = QTimer(self)
        self._plugin_startup_timer.setInterval(25)
        self._plugin_startup_timer.timeout.connect(self._enable_next_startup_plugin)

        # 内存保护
        from core.memory_guard import MemoryGuard

        self.memory_guard = MemoryGuard(critical_mb=200)  # 提高阈值到200MB
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

        # hook.dll 模式下，仅在特殊进程启动时尝试重装一次钩子
        self._known_processes = set()
        self._process_check_future = None
        self._process_check_timer = QTimer(self)
        self._process_check_timer.setInterval(10000)
        self._process_check_timer.timeout.connect(self._check_new_processes)
        self._process_check_done_signal.connect(self._on_process_check_done)

        self._hook_health_timer = QTimer(self)
        self._hook_health_timer.setInterval(3000)
        self._hook_health_timer.timeout.connect(self._check_hook_health)

        self._update_checker = None
        self._update_downloader = None
        self._update_installer = None
        self._pending_update_info = None
        self._pending_update_installer = ""
        self._update_dialog_parent = None

        # 全局快捷键管理器（Win32 RegisterHotKey，独立于 DLL 热键）
        from ui.utils.global_hotkey import Win32GlobalHotkey

        self._win32_hotkey = Win32GlobalHotkey()
        self._config_toggle_hotkey_id = 0

        logger.info("TrayApp 初始化完成，耗时 %.1f ms", (time.perf_counter() - init_start) * 1000)

    def start(self):
        """Start timers and hooks after main.py finishes callback registration."""
        if self._started:
            return
        self._started = True

        self._deferred_startup_timer.start()
        if self._pending_startup_plugin_ids:
            self._plugin_startup_timer.start()
        self._memory_check_timer.start()

        # 延迟注册全局快捷键 Ctrl+Shift+L（等待事件循环就绪）
        QTimer.singleShot(200, self._register_config_toggle_hotkey)

        if not self._safe_mode:
            logger.info("安装鼠标钩子...")
            QTimer.singleShot(0, self._install_hook)
            logger.info("安装键盘钩子...")
            QTimer.singleShot(0, self._install_keyboard_hook_and_hotkey)
            self._update_special_app_monitors(reset_state=True)
            self._hook_health_timer.start()
            try:
                if getattr(self.data_manager.get_settings(), "auto_update_enabled", False):
                    QTimer.singleShot(5000, self._init_update_system)
            except Exception as exc:
                logger.debug("获取设置: %s", exc, exc_info=True)
        else:
            logger.info("安全模式：鼠标钩子已禁用")
            logger.info("安全模式：键盘钩子已禁用")
            logger.info("安全模式：自动更新检查已禁用")

        self._mark_activity("startup")

    def _emit_config_saved_event(self, event):
        try:
            self._config_saved_signal.emit(event)
        except RuntimeError as exc:
            logger.debug("配置保存事件转发失败: %s", exc, exc_info=True)

    def _on_config_saved_event(self, event):
        if not bool(getattr(event, "trigger_settings_preserved", False)):
            return
        if bool(getattr(self, "_runtime_shutdown_started", False)):
            return
        try:
            logger.info("检测到触发设置由磁盘新值恢复，重新应用鼠标钩子配置")
            self._apply_mouse_hook_settings()
        except Exception as exc:
            logger.debug("恢复触发设置后重新应用鼠标钩子失败: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # DPI change handler (WM_DPICHANGED / PerMonitorV2)
    # ------------------------------------------------------------------

    def _on_system_dpi_changed(self, new_scale_percent: int):
        """Handle system DPI change when a window moves to a different monitor.

        Only auto-adjusts when the user has *not* manually set a custom
        UI scale (i.e. the saved value is still the default or matches
        the previously auto-detected value).  If the user has explicitly
        chosen a scale, we respect that choice.
        """
        from ui.utils.ui_scale import DEFAULT_SCALE_PERCENT

        try:
            current = getattr(
                self.data_manager.get_settings(),
                "ui_scale_percent",
                DEFAULT_SCALE_PERCENT,
            )
        except Exception:
            current = DEFAULT_SCALE_PERCENT

        # Only auto-adjust if the user hasn't manually set scale
        if current == DEFAULT_SCALE_PERCENT or (
            self._last_auto_detected is not None and current == self._last_auto_detected
        ):
            logger.info(
                "Auto-adjusting UI scale to %d%% (was %d%%)",
                new_scale_percent,
                current,
            )
            self._last_auto_detected = new_scale_percent
            self.data_manager.update_settings(ui_scale_percent=new_scale_percent)
            if hasattr(self, "apply_ui_scale_and_reopen_config"):
                self.apply_ui_scale_and_reopen_config(new_scale_percent)
        else:
            logger.debug(
                "System DPI changed to %d%% but user has manually set %d%% — respecting user choice",
                new_scale_percent,
                current,
            )

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
            "ui_scale_percent": int(getattr(settings, "ui_scale_percent", 100) or 100),
            # 布局参数（用于检测变更后刷新弹窗）
            "cols": int(getattr(settings, "cols", 4) or 4),
            "cell_size": int(getattr(settings, "cell_size", 72) or 72),
            "icon_size": int(getattr(settings, "icon_size", 48) or 48),
        }

    def _make_popup_model_snapshot(self) -> tuple:
        """Snapshot launcher folders/items so settings-only changes can avoid full data refresh."""
        try:
            folders = []
            for folder in list(getattr(getattr(self.data_manager, "data", None), "folders", []) or []):
                if bool(getattr(folder, "is_icon_repo", False)) or getattr(folder, "id", "") == "icon_repo":
                    continue
                items = []
                for item in list(getattr(folder, "items", []) or []):
                    tags = tuple(getattr(item, "tags", []) or [])
                    items.append(
                        (
                            getattr(item, "id", ""),
                            getattr(item, "name", ""),
                            getattr(item, "type", ""),
                            getattr(item, "order", 0),
                            bool(getattr(item, "enabled", True)),
                            getattr(item, "icon_path", ""),
                            getattr(item, "target_path", ""),
                            getattr(item, "target_args", ""),
                            getattr(item, "working_dir", ""),
                            getattr(item, "url", ""),
                            getattr(item, "command", ""),
                            getattr(item, "command_type", ""),
                            getattr(item, "trigger_mode", ""),
                            getattr(item, "alias", ""),
                            tags,
                        )
                    )
                folders.append(
                    (
                        getattr(folder, "id", ""),
                        getattr(folder, "name", ""),
                        getattr(folder, "order", 0),
                        bool(getattr(folder, "is_dock", False)),
                        getattr(folder, "linked_path", ""),
                        tuple(items),
                    )
                )
            return tuple(folders)
        except Exception as exc:
            logger.debug("创建弹窗数据快照失败: %s", exc, exc_info=True)
            return ()

    def _apply_win10_shadow_settings(self, source=None):
        try:
            if source is None:
                source = self.data_manager.get_settings()
            if isinstance(source, dict):
                shadow_size = source.get("shadow_size", 0)
                shadow_distance = source.get("shadow_distance", 0)
            else:
                shadow_size = getattr(source, "shadow_size", 0)
                shadow_distance = getattr(source, "shadow_distance", 0)

            from ui.utils.window_effect import configure_win10_window_shadow

            configure_win10_window_shadow(shadow_size=shadow_size, shadow_distance=shadow_distance)
        except Exception as exc:
            logger.debug("同步 Win10 全局阴影设置失败: %s", exc, exc_info=True)

    def _refresh_popup_after_settings_change(self, *, model_changed: bool, preload_icons: bool = False):
        popup = getattr(self, "popup_window", None)
        if popup is None:
            return

        try:
            _ = popup.width()
        except RuntimeError:
            self.popup_window = None
            return
        except Exception:
            self.popup_window = None
            return

        try:
            if model_changed:
                pos = popup.geometry().center()
                popup.refresh_data(pos.x(), pos.y(), refresh_selection=False, reposition=False)
            else:
                signal = getattr(popup, "settings_updated", None)
                if signal is not None and callable(getattr(signal, "emit", None)):
                    signal.emit()
                elif hasattr(popup, "_on_settings_updated"):
                    popup._on_settings_updated()

            if preload_icons and hasattr(popup, "preload_visible_icons"):
                popup.preload_visible_icons(force=True, all_pages=True)
        except RuntimeError:
            self.popup_window = None
        except Exception as e:
            logger.error("刷新弹窗失败: %s", e)

    def _apply_pending_settings_changes(self):
        if not self._pending_settings_sync:
            return
        self._pending_settings_sync = False

        prev = self._last_synced_settings_snapshot or {}
        cur = self._make_settings_snapshot()
        self._last_synced_settings_snapshot = cur
        prev_popup_model = getattr(self, "_last_synced_popup_model_snapshot", None)
        cur_popup_model = self._make_popup_model_snapshot()
        self._last_synced_popup_model_snapshot = cur_popup_model
        popup_model_changed = prev_popup_model is not None and cur_popup_model != prev_popup_model

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

        shadow_changed = cur.get("shadow_size") != prev.get("shadow_size") or cur.get("shadow_distance") != prev.get(
            "shadow_distance"
        )
        if shadow_changed:
            self._apply_win10_shadow_settings(cur)

        ui_scale_changed = cur.get("ui_scale_percent") != prev.get("ui_scale_percent")
        self._refresh_popup_after_settings_change(
            model_changed=popup_model_changed,
            preload_icons=ui_scale_changed,
        )

    def _apply_initial_settings(self):
        """应用初始设置"""
        settings = self.data_manager.get_settings()
        self._apply_win10_shadow_settings(settings)

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
        app.setDoubleClickInterval(interval)  # type: ignore[unused-ignore, attr-defined]

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
            import tempfile

            packaged = is_packaged_runtime()
            exe = str(app_executable() if packaged else sys.executable)
            logger.info(f"sys.executable = {exe}")
            logger.info(f"packaged_runtime = {packaged}")
            logger.info(f"sys.argv[0] = {sys.argv[0]}")

            logger.info(f"最终检测: packaged={packaged}, exe={exe}")

            if packaged:
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
                process_runtime.popen(["wscript.exe", vbs_file], cwd=cwd, creationflags=0x08000000, shell=False)

            else:
                # 开发模式：使用 VBScript 无窗口延迟启动
                cwd = str(app_root())
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
                process_runtime.popen(["wscript.exe", vbs_file], cwd=cwd, creationflags=0x08000000, shell=False)

            # 立即退出当前进程
            logger.info("准备退出当前进程...")
            QTimer.singleShot(100, QApplication.quit)

        except Exception as e:
            logger.exception("重新启动失败")
            # TrayApp 是 QObject，不能作为 QDialog 的 parent
            # 尝试使用配置窗口作为 parent，如果没有则使用 None
            parent = self.config_window if self.config_window else None
            ThemedMessageBox.critical(parent, tr("重启失败"), tr("无法重新启动程序\n\n{error}", error=str(e)))

    def _register_config_toggle_hotkey(self):
        """注册全局快捷键 Ctrl+Shift+L 用于切换配置窗口"""
        try:
            hotkey_id = self._win32_hotkey.register("Ctrl+Shift+L", self._toggle_config)
            if hotkey_id:
                self._config_toggle_hotkey_id = hotkey_id
                logger.info("全局快捷键 Ctrl+Shift+L 已注册 (id=%d)", hotkey_id)
            else:
                logger.warning("全局快捷键 Ctrl+Shift+L 注册失败，可能已被其他程序占用")
        except Exception as exc:
            logger.error("注册全局快捷键失败: %s", exc, exc_info=True)

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
            process_runtime.startfile(path)
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
            process_runtime.startfile(path)
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
