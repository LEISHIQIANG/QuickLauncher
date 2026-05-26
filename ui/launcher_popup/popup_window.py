"""
弹出启动器窗口
"""

import logging
import os
import threading
import time
from collections import OrderedDict

try:
    import win32com.client  # noqa: F401
    import win32gui
    HAS_WIN32_SHELL = True
except ImportError:
    HAS_WIN32_SHELL = False

from core import DataManager, ShortcutItem, ShortcutType
from core.fuzzy_search import FuzzyMatchResult, search_shortcuts
from core.search_engines import build_search_url, parse_search_action
from core.slash_commands import find_matching_commands
from core.windows_uipi import allow_drag_drop_for_widget
from qt_compat import (
    QApplication,
    QBitmap,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPixmap,
    QPoint,
    QRect,
    QRectF,
    QRegion,
    Qt,
    QtCompat,
    QTimer,
    QWidget,
    pyqtProperty,
    pyqtSignal,
    QThread,
)
from ui.launcher_popup.file_selection import FileSelectionThread, SelectionTriggerContext
from ui.launcher_popup.popup_background import PopupBackgroundMixin
from ui.launcher_popup.popup_drag_drop import PopupDragDropMixin
from ui.launcher_popup.popup_icons import PopupIconMixin
from ui.launcher_popup.popup_command_result import CompactResultPopupMenu, PopupCommandResultMixin
from ui.launcher_popup.popup_renderer import PopupRendererMixin
from ui.launcher_popup.window_detection import _is_desktop_window, _is_explorer_like_window
from ui.utils.window_effect import WindowEffect, is_win10, is_win11

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


class FolderSyncWorker(QThread):
    """后台文件夹同步工作线程，避免 GUI 线程卡顿"""
    def __init__(self, launcher):
        super().__init__(launcher)
        self.launcher = launcher

    def run(self):
        try:
            self.launcher._sync_all_folders()
        except Exception as e:
            logger.error(f"后台文件夹同步失败: {e}")


class IconFlashOverlay(QWidget):
    """Lightweight icon flash layer that does not repaint the launcher content."""

    def __init__(self, launcher):
        super().__init__(launcher)
        self.launcher = launcher
        self._opacity = 0.0
        self._started_at = 0.0
        self._duration_ms = 300
        self._items = []
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.hide()

    def start(self):
        self.setGeometry(self.launcher.rect())
        self._items = list(self._snapshot_icons())
        if not self._items:
            return
        self.raise_()
        self._started_at = time.perf_counter()
        self._opacity = 0.35
        self.show()
        if not self._timer.isActive():
            self._timer.start()
        self.repaint()

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
        self._opacity = 0.0
        self._items = []
        self.hide()

    def _tick(self):
        elapsed_ms = (time.perf_counter() - self._started_at) * 1000.0
        t = max(0.0, min(1.0, elapsed_ms / self._duration_ms))
        if t >= 1.0:
            self.stop()
            return

        if t < 0.42:
            pulse_t = t / 0.42
            self._opacity = 0.85 * (1.0 - abs(2.0 * pulse_t - 1.0))
        else:
            pulse_t = (t - 0.42) / 0.58
            self._opacity = 0.65 * (1.0 - abs(2.0 * pulse_t - 1.0))
        self.update()

    def _snapshot_icons(self):
        launcher = self.launcher
        icon_size = int(getattr(launcher, "icon_size", 0) or 0)
        if icon_size <= 0:
            return

        pages = getattr(launcher, "pages", []) or []
        current_page = int(getattr(launcher, "current_page", 0) or 0)
        cols = max(1, int(getattr(launcher, "cols", 1) or 1))
        fixed_rows = max(1, int(getattr(launcher, "fixed_rows", 1) or 1))
        cell_size = int(getattr(launcher, "cell_size", icon_size) or icon_size)
        cell_h = int(getattr(launcher, "cell_h", cell_size) or cell_size)
        padding = int(getattr(launcher, "padding", 0) or 0)
        text_h = QFontMetrics(getattr(launcher, "_label_font", launcher.font())).height()
        text_spacing = 1
        use_card = getattr(getattr(launcher, "settings", None), "bg_mode", "theme") == "acrylic"

        if 0 <= current_page < len(pages):
            items = getattr(pages[current_page], "items", []) or []
            for i, item in enumerate(items[:cols * fixed_rows]):
                row = i // cols
                col = i % cols
                x = padding + col * cell_size
                y = padding + row * cell_h
                if use_card:
                    card_pad = 2
                    card_size = icon_size + card_pad * 2
                    total_h = card_size + text_spacing + text_h
                    card_y = y + (cell_h - total_h) // 2
                    card_x = x + (cell_size - card_size) // 2
                    icon_x = card_x + card_pad
                    icon_y = card_y + card_pad
                else:
                    total_h = icon_size + text_spacing + text_h
                    icon_x = x + (cell_size - icon_size) // 2
                    icon_y = y + (cell_h - total_h) // 2
                pixmap = self._icon_pixmap(item)
                if pixmap is not None:
                    yield icon_x, icon_y, pixmap, self._cover_pixmap(pixmap)

        dock_items = getattr(launcher, "dock_items", []) or []
        dock_height = int(getattr(launcher, "dock_height", 0) or 0)
        if dock_items and dock_height > 0:
            dock_height_mode = max(1, int(getattr(launcher.settings, "dock_height_mode", 1) or 1))
            visible_count = len(dock_items)
            if dock_height_mode == 1:
                visible_count = min(visible_count, cols)
            line_width = (
                cols * cell_size
                if dock_height_mode > 1 and visible_count > cols
                else min(visible_count, cols) * cell_size
            )
            start_x = (launcher.width() - line_width) // 2
            dock_y = int(getattr(launcher, "dock_y", 0) or 0)
            dock_row_stride = icon_size + 6
            for i in range(visible_count):
                row = i // cols
                if row >= dock_height_mode:
                    break
                col = i % cols
                x = start_x + col * cell_size
                y = dock_y + 8 + row * dock_row_stride
                icon_x = x + (cell_size - icon_size) // 2
                pixmap = self._icon_pixmap(dock_items[i])
                if pixmap is not None:
                    yield icon_x, y, pixmap, self._cover_pixmap(pixmap)

    def _icon_pixmap(self, item):
        try:
            need_invert = False
            try:
                if _should_invert_icon is not None:
                    current_theme = getattr(self.launcher.settings, "theme", "dark")
                    need_invert = _should_invert_icon(item, current_theme)
            except Exception:
                need_invert = False

            pixmap = self.launcher._get_cached_icon_for_animation(item, need_invert)
            if pixmap is None:
                default_key = self.launcher._default_icon_cache_key(item)
                pixmap = self.launcher._default_icon_cache.get(default_key)
        except Exception:
            return None
        if pixmap is None or pixmap.isNull():
            return None
        return pixmap

    def _cover_pixmap(self, pixmap):
        cover = QPixmap(pixmap.size())
        cover.fill(QtCompat.transparent)
        painter = QPainter(cover)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        theme = getattr(getattr(self.launcher, "settings", None), "theme", "dark")
        color = QColor(200, 200, 200) if theme == "dark" else QColor(255, 255, 255)
        painter.fillRect(cover.rect(), color)
        painter.end()
        return cover

    def paintEvent(self, event):
        if self._opacity <= 0.0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform)
        painter.setOpacity(self._opacity)
        for x, y, _pixmap, cover in self._items:
            painter.drawPixmap(x, y, cover)
        painter.end()


class LauncherPopup(PopupCommandResultMixin, PopupBackgroundMixin, PopupRendererMixin, PopupDragDropMixin, PopupIconMixin, QWidget):
    """弹出启动器窗口"""

    # 启动错误信号 (name, error_msg)
    execution_error = pyqtSignal(str, str)

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

    SELECTED_FILES_CACHE_TTL_SECONDS = 5.0

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

        # 连接信号
        self.bg_loaded_signal.connect(self._on_bg_loaded)
        self.execution_error.connect(self._on_execution_error)
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
        self.pages = data_manager.data.get_pages()
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
        except Exception:
            pass

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
        dock_enabled = getattr(self.settings, 'dock_enabled', True)
        if dock_enabled and self.dock_items:
            max_rows = getattr(self.settings, 'dock_height_mode', 1)
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

    def prepare_show_animation_state(self):
        """Set a deterministic hidden animation state before the native window is shown."""
        self._is_hiding = False

        for group_name in ("anim_group", "hide_anim_group"):
            group = getattr(self, group_name, None)
            try:
                if group and group.state() == QtCompat.QParallelAnimationGroup.State.Running:
                    group.stop()
            except Exception:
                pass

        self._reveal_progress = 0.0
        if hasattr(self, 'anim_group'):
            try:
                self.anim_group.stop()
            except Exception:
                pass

        self.setWindowOpacity(0.0)
        self.update()

        try:
            QApplication.processEvents()
        except Exception:
            pass

    def show(self):
        """Show with a stable fade-in start state."""
        if not self.isVisible():
            self.prepare_show_animation_state()
        super().show()

    def showEvent(self, event):
        # 停止隐藏动画和重置状态
        self._is_hiding = False
        if hasattr(self, 'hide_anim_group'):
            self.hide_anim_group.stop()
        if not self._drag_drop_compat_applied:
            self._drag_drop_compat_applied = True
            QTimer.singleShot(0, lambda: allow_drag_drop_for_widget(self))

        try:
            # 延迟启动，避免弹窗刚显示时鼠标尚未进入窗口就触发关闭
            if not self._auto_close_timer.isActive():
                QTimer.singleShot(300, lambda: self._auto_close_timer.start() if self.isVisible() and not self._auto_close_timer.isActive() else None)
            # 延迟应用窗口特效，确保窗口尺寸和DPI已稳定
            QTimer.singleShot(50, self._update_window_effect)
        except Exception:
            pass

        # 启动出现动画
        self._start_show_animation()

        # ===== v2.6.6.0 修复：弹窗显示时释放残留的修饰键 =====
        # 用户可能通过全局热键（如中键）唤起弹窗，此时某些修饰键可能残留
        # 在这里延迟释放，避免影响后续图标点击时的快捷键执行
        try:
            if HAS_EXECUTOR:
                QTimer.singleShot(50, self._release_residual_modifiers)
        except Exception:
            pass
        # ===== 修复结束 =====

        # 延迟预热所有页面的动画缓存，确保后续翻页动画图标正常显示
        QTimer.singleShot(200, self._preload_animation_pages)

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
        if hasattr(self, '_is_hiding') and self._is_hiding:
            return
        self._is_hiding = True

        # 停止可能正在运行的显示动画
        if hasattr(self, 'anim_group') and self.anim_group.state() == QtCompat.QParallelAnimationGroup.State.Running:
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
        overlay = getattr(self, "_icon_flash_overlay", None)
        if overlay is not None:
            overlay.stop()
        try:
            self._reset_search_state()
        except Exception:
            pass
        self._search_body_anchor_y = 0
        try:
            if self._auto_close_timer.isActive():
                self._auto_close_timer.stop()
        except Exception:
            pass
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
        except Exception:
            pass
        # ===== 修复结束 =====

        super().hideEvent(event)

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

    def _get_win11_corner_preference(self, desired_radius: int):
        r = max(0, int(desired_radius))
        if r <= 0:
            return self.window_effect.DWMWCP_DONOTROUND
        if r <= 6:
            return self.window_effect.DWMWCP_ROUNDSMALL
        return self.window_effect.DWMWCP_ROUND

    def _get_win11_effective_radius(self, desired_radius: int) -> int:
        r = max(0, int(desired_radius))
        if r <= 0:
            return 0
        if r <= 6:
            return 4
        return 8

    def _get_paint_corner_radius(self, bg_mode=None, blur_radius=None) -> int:
        desired = getattr(self.settings, 'corner_radius', 8)
        desired = max(0, int(desired))

        if bg_mode is None:
            bg_mode = getattr(self.settings, 'bg_mode', 'theme')
        if blur_radius is None:
            blur_radius = getattr(self.settings, 'bg_blur_radius', 0)

        # 亚克力模式：使用 paintEvent 绘制完美圆角，直接返回用户设置值
        if bg_mode == 'acrylic':
            return desired

        effect_enabled = (bg_mode == 'theme' and blur_radius > 0)

        # Win11 特殊逻辑
        if is_win11() and effect_enabled:
            return self._get_win11_effective_radius(desired)

        return desired

    def _apply_win10_rounded_mask(self, margin: int, clip_w: int, clip_h: int, radius: int):
        logger.info(f"[MASK] 设置Win10遮罩: clip={clip_w}x{clip_h}, window={self.width()}x{self.height()}, margin={margin}, radius={radius}")
        r = max(0, int(radius))
        if r <= 0:
            self.clearMask()
            return
        rect = QRect(int(margin), int(margin), int(clip_w), int(clip_h))
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), r, r)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        logger.info("[MASK] 遮罩已应用")

    def _update_window_effect(self):
        """更新窗口特效 (Acrylic / Blur)"""
        try:
            bg_mode = getattr(self.settings, 'bg_mode', 'theme')
            desired_radius = getattr(self.settings, 'corner_radius', 8)

            hwnd = int(self.winId())
            if not hwnd:
                return

            logger.debug(f"[EFFECT] 更新窗口效果: mode={bg_mode}, size={self.width()}x{self.height()}")

            if bg_mode == 'acrylic':
                # ===== 亚克力模式：使用与配置窗口完全相同的磨砂玻璃效果 =====
                # 禁用旧的 DWM Blur
                if getattr(self, '_win10_dwm_blur_active', False):
                    self.window_effect.set_dwm_blur_behind(hwnd, 0, 0, 0, enable=False)
                    self._win10_dwm_blur_active = False

                theme = getattr(self.settings, 'theme', 'dark')
                radius = max(0, int(desired_radius))
                # bg_alpha: 0-100 (0=全透明/最强磨砂, 100=不透明)
                bg_alpha = getattr(self.settings, 'bg_alpha', 90)

                # 线性映射 bg_alpha(0-100) 到 DWM tint alpha(0-255)
                # 低不透明度 → 薄 tint → 背景透光性强；高不透明度 → 厚 tint → 背景更实
                # Win11: DWM Acrylic tint alpha 10~80 小范围加权（危险冒泰保留磨砂感）
                # Win10: 告色层 alpha 40~200（Win10 DWM模糊能力较弱，需较强 tint）
                if theme == 'dark':
                    r_c, g_c, b_c = 0x1c, 0x1c, 0x1e
                else:
                    r_c, g_c, b_c = 0xf2, 0xf2, 0xf7

                if is_win11():
                    # Win11: DWM Acrylic tint alpha 0~180 (0%=纯磨砂, 100%=接近实色)
                    dwm_alpha = max(0, min(180, int(bg_alpha * 1.75)))
                    gradient_color = f"{dwm_alpha:02x}{r_c:02x}{g_c:02x}{b_c:02x}"
                    self.window_effect.set_acrylic(hwnd, gradient_color=gradient_color, enable=True, blur=True)
                    # DWM 圆角裁剪，防止亚克力背景直角残留
                    self.window_effect.set_round_corners(
                        hwnd,
                        preference=self._get_win11_corner_preference(desired_radius)
                    )
                    self.window_effect.clear_window_region(hwnd)
                    self.clearMask()
                else:
                    # Win10: 着色层 alpha 范围 20~240
                    dwm_alpha = max(20, min(240, int(bg_alpha * 2.2)))
                    gradient_color = f"{dwm_alpha:02x}{r_c:02x}{g_c:02x}{b_c:02x}"
                    w = self.width()
                    h = self.height()
                    logger.info(f"[REGION] Win10亚克力模式: window={w}x{h}, radius={radius}")
                    if w > 0 and h > 0:
                        # 步骤1: 设置窗口裁剪区域（硬性圆角边界）
                        self.window_effect.set_window_region(hwnd, w, h, radius)
                        logger.info("[REGION] 窗口区域已设置")
                        # 步骤2: 设置 DWM 模糊区域（与裁剪区域完全一致）
                        self.window_effect.set_dwm_blur_behind(hwnd, w, h, radius, enable=True)
                    # 步骤3: 应用 Acrylic 半透明着色层（blur=False 避免冲突）
                    self.window_effect.set_acrylic(hwnd, gradient_color, enable=True, blur=False)

            else:
                # 其他模式禁用特效 (Theme / Image 模式)
                self.window_effect.set_dwm_blur_behind(hwnd, 0, 0, 0, enable=False)
                self._win10_dwm_blur_active = False
                self.window_effect.set_acrylic(hwnd, enable=False)
                self.window_effect.set_round_corners(hwnd, enable=False)
                self.window_effect.clear_window_region(hwnd)
                # 非亚克力模式用 mask 裁掉顶部透明区域（搜索框隐藏时 top_inset=34）
                if hasattr(self, '_apply_search_mask'):
                    self._apply_search_mask()

        except Exception as e:
            logger.error(f"更新窗口特效失败: {e}")

    def _setup_window(self):
        """设置窗口属性"""
        self.setWindowFlags(
            QtCompat.FramelessWindowHint |
            QtCompat.Tool |
            QtCompat.WindowStaysOnTopHint
        )
        self.setAttribute(QtCompat.WA_TranslucentBackground, True)
        self.setWindowOpacity(0)  # 初始透明度为 0
        try:
            self.setAttribute(QtCompat.WA_NoSystemBackground, True)
        except Exception:
            pass

        # 启用DPI感知，确保在不同缩放屏幕上正确显示
        try:
            self.setAttribute(QtCompat.WA_NativeWindow, True)
        except Exception:
            pass
        try:
            self.setFocusPolicy(QtCompat.StrongFocus)
            self.setAttribute(Qt.WA_InputMethodEnabled, True)
        except Exception:
            pass

    def _calculate_fixed_size(self, y_offset_override=None):
        """基于"常用"页面计算固定窗口大小"""
        # 使用配置的每列行数
        self.fixed_rows = getattr(self.settings, 'popup_max_rows', 3)
        self.shadow_margin = 0
        self.cell_h = int(self.cell_size * 1.15)

        width = self.padding * 2 + self.cols * self.cell_size
        # 增加搜索框导致的Y偏移
        if y_offset_override is None:
            y_offset = self._body_y_offset() if hasattr(self, '_body_y_offset') else 0
        else:
            y_offset = int(y_offset_override)

        logger.debug(f"[SIZE] 计算窗口尺寸: y_offset={y_offset}, "
                     f"search_reveal_progress={getattr(self, '_search_reveal_progress', 'N/A')}")

        # theme/image 模式：mask 裁掉顶部34px，所有坐标需整体下移补偿；搜索展开时 y_offset 已撑高，补偿相应减少
        self.content_height = self.padding + y_offset + self.fixed_rows * self.cell_h

        indicator_height = 16 if len(self.pages) > 1 else 0
        indicator_spacing = 4 if len(self.pages) > 1 else 0  # 指示器上方间距
        self.indicator_y = self.content_height + indicator_spacing

        dock_height = self.dock_height if (self.dock_items and self.dock_height > 0) else 0
        self.dock_y = self.indicator_y + indicator_height

        # 窗口总高度：内容 + 指示器间距 + 指示器 + Dock + 底部间距6px（与左右间距一致）
        height = self.content_height + indicator_spacing + indicator_height + dock_height + 6

        # 增加阴影边距
        total_width = width + self.shadow_margin * 2
        total_height = height + self.shadow_margin * 2

        self.setFixedSize(total_width, total_height)

        # 返回计算的尺寸供_center_to使用
        return total_width, total_height

    def _center_to(self, x: int, y: int, window_width: int = None, window_height: int = None):
        """定位窗口"""
        if window_width is None:
            window_width = self.width()
        if window_height is None:
            window_height = self.height()

        # 获取Qt屏幕对象
        screen = QApplication.screenAt(QPoint(x, y))
        if not screen:
            screen = QApplication.primaryScreen()

        work_area = screen.availableGeometry()

        # 将物理坐标转换为Qt逻辑坐标（处理非整数DPI缩放）
        dpr = screen.devicePixelRatio()
        if dpr and dpr != 1.0:
            # Qt逻辑坐标 = 物理坐标 / DPR
            lx = int(x / dpr)
            ly = int(y / dpr)
        else:
            lx, ly = x, y

        # 获取定位模式
        align_mode = getattr(self.settings, 'popup_align_mode', 'mouse_center')

        if align_mode == 'screen_center':
            left = work_area.center().x() - window_width // 2
            top = work_area.center().y() - window_height // 2
        elif align_mode == 'bottom_right':
            left = work_area.right() - window_width - 10
            top = work_area.bottom() - window_height - 10
        elif align_mode == 'mouse_top_left':
            left = lx
            top = ly
        else:  # mouse_center
            left = lx - window_width // 2
            top = ly - window_height // 2

        # 确保不超出屏幕边界
        left = max(work_area.left() + 5, min(left, work_area.right() - window_width - 5))
        top = max(work_area.top() + 5, min(top, work_area.bottom() - window_height - 5))

        self.move(left, top)

    def resizeEvent(self, event):
        self._bg_cache = None
        self._cached_bg_path = None
        overlay = getattr(self, "_icon_flash_overlay", None)
        if overlay is not None:
            overlay.setGeometry(self.rect())
        QTimer.singleShot(0, self._update_window_effect)
        super().resizeEvent(event)

    def moveEvent(self, event):
        """窗口移动时更新特效，确保在新屏幕上正确显示"""
        try:
            # 检测屏幕切换，清空背景缓存
            old_screen = QApplication.screenAt(event.oldPos()) if hasattr(event, 'oldPos') else None
            new_screen = QApplication.screenAt(self.pos())

            if old_screen and new_screen and old_screen != new_screen:
                # 切换到不同屏幕，清空实例缓存
                self._bg_cache = None
                self._last_bg_params = None
                logger.debug(f"屏幕切换，清空背景缓存: {old_screen.name()} -> {new_screen.name()}")
                # 延迟应用特效，等待Qt完成DPI调整
                QTimer.singleShot(50, self._update_window_effect)
            else:
                self._update_window_effect()
        except Exception:
            pass
        super().moveEvent(event)

    def _on_settings_updated(self):
        """设置更新时刷新"""
        prev_icon_size = self.icon_size
        prev_settings = self.settings
        self.settings = self.data_manager.get_settings()

        try:
            prev_cols = getattr(prev_settings, "cols", self.cols)
            prev_cell = getattr(prev_settings, "cell_size", self.cell_size)
            prev_icon = getattr(prev_settings, "icon_size", self.icon_size)
            prev_dock_enabled = getattr(prev_settings, "dock_enabled", True)
            prev_dock_height_mode = getattr(prev_settings, "dock_height_mode", 1)
            prev_bg_mode = getattr(prev_settings, "bg_mode", "theme")
            prev_corner = getattr(prev_settings, "corner_radius", 8)
            prev_path = getattr(prev_settings, "custom_bg_path", "")
            prev_blur = getattr(prev_settings, "bg_blur_radius", 0)
        except Exception:
            prev_cols = self.cols
            prev_cell = self.cell_size
            prev_icon = self.icon_size
            prev_dock_enabled = True
            prev_dock_height_mode = 1
            prev_bg_mode = "theme"
            prev_corner = 8
            prev_path = ""
            prev_blur = 0

        self.cols = self.settings.cols
        self.cell_size = self.settings.cell_size
        self.icon_size = self.settings.icon_size
        self._label_font.setPointSize(int(self.icon_size * 0.34))
        self.cell_h = int(self.cell_size * 1.15)

        layout_changed = (
            self.cols != prev_cols
            or self.cell_size != prev_cell
            or self.icon_size != prev_icon
            or getattr(self.settings, "dock_enabled", True) != prev_dock_enabled
            or getattr(self.settings, "dock_height_mode", 1) != prev_dock_height_mode
        )
        bg_mode = getattr(self.settings, "bg_mode", "theme")
        blur_radius = getattr(self.settings, "bg_blur_radius", 0)
        bg_path = getattr(self.settings, "custom_bg_path", "")
        def calc_paint_radius(desired_radius: int, mode: str, blur: int) -> int:
            desired = max(0, int(desired_radius))
            if mode == 'acrylic' and is_win10():
                # Win10 Acrylic allows DWM Blur rounding now
                pass
            effect_enabled = (mode == 'acrylic') or (mode == 'theme' and int(blur or 0) > 0)
            if is_win11() and effect_enabled:
                return self._get_win11_effective_radius(desired)
            return desired

        prev_paint_radius = calc_paint_radius(prev_corner, prev_bg_mode, prev_blur)
        paint_radius = calc_paint_radius(getattr(self.settings, "corner_radius", 8), bg_mode, blur_radius)

        radius_changed = (getattr(self.settings, "corner_radius", 8) != prev_corner) or (paint_radius != prev_paint_radius)
        bg_params_changed = (bg_mode != prev_bg_mode) or (bg_path != prev_path) or (blur_radius != prev_blur)

        # Dock 高度更新
        # 单行：icon_size + 16（与原来保持完全一致）
        # 多行：icon_size + (display_rows-1)*dock_row_stride + 16
        # dock_row_stride = icon_size + 6 --- 行间距6px，上下边距保持 8px 不变
        dock_enabled = getattr(self.settings, 'dock_enabled', True)
        if dock_enabled and self.dock_items:
            max_rows = getattr(self.settings, 'dock_height_mode', 1)
            # 计算实际行数
            actual_rows = (len(self.dock_items) + self.cols - 1) // self.cols
            # 最终显示行数，不超过设置的最大行数
            display_rows = min(max(1, actual_rows), max_rows)
            dock_row_stride = self.icon_size + 6  # 行间距6px
            # 单行：icon_size + 16；多行：icon_size + (rows-1)*dock_row_stride + 16
            self.dock_height = self.icon_size + (display_rows - 1) * dock_row_stride + 12
        else:
            self.dock_height = 0

        if self.icon_size != prev_icon_size:
            self._icon_pixmap_cache.clear()
            self._default_icon_cache.clear()
            self._visible_icons_preloaded = False

        if layout_changed:
            self._calculate_fixed_size()

        if radius_changed:
            self._cached_bg_path = None

        if bg_mode == "acrylic" or prev_bg_mode == "acrylic" or radius_changed:
            self._update_window_effect()

        # 重绘
        self.update()

        if bg_mode == "image" and bg_path and os.path.exists(bg_path):
            if bg_params_changed or layout_changed:
                try:
                    self._schedule_bg_load()
                except Exception:
                    pass

    def refresh_settings(self):
        """外部调用刷新设置"""
        self.settings = self.data_manager.get_settings()
        self.update()

    def preload_background(self):
        """预加载背景图片"""
        self._get_cached_bg_pixmap()

    def preload_visible_icons(self, force: bool = False):
        """预热首屏可见图标，减少首次弹出时的图标补绘感。"""
        if not force and not self.isVisible():
            return

        if self._visible_icons_preloaded:
            return

        self._visible_icons_preloaded = True

        if not HAS_ICON_EXTRACTOR or not IconExtractor:
            return

        try:
            items = []

            if self.pages and 0 <= self.current_page < len(self.pages):
                max_visible = self.cols * getattr(self, 'fixed_rows', getattr(self.settings, 'popup_max_rows', 3))
                items.extend((self.pages[self.current_page].items or [])[:max_visible])

            if self.dock_items:
                dock_rows = max(1, int(getattr(self.settings, 'dock_height_mode', 1) or 1))
                max_dock_items = self.cols * dock_rows
                items.extend((self.dock_items or [])[:max_dock_items])

            for item in items:
                try:
                    self._get_icon(item)
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"preload visible icons failed: {e}")

    def prepare_first_show(self, create_native_window: bool = True):
        """Warm up Qt's first paint path before the popup is shown to the user."""
        if self._first_show_ready:
            return

        try:
            self.ensurePolished()
        except Exception:
            pass

        try:
            # Force native window creation while the popup is still off-screen.
            self.winId()
        except Exception:
            pass

        try:
            self.preload_background()
        except Exception:
            pass

        try:
            self.preload_visible_icons(force=True)
        except Exception:
            pass

        try:
            if hasattr(self, "preload_page_animation_pixmaps"):
                self.preload_page_animation_pixmaps()
        except Exception:
            pass

        try:
            self._update_window_effect()
        except Exception:
            pass

        old_progress = self._reveal_progress
        old_opacity = self.windowOpacity()
        try:
            self._reveal_progress = 1.0
            self.setWindowOpacity(1.0)
            warmup = QPixmap(max(1, self.width()), max(1, self.height()))
            warmup.fill(QtCompat.transparent)
            self.render(warmup)
        except Exception as e:
            logger.debug(f"first show warmup failed: {e}")
        finally:
            self._reveal_progress = old_progress
            self.setWindowOpacity(old_opacity)

        self._first_show_ready = True

    def _start_file_check(self, hwnd=None, trigger_method: str = "mouse"):
        """启动文件检测线程"""
        self._file_check_seq += 1
        request_started_at = time.monotonic()
        context = SelectionTriggerContext.capture(
            request_id=self._file_check_seq,
            trigger_method=trigger_method,
            trigger_pos=self._selected_files_trigger_pos,
            foreground_hwnd=hwnd,
            started_at=request_started_at,
        )
        self._selected_files_context = context
        self._selected_files_status = "pending"
        self._selected_files_request_hwnd = int(context.target_root_hwnd or 0)
        self._selected_files_request_started_at = float(context.started_at or request_started_at)
        logger.info(
            "selection_request start id=%s kind=%s target=%s fg=%s cursor=%s pos=%s%s",
            context.request_id,
            context.target_kind,
            context.target_root_hwnd,
            context.foreground_root_hwnd,
            context.cursor_root_hwnd,
            context.trigger_pos,
            f" ignore={context.ignore_reason}" if context.ignore_reason else "",
        )
        if context.ignore_reason and not context.target_root_hwnd:
            self._selected_files = []
            self._selected_files_source_hwnd = 0
            self._selected_files_captured_at = time.monotonic()
            self._selected_files_status = "empty"
            self._refresh_selected_files_indicator()
            return

        thread = FileSelectionThread(
            context,
        )
        thread.files_found.connect(self._on_files_found)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        # 保存引用防止被 GC
        self._file_thread = thread

    def _clear_selected_files_context(self):
        self._selected_files = []
        self._selected_files_source_hwnd = 0
        self._selected_files_request_hwnd = 0
        self._selected_files_request_started_at = 0.0
        self._selected_files_captured_at = 0.0
        self._selected_files_trigger_pos = None
        self._selected_files_context = None
        self._selected_files_status = "idle"

    def _refresh_selected_files_indicator(self):
        try:
            if hasattr(self, "_request_page_animation_update"):
                self._request_page_animation_update()
            else:
                self.update()
        except Exception:
            pass

    def _schedule_selected_files_expiry_refresh(self):
        context = getattr(self, "_selected_files_context", None)
        request_id = int(getattr(context, "request_id", 0) or 0)
        captured_at = float(getattr(self, "_selected_files_captured_at", 0.0) or 0.0)
        if not request_id or captured_at <= 0.0:
            return
        delay_ms = int(float(self.SELECTED_FILES_CACHE_TTL_SECONDS) * 1000) + 50
        QTimer.singleShot(delay_ms, lambda: self._expire_selected_files_if_current(request_id, captured_at))

    def _expire_selected_files_if_current(self, request_id: int, captured_at: float):
        context = getattr(self, "_selected_files_context", None)
        if int(getattr(context, "request_id", 0) or 0) != int(request_id or 0):
            return
        current_captured_at = float(getattr(self, "_selected_files_captured_at", 0.0) or 0.0)
        if abs(current_captured_at - float(captured_at or 0.0)) > 0.001:
            return
        if (time.monotonic() - current_captured_at) < float(self.SELECTED_FILES_CACHE_TTL_SECONDS):
            return
        logger.info("selection_request ignore id=%s reason=expired_cache", request_id)
        self._clear_selected_files_context()
        self._refresh_selected_files_indicator()

    def _take_valid_selected_files_for_click(self) -> list:
        status = getattr(self, "_selected_files_status", "idle")
        if status == "pending":
            logger.info("selection_request ignore id=%s reason=stale_request", self._file_check_seq)
            self._file_check_seq += 1
            self._clear_selected_files_context()
            return []

        if not self._selected_files:
            return []

        request_hwnd = int(self._selected_files_request_hwnd or 0)
        source_hwnd = int(self._selected_files_source_hwnd or 0)
        context = getattr(self, "_selected_files_context", None)
        if not context or int(getattr(context, "request_id", 0) or 0) != self._file_check_seq:
            logger.info("selection_request ignore id=%s reason=stale_request", self._file_check_seq)
            self._clear_selected_files_context()
            return []

        if (time.monotonic() - float(self._selected_files_captured_at or 0.0)) > self.SELECTED_FILES_CACHE_TTL_SECONDS:
            logger.info("selection_request ignore id=%s reason=expired_cache", context.request_id)
            self._clear_selected_files_context()
            return []

        target_kind = getattr(context, "target_kind", "none")
        if not request_hwnd or target_kind not in {"explorer", "desktop"}:
            logger.info("selection_request ignore id=%s reason=not_explorer_or_desktop", context.request_id)
            self._clear_selected_files_context()
            return []

        if target_kind == "explorer":
            if not _is_explorer_like_window(request_hwnd) or _is_desktop_window(request_hwnd):
                logger.info("selection_request ignore id=%s reason=not_explorer_or_desktop", context.request_id)
                self._clear_selected_files_context()
                return []
            if request_hwnd and source_hwnd and request_hwnd != source_hwnd:
                logger.info(
                    "selection_request ignore id=%s reason=window_mismatch target=%s source=%s",
                    context.request_id,
                    request_hwnd,
                    source_hwnd,
                )
                self._clear_selected_files_context()
                return []
        elif source_hwnd and not _is_desktop_window(source_hwnd):
            logger.info(
                "selection_request ignore id=%s reason=window_mismatch target=%s source=%s",
                context.request_id,
                request_hwnd,
                source_hwnd,
            )
            self._clear_selected_files_context()
            return []

        return list(self._selected_files)

    def _on_files_found(self, files):
        """文件检测回调"""
        thread = self.sender()
        request_id = int(getattr(thread, "request_id", 0) or 0)
        if request_id and request_id != self._file_check_seq:
            logger.info(
                "selection_request ignore id=%s reason=stale_request current=%s",
                request_id,
                self._file_check_seq,
            )
            return

        self._selected_files = list(files or [])
        self._selected_files_source_hwnd = int(getattr(thread, "matched_root_hwnd", 0) or 0)
        self._selected_files_request_hwnd = int(getattr(thread, "requested_root_hwnd", 0) or 0)
        self._selected_files_request_started_at = float(getattr(thread, "request_started_at", 0.0) or 0.0)
        self._selected_files_captured_at = float(getattr(thread, "captured_at", 0.0) or 0.0)
        self._selected_files_context = getattr(thread, "context", None)
        self._selected_files_status = "ready" if self._selected_files else "empty"
        ignore_reason = getattr(thread, "ignore_reason", "") or ("no_selected_items" if not self._selected_files else "")
        logger.info(
            "selection_request done id=%s status=%s count=%s target=%s source=%s%s",
            request_id,
            self._selected_files_status,
            len(self._selected_files),
            self._selected_files_request_hwnd,
            self._selected_files_source_hwnd,
            f" reason={ignore_reason}" if ignore_reason else "",
        )
        if self._selected_files_status == "ready":
            self._schedule_selected_files_expiry_refresh()
        self._refresh_selected_files_indicator()

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
        except Exception:
            pass
        self._search_reveal_progress = 0.0
        self._search_target_progress = 0.0
        self._search_hide_geometry_pending = False
        if preserved_search_state is not None:
            self.search_query = preserved_search_state["query"]
            self.search_cursor_pos = max(0, min(
                preserved_search_state["cursor_pos"],
                len(self.search_query)
            ))
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
        except Exception:
            pass

        # 强制刷新屏幕DPI信息
        QApplication.processEvents()

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
        self.pages = self.data_manager.data.get_pages()
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
            prev_item_count != current_item_count or
            prev_dock_count != current_dock_count or
            prev_page_count != current_page_count
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

            # 2. 强制处理事件流，让 OS 和 Qt 完成 DPI 信息的同步
            QApplication.processEvents()
            QApplication.processEvents()

        # 更新 Dock 高度
        # 单行：icon_size + 16（与原来保持完全一致）
        # 多行：icon_size + (display_rows-1)*dock_row_stride + 16
        # dock_row_stride = icon_size + 6 --- 行间距6px，上下边距保持 8px 不变
        dock_enabled = getattr(self.settings, 'dock_enabled', True)
        if dock_enabled and self.dock_items:
            max_rows = getattr(self.settings, 'dock_height_mode', 1)
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
            except Exception:
                pass

        # 确保重绘
        self.update()

    def _sync_all_folders(self):
        """同步所有文件夹 - 等同于配置窗口的手动同步功能"""
        try:
            from core.folder_sync import sync_folder

            # 获取所有文件夹 - 直接访问 folders 属性
            folders = self.data_manager.data.folders
            total_added = 0
            total_removed = 0

            # 遍历所有文件夹，执行同步
            for folder in folders:
                if folder.linked_path:  # 只同步有链接路径的文件夹
                    try:
                        added, removed = sync_folder(self.data_manager, folder.id)
                        total_added += added
                        total_removed += removed
                        logger.info(f"同步文件夹 '{folder.name}': 新增 {added} 项, 删除 {removed} 项")
                    except Exception as e:
                        logger.error(f"同步文件夹 '{folder.name}' 失败: {e}")

            if total_added > 0 or total_removed > 0:
                logger.info(f"所有文件夹同步完成: 总计新增 {total_added} 项, 删除 {total_removed} 项")
            else:
                logger.info("所有文件夹已是最新状态")

        except Exception as e:
            logger.error(f"同步文件夹失败: {e}")

    def _flash_icons(self):
        """Flash icons through a cheap child overlay instead of repainting icons."""
        overlay = getattr(self, "_icon_flash_overlay", None)
        if overlay is not None and self.isVisible():
            self._start_icon_flash_overlay()

    def _start_icon_flash_overlay(self):
        overlay = getattr(self, "_icon_flash_overlay", None)
        if overlay is not None and self.isVisible():
            overlay.start()


    # ===== 拖放事件处理 =====

    def _get_event_pos(self, event):
        """获取事件位置"""
        if hasattr(event, 'position'):
            # Newer Qt event API
            return event.position().toPoint()
        else:
            # PyQt5
            return event.pos()

    def _get_event_global_pos(self, event):
        """获取事件全局位置"""
        if hasattr(event, 'globalPosition'):
            return event.globalPosition().toPoint()
        if hasattr(event, 'globalPos'):
            return event.globalPos()
        return self.mapToGlobal(self._get_event_pos(event))

    def _get_clicked_item_at(self, pos: QPoint):
        """返回指定位置命中的项目，没有命中则返回 None"""
        if self._search_bar_contains(pos):
            return None

        if pos.y() >= self.dock_y and self.dock_items:
            dock_height_mode = getattr(self.settings, 'dock_height_mode', 1)
            visible_count = len(self.dock_items)
            if dock_height_mode == 1:
                visible_count = min(visible_count, self.cols)
            max_cols = self.cols
            line_width = (
                max_cols * self.cell_size
                if (dock_height_mode > 1 and visible_count > max_cols)
                else min(visible_count, max_cols) * self.cell_size
            )
            start_x = (self.width() - line_width) // 2
            dock_row_stride = self.icon_size + 6

            if start_x <= pos.x() < start_x + line_width:
                dock_col = (pos.x() - start_x) // self.cell_size
                dock_row = (pos.y() - self.dock_y - 8) // dock_row_stride
                if 0 <= dock_col < max_cols and 0 <= dock_row < dock_height_mode:
                    idx = dock_row * max_cols + dock_col
                    if 0 <= idx < visible_count:
                        return self.dock_items[idx]

        if self.padding <= pos.x() and self.padding <= pos.y() < self.content_height:
            # 从窗口底部算起，与图标绘制逻辑一致
            bottom_margin = 6
            indicator_height = 16 if len(self.pages) > 1 else 0
            indicator_spacing = 4 if len(self.pages) > 1 else 0
            dock_height = self.dock_height if (self.dock_items and self.dock_height > 0) else 0
            icons_bottom = self.height() - bottom_margin - dock_height - indicator_height - indicator_spacing

            if pos.y() <= icons_bottom:
                col = (pos.x() - self.padding) // self.cell_size
                row_from_bottom = (icons_bottom - pos.y()) // self.cell_h
                row = self.fixed_rows - 1 - row_from_bottom

                if 0 <= col < self.cols and row < self.fixed_rows:
                    index = row * self.cols + col
                    if getattr(self, "search_query", ""):
                        if 0 <= index < len(self.search_results):
                            return self.search_results[index].shortcut
                    elif self.pages and self.current_page < len(self.pages):
                        items = self.pages[self.current_page].items
                        if 0 <= index < len(items):
                            return items[index]

        return None

    def _on_folder_sync_finished(self):
        """Handle completed folder sync on the GUI thread."""
        self._refresh_after_folder_sync(sync_first=False)

    def _refresh_after_folder_sync(self, sync_first: bool = True):
        """Refresh after folder sync while preserving transient search state."""
        try:
            if sync_first:
                self._sync_all_folders()
            self.refresh_data(
                refresh_selection=False,
                force=True,
                reposition=False,
                preserve_search_state=True,
            )
            self._flash_icons()
            if self.tray_app and getattr(self.tray_app, 'config_window', None):
                if hasattr(self.tray_app.config_window, '_on_settings_panel_changed'):
                    self.tray_app.config_window._on_settings_panel_changed()
            logger.info(f"同步并刷新完成，页面数: {len(self.pages)}, Dock项: {len(self.dock_items)}")
        except Exception as e:
            logger.error(f"同步刷新处理失败: {e}")
        finally:
            self._blank_refresh_in_progress = False

    def _run_blank_area_refresh(self):
        """在双击事件结束后执行空白区刷新，避免重入和窗口抖动"""
        if self._blank_refresh_in_progress:
            return

        self._blank_refresh_in_progress = True
        try:
            logger.info("左键双击空白区域，异步启动文件夹同步")
            # 立即提供无延迟的视觉反馈
            self._flash_icons()
            
            # 启动后台同步工作线程
            self._sync_worker = FolderSyncWorker(self)
            self._sync_worker.finished.connect(self.folder_sync_finished.emit)
            self._sync_worker.finished.connect(self._sync_worker.deleteLater)
            self._sync_worker.finished.connect(lambda: setattr(self, "_sync_worker", None))
            self._sync_worker.start()
        except Exception as e:
            logger.error(f"启动同步线程失败: {e}")
            self._blank_refresh_in_progress = False








    # ===== 拖放事件处理结束 =====















    def _is_click_on_result_panel(self, pos) -> bool:
        """判断鼠标位置是否在命令结果展示面板内"""
        if self.__dict__.get("_command_result") is None:
            return False
        # 获取结果面板区域的顶部和底部
        y_top = self._body_y_offset() if hasattr(self, "_body_y_offset") else 38
        y_bottom = self.__dict__.get("dock_y")
        if y_bottom is None:
            y_bottom = self.height() - 6
        return y_top <= pos.y() < y_bottom

    def _search_query_matches_result_command(self) -> bool:
        """Return True when the search box still contains the full panel command."""
        if self.__dict__.get("_command_result") is None:
            return False
        command_id = str(self.__dict__.get("_command_id") or "").strip().lower()
        if not command_id:
            return False
        query = str(getattr(self, "search_query", "") or "").strip()
        if not query.startswith("/"):
            return False
        command_token = query[1:].split(None, 1)[0].strip().lower()
        return command_token == command_id

    def _search_shortcuts_have_priority_over_result(self) -> bool:
        """Return True when edit shortcuts should target the custom search field."""
        shortcut_target = self.__dict__.get("_text_shortcut_target")
        if shortcut_target == "search":
            return True
        if shortcut_target == "result":
            return False

        te = self.__dict__.get("_result_text_edit", None)
        try:
            if te is not None and te.isVisible() and te.hasFocus():
                return False
        except Exception:
            pass

        try:
            if self._search_selection_bounds():
                return True
        except Exception:
            pass

        return self._search_query_matches_result_command()

    def mouseMoveEvent(self, event):
        """鼠标移动"""
        pos = self._get_event_pos(event)
        if getattr(self, "_search_drag_selecting", False):
            cursor = self._search_pos_from_point(pos)
            self.search_cursor_pos = cursor
            self.search_selection_anchor = getattr(self, "_search_drag_anchor", cursor)
            self._restart_search_cursor_blink()
            self.update()
            event.accept()
            return

        try:
            self.setCursor(Qt.IBeamCursor if self._search_bar_contains(pos) else QtCompat.ArrowCursor)
        except Exception:
            pass

        new_hover = -1
        new_dock_hover = -1

        if not self._is_click_on_result_panel(pos) and hasattr(self, "clear_result_button_feedback"):
            self.clear_result_button_feedback()

        if self._is_click_on_result_panel(pos):
            if hasattr(self, "update_result_button_hover"):
                self.update_result_button_hover(pos)
            # 鼠标在结果面板区域内移动，不应触发底层图标的高亮悬停
            pass
        elif pos.y() >= self.dock_y and self.dock_items:
            if hasattr(self, "clear_result_button_feedback"):
                self.clear_result_button_feedback()
            dock_height_mode = getattr(self.settings, 'dock_height_mode', 1)
            visible_count = len(self.dock_items)
            if dock_height_mode == 1:
                visible_count = min(visible_count, self.cols)
            max_cols = self.cols
            line_width = max_cols * self.cell_size if (dock_height_mode > 1 and visible_count > max_cols) else min(visible_count, max_cols) * self.cell_size
            start_x = (self.width() - line_width) // 2
            dock_row_stride = self.icon_size + 6  # 行间距6px

            if start_x <= pos.x() < start_x + line_width:
                dock_col = (pos.x() - start_x) // self.cell_size
                dock_row = (pos.y() - self.dock_y - 8) // dock_row_stride
                if 0 <= dock_col < max_cols and 0 <= dock_row < dock_height_mode:
                    idx = dock_row * max_cols + dock_col
                    if 0 <= idx < visible_count:
                        new_dock_hover = idx

        elif self.padding <= pos.x() and self.padding <= pos.y() < self.content_height:
            if hasattr(self, "clear_result_button_feedback"):
                self.clear_result_button_feedback()
            # 从窗口底部算起，与图标绘制逻辑一致
            bottom_margin = 6
            indicator_height = 16 if len(self.pages) > 1 else 0
            indicator_spacing = 4 if len(self.pages) > 1 else 0
            dock_height = self.dock_height if (self.dock_items and self.dock_height > 0) else 0
            icons_bottom = self.height() - bottom_margin - dock_height - indicator_height - indicator_spacing

            if pos.y() <= icons_bottom:
                col = (pos.x() - self.padding) // self.cell_size
                row_from_bottom = (icons_bottom - pos.y()) // self.cell_h
                row = self.fixed_rows - 1 - row_from_bottom

                if 0 <= col < self.cols and row < self.fixed_rows:
                    index = row * self.cols + col
                    if getattr(self, "search_query", ""):
                        if 0 <= index < len(self.search_results):
                            new_hover = index
                    elif self.pages and self.current_page < len(self.pages):
                        items = self.pages[self.current_page].items
                        if 0 <= index < len(items):
                            new_hover = index

        if new_hover != self.hover_index or new_dock_hover != self.dock_hover_index:
            self.hover_index = new_hover
            self.dock_hover_index = new_dock_hover
            self.update()

    def mousePressEvent(self, event):
        """鼠标按下"""
        pos = self._get_event_pos(event)
        if self._is_click_on_result_panel(pos):
            self._text_shortcut_target = "result"
            # 点击在命令结果展示面板内，交由 PopupCommandResultMixin.mousePressEvent 处理，并拦截穿透
            super().mousePressEvent(event)
            event.accept()
            return

        if event.button() == QtCompat.LeftButton and self._search_bar_contains(pos):
            # 保留完整 /命令 的结果面板，便于继续选中、复制或补参数；命令不完整时再关闭。
            if (
                self.__dict__.get("_command_result") is not None
                and not self._search_query_matches_result_command()
            ):
                self.clear_command_result()
            self._text_shortcut_target = "search"
            self._search_forced_active = True
            self._start_search_reveal_animation(True)
            try:
                self.setFocus()
            except Exception:
                pass
            cursor = self._search_pos_from_point(pos)
            modifiers = event.modifiers()
            if modifiers & QtCompat.ShiftModifier:
                if self.search_selection_anchor is None:
                    self.search_selection_anchor = self.search_cursor_pos
                self.search_cursor_pos = cursor
                self._search_drag_anchor = self.search_selection_anchor
            else:
                self.search_cursor_pos = cursor
                self.search_selection_anchor = None
                self._search_drag_anchor = cursor
            self._search_drag_selecting = True
            self._restart_search_cursor_blink()
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        pos = self._get_event_pos(event)

        # ===== 结果面板区域处理 (不穿透至底层图标) =====
        if self._is_click_on_result_panel(pos):
            super().mouseReleaseEvent(event)
            event.accept()
            return
        if hasattr(self, "clear_result_button_feedback"):
            self.clear_result_button_feedback()

        # ===== 右键处理 =====
        if event.button() == QtCompat.RightButton:
            if self._search_bar_contains(pos):
                self._show_search_context_menu(event)
                event.accept()
                return

            if (
                self.__dict__.get("_command_result") is not None
                and hasattr(self, "toggle_result_panel_post_close_pin")
                and self.toggle_result_panel_post_close_pin()
            ):
                logger.debug(
                    "结果面板期间右键切换关闭后的固定状态: %s",
                    self.__dict__.get("_result_auto_pin_previous_state"),
                )
                event.accept()
                return

            # 右键点击窗口任何位置 -> 切换固定状态
            self.is_pinned = not self.is_pinned
            if self.is_pinned and self._hide_timer.isActive():
                self._hide_timer.stop()
            self.update()
            logger.debug(f"右键单击切换固定状态: {self.is_pinned}")
            event.accept()
            return

        # ===== 左键处理 =====
        if event.button() == QtCompat.LeftButton:
            if getattr(self, "_search_drag_selecting", False):
                self._search_drag_selecting = False
                self._restart_search_cursor_blink()
                self.update()
                event.accept()
                return

            if self._executing:
                return

            clicked_item = self._get_clicked_item_at(pos)

            if clicked_item:
                # 检查是否按住 Alt 键
                is_alt_pressed = event.modifiers() & QtCompat.AltModifier

                if is_alt_pressed:
                    # Alt + 左键点击图标 -> 强制打开新窗口
                    logger.debug(f"Alt + 左键点击图标，强制新开: {clicked_item.name}")
                    self._execute_item(clicked_item, force_new=True)
                else:
                    # 普通左键点击图标 -> 立即执行
                    self._execute_item(clicked_item, force_new=False)

            event.accept()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """鼠标双击"""
        pos = self._get_event_pos(event)
        if self._is_click_on_result_panel(pos):
            event.accept()
            return

        if event.button() != QtCompat.LeftButton:
            super().mouseDoubleClickEvent(event)
            return

        if self._executing or self._blank_refresh_in_progress:
            event.accept()
            return

        if self._search_bar_contains(pos):
            cursor = self._search_pos_from_point(pos)
            start, end = self._search_word_bounds(cursor)
            self.search_cursor_pos = end
            self.search_selection_anchor = start if start != end else None
            self._search_drag_selecting = False
            self._restart_search_cursor_blink()
            self.update()
            event.accept()
            return

        if self._get_clicked_item_at(pos):
            super().mouseDoubleClickEvent(event)
            return

        QTimer.singleShot(0, self._run_blank_area_refresh)
        event.accept()

    def _execute_item(self, item: ShortcutItem, force_new: bool = False):
        """执行项目"""
        if self._executing:
            return

        # 检查是否有选中文件需要打开
        files_to_use = []
        if item.type in (ShortcutType.FILE, ShortcutType.FOLDER):
            files_to_use = self._take_valid_selected_files_for_click()

        if files_to_use:
            logger.info(f"使用Explorer选中文件启动: {item.name}, 文件: {files_to_use}")
            # 先立即隐藏窗口，再执行拖放
            if not self.is_pinned:
                self.hide()
            # 清空选中文件，防止下次误用
            self._clear_selected_files_context()
            # 使用拖放逻辑执行
            self._execute_drop(item, files_to_use)
            return

        # ===== 优化修复：运行时输入 `{input}` 参数收集 =====
        input_prompts = []
        if item.type == ShortcutType.COMMAND and item.command:
            try:
                from core.command_variables import should_expand_command_variables
                command_type = getattr(item, "command_type", "cmd")
                enabled = getattr(item, "command_variables_enabled", None)
                if should_expand_command_variables(command_type, enabled):
                    from core.command_variables import collect_input_prompts
                    input_prompts = collect_input_prompts(item.command)
            except Exception as e:
                logger.error(f"提取命令输入变量失败: {e}")
        elif item.type == ShortcutType.URL and item.url:
            try:
                from core.command_variables import collect_input_prompts
                input_prompts = collect_input_prompts(item.url)
            except Exception as e:
                logger.error(f"提取URL输入变量失败: {e}")

        if input_prompts:
            try:
                from ui.styles.themed_messagebox import ThemedInputDialog
                runtime_inputs = {}
                for prompt in input_prompts:
                    label = prompt or "输入内容"
                    val, ok = ThemedInputDialog.getText(self, "运行参数", label)
                    if not ok:
                        logger.info("用户取消了运行时参数输入，快捷方式执行终止")
                        return
                    runtime_inputs[prompt] = val
                    if not prompt:
                        runtime_inputs["input"] = val
                item._runtime_input_values = runtime_inputs
            except Exception as e:
                logger.error(f"交互式参数收集失败: {e}")

        execute_item = item
        force_close_builtin_direct = False

        # Phase 2: route builtin slash commands by explicit interaction metadata.
        cmd_text = (item.command or "").strip()
        cmd_str = cmd_text.lower()
        if item.type == ShortcutType.COMMAND and item.command_type == "builtin" and cmd_str:
            force_close_builtin_direct = True
            _panel_v2_enabled = True
            try:
                from core import data_manager
                if data_manager is not None:
                    _panel_v2_enabled = data_manager.get_settings().enable_command_panel_v2
            except Exception:
                pass
            if _panel_v2_enabled:
                try:
                    from core import registry
                    from core.command_registry import (
                        COMMAND_INTERACTION_PANEL,
                        CommandContext,
                        CommandResult,
                        _CallbackHandler,
                        set_pending_command_result,
                    )
                    if registry is not None and registry.count() > 0:
                        from core.builtin_commands import canonical_builtin_command

                        command_parts = cmd_text.lstrip("/").split(None, 1)
                        cmd_word = command_parts[0].lower() if command_parts else ""
                        args_text = command_parts[1].strip() if len(command_parts) > 1 else ""
                        canonical = canonical_builtin_command(cmd_word)
                        registry_canonical = registry.get_canonical(cmd_word)
                        command_canonical = canonical or registry_canonical or cmd_word
                        cmd_def = (
                            registry.get(cmd_word)
                            or registry.get(registry_canonical)
                            or registry.get(canonical)
                        )

                        query = getattr(self, 'search_query', '').strip()
                        if query:
                            query_text = query[1:] if query.startswith('/') else query
                            query_parts = query_text.split(None, 1)
                            query_cmd = query_parts[0].lower() if query_parts else ""
                            query_args = query_parts[1].strip() if len(query_parts) > 1 else ""
                            query_canonical = canonical_builtin_command(query_cmd) or registry.get_canonical(query_cmd) or query_cmd
                            if query_args and (query_cmd == cmd_word or query_canonical == command_canonical):
                                args_text = query_args

                        if cmd_def is not None:
                            command_to_execute = cmd_def.id
                            if args_text:
                                command_to_execute = f"{command_to_execute} {args_text}"
                            if getattr(cmd_def, "interaction_mode", "") != COMMAND_INTERACTION_PANEL:
                                try:
                                    from dataclasses import replace
                                    execute_item = replace(item, command=command_to_execute)
                                except Exception:
                                    item.command = command_to_execute
                                    execute_item = item
                            elif not isinstance(cmd_def.handler, _CallbackHandler):
                                query_for_panel = f"/{cmd_def.id}"
                                if args_text:
                                    query_for_panel = f"{query_for_panel} {args_text}"
                                auto_fill_command = not bool(
                                    self.__dict__.get("_search_execute_from_keyboard", False)
                                )
                                if auto_fill_command and hasattr(self, '_set_search_query'):
                                    self._set_search_query(query_for_panel)
                                self._executing = True

                                def _on_update(update: CommandResult) -> None:
                                    self.show_command_result(update, cmd_def.id)

                                clipboard_text = ""
                                try:
                                    clipboard_text = self._read_clipboard_text()
                                except Exception:
                                    pass

                                selected_files = []
                                try:
                                    if self.__dict__.get("_selected_files_status", "") == "ready":
                                        selected_files = list(self.__dict__.get("_selected_files", []) or [])
                                except Exception:
                                    pass

                                ctx = CommandContext(
                                    raw_input=query_for_panel,
                                    args_text=args_text,
                                    clipboard_text=clipboard_text,
                                    selected_files=selected_files,
                                    update_callback=_on_update,
                                )
                                result = cmd_def.handler(ctx)
                                set_pending_command_result(result)
                                if not self.is_pinned:
                                    self.show()
                                    self.raise_()
                                    self.activateWindow()
                                self.show_command_result(result, cmd_def.id)
                                return
                except Exception as e:
                    logger.exception("Phase 2 command failed: %s", e)
                finally:
                    if self.__dict__.get("_executing", False):
                        self._executing = False

        self._executing = True
        self._launched_app = True  # 启动外部程序，隐藏时不恢复焦点
        logger.info(f"执行: {item.name} (类型: {item.type})")

        should_close = force_close_builtin_direct or not self.is_pinned

        # 优化：点击图标后立即隐藏窗口
        if should_close:
            self.hide()

        # 使用线程执行，避免阻塞 UI
        def do_execute_thread():
            try:
                if HAS_EXECUTOR and ShortcutExecutor:
                    success, error_msg = ShortcutExecutor.execute(execute_item, force_new)
                    if not success and error_msg:
                        # 在 UI 线程显示错误
                        self.execution_error.emit(item.name, error_msg)
                else:
                    if item.target_path:
                        try:
                            # 简单的 startfile 不支持获取详细错误
                            os.startfile(item.target_path)
                        except Exception as e:
                            self.execution_error.emit(item.name, str(e))
            except Exception as e:
                logger.error(f"执行失败: {e}")
                self.execution_error.emit(item.name, str(e))
            finally:
                self._executing = False

        threading.Thread(target=do_execute_thread, daemon=True, name="ItemExecutor").start()

    def _on_execution_error(self, name: str, error: str):
        """启动失败的处理"""
        # 确保在主线程显示弹窗
        try:
            from ui.styles.themed_messagebox import ThemedMessageBox
            ThemedMessageBox.critical(self.window(), "启动失败", f"无法启动: {name}\n\n原因: {error}")
        except Exception as e:
            logger.error(f"显示错误弹窗失败: {e}")



    def wheelEvent(self, event):
        """滚轮事件"""
        if hasattr(self, "has_command_result") and self.has_command_result():
            # 命令结果展示面板处于激活状态，彻底屏蔽滚轮切页
            event.accept()
            return

        modifiers = event.modifiers()
        delta = event.angleDelta().y()

        if modifiers == QtCompat.NoModifier:
            if self._is_search_active():
                # 搜索激活时，屏蔽滚轮翻页，指示器保持不动
                event.accept()
                return

            if len(self.pages) <= 1:
                event.accept()
                return

            import time
            now = time.time()

            # 计算滚动速度
            time_delta = now - self._last_wheel_time
            if time_delta < 0.15:  # 150ms内视为快速滚动
                self._wheel_speed = min(2.5, self._wheel_speed + 0.3)
            else:
                self._wheel_speed = 1.0
            self._last_wheel_time = now

            # 更新目标页面（不重置进度）
            direction = -1 if delta > 0 else 1
            old_page = self.current_page
            self.current_page = (self.current_page + direction) % len(self.pages)

            if self.current_page != old_page:
                self._target_page = self.current_page
                self.data_manager.update_settings(last_page_index=self.current_page)
                if not self._indicator_timer.isActive():
                    self._indicator_timer.start()

            self.hover_index = -1
            self.update()
            event.accept()
            return

        elif modifiers == QtCompat.ControlModifier:
            change = 5 if delta > 0 else -5
            new_alpha = max(0, min(100, self.settings.bg_alpha + change))
            if new_alpha != self.settings.bg_alpha:
                self.data_manager.update_settings(bg_alpha=new_alpha)
                self.settings = self.data_manager.get_settings()
                self.update()
            event.accept()
            return

        elif modifiers == QtCompat.ShiftModifier:
            change = 0.1 if delta > 0 else -0.1
            new_alpha = max(0.2, min(1.0, self.settings.icon_alpha + change))
            if abs(new_alpha - self.settings.icon_alpha) > 1e-9:
                self.data_manager.update_settings(icon_alpha=new_alpha)
                self.settings = self.data_manager.get_settings()
                self.update()
            event.accept()
            return

        super().wheelEvent(event)

    def keyPressEvent(self, event):
        """按键事件 - 支持平滑 caret、拼音搜索、以及 slash(/) 命令"""
        # Phase 2: command result mode interception (defensive against mock tests)
        try:
            cr = self._command_result
        except RuntimeError:
            cr = None
        if cr is not None:
            key = event.key()
            modifiers = event.modifiers()
            allow_search_edit_shortcut = False
            
            # 1. Ignore modifier keys alone to prevent closing the result card when Ctrl/Shift/Alt/Meta is pressed
            if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
                event.accept()
                return

            # 2. Support Ctrl+C (Copy) and Ctrl+A (Select All) without closing the panel
            if modifiers & Qt.ControlModifier:
                if key == Qt.Key_C:
                    if self._search_shortcuts_have_priority_over_result():
                        self._copy_search_selection()
                    else:
                        te = self.__dict__.get("_result_text_edit", None)
                        if te is not None and te.isVisible():
                            if te.textCursor().hasSelection():
                                te.copy()
                    event.accept()
                    return
                elif key == Qt.Key_A:
                    if self._search_shortcuts_have_priority_over_result():
                        self._select_all_search_text()
                    else:
                        te = self.__dict__.get("_result_text_edit", None)
                        if te is not None and te.isVisible():
                            te.selectAll()
                    event.accept()
                    return
                elif key in (Qt.Key_X, Qt.Key_V):
                    if self._search_shortcuts_have_priority_over_result():
                        allow_search_edit_shortcut = True
                    else:
                        event.accept()
                        return
                elif key in (Qt.Key_Z, Qt.Key_Y):
                    # Ignore other common editing shortcuts to avoid dismissing the panel or searching
                    event.accept()
                    return

            # 3. Allow arrow and navigation keys to navigate/scroll the QTextEdit, avoiding panel closing
            if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
                       Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown):
                te = self.__dict__.get("_result_text_edit", None)
                if te is not None and te.isVisible():
                    # Send event to QTextEdit if it doesn't already have focus
                    if not te.hasFocus():
                        QApplication.sendEvent(te, event)
                event.accept()
                return

            # 4. Handle Escape and Return/Enter as closing/execution keys
            if key in (Qt.Key_Escape, 16777216):
                self.clear_command_result()
                event.accept()
                return
            if key in (Qt.Key_Return, Qt.Key_Enter):
                for action in cr.actions:
                    if action.type == "copy" and action.value:
                        QApplication.clipboard().setText(action.value)
                        self.clear_command_result()
                        event.accept()
                        return
                self.clear_command_result()
                event.accept()
                return

            # 5. For any other key, if it is a printable key or backspace/delete, it closes the panel
            # and falls through to be entered into the search query.
            # Non-printable/control keys are accepted and ignored.
            text = event.text()
            is_printable = bool(text) and ord(text) >= 32 if len(text) == 1 else False
            if (
                not is_printable
                and key not in (Qt.Key_Backspace, Qt.Key_Delete)
                and not allow_search_edit_shortcut
            ):
                event.accept()
                return
            if not self._search_query_matches_result_command():
                self.clear_command_result()

        key = event.key()
        text = event.text()

        # 1. ESC 键清除搜索或隐藏窗口
        if key in (Qt.Key_Escape, 16777216): # 16777216 is Qt.Key_Escape
            if self._is_search_active():
                self._reset_search_state()
                event.accept()
                return
            else:
                event.accept()
                self.hide()
                return

        if event.modifiers() & QtCompat.ControlModifier and key == Qt.Key_V and not self._is_search_active():
            text_to_paste = self._read_clipboard_text()
            if text_to_paste:
                self._search_forced_active = True
                self._insert_or_replace_text(text_to_paste.replace("\r\n", " ").replace("\n", " ").replace("\r", " "))
            event.accept()
            return

        # 2. 如果搜索未激活，判断是否需要启动搜索
        is_printable = bool(text) and ord(text) >= 32 if len(text) == 1 else False

        if not self._is_search_active():
            if key == Qt.Key_Space:
                # 首个空格仅启动搜索，不触发实际查询
                self._search_forced_active = True
                self._set_search_query("")
                event.accept()
                return
            elif is_printable:
                # 键盘输入字符直接激活搜索
                self._insert_or_replace_text(text)
                event.accept()
                return
            elif key == Qt.Key_Left:
                self._switch_page(-1)
                event.accept()
                return
            elif key == Qt.Key_Right:
                self._switch_page(1)
                event.accept()
                return
            else:
                try:
                    super().keyPressEvent(event)
                except Exception:
                    pass
                return

        # 3. 搜索激活状态下的按键逻辑
        modifiers = event.modifiers()
        ctrl = bool(modifiers & QtCompat.ControlModifier)
        shift = bool(modifiers & QtCompat.ShiftModifier)

        if ctrl and key == Qt.Key_A:
            self._select_all_search_text()
            event.accept()
            return

        if ctrl and key in (Qt.Key_C, Qt.Key_Insert):
            self._copy_search_selection()
            event.accept()
            return

        if ctrl and key == Qt.Key_X:
            self._copy_search_selection()
            self._delete_search_selection()
            event.accept()
            return

        if (ctrl and key == Qt.Key_V) or (shift and key == Qt.Key_Insert):
            text_to_paste = self._read_clipboard_text()
            if text_to_paste:
                self._insert_or_replace_text(text_to_paste.replace("\r\n", " ").replace("\n", " ").replace("\r", " "))
            event.accept()
            return

        if key == Qt.Key_Up:
            if self.search_results:
                self.search_selected_index = max(0, self.search_selected_index - 1)
            event.accept()
            self.update()
            return

        elif key == Qt.Key_Down:
            if self.search_results:
                self.search_selected_index = min(len(self.search_results) - 1, self.search_selected_index + 1)
            event.accept()
            self.update()
            return

        elif key == Qt.Key_Left:
            self._move_search_cursor(self._previous_search_boundary(self.search_cursor_pos) if ctrl else self.search_cursor_pos - 1, keep_selection=shift)
            event.accept()
            return

        elif key == Qt.Key_Right:
            self._move_search_cursor(self._next_search_boundary(self.search_cursor_pos) if ctrl else self.search_cursor_pos + 1, keep_selection=shift)
            event.accept()
            return

        elif key == Qt.Key_Home:
            self._move_search_cursor(0, keep_selection=shift)
            event.accept()
            return

        elif key == Qt.Key_End:
            self._move_search_cursor(len(self.search_query), keep_selection=shift)
            event.accept()
            return

        elif key == Qt.Key_Backspace:
            self._delete_search_backward(word=ctrl)
            event.accept()
            return

        elif key == Qt.Key_Delete:
            self._delete_search_forward(word=ctrl)
            event.accept()
            return

        elif key in (Qt.Key_Return, Qt.Key_Enter):
            if self.search_results and 0 <= self.search_selected_index < len(self.search_results):
                shortcut = self.search_results[self.search_selected_index].shortcut
                if hasattr(self, '_execute_item'):
                    try:
                        self._search_execute_from_keyboard = True
                        self._execute_item(shortcut, force_new=False)
                    except Exception as e:
                        logger.exception("Failed to execute search item: %s", e)
                    finally:
                        self._search_execute_from_keyboard = False
                event.accept()
            return

        elif is_printable:
            self._insert_or_replace_text(text)
            event.accept()
            return

        else:
            try:
                super().keyPressEvent(event)
            except Exception:
                pass

    def inputMethodEvent(self, event):
        """输入法事件支持 (支持拼音输入法，测试安全)"""
        self._search_forced_active = True
        commit = ""
        preedit = ""

        if hasattr(event, 'commitString'):
            commit = event.commitString()
        else:
            commit = getattr(event, '_commit', "")

        if hasattr(event, 'preeditString'):
            preedit = event.preeditString()
        else:
            preedit = getattr(event, '_preedit', "")

        if commit:
            self._insert_or_replace_text(commit)
            self._search_preedit_text = ""
        else:
            self._search_preedit_text = preedit
            self._start_search_reveal_animation(True)
            self._restart_search_cursor_blink()
            self.update()

        event.accept()

        if type(event).__name__ != "_FakeInputMethodEvent":
            try:
                super().inputMethodEvent(event)
            except Exception:
                pass

    def inputMethodQuery(self, query):
        """Expose caret and surrounding text to IME for Chinese/Japanese/Korean input."""
        try:
            if query == Qt.ImCursorRectangle:
                return self._search_cursor_rect()
            if query == Qt.ImSurroundingText:
                return self.search_query
            if query == Qt.ImCursorPosition:
                return self.search_cursor_pos
            if query == Qt.ImAnchorPosition:
                return self.search_selection_anchor if self.search_selection_anchor is not None else self.search_cursor_pos
            if query == Qt.ImCurrentSelection:
                bounds = self._search_selection_bounds()
                if bounds:
                    start, end = bounds
                    return self.search_query[start:end]
                return ""
        except Exception:
            pass
        try:
            return super().inputMethodQuery(query)
        except Exception:
            return None

    def _insert_or_replace_text(self, new_text: str):
        """插入或替换选中文本"""
        if not new_text:
            return
        query = self.search_query
        cursor = self._clamp_search_pos(self.search_cursor_pos)
        anchor = self.search_selection_anchor

        if anchor is not None and anchor != cursor:
            start_sel = min(cursor, anchor)
            end_sel = max(cursor, anchor)
            query = query[:start_sel] + new_text + query[end_sel:]
            cursor = start_sel + len(new_text)
            anchor = None
        else:
            query = query[:cursor] + new_text + query[cursor:]
            cursor = cursor + len(new_text)
            anchor = None

        self._set_search_query(query, cursor_pos=cursor, selection_anchor=anchor)

    def _clamp_search_pos(self, pos: int) -> int:
        try:
            pos = int(pos)
        except Exception:
            pos = 0
        return max(0, min(len(getattr(self, "search_query", "") or ""), pos))

    def _search_selection_bounds(self):
        anchor = getattr(self, "search_selection_anchor", None)
        cursor = self._clamp_search_pos(getattr(self, "search_cursor_pos", 0))
        if anchor is None:
            return None
        anchor = self._clamp_search_pos(anchor)
        if anchor == cursor:
            return None
        return min(anchor, cursor), max(anchor, cursor)

    def _get_search_cursor_pos(self) -> int:
        return self._clamp_search_pos(getattr(self, "search_cursor_pos", 0))

    def _search_bar_full_height(self) -> int:
        return 34

    def _search_text_prefix(self) -> str:
        return "搜索: " if (getattr(self, "search_query", "") or getattr(self, "_search_preedit_text", "")) else "搜索"

    def _search_font(self) -> QFont:
        base_font = self.__dict__.get("_label_font")
        font = QFont(base_font) if base_font is not None else QFont()
        font.setPointSize(max(8, font.pointSize() + 1))
        return font

    def _search_metrics(self) -> QFontMetrics:
        return QFontMetrics(self._search_font())

    def _search_text_width(self, value: str) -> int:
        if QApplication.instance() is None:
            return sum(14 if ord(ch) > 127 else 7 for ch in (value or ""))
        metrics = self._search_metrics()
        if hasattr(metrics, "horizontalAdvance"):
            return metrics.horizontalAdvance(value)
        return metrics.width(value)

    def _search_bar_rect(self) -> QRectF:
        full_h = self._search_bar_full_height()
        x = self.padding
        w = self.width() - self.padding * 2
        return QRectF(x, 4, w, max(6, full_h - 8))

    def _search_text_rect(self) -> QRectF:
        return self._search_bar_rect().adjusted(9, 0, -9, 0)

    def _search_bar_contains(self, pos: QPoint) -> bool:
        try:
            if not self._is_search_layout_visible() and not self._is_search_active():
                return False
            return self._search_bar_rect().contains(pos)
        except Exception:
            return False

    def _ensure_search_cursor_visible(self):
        try:
            _ = self.width()
            _ = self.padding
        except Exception:
            self._search_scroll_x = 0
            return
        text_rect = self._search_text_rect()
        visible_w = max(1, int(text_rect.width()))
        prefix = self._search_text_prefix()
        query = getattr(self, "search_query", "") or ""
        cursor = self._clamp_search_pos(getattr(self, "search_cursor_pos", 0))
        preedit = getattr(self, "_search_preedit_text", "") or ""
        cursor_x = self._search_text_width(prefix + query[:cursor] + preedit)
        scroll = max(0, int(self.__dict__.get("_search_scroll_x", 0) or 0))
        margin = 8
        if cursor_x - scroll > visible_w - margin:
            scroll = cursor_x - visible_w + margin
        elif cursor_x - scroll < margin:
            scroll = max(0, cursor_x - margin)
        total_w = self._search_text_width(prefix + query + preedit)
        self._search_scroll_x = max(0, min(scroll, max(0, total_w - visible_w + margin)))

    def _search_cursor_rect(self) -> QRect:
        self._ensure_search_cursor_visible()
        text_rect = self._search_text_rect()
        prefix = self._search_text_prefix()
        query = getattr(self, "search_query", "") or ""
        cursor = self._clamp_search_pos(getattr(self, "search_cursor_pos", 0))
        preedit = getattr(self, "_search_preedit_text", "") or ""
        x = int(text_rect.left() + self._search_text_width(prefix + query[:cursor] + preedit) - int(self.__dict__.get("_search_scroll_x", 0) or 0))
        y = int(text_rect.top() + 7)
        return QRect(x, y, 1, max(12, int(text_rect.height() - 14)))

    def _search_pos_from_point(self, pos: QPoint) -> int:
        text_rect = self._search_text_rect()
        prefix_w = self._search_text_width(self._search_text_prefix())
        target = int(pos.x() - text_rect.left() + int(self.__dict__.get("_search_scroll_x", 0) or 0) - prefix_w)
        query = getattr(self, "search_query", "") or ""
        if target <= 0:
            return 0
        best = len(query)
        for i in range(len(query) + 1):
            left = self._search_text_width(query[:i])
            right = self._search_text_width(query[:i + 1]) if i < len(query) else left
            midpoint = (left + right) / 2
            if target < midpoint:
                best = i
                break
        return self._clamp_search_pos(best)

    def _restart_search_cursor_blink(self):
        self._search_cursor_visible = True
        timer = self.__dict__.get("_search_cursor_timer")
        try:
            if timer is not None and self._is_search_active():
                timer.start()
        except Exception:
            pass

    def _toggle_search_cursor(self):
        if not self._is_search_active():
            try:
                self._search_cursor_timer.stop()
            except Exception:
                pass
            self._search_cursor_visible = True
            return
        self._search_cursor_visible = not bool(getattr(self, "_search_cursor_visible", True))
        self.update(self._search_animation_update_rect())

    def _move_search_cursor(self, pos: int, keep_selection: bool = False):
        old_cursor = self._clamp_search_pos(getattr(self, "search_cursor_pos", 0))
        new_cursor = self._clamp_search_pos(pos)
        if keep_selection:
            if self.search_selection_anchor is None:
                self.search_selection_anchor = old_cursor
        else:
            self.search_selection_anchor = None
        self.search_cursor_pos = new_cursor
        self._ensure_search_cursor_visible()
        self._restart_search_cursor_blink()
        self.update()

    def _word_boundary_left(self, pos: int) -> int:
        query = getattr(self, "search_query", "") or ""
        pos = self._clamp_search_pos(pos)
        while pos > 0 and query[pos - 1].isspace():
            pos -= 1
        while pos > 0 and not query[pos - 1].isspace():
            pos -= 1
        return pos

    def _word_boundary_right(self, pos: int) -> int:
        query = getattr(self, "search_query", "") or ""
        pos = self._clamp_search_pos(pos)
        while pos < len(query) and query[pos].isspace():
            pos += 1
        while pos < len(query) and not query[pos].isspace():
            pos += 1
        return pos

    def _previous_search_boundary(self, pos: int) -> int:
        return self._word_boundary_left(pos)

    def _next_search_boundary(self, pos: int) -> int:
        return self._word_boundary_right(pos)

    def _search_word_bounds(self, pos: int) -> tuple[int, int]:
        query = getattr(self, "search_query", "") or ""
        pos = self._clamp_search_pos(pos)
        if not query:
            return 0, 0
        if pos == len(query) and pos > 0:
            pos -= 1
        if query[pos].isspace():
            return pos, pos
        start = pos
        end = pos + 1
        while start > 0 and not query[start - 1].isspace():
            start -= 1
        while end < len(query) and not query[end].isspace():
            end += 1
        return start, end

    def _delete_search_selection(self) -> bool:
        bounds = self._search_selection_bounds()
        if not bounds:
            return False
        start, end = bounds
        query = self.search_query[:start] + self.search_query[end:]
        self._set_search_query(query, cursor_pos=start, selection_anchor=None)
        return True

    def _delete_search_backward(self, word: bool = False):
        if self._delete_search_selection():
            return
        cursor = self._clamp_search_pos(self.search_cursor_pos)
        if cursor <= 0:
            return
        start = self._word_boundary_left(cursor) if word else cursor - 1
        query = self.search_query[:start] + self.search_query[cursor:]
        self._set_search_query(query, cursor_pos=start, selection_anchor=None)

    def _delete_search_forward(self, word: bool = False):
        if self._delete_search_selection():
            return
        cursor = self._clamp_search_pos(self.search_cursor_pos)
        if cursor >= len(self.search_query):
            return
        end = self._word_boundary_right(cursor) if word else cursor + 1
        query = self.search_query[:cursor] + self.search_query[end:]
        self._set_search_query(query, cursor_pos=cursor, selection_anchor=None)

    def _select_all_search_text(self):
        self.search_cursor_pos = len(self.search_query)
        self.search_selection_anchor = 0 if self.search_query else None
        self._restart_search_cursor_blink()
        self.update()

    def _selected_search_text(self) -> str:
        bounds = self._search_selection_bounds()
        if not bounds:
            return ""
        start, end = bounds
        return self.search_query[start:end]

    def _copy_search_selection(self):
        text = self._selected_search_text()
        if not text:
            return
        try:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(text)
        except Exception:
            pass

    def _cut_search_selection(self):
        if not self._selected_search_text():
            return
        self._copy_search_selection()
        self._delete_search_selection()

    def _paste_search_clipboard(self):
        text_to_paste = self._read_clipboard_text()
        if not text_to_paste:
            return
        self._search_forced_active = True
        self._insert_or_replace_text(text_to_paste.replace("\r\n", " ").replace("\n", " ").replace("\r", " "))

    def _clear_search_text(self):
        self._set_search_query("", cursor_pos=0, selection_anchor=None)
        self._search_forced_active = True

    def _show_search_context_menu(self, event):
        pos = self._get_event_pos(event)
        cursor = self._search_pos_from_point(pos)
        bounds = self._search_selection_bounds()
        if not bounds or not (bounds[0] <= cursor <= bounds[1]):
            self.search_cursor_pos = cursor
            self.search_selection_anchor = None
            self._ensure_search_cursor_visible()
            self._restart_search_cursor_blink()
            self.update()

        theme = getattr(self.settings, "theme", "dark")
        has_text = bool(getattr(self, "search_query", ""))
        has_selection = bool(self._selected_search_text())
        has_clipboard = bool(self._read_clipboard_text())
        menu = CompactResultPopupMenu(theme=theme, parent=None)
        menu.add_action("粘贴", self._paste_search_clipboard, enabled=has_clipboard)
        menu.add_separator()
        menu.add_action("复制", self._copy_search_selection, enabled=has_selection)
        menu.add_action("剪切", self._cut_search_selection, enabled=has_selection)
        menu.add_action("全选", self._select_all_search_text, enabled=has_text)
        menu.add_action("清空", self._clear_search_text, enabled=has_text)
        self._search_context_menu = menu
        menu.popup(self._get_event_global_pos(event))

    def _read_clipboard_text(self) -> str:
        try:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                return clipboard.text() or ""
        except Exception:
            pass
        return ""

    def _switch_page(self, direction: int):
        """切换页面"""
        if len(self.pages) <= 1:
            return

        old_page = self.current_page
        self.current_page = (self.current_page + direction) % len(self.pages)
        if self.current_page != old_page:
            self._target_page = self.current_page
            self.data_manager.update_settings(last_page_index=self.current_page)
            if not self._indicator_timer.isActive():
                self._indicator_timer.start()
        self.hover_index = -1
        self.update()

    def enterEvent(self, event):
        """鼠标进入"""
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开"""
        self.hover_index = -1
        self.dock_hover_index = -1
        self.update()

    def _check_close(self):
        """检查是否应该关闭 (Fallback)"""
        if self.is_pinned or self._executing or self._is_dragging:
            if self._hide_timer.isActive():
                self._hide_timer.stop()
            return

        cursor_pos = self.mapFromGlobal(QCursor.pos())
        inside = self.rect().contains(cursor_pos)

        auto_close = getattr(self.settings, 'popup_auto_close', True)

        if auto_close:
            if inside:
                if self._hide_timer.isActive():
                    self._hide_timer.stop()
                return
            if not self._hide_timer.isActive():
                delay = getattr(self.settings, 'hover_leave_delay', 200)
                self._hide_timer.start(delay)
        else:
            if self._hide_timer.isActive():
                self._hide_timer.stop()
            if inside:
                return
            try:
                import ctypes
                user32 = ctypes.windll.user32
                left_pressed = (user32.GetAsyncKeyState(0x01) & 0x8000) != 0
                right_pressed = (user32.GetAsyncKeyState(0x02) & 0x8000) != 0
                if left_pressed or right_pressed:
                    QTimer.singleShot(50, self.hide)
            except Exception:
                pass

    def focusOutEvent(self, event):
        """失去焦点"""
        if not self.is_pinned and not self._executing and not self._is_dragging:
            auto_close = getattr(self.settings, 'popup_auto_close', True)
            if auto_close:
                QTimer.singleShot(100, self._check_close)

    # ===== 搜索与 slash(/) 命令辅助方法 =====

    def _set_search_query(self, query: str, cursor_pos: int = None, selection_anchor: int = None):
        """设置搜索查询文本，并触发更新与动画"""
        self.search_query = query or ""
        if cursor_pos is None:
            self.search_cursor_pos = len(self.search_query)
        else:
            self.search_cursor_pos = self._clamp_search_pos(cursor_pos)
        self.search_selection_anchor = None if selection_anchor is None else self._clamp_search_pos(selection_anchor)
        self._ensure_search_cursor_visible()
        self._restart_search_cursor_blink()
        if (
            self.__dict__.get("_command_result") is not None
            and not self._search_query_matches_result_command()
        ):
            self.clear_command_result()

        is_active = bool(self.search_query) or self._search_forced_active
        self._start_search_reveal_animation(is_active)
        self._refresh_search_results()

    def _refresh_search_results(self):
        """核心刷新搜索结果，支持 Web 搜索引擎，Slash 命令及本地 + Dock 图标混合"""
        query = self.search_query.strip()
        if not query:
            self.search_results = []
            self.search_selected_index = -1
            self.update()
            return

        results = []

        def append_command_results(matched_cmds, folder_name="Slash Commands", score_start=100.0):
            for i, cmd_info in enumerate(matched_cmds):
                cmd_value = cmd_info.handler
                shortcut = ShortcutItem(
                    id=cmd_info.canonical,
                    name=cmd_info.display_name or cmd_info.canonical,
                    type=ShortcutType.COMMAND,
                    command=cmd_value,
                    command_type="builtin",
                    icon_path=cmd_info.icon_path,
                    enabled=True)
                results.append(FuzzyMatchResult(
                    shortcut=shortcut,
                    folder_id="slash_commands",
                    folder_name=folder_name,
                    score=score_start - i,
                    original_index=i,
                    matched_fields=["command"]))

        # 1. 尝试解析 Web 搜索引擎快捷搜索 (例如 "g cats")
        action = parse_search_action(self.search_query)
        if action is not None:
            url = build_search_url(action)
            web_shortcut = ShortcutItem(
                id=f"web_search_{action.engine}",
                name=f"{action.engine}: {action.keyword}",
                type=ShortcutType.URL,
                url=url,
                enabled=True
            )
            results.append(FuzzyMatchResult(
                shortcut=web_shortcut,
                folder_id="web_search",
                folder_name="Web Search",
                score=999.0,
                original_index=0,
                matched_fields=["url"]
            ))

        # 2. 检查是否为以 / 开头的内置 Slash 命令
        if self.search_query.startswith("/"):
            cmd_query = self.search_query[1:]
            matched_cmds = find_matching_commands(cmd_query)

            # When query is empty, prioritize favorites.
            if not cmd_query:
                fav_order = []
                try:
                    from core import data_manager
                    if data_manager is not None:
                        fav_order = data_manager.get_settings().favorite_commands or []
                except Exception:
                    pass

                cmd_map = {cmd_info.canonical: cmd_info for cmd_info in matched_cmds}
                fav_results = []
                seen_ids = set()

                # 1. Add favorites in their exact saved order
                for cid in fav_order:
                    if cid in cmd_map and cid not in seen_ids:
                        seen_ids.add(cid)
                        cmd_info = cmd_map[cid]
                        cmd_value = cmd_info.handler
                        shortcut = ShortcutItem(
                            id=cid, name=cmd_info.display_name or cid,
                            type=ShortcutType.COMMAND, command=cmd_value,
                            command_type="builtin", icon_path=cmd_info.icon_path,
                            enabled=True)
                        result = FuzzyMatchResult(
                            shortcut=shortcut, folder_id="slash_commands",
                            folder_name="收藏命令",
                            score=300.0, original_index=0,
                            matched_fields=["command"])
                        fav_results.append(result)

                results = fav_results
            else:
                append_command_results(matched_cmds, "Slash Commands", 100.0)

            # Plugin search sources
            try:
                from core.command_registry import _search_sources
                for src_id, src_info in _search_sources.items():
                    handler = src_info.get("handler")
                    if handler is None:
                        continue
                    try:
                        src_results = handler(cmd_query)
                        if src_results:
                            for sr in src_results:
                                shortcut = ShortcutItem(
                                    id=sr.get("id", src_id),
                                    name=sr.get("title", sr.get("name", src_id)),
                                    type=ShortcutType.COMMAND,
                                    command=sr.get("command", ""),
                                    command_type="builtin",
                                    enabled=True,
                                )
                                results.append(FuzzyMatchResult(
                                    shortcut=shortcut,
                                    folder_id=f"plugin_{src_info['plugin_id']}",
                                    folder_name=sr.get("folder", src_info.get("plugin_id", "插件")),
                                    score=150.0,
                                    original_index=0,
                                    matched_fields=["name"],
                                ))
                    except Exception:
                        logger.exception("搜索源 %s 查询失败", src_id)
            except Exception:
                pass
        else:
            # 3. 本地快捷图标 + Dock 图标的拼音/Fuzzy混合检索
            search_folders = list(self.pages or [])

            dock_folder = getattr(self, 'dock_folder', None)
            if dock_folder is not None:
                if dock_folder not in search_folders:
                    search_folders.append(dock_folder)
            elif getattr(self, 'dock_items', None):
                from core.data_models import Folder
                temp_dock_folder = Folder(id="dock", name="Dock", is_dock=True, items=self.dock_items)
                search_folders.append(temp_dock_folder)

            sort_mode = getattr(self.settings, 'sort_mode', 'smart')
            local_results = search_shortcuts(search_folders, query, sort_mode=sort_mode)
            results.extend(local_results)

            if len(query) >= 2:
                try:
                    matched_cmds = find_matching_commands(query)
                    append_command_results(matched_cmds, "Commands", 80.0)
                except Exception:
                    logger.exception("鍛戒护鎼滅储澶辫触: %s", query)

        self.search_results = results
        if results:
            self.search_selected_index = 0
        else:
            self.search_selected_index = -1

        self.update()

    def _current_search_bar_height(self) -> int:
        """返回搜索框高度 (常量 34)"""
        return 34

    def _search_visible_height(self) -> int:
        """返回当前动画进度下的搜索框可见高度"""
        return int(self._search_reveal_progress * 34)

    def _body_y_offset(self) -> int:
        """返回由于搜索框显示而导致主体区域下移的Y偏移量"""
        if not hasattr(self, '_search_reveal_progress'):
            return 0
        return int(self._search_reveal_progress * 34)

    def _search_visible_top_inset(self) -> int:
        """返回搜索框渲染所需的顶部剪切偏移 (0 代表完全可见, 34 代表完全隐藏)"""
        progress_px = int(self._search_reveal_progress * 34)
        return 34 - progress_px

    def _background_top_inset(self) -> int:
        """Return the outer background inset used only during search reveal."""
        if not self._is_search_layout_visible():
            return 0
        return self._search_visible_top_inset()

    def _is_search_layout_visible(self) -> bool:
        """返回搜索框布局在视觉上是否可见"""
        if not hasattr(self, 'search_query'):
            return False
        return (
            bool(self.search_query)
            or self._search_reveal_progress > 0.001
            or self._search_target_progress > 0.0
            or self._search_hide_geometry_pending
        )

    def _is_search_active(self) -> bool:
        """搜索模式是否处于激活状态"""
        if self.__dict__.get("_command_result", None) is not None:
            return self._search_query_matches_result_command()
        return bool(self.search_query) or self._search_forced_active

    def _search_animation_update_rect(self) -> QRect:
        """返回用于重绘搜索栏区域的 QRect"""
        return QRect(0, 0, self.width(), 34 + self._get_paint_corner_radius() + 2)

    def _remember_search_body_anchor(self):
        """记录弹窗主体的基准 Y 坐标 (无搜索状态时的窗口顶部 Y)"""
        old_anchor = getattr(self, '_search_body_anchor_y', 0)
        if old_anchor == 0:
            self._search_body_anchor_y = self.geometry().y()
            logger.debug(f"[ANCHOR] 记录基准点: y={self._search_body_anchor_y}, geometry={self.geometry()}, search_progress={getattr(self, '_search_reveal_progress', 'N/A')}")
        else:
            logger.debug(f"[ANCHOR] 使用已有基准点: y={old_anchor}")

    def _set_fixed_geometry_atomically(self, left: int, top: int, width: int, height: int):
        """原子级设置窗口尺寸与位置，防止 DWM 多重绘制闪烁"""
        self.setGeometry(left, top, width, height)
        try:
            self._update_window_effect()
        except Exception:
            pass

    def _apply_search_geometry(self, skip_effect_update=False, repaint=True, restore_updates=True, progress_override=None):
        """物理几何体位置/尺寸调整"""
        self._remember_search_body_anchor()
        base_y = self._search_body_anchor_y
        geom = self.geometry()
        x = geom.x()
        w = geom.width()

        progress = self._search_reveal_progress if progress_override is None else float(progress_override)
        y_offset = int(progress * 34)

        if hasattr(self, '_calculate_fixed_size'):
            calc_w, calc_h = self._calculate_fixed_size(y_offset_override=y_offset)
        else:
            calc_w = w
            calc_h = geom.height()

        target_h = calc_h
        target_y = base_y - y_offset

        if geom.y() != target_y or geom.height() != target_h or geom.width() != calc_w:
            logger.debug(f"[GEOM] 调整窗口: progress={self._search_reveal_progress:.3f}, "
                         f"old=({geom.x()},{geom.y()},{geom.width()}x{geom.height()}), "
                         f"new=({x},{target_y},{calc_w}x{target_h})")

            # 设置标志，避免重复更新窗口效果
            self._geometry_adjusting = True

            try:
                # 禁用更新
                self.setUpdatesEnabled(False)

                # 使用 Qt 方法调整几何
                if skip_effect_update:
                    self.setGeometry(x, target_y, calc_w, target_h)
                else:
                    self._set_fixed_geometry_atomically(x, target_y, calc_w, target_h)

                # 同步几何信息
                QApplication.processEvents()

                # 更新窗口效果（只更新一次）
                if not skip_effect_update:
                    try:
                        self._geometry_adjusting = False
                        self._update_window_effect()
                        self._geometry_adjusting = True
                    except Exception:
                        pass

                # 启用更新并重绘
                if restore_updates:
                    self.setUpdatesEnabled(True)
                    if repaint:
                        self.repaint()
            finally:
                self._geometry_adjusting = False

    def _apply_search_mask(self, force: bool = False):
        """采用遮罩掩码裁剪顶部搜索区域"""
        if not self._is_search_layout_visible() and not force:
            logger.debug(f"[SEARCH_MASK] 清除搜索遮罩: window={self.width()}x{self.height()}")
            self.clearMask()
            return

        inset = self._search_visible_top_inset()
        w = self.width()
        h = self.height()
        r = self._get_paint_corner_radius()

        logger.debug(f"[SEARCH_MASK] 应用搜索遮罩: window={w}x{h}, inset={inset}, visible_y={inset}, visible_h={h - inset}, radius={r}")

        mask = QBitmap(w, h)
        mask.fill(Qt.color0)

        painter = QPainter(mask)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.color1)
        painter.setPen(Qt.NoPen)

        path = QPainterPath()
        visible_y = inset
        visible_h = h - inset
        path.addRoundedRect(QRectF(0, visible_y, w, visible_h), r, r)
        painter.drawPath(path)
        painter.end()

        self.setMask(mask)
        logger.debug("[SEARCH_MASK] 遮罩已应用")



    def _start_search_reveal_animation(self, active: bool):
        """启动展开或收起动画"""
        self._remember_search_body_anchor()
        target = 1.0 if active else 0.0

        if (
            abs(self._search_target_progress - target) < 1e-9
            and abs(self._search_reveal_progress - target) < 1e-9
        ):
            return

        self._search_target_progress = target
        self._search_anim_from_progress = self._search_reveal_progress
        self._search_anim_started_at = time.time()
        self._search_anim_last_ts = self._search_anim_started_at

        if active:
            self._search_hide_geometry_pending = False
            self._search_reveal_progress = 1.0
            self._search_anim_from_progress = 1.0
            self._apply_search_geometry(repaint=False)
            # 立即调整窗口到最终位置
            # 重置进度开始动画
            self._apply_search_mask(force=True)
            self.update(self._search_animation_update_rect())
            self.repaint()
            return

        if not self._search_anim_timer.isActive():
            self._search_anim_timer.start()

    def _tick_search_reveal(self):
        """处理动画每帧更新"""
        now = time.time()
        elapsed_ms = (now - self._search_anim_started_at) * 1000.0
        duration = self._search_anim_duration_ms

        if elapsed_ms >= duration:
            self._search_reveal_progress = self._search_target_progress
            self._search_anim_timer.stop()

            if self._search_target_progress == 0.0:
                self._finish_search_hide_geometry()
                return
            else:
                self._apply_search_mask()
                self.update()
        else:
            t = elapsed_ms / duration
            ease_t = 1.0 - (1.0 - t) ** 3

            diff = self._search_target_progress - self._search_anim_from_progress
            self._search_reveal_progress = self._search_anim_from_progress + diff * ease_t

            self._apply_search_mask()
            self.update(self._search_animation_update_rect())

        try:
            import sys
            if 'pytest' in sys.modules:
                self.repaint()
        except Exception:
            pass

    def _finish_search_hide_geometry(self):
        """收尾隐藏动画并恢复尺寸"""
        self._search_hide_geometry_pending = False
        self._apply_search_geometry()
        self.clearMask()
        self.update()
        try:
            import sys
            if 'pytest' in sys.modules:
                self.repaint()
        except Exception:
            pass

    def _reset_search_state(self):
        """重置所有搜索状态"""
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
        self._search_reveal_progress = 0.0
        self._search_target_progress = 0.0
        self._search_hide_geometry_pending = False

        # 确保窗口显示状态下，组件透明度/出现进度恢复为 1.0
        try:
            if self.isVisible():
                self._reveal_progress = 1.0
        except Exception:
            self._reveal_progress = 1.0

        try:
            self._apply_search_geometry()
            self.clearMask()
        except Exception:
            pass
        self.update()

    # ===== 页面切换与绘图缓存辅助方法 =====

    def _preload_animation_pages(self):
        """增量式预加载：不阻塞 UI 线程，分帧逐步加载图标和渲染 page pixmap"""
        if not self.pages:
            return
        # 停止已有的预加载定时器（如果有）
        old_timer = getattr(self, '_preload_batch_timer', None)
        if old_timer is not None:
            old_timer.stop()

        # 构建待加载的 item 列表（优先当前页和相邻页）
        items_list = []
        n = len(self.pages)
        # 优先顺序：当前页 → 下一页 → 上一页 → 其余页
        priority_order = [self.current_page]
        if n > 1:
            priority_order.append((self.current_page + 1) % n)
        if n > 2:
            priority_order.append((self.current_page - 1) % n)
        for i in range(n):
            if i not in priority_order:
                priority_order.append(i)

        for page_idx in priority_order:
            page = self.pages[page_idx]
            for item_entry in page.items:
                if isinstance(item_entry, dict):
                    item = item_entry.get("item")
                else:
                    item = item_entry
                if item is not None:
                    items_list.append(item)

        self._preload_items_list = items_list
        self._preload_icon_idx = 0
        self._preload_page_queue = list(priority_order)

        self._preload_batch_timer = QTimer(self)
        self._preload_batch_timer.setInterval(1)
        self._preload_batch_timer.timeout.connect(self._preload_next_batch)
        self._preload_batch_timer.start()

    def _preload_next_batch(self):
        """每帧处理一小批图标加载，8ms 预算内完成后让出事件循环"""
        import time
        deadline = time.perf_counter() + 0.008  # 8ms 预算，不影响 60fps

        # 阶段1：加载图标到 _icon_pixmap_cache
        items = getattr(self, '_preload_items_list', None)
        idx = getattr(self, '_preload_icon_idx', 0)
        if items and idx < len(items):
            while idx < len(items) and time.perf_counter() < deadline:
                try:
                    self._get_icon(items[idx])
                except Exception:
                    pass
                idx += 1
            self._preload_icon_idx = idx
            if idx < len(items):
                return  # 还有图标未加载，下一帧继续

        # 阶段2：预渲染 page pixmap（每帧渲染一页）
        page_queue = getattr(self, '_preload_page_queue', None)
        if page_queue:
            page_idx = page_queue.pop(0)
            theme = getattr(self.settings, 'theme', 'dark')
            text_color = QColor(255, 255, 255) if theme == 'dark' else QColor(0, 0, 0)
            hover_color = QColor(255, 255, 255, 20) if theme == 'dark' else QColor(0, 0, 0, 20)
            drop_highlight_color = QColor(0, 120, 215, 100)
            bg_mode = getattr(self.settings, 'bg_mode', 'acrylic')
            try:
                self._get_page_animation_pixmap(page_idx, text_color, hover_color, drop_highlight_color, bg_mode)
            except Exception:
                pass
            if page_queue:
                return  # 还有页面未渲染，下一帧继续

        # 全部完成，停止定时器并清理
        timer = getattr(self, '_preload_batch_timer', None)
        if timer:
            timer.stop()
        self._preload_items_list = None
        self._preload_page_queue = None

    def _warm_page_pixmap_cache(self, pages):
        """预热指定页面的绘图缓存"""
        theme = getattr(self.settings, 'theme', 'dark')
        text_color = QColor(255, 255, 255) if theme == 'dark' else QColor(0, 0, 0)
        hover_color = QColor(255, 255, 255, 20) if theme == 'dark' else QColor(0, 0, 0, 20)
        drop_highlight_color = QColor(0, 120, 215, 100)
        bg_mode = getattr(self.settings, 'bg_mode', 'acrylic')
        for page_idx in pages:
            try:
                self._get_page_animation_pixmap(page_idx, text_color, hover_color, drop_highlight_color, bg_mode)
            except Exception:
                pass

    def _request_page_animation_update(self):
        """请求页面切换动画的重绘区域"""
        dock_y = getattr(self, 'dock_y', self.height())
        self.update(QRect(0, 0, self.width(), dock_y))
