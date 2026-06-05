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
    QCoreApplication,
    QEventLoop,
    QFont,
    QImage,
    QtCompat,
    QTimer,
    QWidget,
    pyqtProperty,
    pyqtSignal,
)
from ui.launcher_popup.popup_background import PopupBackgroundMixin
from ui.launcher_popup.popup_command_result import PopupCommandResultMixin
from ui.launcher_popup.popup_data_refresh import PopupDataRefreshMixin
from ui.launcher_popup.popup_drag_drop import PopupDragDropMixin
from ui.launcher_popup.popup_events import PopupEventsMixin
from ui.launcher_popup.popup_icons import PopupIconMixin
from ui.launcher_popup.popup_item_execution import PopupItemExecutionMixin
from ui.launcher_popup.popup_renderer import PopupRendererMixin
from ui.launcher_popup.popup_search import PopupSearchMixin
from ui.launcher_popup.popup_window_effect import PopupLayoutMixin, PopupWindowEffectMixin
from ui.launcher_popup.popup_window_helpers import IconFlashOverlay
from ui.utils.window_effect import WindowEffect

logger = logging.getLogger(__name__)

try:
    from core import ShortcutExecutor

    HAS_EXECUTOR = True
except ImportError:
    HAS_EXECUTOR = False

try:
    from core import IconExtractor
    from core.icon_extractor import should_invert_icon as _should_invert_icon

    HAS_ICON_EXTRACTOR = True
except ImportError:
    HAS_ICON_EXTRACTOR = False
    _should_invert_icon = None


class LauncherPopup(
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
    PopupItemExecutionMixin,
    QWidget,
):
    """弹出启动器窗口"""

    # 启动错误信号 (name, error_msg)
    execution_error = pyqtSignal(str, str)
    command_panel_result_ready = pyqtSignal(object, str, str)
    plugin_search_results_ready = pyqtSignal(int, str, object)

    # 全局背景缓存 (path, blur, width, height) -> QPixmap
    # 使用 OrderedDict 实现 LRU 缓存，限制大小防止内存泄漏
    _global_bg_cache = OrderedDict()
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

        # 连接信号
        self.bg_loaded_signal.connect(self._on_bg_loaded)
        self.execution_error.connect(self._on_execution_error)
        self.command_panel_result_ready.connect(self._on_command_panel_result_ready)
        self.plugin_search_results_ready.connect(self._on_plugin_search_results_ready)
        self.folder_sync_finished.connect(self._on_folder_sync_finished)
        self._is_loading_bg = False
        self._pending_bg_params = None
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
        self._wheel_speed = 1.0  # 滚动速度系数

        # 动画进度 (0.0 到 1.0)
        self._reveal_progress = 0.0
        self._is_hiding = False

        self._icon_pixmap_cache = OrderedDict()
        self._default_icon_cache = {}
        self._visible_icons_preloaded = False
        self._first_show_ready = False
        self._blank_refresh_in_progress = False
        self._icon_flash_overlay = IconFlashOverlay(self)
        self._sync_worker = None
        # 使用全局字体
        self._label_font = QFont()
        self._label_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        self._label_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)

        # ===== 选中文件状态 =====
        self._selected_files = []
        self._file_thread = None
        self._file_check_seq = 0
        self._selected_files_source_hwnd = 0
        self._selected_files_request_hwnd = 0
        self._selected_files_request_started_at = 0.0
        self._selected_files_captured_at = 0.0
        self._selected_files_trigger_pos = None
        self._selected_files_context = None
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

        # ===== 双击检测相关状态 =====
        # ===== 双击检测状态结束 =====

        # 背景缓存
        self._bg_cache = None
        self._last_bg_params = None
        self._cached_bg_path = None
        self._win10_fallback_bg = None  # Win10回退背景，避免重新显示时闪烁

        # 布局参数
        self.padding = 8
        self.cols = self.settings.cols
        self.cell_size = self.settings.cell_size
        self.icon_size = self.settings.icon_size
        self._label_font.setPointSize(int(self.icon_size * 0.34))
        self.row_spacing = 2
        self.cell_h = int(self.cell_size * 1.15)

        # Dock 高度计算
        # 单行：icon_size + 16（与原来保持完全一致）
        # 多行：icon_size + (display_rows-1)*dock_row_stride + 16
        # dock_row_stride = icon_size + 6 --- 行间距6px，上下边距保持 8px 不变
        dock_enabled = getattr(self.settings, "dock_enabled", True)
        if dock_enabled and self.dock_items:
            max_rows = getattr(self.settings, "dock_height_mode", 1)
            # 计算实际行数
            actual_rows = (len(self.dock_items) + self.cols - 1) // self.cols
            # 最终显示行数，不超过设置的最大行数
            display_rows = min(max(1, actual_rows), max_rows)
            dock_row_stride = self.icon_size + 6  # 行间距6px
            self.dock_height = self.icon_size + (display_rows - 1) * dock_row_stride + 12
        self.window_effect = WindowEffect()

        # 设置窗口
        self._setup_window()
        calculated_width, calculated_height = self._calculate_fixed_size()
        self._center_to(x, y, calculated_width, calculated_height)

        self.setMouseTracking(True)
        self.settings_updated.connect(self._on_settings_updated)

        # ===== 启用拖放 =====
        self.setAcceptDrops(True)
        # ===== 启用拖放结束 =====

        self._indicator_timer = QTimer(self)
        self._indicator_timer.setInterval(16)
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
        self._search_cursor_visible = True
        self._search_cursor_timer = QTimer(self)
        self._search_cursor_timer.setInterval(530)
        self._search_cursor_timer.timeout.connect(self._toggle_search_cursor)
        self._search_reveal_progress = 0.0
        self._search_target_progress = 0.0
        self._search_hide_geometry_pending = False
        self._search_body_anchor_y = 0
        self._search_anim_duration_ms = 180
        self._search_anim_from_progress = 0.0
        self._search_anim_started_at = 0.0
        self._search_anim_last_ts = 0.0
        self._search_anim_timer = QTimer(self)
        self._search_anim_timer.setInterval(16)
        self._search_anim_timer.timeout.connect(self._tick_search_reveal)
        self._page_icon_warm_queue = []
        self._page_icon_warm_keys = set()
        self._page_icon_warm_timer = None
        self._page_render_cache = {}

        logger.info(f"弹窗创建: {self.width()}x{self.height()}")

    def getRevealProgress(self):
        """获取动画进度"""
        return self._reveal_progress

    def setRevealProgress(self, value):
        """设置动画进度并触发重绘"""
        self._reveal_progress = value
        self.update()

    revealProgress = pyqtProperty(float, getRevealProgress, setRevealProgress)

    def _next_lifecycle_generation(self) -> int:
        self._lifecycle_generation = int(getattr(self, "_lifecycle_generation", 0) or 0) + 1
        return self._lifecycle_generation

    def _run_if_lifecycle_current(self, generation: int, callback, *args) -> bool:
        if generation != int(getattr(self, "_lifecycle_generation", -1) or -1):
            return False
        if bool(getattr(self, "_closing", False)):
            return False
        try:
            callback(*args)
            return True
        except Exception as exc:
            logger.debug("discarded popup lifecycle callback failed: %s", exc)
            return False

    def _defer_lifecycle_callback(self, delay_ms: int, callback, *args, generation: int | None = None) -> None:
        token = int(self._lifecycle_generation if generation is None else generation)
        QTimer.singleShot(
            int(delay_ms),
            lambda token=token, callback=callback, args=args: self._run_if_lifecycle_current(token, callback, *args),
        )

    def _stop_lifecycle_timers(self) -> None:
        for timer_name in (
            "_auto_close_timer",
            "_indicator_timer",
            "_search_cursor_timer",
            "_search_anim_timer",
            "_preload_batch_timer",
            "_bg_load_timer",
        ):
            timer = self.__dict__.get(timer_name)
            if timer is None:
                continue
            try:
                timer.stop()
            except Exception as exc:
                logger.debug("停止定时器失败: %s", exc, exc_info=True)

    def _start_auto_close_timer_if_visible(self) -> None:
        if self.isVisible() and not self._auto_close_timer.isActive():
            self._auto_close_timer.start()

    def prepare_show_animation_state(self):
        """Set a deterministic hidden animation state before the native window is shown."""
        self._is_hiding = False

        for group_name in ("anim_group", "hide_anim_group"):
            group = getattr(self, group_name, None)
            try:
                if group and group.state() == QtCompat.QParallelAnimationGroup.State.Running:
                    group.stop()
            except Exception as exc:
                logger.debug("停止动画组失败: %s", exc, exc_info=True)

        self._reveal_progress = 0.0
        if hasattr(self, "anim_group"):
            try:
                self.anim_group.stop()
            except Exception as exc:
                logger.debug("停止动画组失败: %s", exc, exc_info=True)

        self.setWindowOpacity(0.0)
        self.update()

    def show(self):
        """Show with a stable fade-in start state."""
        if not self.isVisible():
            self.prepare_show_animation_state()
        super().show()

    def showEvent(self, event):
        self._closing = False
        generation = self._next_lifecycle_generation()
        # 停止隐藏动画和重置状态
        self._is_hiding = False
        if hasattr(self, "hide_anim_group"):
            self.hide_anim_group.stop()
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

    def _start_show_animation(self):
        """窗口出现动画 - 从中心向外扩散"""
        # 重置状态
        self._reveal_progress = 0.0
        self.setWindowOpacity(0.0)

        # 透明度动画
        self.opacity_anim = QtCompat.QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(100)
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        self.opacity_anim.setEasingCurve(QtCompat.OutCubic)

        # 扩散进度动画
        self.reveal_anim = QtCompat.QPropertyAnimation(self, b"revealProgress")
        self.reveal_anim.setDuration(100)
        self.reveal_anim.setStartValue(0.0)
        self.reveal_anim.setEndValue(1.0)
        self.reveal_anim.setEasingCurve(QtCompat.OutCubic)

        self.anim_group = QtCompat.QParallelAnimationGroup()
        self.anim_group.addAnimation(self.opacity_anim)
        self.anim_group.addAnimation(self.reveal_anim)
        self.anim_group.finished.connect(self._finish_show_animation)
        self.anim_group.start()

    def _finish_show_animation(self):
        self._reveal_progress = 1.0
        self.setWindowOpacity(1.0)
        self.update()

    def hide(self):
        """隐藏窗口（带动画）"""
        if hasattr(self, "_is_hiding") and self._is_hiding:
            return
        self._is_hiding = True

        # 停止可能正在运行的显示动画
        if hasattr(self, "anim_group") and self.anim_group.state() == QtCompat.QParallelAnimationGroup.State.Running:
            self.anim_group.stop()

        self._start_hide_animation()

    def _start_hide_animation(self):
        """窗口消失动画 - 从外向中心收缩"""
        # 透明度动画
        self.hide_opacity_anim = QtCompat.QPropertyAnimation(self, b"windowOpacity")
        self.hide_opacity_anim.setDuration(100)
        self.hide_opacity_anim.setStartValue(self.windowOpacity())
        self.hide_opacity_anim.setEndValue(0.0)
        self.hide_opacity_anim.setEasingCurve(QtCompat.OutCubic)

        # 收缩进度动画
        self.hide_reveal_anim = QtCompat.QPropertyAnimation(self, b"revealProgress")
        self.hide_reveal_anim.setDuration(100)
        self.hide_reveal_anim.setStartValue(self._reveal_progress)
        self.hide_reveal_anim.setEndValue(0.0)
        self.hide_reveal_anim.setEasingCurve(QtCompat.OutCubic)

        self.hide_anim_group = QtCompat.QParallelAnimationGroup()
        self.hide_anim_group.addAnimation(self.hide_opacity_anim)
        self.hide_anim_group.addAnimation(self.hide_reveal_anim)
        self.hide_anim_group.finished.connect(self._on_hide_finished)
        self.hide_anim_group.start()

    def _on_hide_finished(self):
        """动画结束后真正隐藏窗口"""
        self._is_hiding = False
        self._reveal_progress = 0.0
        super().hide()

    def hideEvent(self, event):
        self._next_lifecycle_generation()
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

        # ===== 修复 Win10 左键选择失效 bug =====
        # 弹窗隐藏时必须主动恢复之前的前台窗口焦点
        # 否则可能导致系统焦点状态异常，表现为左键无法选择桌面图标等
        # 这个问题在 Win10 上更容易出现
        try:
            if HAS_EXECUTOR and not self._launched_app:
                # 延迟一小段时间再恢复焦点，确保隐藏动画完成
                QTimer.singleShot(50, self._restore_focus_safe)
            self._launched_app = False
        except Exception as exc:
            logger.debug("恢复焦点失败: %s", exc, exc_info=True)
        # ===== 修复结束 =====

        super().hideEvent(event)

    def closeEvent(self, event):
        self._closing = True
        self._next_lifecycle_generation()
        self._stop_lifecycle_timers()
        super().closeEvent(event)

    def _restore_focus_safe(self):
        """安全地恢复之前的前台窗口焦点"""
        try:
            if HAS_EXECUTOR:
                ShortcutExecutor.restore_foreground_window()
        except Exception as e:
            logger.debug(f"恢复焦点失败: {e}")

    def _release_residual_modifiers(self):
        """释放残留的修饰键

        v2.6.6.0 新增：
        弹窗显示时调用，释放可能由全局热键遗留的修饰键状态
        """
        try:
            if HAS_EXECUTOR:
                ShortcutExecutor._pre_execution_cleanup()
                logger.debug("弹窗显示：已清理残留修饰键")
        except Exception as e:
            logger.debug(f"释放残留修饰键失败: {e}")

    def refresh_data(
        self,
        x: int = None,
        y: int = None,
        refresh_selection: bool = True,
        force: bool = False,
        reposition: bool = True,
        preserve_search_state: bool = False,
        selection_trigger_pos=None,
        trigger_method: str = "mouse",
    ):
        """刷新数据并重置位置"""
        preserved_search_state = None
        if preserve_search_state:
            current_query = getattr(self, "search_query", "") or ""
            current_forced_active = bool(getattr(self, "_search_forced_active", False))
            current_progress = float(getattr(self, "_search_reveal_progress", 0.0) or 0.0)
            if current_query or current_forced_active or current_progress > 0.001:
                current_progress = max(0.0, min(1.0, current_progress))
                body_anchor_y = int(getattr(self, "_search_body_anchor_y", 0) or 0)
                if body_anchor_y <= 0:
                    try:
                        body_anchor_y = int(self.geometry().y()) + int(
                            current_progress * self._current_search_bar_height()
                        )
                    except Exception:
                        body_anchor_y = 0
                preserved_search_state = {
                    "query": current_query,
                    "cursor_pos": int(getattr(self, "search_cursor_pos", len(current_query)) or 0),
                    "selection_anchor": getattr(self, "search_selection_anchor", None),
                    "forced_active": current_forced_active,
                    "scroll_x": int(getattr(self, "_search_scroll_x", 0) or 0),
                    "body_anchor_y": body_anchor_y,
                }

        self._search_body_anchor_y = 0
        self.search_query = ""
        self.search_results = []
        self.search_selected_index = -1
        self.search_cursor_pos = 0
        self.search_selection_anchor = None
        self._search_preedit_text = ""
        self._search_forced_active = False
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
        self._search_reveal_progress = 0.0
        self._search_target_progress = 0.0
        self._search_hide_geometry_pending = False
        if preserved_search_state is not None:
            self.search_query = preserved_search_state["query"]
            self.search_cursor_pos = max(0, min(preserved_search_state["cursor_pos"], len(self.search_query)))
            selection_anchor = preserved_search_state["selection_anchor"]
            if selection_anchor is not None:
                selection_anchor = max(0, min(int(selection_anchor), len(self.search_query)))
            self.search_selection_anchor = selection_anchor
            self._search_forced_active = preserved_search_state["forced_active"]
            self._search_scroll_x = preserved_search_state["scroll_x"]
            self._search_reveal_progress = 1.0
            self._search_target_progress = 1.0
            self._search_body_anchor_y = preserved_search_state["body_anchor_y"]
        try:
            self.clearMask()
        except Exception as exc:
            logger.debug("清除窗口遮罩失败: %s", exc, exc_info=True)

        current_revision = self.data_manager.get_runtime_revision()
        revision_changed = force or current_revision != getattr(self, "_model_revision", -1)
        self._model_revision = current_revision
        if revision_changed:
            self._icon_pixmap_cache.clear()
            self._default_icon_cache.clear()
            self._visible_icons_preloaded = False
            self._first_show_ready = False
            self._cached_bg_path = None
            self._bg_cache = None

        # 记录之前的图标数量用于比较
        prev_item_count = 0
        if self.pages and self.default_page_index < len(self.pages):
            prev_item_count = len(self.pages[self.default_page_index].items)
        prev_dock_count = len(self.dock_items)
        prev_page_count = len(self.pages) if self.pages else 0

        # 重新获取数据
        self.pages = [f for f in self.data_manager.data.get_pages() if not getattr(f, "is_icon_repo", False)]
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
        self.cell_size = self.settings.cell_size
        self.icon_size = self.settings.icon_size
        self._label_font.setPointSize(int(self.icon_size * 0.34))
        self.cell_h = int(self.cell_size * 1.15)
        if preserved_search_state is not None:
            self._ensure_search_cursor_visible()
            self._restart_search_cursor_blink()
            self._refresh_search_results()

        if reposition:
            if x is None or y is None:
                center = self.geometry().center()
                x = int(center.x())
                y = int(center.y())

            # === 修复多屏 DPI 切换核心逻辑 ===
            # 1. 强制将底层 HWND 物理移动到鼠标附近，触发 Windows 发送 WM_DPICHANGED
            # 注意：Qt 的 move() 在窗口隐藏时可能是逻辑上的，不会立即触发现生 DPI 变更
            try:
                import ctypes

                hwnd = int(self.winId())
                # SWP_NOSIZE=1, SWP_NOACTIVATE=16, SWP_FRAMECHANGED=32
                ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 0x0001 | 0x0010 | 0x0020)
            except Exception:
                self.move(x, y)

            # 2. 处理系统事件以完成 DPI 同步，但排除用户输入事件防止重入
            QCoreApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

        # 更新 Dock 高度
        # 单行：icon_size + 16（与原来保持完全一致）
        # 多行：icon_size + (display_rows-1)*dock_row_stride + 16
        # dock_row_stride = icon_size + 6 --- 行间距6px，上下边距保持 8px 不变
        dock_enabled = getattr(self.settings, "dock_enabled", True)
        if dock_enabled and self.dock_items:
            max_rows = getattr(self.settings, "dock_height_mode", 1)
            actual_rows = (len(self.dock_items) + self.cols - 1) // self.cols
            display_rows = min(max(1, actual_rows), max_rows)
            dock_row_stride = self.icon_size + 6  # 行间距6px
            # 单行：icon_size + 16；多行：icon_size + (rows-1)*dock_row_stride + 16
            self.dock_height = self.icon_size + (display_rows - 1) * dock_row_stride + 12
        else:
            self.dock_height = 0

        # 重新计算窗口大小 (现在处于正确的 DPI 上下文中)
        calculated_width, calculated_height = self._calculate_fixed_size()

        # 强制更新窗口特效，确保在新屏幕上正确显示
        self._update_window_effect()

        # 最后精确居中显示
        if reposition:
            self._center_to(x, y, calculated_width, calculated_height)

        # 调试输出：记录屏幕、位置、尺寸和缩放等详细信息 (已在正常运行中注释)
        # try:
        #     get_display_debug_logger().log_all_display_info(
        #         cursor_x=x,
        #         cursor_y=y,
        #         window_width=calculated_width,
        #         window_height=calculated_height,
        #         icon_size=self.icon_size,
        #         cell_size=self.cell_size,
        #         hwnd=int(self.winId())
        #     )
        # except Exception as e:
        #     logger.debug(f"记录显示调试日志失败: {e}")

        self.updateGeometry()
        self.update()
        self.repaint()  # 强制立即重绘，确保不出现视觉残留

        # 保存前台窗口 (如果需要)
        if HAS_EXECUTOR:
            try:
                ShortcutExecutor.save_foreground_window()
            except Exception as exc:
                logger.debug("保存前台窗口失败: %s", exc, exc_info=True)

        # 确保重绘
        self.update()
