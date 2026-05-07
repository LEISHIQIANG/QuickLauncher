"""
弹出启动器窗口
"""

import os
import sys
import logging
import threading
import time
from collections import OrderedDict

try:
    import win32com.client
    import win32gui
    HAS_WIN32_SHELL = True
except ImportError:
    HAS_WIN32_SHELL = False

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from qt_compat import (
    QWidget, QApplication, Qt, QtCompat, QPoint, QTimer, QRect,
    QPixmap, QPainter, QColor, QFont, QBrush, QPen, QPainterPath, QCursor,
    pyqtSignal, QImage, QRectF, QImageReader, QSize, QImageIOHandler, QThread,
    QGraphicsDropShadowEffect, QRegion, QBitmap, pyqtProperty
)

from core import DataManager, ShortcutItem, ShortcutType
from core.windows_uipi import allow_drag_drop_for_widget
from ui.utils.window_effect import WindowEffect, is_win11, is_win10, enable_acrylic_for_config_window, get_window_effect
from core.display_debug_logger import get_display_debug_logger

logger = logging.getLogger(__name__)

from ui.launcher_popup.window_detection import (
    EXPLORER_WINDOW_PROXIMITY_PX, EXPLORER_WINDOW_CLASSES, DESKTOP_WINDOW_CLASSES,
    _normalize_window_hwnd, _get_window_class_name,
    _is_explorer_like_window, _is_desktop_window, _point_near_window
)
from ui.launcher_popup.file_selection import FileSelectionThread
from ui.launcher_popup.popup_background import PopupBackgroundMixin
from ui.launcher_popup.popup_renderer import PopupRendererMixin
from ui.launcher_popup.popup_drag_drop import PopupDragDropMixin
from ui.launcher_popup.popup_icons import PopupIconMixin

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


class LauncherPopup(PopupBackgroundMixin, PopupRendererMixin, PopupDragDropMixin, PopupIconMixin, QWidget):
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
    
    def __init__(self, data_manager: DataManager, x: int, y: int, tray_app=None):
        super().__init__()

        # 保存 TrayApp 引用
        self._drag_drop_compat_applied = False
        self.tray_app = tray_app
        
        # 连接信号
        self.bg_loaded_signal.connect(self._on_bg_loaded)
        self.execution_error.connect(self._on_execution_error)
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

        # 动画进度 (0.0 到 1.0)
        self._reveal_progress = 0.0
        self._is_hiding = False

        self._icon_pixmap_cache = OrderedDict()
        self._default_icon_cache = {}
        self._visible_icons_preloaded = False
        self._first_show_ready = False
        self._blank_refresh_in_progress = False
        # 使用全局字体
        self._label_font = QFont()
        self._label_font.setPointSize(7)
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
        
        # 立即捕获当前环境 (HWND)
        current_hwnd = 0
        if HAS_WIN32_SHELL:
            try:
                current_hwnd = win32gui.GetForegroundWindow()
            except Exception as e:
                logger.debug("Failed to capture foreground window during init: %s", e)
        self._selected_files_trigger_pos = (int(x), int(y))
                 
        # 异步检测选中文件
        self._start_file_check(current_hwnd)
        
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
        r = max(0, int(radius))
        if r <= 0:
            self.clearMask()
            return
        rect = QRect(int(margin), int(margin), int(clip_w), int(clip_h))
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), r, r)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _update_window_effect(self):
        """更新窗口特效 (Acrylic / Blur)"""
        try:
            bg_mode = getattr(self.settings, 'bg_mode', 'theme')
            desired_radius = getattr(self.settings, 'corner_radius', 8)

            hwnd = int(self.winId())
            if not hwnd:
                return
            
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
                    if w > 0 and h > 0:
                        # 步骤1: 设置窗口裁剪区域（硬性圆角边界）
                        self.window_effect.set_window_region(hwnd, w, h, radius)
                        # 步骤2: 设置 DWM 模糊区域（与裁剪区域完全一致）
                        self.window_effect.set_dwm_blur_behind(hwnd, w, h, radius, enable=True)
                    # 步骤3: 应用 Acrylic 半透明着色层（blur=False 避免冲突）
                    self.window_effect.set_acrylic(hwnd, gradient_color, enable=True, blur=False)
                
            else:
                # 其他模式禁用特效 (Theme / Image 模式)
                if getattr(self, '_win10_dwm_blur_active', False):
                    self.window_effect.set_dwm_blur_behind(hwnd, 0, 0, 0, enable=False)
                    self._win10_dwm_blur_active = False
                self.window_effect.set_acrylic(hwnd, enable=False)
                self.window_effect.set_round_corners(hwnd, enable=False)
                self.window_effect.clear_window_region(hwnd)
                self.clearMask()
                
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
    
    def _calculate_fixed_size(self):
        """基于"常用"页面计算固定窗口大小"""
        # 使用配置的每列行数
        self.fixed_rows = getattr(self.settings, 'popup_max_rows', 3)
        self.shadow_margin = 0
        self.cell_h = int(self.cell_size * 1.15)

        width = self.padding * 2 + self.cols * self.cell_size
        self.content_height = self.padding + self.fixed_rows * self.cell_h

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

    def preload_visible_icons(self):
        """预热首屏可见图标，减少首次弹出时的图标补绘感。"""
        if not self.isVisible():
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

    def prepare_first_show(self):
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
            self.preload_visible_icons()
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

    def _start_file_check(self, hwnd=None):
        """启动文件检测线程"""
        # 如果已有线程在运行，就不管了，让它跑完
        # 或者可以保存引用，但这只是检测，频率不高
        self._file_check_seq += 1
        thread = FileSelectionThread(
            hwnd,
            request_id=self._file_check_seq,
            request_started_at=time.monotonic(),
            trigger_pos=self._selected_files_trigger_pos,
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

    def _take_valid_selected_files_for_click(self) -> list:
        if not self._selected_files:
            return []

        request_hwnd = int(self._selected_files_request_hwnd or 0)
        source_hwnd = int(self._selected_files_source_hwnd or 0)
        if not request_hwnd or not _is_explorer_like_window(request_hwnd):
            logger.info(f"忽略 Explorer 选中文件: 前台窗口不是 Explorer request={request_hwnd}")
            self._clear_selected_files_context()
            return []

        if request_hwnd and source_hwnd and request_hwnd != source_hwnd:
            # 桌面文件：request 是文件夹窗口，source 是 Progman/WorkerW，允许通过
            if not _is_desktop_window(source_hwnd):
                logger.info(
                    f"忽略 Explorer 选中文件: 来源窗口不匹配 request={request_hwnd}, source={source_hwnd}"
                )
                self._clear_selected_files_context()
                return []

        trigger_pos = self._selected_files_trigger_pos
        # 桌面是全屏窗口，跳过位置检查
        if not _is_desktop_window(request_hwnd):
            if not trigger_pos or not _point_near_window(request_hwnd, trigger_pos[0], trigger_pos[1]):
                logger.info(
                    f"忽略 Explorer 选中文件: 触发点不在前台 Explorer 窗口附近 "
                    f"request={request_hwnd}, trigger={trigger_pos}"
                )
                self._clear_selected_files_context()
                return []

        return list(self._selected_files)
        
    def _on_files_found(self, files):
        """文件检测回调"""
        thread = self.sender()
        request_id = int(getattr(thread, "request_id", 0) or 0)
        if request_id and request_id != self._file_check_seq:
            logger.debug(f"忽略过期的选中文件结果: request_id={request_id}, current={self._file_check_seq}")
            return

        self._selected_files = list(files or [])
        self._selected_files_source_hwnd = int(getattr(thread, "matched_root_hwnd", 0) or 0)
        self._selected_files_request_hwnd = int(getattr(thread, "requested_root_hwnd", 0) or 0)
        self._selected_files_request_started_at = float(getattr(thread, "request_started_at", 0.0) or 0.0)
        self._selected_files_captured_at = float(getattr(thread, "captured_at", 0.0) or 0.0)
        logger.info(
            f"异步检测到选中文件: {len(self._selected_files)} 个, request={self._selected_files_request_hwnd}, "
            f"source={self._selected_files_source_hwnd}, trigger={self._selected_files_trigger_pos}"
        )

    def refresh_data(
        self,
        x: int = None,
        y: int = None,
        refresh_selection: bool = True,
        force: bool = False,
        reposition: bool = True
    ):
        """刷新数据并重置位置"""
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
            if x is not None and y is not None:
                self._selected_files_trigger_pos = (int(x), int(y))

        # 3. 延迟执行耗时的 COM 操作 (文件查找)
        # 使用线程处理，避免阻塞 UI
        # 3. 延迟执行耗时的 COM 操作 (文件查找)
        # 使用线程处理，避免阻塞 UI
        if refresh_selection:
            self._start_file_check(current_hwnd)
        
        # 4. 始终重新计算窗口大小 (因为 reload 移除后，prev_item_count 比较不再可靠)
        # 更新设置参数
        self.settings = self.data_manager.get_settings()
        self.cols = self.settings.cols
        self.cell_size = self.settings.cell_size
        self.icon_size = self.settings.icon_size
        self.cell_h = int(self.cell_size * 1.15)

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
        """图标闪烁效果 - 模拟桌面刷新的视觉反馈"""
        # 保存原始透明度
        original_alpha = self.settings.icon_alpha

        # 创建闪烁动画序列
        def flash_step_1():
            # 第一步：降低透明度
            self.settings.icon_alpha = 0.3
            self.update()
            QTimer.singleShot(50, flash_step_2)

        def flash_step_2():
            # 第二步：恢复透明度
            self.settings.icon_alpha = original_alpha
            self.update()
            QTimer.singleShot(50, flash_step_3)

        def flash_step_3():
            # 第三步：再次降低（第二次闪烁）
            self.settings.icon_alpha = 0.4
            self.update()
            QTimer.singleShot(50, flash_step_4)

        def flash_step_4():
            # 第四步：最终恢复
            self.settings.icon_alpha = original_alpha
            self.update()

        # 开始闪烁动画
        flash_step_1()


    # ===== 拖放事件处理 =====
    
    def _get_event_pos(self, event):
        """获取事件位置"""
        if hasattr(event, 'position'):
            # Newer Qt event API
            return event.position().toPoint()
        else:
            # PyQt5
            return event.pos()

    def _get_clicked_item_at(self, pos: QPoint):
        """返回指定位置命中的项目，没有命中则返回 None"""
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
            col = (pos.x() - self.padding) // self.cell_size
            row = (pos.y() - self.padding) // self.cell_h

            if 0 <= col < self.cols and row < self.fixed_rows:
                index = row * self.cols + col
                if self.pages and self.current_page < len(self.pages):
                    items = self.pages[self.current_page].items
                    if 0 <= index < len(items):
                        return items[index]

        return None

    def _refresh_after_folder_sync(self):
        """同步文件夹后刷新当前弹窗"""
        self._sync_all_folders()
        self.refresh_data(refresh_selection=False, force=True, reposition=False)
        self._flash_icons()
        if self.tray_app and getattr(self.tray_app, 'config_window', None):
            if hasattr(self.tray_app.config_window, '_on_settings_panel_changed'):
                self.tray_app.config_window._on_settings_panel_changed()

    def _run_blank_area_refresh(self):
        """在双击事件结束后执行空白区刷新，避免重入和窗口抖动"""
        if self._blank_refresh_in_progress:
            return

        self._blank_refresh_in_progress = True
        try:
            logger.info("左键双击空白区域，同步文件夹并刷新图标")
            self._refresh_after_folder_sync()
            logger.info(f"同步并刷新完成，页面数: {len(self.pages)}, Dock项: {len(self.dock_items)}")
        except Exception as e:
            logger.error(f"同步并刷新失败: {e}")
        finally:
            self._blank_refresh_in_progress = False
    
    
    
    
    
    

    
    # ===== 拖放事件处理结束 =====
    





    
    

    

    

    
    
    def mouseMoveEvent(self, event):
        """鼠标移动"""
        pos = self._get_event_pos(event)
        new_hover = -1
        new_dock_hover = -1
        
        if pos.y() >= self.dock_y and self.dock_items:
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
            col = (pos.x() - self.padding) // self.cell_size
            row = (pos.y() - self.padding) // self.cell_h

            if 0 <= col < self.cols and row < self.fixed_rows:
                index = row * self.cols + col

                if self.pages and self.current_page < len(self.pages):
                    items = self.pages[self.current_page].items
                    if 0 <= index < len(items):
                        new_hover = index
        
        if new_hover != self.hover_index or new_dock_hover != self.dock_hover_index:
            self.hover_index = new_hover
            self.dock_hover_index = new_dock_hover
            self.update()
    
    def mousePressEvent(self, event):
        """鼠标按下"""
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        pos = self._get_event_pos(event)

        # ===== 右键处理 =====
        if event.button() == QtCompat.RightButton:
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
        if event.button() != QtCompat.LeftButton:
            super().mouseDoubleClickEvent(event)
            return

        if self._executing or self._blank_refresh_in_progress:
            event.accept()
            return

        pos = self._get_event_pos(event)
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
        
        self._executing = True
        self._launched_app = True  # 启动外部程序，隐藏时不恢复焦点
        logger.info(f"执行: {item.name} (类型: {item.type})")
        
        should_close = not self.is_pinned
        
        # 优化：点击图标后立即隐藏窗口
        if should_close:
            self.hide()
        
        # 使用线程执行，避免阻塞 UI
        def do_execute_thread():
            try:
                if HAS_EXECUTOR and ShortcutExecutor:
                    success, error_msg = ShortcutExecutor.execute(item, force_new)
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
        modifiers = event.modifiers()
        delta = event.angleDelta().y()
        
        if modifiers == QtCompat.NoModifier:
            if len(self.pages) <= 1:
                event.accept()
                return
            old_page = self.current_page
            direction = -1 if delta > 0 else 1
            self.current_page = (self.current_page + direction) % len(self.pages)

            if self.current_page != old_page:
                self._prev_page = old_page
                self._page_slide_dir = direction
                self._page_slide_progress = 0.0
                self.data_manager.update_settings(last_page_index=self.current_page)
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
        """按键事件"""
        key = event.key()
        
        if key == QtCompat.Key_Escape:
            self.close()
        elif key == QtCompat.Key_Left:
            self._switch_page(-1)
        elif key == QtCompat.Key_Right:
            self._switch_page(1)
    
    def _switch_page(self, direction: int):
        """切换页面"""
        if len(self.pages) <= 1:
            return

        old_page = self.current_page
        self.current_page = (self.current_page + direction) % len(self.pages)
        if self.current_page != old_page:
            self._prev_page = old_page
            self._page_slide_dir = direction
            self._page_slide_progress = 0.0
            self.data_manager.update_settings(last_page_index=self.current_page)
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
        
        # 检查是否启用自动关闭
        auto_close = getattr(self.settings, 'popup_auto_close', True)
        
        if auto_close:
            # 自动关闭模式：鼠标离开窗口后延迟关闭
            if inside:
                if self._hide_timer.isActive():
                    self._hide_timer.stop()
                return
            
            if not self._hide_timer.isActive():
                delay = getattr(self.settings, 'hover_leave_delay', 200)
                self._hide_timer.start(delay)
        else:
            # 手动关闭模式：检测鼠标按钮是否在窗口外被按下
            if self._hide_timer.isActive():
                self._hide_timer.stop()
            
            # 如果鼠标在窗口内，直接返回
            if inside:
                return
            
            # 鼠标在窗口外，检测鼠标按钮状态
            try:
                import ctypes
                user32 = ctypes.windll.user32
                # VK_LBUTTON = 0x01 (左键)
                # VK_RBUTTON = 0x02 (右键) 
                # VK_MBUTTON = 0x04 (中键)
                left_pressed = (user32.GetAsyncKeyState(0x01) & 0x8000) != 0
                right_pressed = (user32.GetAsyncKeyState(0x02) & 0x8000) != 0
                
                # 如果鼠标按钮在窗口外被按下，关闭窗口
                if left_pressed or right_pressed:
                    # 延迟一小段时间关闭，避免影响点击操作
                    QTimer.singleShot(50, self.hide)
            except Exception:
                pass

    
    def focusOutEvent(self, event):
        """失去焦点"""
        # 如果正在拖放，不要关闭窗口
        if not self.is_pinned and not self._executing and not self._is_dragging:
            # 检查是否启用自动关闭
            auto_close = getattr(self.settings, 'popup_auto_close', True)
            if auto_close:
                QTimer.singleShot(100, self._check_close)
            # 如果自动关闭禁用，焦点丢失不会触发关闭
            # 只有点击操作才会关闭窗口
