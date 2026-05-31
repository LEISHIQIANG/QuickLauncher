"""Data refresh, folder sync, icon flash, settings refresh, and file selection for LauncherPopup."""

import logging
import os
import time

try:
    import win32gui

    HAS_WIN32_SHELL = True
except ImportError:
    HAS_WIN32_SHELL = False

from core.window_detection import _is_desktop_window, _is_explorer_like_window
from qt_compat import (
    QPixmap,
    QtCompat,
    QTimer,
)
from ui.launcher_popup.file_selection import FileSelectionThread, SelectionTriggerContext
from ui.launcher_popup.popup_window_helpers import FolderSyncWorker
from ui.utils.window_effect import is_win10, is_win11

logger = logging.getLogger(__name__)

try:
    from core import IconExtractor

    HAS_ICON_EXTRACTOR = True
except ImportError:
    HAS_ICON_EXTRACTOR = False
    IconExtractor = None


class PopupDataRefreshMixin:
    """Data refresh, folder sync, icon flash, settings refresh, and file selection."""

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
            if mode == "acrylic" and is_win10():
                # Win10 Acrylic allows DWM Blur rounding now
                pass
            effect_enabled = (mode == "acrylic") or (mode == "theme" and int(blur or 0) > 0)
            if is_win11() and effect_enabled:
                return self._get_win11_effective_radius(desired)
            return desired

        prev_paint_radius = calc_paint_radius(prev_corner, prev_bg_mode, prev_blur)
        paint_radius = calc_paint_radius(getattr(self.settings, "corner_radius", 8), bg_mode, blur_radius)

        radius_changed = (getattr(self.settings, "corner_radius", 8) != prev_corner) or (
            paint_radius != prev_paint_radius
        )
        bg_params_changed = (bg_mode != prev_bg_mode) or (bg_path != prev_path) or (blur_radius != prev_blur)

        # Dock 高度更新
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
                except Exception as exc:
                    logger.debug("调度背景加载失败: %s", exc, exc_info=True)

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
                max_visible = self.cols * getattr(self, "fixed_rows", getattr(self.settings, "popup_max_rows", 3))
                items.extend((self.pages[self.current_page].items or [])[:max_visible])

            if self.dock_items:
                dock_rows = max(1, int(getattr(self.settings, "dock_height_mode", 1) or 1))
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
        except Exception as exc:
            logger.debug("确保窗口抛光失败: %s", exc, exc_info=True)

        try:
            # Force native window creation while the popup is still off-screen.
            self.winId()
        except Exception as exc:
            logger.debug("获取窗口ID失败: %s", exc, exc_info=True)

        try:
            self.preload_background()
        except Exception as exc:
            logger.debug("预加载背景失败: %s", exc, exc_info=True)

        try:
            self.preload_visible_icons(force=True)
        except Exception as exc:
            logger.debug("预加载可见图标失败: %s", exc, exc_info=True)

        try:
            if hasattr(self, "preload_page_animation_pixmaps"):
                self.preload_page_animation_pixmaps()
        except Exception as exc:
            logger.debug("预加载页面动画像素图失败: %s", exc, exc_info=True)

        try:
            self._update_window_effect()
        except Exception as exc:
            logger.debug("更新窗口特效失败: %s", exc, exc_info=True)

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
        except Exception as exc:
            logger.debug("请求页面动画更新失败: %s", exc, exc_info=True)

    def _schedule_selected_files_expiry_refresh(self):
        context = getattr(self, "_selected_files_context", None)
        request_id = int(getattr(context, "request_id", 0) or 0)
        started_at = float(getattr(self, "_selected_files_request_started_at", 0.0) or 0.0)
        if not request_id or started_at <= 0.0:
            return
        delay_ms = int(float(self.SELECTED_FILES_CACHE_TTL_SECONDS) * 1000) + 50
        QTimer.singleShot(delay_ms, lambda: self._expire_selected_files_if_current(request_id, started_at))

    def _expire_selected_files_if_current(self, request_id: int, started_at: float):
        context = getattr(self, "_selected_files_context", None)
        if int(getattr(context, "request_id", 0) or 0) != int(request_id or 0):
            return
        current_started_at = float(getattr(self, "_selected_files_request_started_at", 0.0) or 0.0)
        if abs(current_started_at - float(started_at or 0.0)) > 0.001:
            return
        if (time.monotonic() - current_started_at) < float(self.SELECTED_FILES_CACHE_TTL_SECONDS):
            return
        logger.info("selection_request ignore id=%s reason=expired_cache", request_id)
        self._clear_selected_files_context()
        self._refresh_selected_files_indicator()

    def _take_valid_selected_files_for_click(self) -> list:
        state = self.__dict__
        status = state.get("_selected_files_status", "idle")
        request_seq = int(state.get("_file_check_seq", 0) or 0)
        if status == "pending":
            logger.info("selection_request ignore id=%s reason=stale_request", request_seq)
            state["_file_check_seq"] = request_seq + 1
            self._clear_selected_files_context()
            return []

        selected_files = list(state.get("_selected_files") or [])
        if not selected_files:
            return []

        request_hwnd = int(state.get("_selected_files_request_hwnd", 0) or 0)
        source_hwnd = int(state.get("_selected_files_source_hwnd", 0) or 0)
        context = state.get("_selected_files_context")
        if not context or int(getattr(context, "request_id", 0) or 0) != request_seq:
            logger.info("selection_request ignore id=%s reason=stale_request", request_seq)
            self._clear_selected_files_context()
            return []

        started_at = float(state.get("_selected_files_request_started_at", 0.0) or 0.0)
        if (time.monotonic() - started_at) > self.SELECTED_FILES_CACHE_TTL_SECONDS:
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

        return selected_files

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
        ignore_reason = getattr(thread, "ignore_reason", "") or (
            "no_selected_items" if not self._selected_files else ""
        )
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
            if self.tray_app and getattr(self.tray_app, "config_window", None):
                if hasattr(self.tray_app.config_window, "_on_settings_panel_changed"):
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
