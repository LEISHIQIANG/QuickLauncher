"""
弹出启动器窗口
"""

import logging
from collections import OrderedDict

try:
    import win32com.client  # noqa: F401
    import win32gui

    HAS_WIN32_SHELL = True
except ImportError:
    HAS_WIN32_SHELL = False

from core import DataManager
from core.windows_uipi import allow_drag_drop_for_widget
from qt_compat import (
    QFont,
    QImage,
    QTimer,
    QWidget,
    pyqtProperty,
    pyqtSignal,
)
from ui.launcher_popup.glass_background import GlassBackgroundError, GlassBackgroundRenderer
from ui.launcher_popup.popup_background import PopupBackgroundMixin
from ui.launcher_popup.popup_command_result import PopupCommandResultMixin
from ui.launcher_popup.popup_data_refresh import PopupDataRefreshMixin
from ui.launcher_popup.popup_drag_drop import PopupDragDropMixin
from ui.launcher_popup.popup_events import PopupEventsMixin
from ui.launcher_popup.popup_icons import PopupIconMixin
from ui.launcher_popup.popup_item_execution import PopupItemExecutionMixin
from ui.launcher_popup.popup_renderer import PopupRendererMixin
from ui.launcher_popup.popup_search import PopupSearchMixin
from ui.launcher_popup.popup_window_animation import PopupWindowAnimationMixin
from ui.launcher_popup.popup_window_effect import PopupLayoutMixin, PopupWindowEffectMixin
from ui.launcher_popup.popup_window_helpers import IconFlashOverlay
from ui.launcher_popup.popup_window_hwnd import PopupWindowHwndMixin
from ui.launcher_popup.popup_window_lifecycle import PopupWindowLifecycleMixin
from ui.utils.animations import DisposableWidget
from ui.utils.interruptible_animation import set_precise_timer, stop_named_animations
from ui.utils.ui_scale import sp
from ui.utils.window_effect import WindowEffect, is_glass_background_supported

logger = logging.getLogger(__name__)

try:
    from core import ShortcutExecutor

    HAS_EXECUTOR = True
except ImportError:
    HAS_EXECUTOR = False


class LauncherPopup(
    PopupWindowLifecycleMixin,
    PopupWindowAnimationMixin,
    PopupWindowHwndMixin,
    PopupEventsMixin,
    PopupDataRefreshMixin,
    PopupCommandResultMixin,
    PopupBackgroundMixin,
    PopupRendererMixin,
    PopupDragDropMixin,
    PopupIconMixin,
    PopupSearchMixin,
    PopupWindowEffectMixin,
    PopupLayoutMixin,
    DisposableWidget,
    PopupItemExecutionMixin,
    QWidget,
):
    """弹出启动器窗口"""

    # Owner-Disposable: 列出本 widget 持有的 QPropertyAnimation 属性名，
    # DisposableWidget 会在 hide/close 事件中通过 interruptible_animation
    # 统一停止。命名必须与 popup_window_animation.py / popup_command_result.py
    # 等模块的 setattr 一致。
    _animation_names: tuple = (
        "anim_group",
        "hide_anim_group",
        "reveal_anim",
        "opacity_anim",
        "hide_opacity_anim",
        "hide_reveal_anim",
    )

    # 启动错误信号 (name, error_msg)
    execution_error = pyqtSignal(str, str)
    command_panel_result_ready = pyqtSignal(object, str, str)
    plugin_search_results_ready = pyqtSignal(int, str, object)

    # 全局背景缓存 (path, blur, width, height) -> QPixmap
    # 使用 OrderedDict 实现 LRU 缓存，限制大小防止内存泄漏
    _global_bg_cache = OrderedDict()  # type: ignore[var-annotated]
    _MAX_BG_CACHE = 3  # 降低到3个，减少内存占用

    # 背景加载完成信号
    bg_loaded_signal = pyqtSignal(QImage, tuple, int)

    # 设置更新信号
    settings_updated = pyqtSignal()

    # 文件夹同步完成信号
    folder_sync_finished = pyqtSignal()

    SELECTED_FILES_CACHE_TTL_SECONDS = 8.0

    def __init__(
        self,
        data_manager: DataManager,
        x: int,
        y: int,
        tray_app=None,
        selection_trigger_pos=None,
        trigger_method: str = "mouse",
        capture_selection: bool = True,
    ):
        super().__init__()

        # 保存 TrayApp 引用
        self._drag_drop_compat_applied = False
        self.tray_app = tray_app
        self._lifecycle_generation = 0
        self._closing = False
        self._visibility_animation_generation = 0

        # 连接信号
        self.bg_loaded_signal.connect(self._on_bg_loaded)
        self.execution_error.connect(self._on_execution_error)
        self.command_panel_result_ready.connect(self._on_command_panel_result_ready)
        self.plugin_search_results_ready.connect(self._on_plugin_search_results_ready)
        self.folder_sync_finished.connect(self._on_folder_sync_finished)
        self._is_loading_bg = False
        self._pending_bg_params = None  # type: ignore[assignment]
        self._bg_load_timer = QTimer(self)
        self._bg_load_timer.setSingleShot(True)
        self._bg_load_timer.timeout.connect(self._run_bg_load_request)
        self._bg_load_seq = 0
        self._bg_loading_seq = 0

        # ===== 保存当前前台窗口，用于快捷键执行后恢复焦点 =====
        if HAS_EXECUTOR:
            try:
                ShortcutExecutor.save_foreground_window()
            except Exception as e:
                logger.debug(f"保存前台窗口失败: {e}")
        # ===== 保存结束 =====

        self.data_manager = data_manager
        self.settings = data_manager.get_settings()

        # 获取数据
        self.pages = [f for f in data_manager.data.get_pages() if not getattr(f, "is_icon_repo", False)]
        dock = data_manager.data.get_dock()
        self.dock_items = dock.items if dock else []
        self._model_revision = data_manager.get_runtime_revision()

        # 找到"常用"页面索引
        self.default_page_index = 0
        for i, page in enumerate(self.pages):
            if page.name == "常用" or page.id == "default":
                self.default_page_index = i
                break

        # 当前页
        self.current_page = 0
        if self.pages:
            self.current_page = min(self.settings.last_page_index, len(self.pages) - 1)
            self.current_page = max(0, self.current_page)

        # 状态
        self.is_pinned = False
        self.hover_index = -1
        self.dock_hover_index = -1
        self._executing = False
        self._launched_app = False  # 是否刚启动了外部程序（跳过焦点恢复）
        self._win10_dwm_blur_active = False

        # 指示器动画
        self._indicator_pos = float(self.current_page)

        # 翻页滑动动画
        self._prev_page = self.current_page
        self._page_slide_progress = 1.0  # 1.0 = 动画完成
        self._page_slide_dir = 1  # +1 向左滑, -1 向右滑

        # 平滑滚动状态
        self._page_offset = float(self.current_page)  # 当前页面偏移量（浮点数）
        self._page_position = float(self.current_page)  # 动画当前位置（浮点数）
        self._target_page = self.current_page  # 目标页面
        self._last_wheel_time = 0.0
        self._last_wheel_page_time = 0.0
        self._last_wheel_direction = 0
        self._wheel_accumulator = 0.0
        self._wheel_speed = 1.0  # 兼容旧状态名，滚轮翻页不再用它做加速

        # 动画进度 (0.0 到 1.0)
        self._reveal_progress = 0.0
        self._is_hiding = False

        self._icon_pixmap_cache = OrderedDict()
        self._default_icon_cache = OrderedDict()
        self._visible_icons_preloaded = False
        self._all_page_icons_preloaded = False
        self._first_show_ready = False
        self._blank_refresh_in_progress = False
        self._blank_refresh_pending = False
        self._blank_refresh_worker_started = False
        self._blank_refresh_generation = 0
        self._blank_refresh_requested_at = 0.0
        self._blank_refresh_not_before = 0.0
        self._icon_flash_overlay = IconFlashOverlay(self)
        self._sync_worker = None
        self._folder_sync_refresh_seq = 0
        self._pending_last_page_index = None  # type: ignore[assignment]
        self._last_page_save_timer = None  # type: ignore[unused-ignore, assignment]
        self._label_font = QFont()

        # ===== 选中文件状态 =====
        self._selected_files = []
        self._file_thread = None  # type: ignore[assignment]
        self._pending_file_check_context = None  # type: ignore[assignment]
        self._file_check_seq = 0
        self._selected_files_source_hwnd = 0
        self._selected_files_request_hwnd = 0
        self._selected_files_request_started_at = 0.0
        self._selected_files_captured_at = 0.0
        self._selected_files_trigger_pos = None
        self._selected_files_context = None  # type: ignore[assignment]
        self._selected_files_status = "idle"
        try:
            if hasattr(self, "_request_page_animation_update"):
                self._request_page_animation_update()
            else:
                self.update()
        except Exception as exc:
            logger.debug("更新窗口失败: %s", exc, exc_info=True)

        # 立即捕获当前环境 (HWND)
        current_hwnd = 0
        if capture_selection and HAS_WIN32_SHELL:
            try:
                current_hwnd = win32gui.GetForegroundWindow()
            except Exception as e:
                logger.debug("Failed to capture foreground window during init: %s", e)
        self._selected_files_trigger_pos = selection_trigger_pos or (int(x), int(y))

        # 异步检测选中文件
        if capture_selection:
            self._start_file_check(current_hwnd, trigger_method=trigger_method)

        # ===== 拖放相关状态 =====
        self._drag_hover_index = -1  # 拖放时悬停的图标索引
        self._drag_dock_hover_index = -1  # 拖放时悬停的 Dock 图标索引
        self._is_dragging = False  # 是否正在拖放
        # ===== 拖放状态结束 =====

        # ===== 固定窗口拖动状态 =====
        self._pinned_window_drag_pending = False
        self._pinned_window_drag_active = False
        self._pinned_window_drag_start_global = None
        self._pinned_window_drag_window_pos = None
        self._pinned_window_drag_offset = None
        # ===== 固定窗口拖动状态结束 =====

        # 背景缓存
        self._bg_cache = None  # type: ignore[unused-ignore, assignment]
        self._last_bg_params = None
        self._cached_bg_path = None
        self._win10_fallback_bg = None  # Win10回退背景，避免重新显示时闪烁
        self._last_effect_state = None
        self._glass_renderer = GlassBackgroundRenderer(self)

        # 布局参数
        self._base_padding = sp(8)
        self.padding = self._base_padding
        self.cols = self.settings.cols
        self.cell_size = sp(self.settings.cell_size)
        self.icon_size = sp(self.settings.icon_size)
        # Font and row height are finalized together in _calculate_fixed_size().
        self.row_spacing = sp(4)
        self._update_grid_text_metrics()

        self.dock_height = self._calculate_dock_height()
        self.window_effect = WindowEffect()

        # 设置窗口
        self._setup_window()
        calculated_width, calculated_height = self._calculate_fixed_size()
        # 优先用 _center_to 的返回值（精确计算位置），不要回退到 (x, y) 鼠标点
        positioned = self._center_to(x, y, calculated_width, calculated_height)
        if positioned is not None:
            # 同步 HWND 位置：避免 Qt 内部布局逻辑把窗口拉回鼠标点
            try:
                import ctypes

                hwnd = int(self.winId())
                ctypes.windll.user32.SetWindowPos(hwnd, 0, positioned[0], positioned[1], 0, 0, 0x0001 | 0x0010)
            except Exception as exc:
                logger.debug("__init__ 阶段同步 HWND 位置失败: %s", exc)

        self.setMouseTracking(True)
        self.settings_updated.connect(self._on_settings_updated)

        # ===== 启用拖放 =====
        self.setAcceptDrops(True)
        # ===== 启用拖放结束 =====

        self._indicator_timer = QTimer(self)
        self._indicator_timer.setInterval(16)
        set_precise_timer(self._indicator_timer, owner="LauncherPopup._indicator_timer")
        self._indicator_timer.timeout.connect(self._tick_indicator)

        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setInterval(200)
        self._auto_close_timer.timeout.connect(self._check_close)

        # 延迟隐藏计时器
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        # ===== 搜索与动画预热状态初始化 =====
        self.search_query = ""
        self.search_results = []
        self.search_selected_index = -1
        self._plugin_search_seq = 0
        self.search_cursor_pos = 0
        self.search_selection_anchor = None
        self._search_preedit_text = ""
        self._search_forced_active = False
        self._search_drag_selecting = False
        self._search_drag_anchor = 0
        self._search_scroll_x = 0
        self._page_header_scroll_x = 0.0
        self._page_header_target_scroll_x = 0.0
        self._page_tab_widths = []
        self._page_tab_x = []
        self._page_tab_total_width = 0.0
        self._search_cursor_visible = True
        self._search_cursor_timer = QTimer(self)
        self._search_cursor_timer.setInterval(530)
        self._search_cursor_timer.timeout.connect(self._toggle_search_cursor)
        self._search_reveal_progress = 0.0
        self._search_target_progress = 0.0
        self._search_hide_geometry_pending = False
        self._search_mask_cleared = True
        self._search_mask_cache_key = None
        self._search_body_anchor_y = 0
        self._search_anim_duration_ms = 180
        self._search_anim_from_progress = 0.0
        self._search_anim_started_at = 0.0
        self._search_anim_last_ts = 0.0
        self._search_anim_timer = QTimer(self)
        self._search_anim_timer.setInterval(16)
        set_precise_timer(self._search_anim_timer, owner="LauncherPopup._search_anim_timer")
        self._search_anim_timer.timeout.connect(self._tick_search_reveal)
        self._page_icon_warm_queue = []  # type: ignore[var-annotated]
        self._page_icon_warm_keys = set()  # type: ignore[var-annotated]
        self._page_icon_warm_timer = None
        self._page_render_cache = {}  # type: ignore[var-annotated]

        logger.info(f"弹窗创建: {self.width()}x{self.height()}")

    def getRevealProgress(self):
        """获取动画进度"""
        return self._reveal_progress

    def setRevealProgress(self, value):
        """设置动画进度并触发重绘"""
        self._reveal_progress = value
        self.update()

    revealProgress = pyqtProperty(float, getRevealProgress, setRevealProgress)

    def _prepare_selected_background(self) -> bool:
        """Prepare the selected background before the popup becomes visible."""
        if getattr(self.settings, "bg_mode", "theme") != "glass":
            self._glass_renderer.stop(destroy=True)
            return True
        # 防御性回退：系统不支持 WDA_EXCLUDEFROMCAPTURE 时（例如旧版 Win10），
        # 即便配置里残留 bg_mode="glass"（旧机器迁移 / 手动改 data.json），
        # 也不要尝试启动玻璃背景渲染线程，避免触发托盘错误气泡。
        if not is_glass_background_supported():
            logger.warning("当前系统不支持玻璃背景，bg_mode='glass' 已回退为 'theme'")
            self._glass_renderer.stop(destroy=True)
            try:
                self.data_manager.update_settings(bg_mode="theme")
                # 同步本对象的内存快照，避免每次 show 都重跑一次回退逻辑。
                self.settings = self.data_manager.get_settings()
            except Exception as exc:
                logger.debug("回退 bg_mode 失败: %s", exc, exc_info=True)
            return True
        try:
            self._glass_renderer.prepare()
            return True
        except GlassBackgroundError as exc:
            self._handle_glass_background_failure(str(exc), hide_popup=False)
            return False

    def _handle_glass_background_failure(self, message: str, *, hide_popup: bool = True) -> None:
        logger.error("玻璃背景不可用，拒绝显示弹窗: %s", message)
        try:
            self._glass_renderer.stop(destroy=True)
        except Exception:
            logger.debug("停止玻璃背景失败", exc_info=True)
        if hide_popup and self.isVisible():
            self.hide()
        try:
            tray_icon = getattr(getattr(self, "tray_app", None), "tray_icon", None)
            if tray_icon is not None:
                tray_icon.showMessage("QuickLauncher", f"玻璃背景启动失败：{message}")
        except Exception:
            logger.debug("显示玻璃背景失败通知失败", exc_info=True)

    def showEvent(self, event):
        self._closing = False
        generation = self._next_lifecycle_generation()
        # 停止隐藏动画和重置状态
        self._is_hiding = False
        stop_named_animations(self, "hide_anim_group")
        if not self._drag_drop_compat_applied:
            self._drag_drop_compat_applied = True
            self._defer_lifecycle_callback(0, allow_drag_drop_for_widget, self, generation=generation)

        try:
            # 延迟启动，避免弹窗刚显示时鼠标尚未进入窗口就触发关闭
            if not self._auto_close_timer.isActive():
                self._defer_lifecycle_callback(300, self._start_auto_close_timer_if_visible, generation=generation)
            # 延迟应用窗口特效，确保窗口尺寸和DPI已稳定
            self._defer_lifecycle_callback(50, self._update_window_effect, generation=generation)
        except Exception as exc:
            logger.debug("延迟生命周期回调失败: %s", exc, exc_info=True)

        # 启动出现动画
        self._start_show_animation()

        # ===== v2.6.6.0 修复：弹窗显示时释放残留的修饰键 =====
        # 用户可能通过全局热键（如中键）唤起弹窗，此时某些修饰键可能残留
        # 在这里延迟释放，避免影响后续图标点击时的快捷键执行
        try:
            if HAS_EXECUTOR:
                self._defer_lifecycle_callback(50, self._release_residual_modifiers, generation=generation)
        except Exception as exc:
            logger.debug("延迟释放残留修饰键失败: %s", exc, exc_info=True)
        # ===== 修复结束 =====

        # 延迟预热所有页面的动画缓存，确保后续翻页动画图标正常显示
        self._defer_lifecycle_callback(200, self._preload_animation_pages, generation=generation)

        super().showEvent(event)

        # 注册 HWND：仅排除 LauncherPopup 自身，避免配置窗口等 QuickLauncher
        # 窗口被错误地当作"自身窗口"而无法作为焦点恢复目标保存。
        self._register_popup_hwnd()

    def hideEvent(self, event):
        generation = self._next_lifecycle_generation()
        overlay = getattr(self, "_icon_flash_overlay", None)
        if overlay is not None:
            overlay.stop()
        self._stop_lifecycle_timers()
        try:
            self._reset_search_state()
        except Exception as exc:
            logger.debug("重置搜索状态失败: %s", exc, exc_info=True)
        self._search_body_anchor_y = 0
        try:
            if self._auto_close_timer.isActive():
                self._auto_close_timer.stop()
        except Exception as exc:
            logger.debug("停止自动关闭定时器失败: %s", exc, exc_info=True)
        self._release_background_cache()
        self._glass_renderer.stop()

        # ===== 修复 Win10 左键选择失效 bug =====
        # 弹窗隐藏时必须主动恢复之前的前台窗口焦点
        # 否则可能导致系统焦点状态异常，表现为左键无法选择桌面图标等
        # 这个问题在 Win10 上更容易出现
        try:
            if HAS_EXECUTOR and not self._launched_app:
                # 延迟一小段时间再恢复焦点，确保隐藏动画完成
                self._defer_lifecycle_callback(50, self._restore_focus_safe, generation=generation)
            self._launched_app = False
        except Exception as exc:
            logger.debug("恢复焦点失败: %s", exc, exc_info=True)
        # ===== 修复结束 =====

        super().hideEvent(event)

        # 注销 HWND：避免影响下一次 save_foreground_window 的判断
        self._unregister_popup_hwnd()

    def closeEvent(self, event):
        self._closing = True
        self._next_lifecycle_generation()
        self._stop_lifecycle_timers()
        try:
            self._release_background_cache()
        except Exception as exc:
            logger.debug("释放背景缓存失败: %s", exc, exc_info=True)
        try:
            self._glass_renderer.close()
        except Exception as exc:
            logger.debug("关闭玻璃背景失败: %s", exc, exc_info=True)
        try:
            self.stop_background_threads()
        except Exception as exc:
            logger.debug("停止弹窗后台线程失败: %s", exc, exc_info=True)
        try:
            shutdown_service = getattr(self, "_shutdown_popup_execution_service", None)
            if callable(shutdown_service):
                shutdown_service()
        except Exception as exc:
            logger.debug("关闭弹窗执行服务失败: %s", exc, exc_info=True)
        super().closeEvent(event)

        # 注销 HWND：避免影响下一次 save_foreground_window 的判断
        self._unregister_popup_hwnd()

    def refresh_data(
        self,
        x: int = None,  # type: ignore[assignment]
        y: int = None,  # type: ignore[assignment]
        refresh_selection: bool = True,
        force: bool = False,
        reposition: bool = True,
        preserve_search_state: bool = False,
        selection_trigger_pos=None,
        trigger_method: str = "mouse",
        skip_effect: bool = False,
    ):
        """刷新数据并重置位置"""
        preserved_search_state = None
        if preserve_search_state:
            current_query = getattr(self, "search_query", "") or ""
            current_forced_active = bool(getattr(self, "_search_forced_active", False))
            if current_query or current_forced_active:
                preserved_search_state = {
                    "query": current_query,
                    "cursor_pos": int(getattr(self, "search_cursor_pos", len(current_query)) or 0),
                    "selection_anchor": getattr(self, "search_selection_anchor", None),
                    "forced_active": current_forced_active,
                    "scroll_x": int(getattr(self, "_search_scroll_x", 0) or 0),
                }

        self._search_body_anchor_y = 0
        self.search_query = ""
        self.search_results = []
        self.search_selected_index = -1
        self.search_cursor_pos = 0
        self.search_selection_anchor = None
        self._search_preedit_text = ""
        self._search_forced_active = bool(getattr(self.settings, "search_default_active", False))
        self._search_drag_selecting = False
        self._search_drag_anchor = 0
        self._search_scroll_x = 0
        self._search_cursor_visible = True
        try:
            timer = self.__dict__.get("_search_cursor_timer")
            if timer is not None:
                timer.stop()
        except Exception as exc:
            logger.debug("停止搜索光标定时器失败: %s", exc, exc_info=True)
        self._search_reveal_progress = 1.0 if self._search_forced_active else 0.0
        self._search_target_progress = 1.0 if self._search_forced_active else 0.0
        self._search_hide_geometry_pending = False
        if preserved_search_state is not None:
            self.search_query = preserved_search_state["query"]  # type: ignore[assignment]
            self.search_cursor_pos = max(0, min(preserved_search_state["cursor_pos"], len(self.search_query)))  # type: ignore[type-var]
            selection_anchor = preserved_search_state["selection_anchor"]
            if selection_anchor is not None:
                selection_anchor = max(0, min(int(selection_anchor), len(self.search_query)))
            self.search_selection_anchor = selection_anchor
            self._search_forced_active = preserved_search_state["forced_active"]
            self._search_scroll_x = preserved_search_state["scroll_x"]
            self._search_reveal_progress = 1.0
            self._search_target_progress = 1.0
        try:
            self.clearMask()
        except Exception as exc:
            logger.debug("清除窗口遮罩失败: %s", exc, exc_info=True)

        current_revision = self.data_manager.get_runtime_revision()
        model_revision_changed = current_revision != getattr(self, "_model_revision", -1)
        revision_changed = force or model_revision_changed
        self._model_revision = current_revision
        if revision_changed:
            page_cache = getattr(self, "_page_pixmap_cache", None)
            if page_cache is not None:
                page_cache.clear()
            self._visible_icons_preloaded = False
            self._all_page_icons_preloaded = False
            self._first_show_ready = False
            self._cached_bg_path = None
            self._bg_cache = None  # type: ignore[unused-ignore, assignment]

        # 记录之前的图标数量用于比较
        prev_item_count = 0
        if self.pages and self.default_page_index < len(self.pages):
            prev_item_count = len(self.pages[self.default_page_index].items)
        prev_dock_count = len(self.dock_items)
        prev_page_count = len(self.pages) if self.pages else 0

        # 重新获取数据
        self.pages = [f for f in self.data_manager.data.get_pages() if not getattr(f, "is_icon_repo", False)]
        self._update_page_header_layout()
        dock = self.data_manager.data.get_dock()
        self.dock_items = dock.items if dock else []

        # 重新查找"常用"页面索引（以防页面结构变化）
        self.default_page_index = 0
        for i, page in enumerate(self.pages):
            if page.name == "常用" or page.id == "default":
                self.default_page_index = i
                break

        # 检测图标数量是否变化
        current_item_count = 0
        if self.pages and self.default_page_index < len(self.pages):
            current_item_count = len(self.pages[self.default_page_index].items)
        current_dock_count = len(self.dock_items)
        current_page_count = len(self.pages) if self.pages else 0

        data_structure_changed = (
            prev_item_count != current_item_count
            or prev_dock_count != current_dock_count
            or prev_page_count != current_page_count
        )
        if data_structure_changed:
            self._visible_icons_preloaded = False
            self._all_page_icons_preloaded = False
            self._first_show_ready = False

        # 修正 current_page 边界（页面数量可能变化）
        if self.pages:
            self.current_page = min(self.current_page, len(self.pages) - 1)
            self.current_page = max(0, self.current_page)
            # 重置滚动动画状态以匹配新的 current_page
            self._page_offset = float(self.current_page)
            self._target_page = self.current_page

        # 1. 立即清空旧状态
        if refresh_selection:
            self._clear_selected_files_context()

        # 2. 立即捕获当前环境 (HWND)，这是唯一必须同步做的
        current_hwnd = 0
        if refresh_selection and HAS_WIN32_SHELL:
            try:
                current_hwnd = win32gui.GetForegroundWindow()
            except Exception as e:
                logger.debug("Failed to capture foreground window before show: %s", e)
            if selection_trigger_pos is not None:
                self._selected_files_trigger_pos = selection_trigger_pos
            elif x is not None and y is not None:
                self._selected_files_trigger_pos = (int(x), int(y))

        # 3. 延迟执行耗时的 COM 操作 (文件查找)
        # 使用线程处理，避免阻塞 UI
        # 3. 延迟执行耗时的 COM 操作 (文件查找)
        # 使用线程处理，避免阻塞 UI
        if refresh_selection:
            self._start_file_check(current_hwnd, trigger_method=trigger_method)

        # 4. 始终重新计算窗口大小 (因为 reload 移除后，prev_item_count 比较不再可靠)
        # 更新设置参数
        self.settings = self.data_manager.get_settings()
        self.cols = self.settings.cols
        self.cell_size = sp(self.settings.cell_size)
        self.icon_size = sp(self.settings.icon_size)
        self._update_grid_text_metrics()
        if preserved_search_state is not None:
            self._ensure_search_cursor_visible()
            self._restart_search_cursor_blink()
            self._refresh_search_results()

        if reposition:
            if x is None or y is None:
                center = self.geometry().center()
                x = int(center.x())
                y = int(center.y())

            # === 修复多屏 DPI 切换核心逻辑 + 跨屏显示 bug ===
            # 关键修复：先计算目标位置，再用计算结果做 SetWindowPos。
            #
            # 旧逻辑的 bug：
            #   1. SetWindowPos(hwnd, 0, mouse_x, mouse_y, ...)  ← 把 HWND 的
            #      左上角定位到鼠标位置（不是中心！）
            #   2. _center_to 之后再 move 到居中位置
            #   在 SetWindowPos 和 _center_to 之间，HWND 的实际位置是
            #   "鼠标点在左上角"——当鼠标在多屏边界时，HWND 就会跨屏显示。
            #
            # 新逻辑：先把 _center_to 跑一遍拿到正确的 (left, top)，
            # 再用这个 (left, top) 做 SetWindowPos，确保 HWND 从一开始就
            # 在正确的位置。WM_DPICHANGED 仍会被触发（HWND 移动到了
            # 目标屏幕所在的 monitor），DPI 上下文正确更新。
            self.dock_height = self._calculate_dock_height()
            calculated_width, calculated_height = self._calculate_fixed_size()
            positioned = self._center_to(x, y, calculated_width, calculated_height)
            if positioned is None:
                positioned = (int(x), int(y))

            try:
                import ctypes

                hwnd = int(self.winId())
                target_left, target_top = positioned
                # SWP_NOSIZE=1, SWP_NOACTIVATE=16, SWP_FRAMECHANGED=32
                ctypes.windll.user32.SetWindowPos(hwnd, 0, target_left, target_top, 0, 0, 0x0001 | 0x0010 | 0x0020)
            except Exception:
                self.move(*positioned)

            # 兜底：SetWindowPos + WM_DPICHANGED 可能让 Qt 内部重新布局
            # 调整窗口位置；再次 _center_to 确保最终位置正确。
            # 这是幂等操作——如果位置已经正确，self.move() 是 no-op。
            self._center_to(x, y, calculated_width, calculated_height)

            # 让 Qt 在下一轮事件循环完成 DPI/窗口状态同步，避免打开路径阻塞 UI。
            try:
                if hasattr(self, "_schedule_window_effect_update"):
                    self._schedule_window_effect_update(0)
                else:
                    QTimer.singleShot(0, self._update_window_effect)
            except Exception as exc:
                logger.debug("调度窗口特效刷新失败: %s", exc, exc_info=True)
        else:
            self.dock_height = self._calculate_dock_height()
            calculated_width, calculated_height = self._calculate_fixed_size()

        # 调度窗口特效刷新，避免打开/刷新链路同步重建 DWM/region。
        if not skip_effect:
            try:
                if hasattr(self, "_schedule_window_effect_update"):
                    self._schedule_window_effect_update(0)
                else:
                    QTimer.singleShot(0, self._update_window_effect)
            except Exception as exc:
                logger.debug("调度窗口特效刷新失败: %s", exc, exc_info=True)

        self.updateGeometry()
        self.update()
        try:
            if self.isVisible() and hasattr(self, "_preload_animation_pages"):
                QTimer.singleShot(0, self._preload_animation_pages)
        except Exception as exc:
            logger.debug("调度刷新后图标预热失败: %s", exc, exc_info=True)

        # 保存前台窗口 (如果需要)
        if HAS_EXECUTOR:
            try:
                ShortcutExecutor.save_foreground_window()
            except Exception as exc:
                logger.debug("保存前台窗口失败: %s", exc, exc_info=True)
