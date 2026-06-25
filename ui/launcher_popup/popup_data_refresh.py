"""Data refresh, folder sync, icon flash, settings refresh, and file selection for LauncherPopup."""

import logging
import os
import time

from core.window_detection import _is_desktop_window, _is_explorer_like_window
from qt_compat import (
    QCursor,
    QTimer,
)
from ui.launcher_popup.file_selection import FileSelectionThread, SelectionTriggerContext
from ui.launcher_popup.popup_window_helpers import FolderSyncWorker, sync_all_folders_for_data_manager
from ui.utils.qt_thread_cleanup import stop_qthread_nonblocking
from ui.utils.ui_scale import sp
from ui.utils.window_effect import is_glass_background_supported, is_win11

logger = logging.getLogger(__name__)

_BLANK_REFRESH_INITIAL_DELAY_MS = 180
_BLANK_REFRESH_INTERACTION_QUIET_MS = 260
_BLANK_REFRESH_RETRY_DELAY_MS = 90

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
            prev_shadow_size = getattr(prev_settings, "shadow_size", 0)
            prev_shadow_distance = getattr(prev_settings, "shadow_distance", 0)
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
            prev_shadow_size = 0
            prev_shadow_distance = 0

        self.cols = self.settings.cols
        self.cell_size = sp(self.settings.cell_size)
        self.icon_size = sp(self.settings.icon_size)
        self._update_grid_text_metrics()
        self._page_tab_widths = []
        self._page_tab_x = []

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
            effect_enabled = (mode == "acrylic") or (mode == "theme" and int(blur or 0) > 0)
            if is_win11() and effect_enabled:
                return self._get_win11_effective_radius(desired)  # type: ignore[attr-defined, no-any-return]
            return desired

        prev_paint_radius = calc_paint_radius(prev_corner, prev_bg_mode, prev_blur)
        paint_radius = calc_paint_radius(getattr(self.settings, "corner_radius", 8), bg_mode, blur_radius)

        radius_changed = (getattr(self.settings, "corner_radius", 8) != prev_corner) or (
            paint_radius != prev_paint_radius
        )
        bg_params_changed = (bg_mode != prev_bg_mode) or (bg_path != prev_path) or (blur_radius != prev_blur)
        shadow_changed = (
            getattr(self.settings, "shadow_size", 0) != prev_shadow_size
            or getattr(self.settings, "shadow_distance", 0) != prev_shadow_distance
        )

        glass_renderer = getattr(self, "_glass_renderer", None)
        if glass_renderer is not None:
            if bg_mode != "glass":
                glass_renderer.stop(destroy=True)
            elif not is_glass_background_supported():
                # 系统不支持 WDA_EXCLUDEFROMCAPTURE：不要碰渲染线程，让
                # _prepare_selected_background 在弹窗显示时再做静默回退。
                glass_renderer.stop(destroy=True)
            elif self.isVisible():
                try:
                    glass_renderer.prepare()
                except Exception as exc:
                    self._handle_glass_background_failure(str(exc))

        self.dock_height = self._calculate_dock_height()

        if self.icon_size != prev_icon_size:
            self._icon_pixmap_cache.clear()
            self._default_icon_cache.clear()
            self._visible_icons_preloaded = False
            self._all_page_icons_preloaded = False

        if layout_changed:
            self._calculate_fixed_size()

        if radius_changed:
            self._cached_bg_path = None

        if prev_bg_mode == "image" and bg_mode != "image":
            try:
                self._release_background_cache()
            except Exception as exc:
                logger.debug("切换背景模式时释放图片背景缓存失败: %s", exc, exc_info=True)

        if bg_mode == "acrylic" or prev_bg_mode == "acrylic" or radius_changed or shadow_changed:
            self._last_effect_state = None
            try:
                visible = bool(self.isVisible())
            except RuntimeError:
                visible = False
            except Exception as exc:
                logger.debug("检查弹窗可见状态失败: %s", exc, exc_info=True)
                visible = False
            if visible:
                try:
                    if hasattr(self, "_schedule_window_effect_update"):
                        self._schedule_window_effect_update(0)
                    else:
                        self._update_window_effect()
                except Exception as exc:
                    logger.debug("调度窗口特效刷新失败: %s", exc, exc_info=True)

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

    def preload_visible_icons(self, force: bool = False, all_pages: bool = False):
        """预热弹窗可见范围内的图标，避免显示后再逐个补绘。

        当 IconExtractor 缓存已命中（启动时 _preload_icons 已预热），
        每个图标的加载仅为缓存查找，耗时 <1ms，整体几乎无延迟。
        显示前调用传 force=True，保证首帧直接使用真实图标。
        all_pages=True 会预热每一页的可见格子，保证首次切页也完整。
        """
        if not force and not self.isVisible():  # type: ignore[attr-defined]
            return

        if all_pages and getattr(self, "_all_page_icons_preloaded", False):
            return
        if not all_pages and self._visible_icons_preloaded:
            return

        if not HAS_ICON_EXTRACTOR or not IconExtractor:
            return

        try:
            items = []
            seen = set()
            max_visible = self.cols * getattr(self, "fixed_rows", getattr(self.settings, "popup_max_rows", 8))

            if self.pages:  # type: ignore[attr-defined]
                page_indexes = range(len(self.pages)) if all_pages else (self.current_page,)  # type: ignore[attr-defined]
                for page_index in page_indexes:
                    if not 0 <= page_index < len(self.pages):  # type: ignore[attr-defined]
                        continue
                    page_items = (
                        self._get_page_animation_items(page_index)
                        if hasattr(self, "_get_page_animation_items")
                        else (self.pages[page_index].items or [])  # type: ignore[attr-defined]
                    )
                    items.extend(list(page_items)[:max_visible])

            if self.dock_items:  # type: ignore[attr-defined]
                dock_rows = max(1, int(getattr(self.settings, "dock_height_mode", 1) or 1))
                max_dock_items = self.cols * dock_rows
                items.extend((self.dock_items or [])[:max_dock_items])  # type: ignore[attr-defined]

            unique_items = []
            for item in items:
                item_key = getattr(item, "id", None) or id(item)
                if item_key in seen:
                    continue
                seen.add(item_key)
                unique_items.append(item)

            reserve_cache = getattr(self, "_reserve_icon_pixmap_cache", None)
            if callable(reserve_cache):
                reserve_cache(len(unique_items))

            previous_batch_state = bool(self.__dict__.get("_batch_icon_preload_active", False))
            self._batch_icon_preload_active = True
            self._icon_cache_batch_changed = False
            batch_changed = False
            try:
                for item in unique_items:
                    try:
                        self._get_icon(item)  # type: ignore[attr-defined]
                    except Exception:
                        continue
                batch_changed = bool(self.__dict__.get("_icon_cache_batch_changed", False))
            finally:
                self._batch_icon_preload_active = previous_batch_state
                self._icon_cache_batch_changed = False
            if batch_changed and not previous_batch_state:
                self._mark_icon_cache_changed()  # type: ignore[attr-defined]
            self._visible_icons_preloaded = True
            if all_pages:
                self._all_page_icons_preloaded = True
        except Exception as e:
            logger.debug(f"preload visible icons failed: {e}")

    def prepare_first_show(self, create_native_window: bool = True):
        """Warm up only cheap Qt state before the popup is shown to the user."""
        if self._first_show_ready:  # type: ignore[has-type]
            return

        try:
            self.ensurePolished()  # type: ignore[attr-defined]
        except Exception as exc:
            logger.debug("确保窗口抛光失败: %s", exc, exc_info=True)

        try:
            # Force native window creation while the popup is still off-screen.
            self.winId()  # type: ignore[attr-defined]
        except Exception as exc:
            logger.debug("获取窗口ID失败: %s", exc, exc_info=True)

        try:
            self._schedule_bg_load()  # type: ignore[attr-defined]
        except Exception as exc:
            logger.debug("调度背景预加载失败: %s", exc, exc_info=True)

        try:
            if hasattr(self, "_schedule_window_effect_update"):
                self._schedule_window_effect_update(0)
            else:
                QTimer.singleShot(0, self._update_window_effect)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.debug("调度窗口特效预热失败: %s", exc, exc_info=True)

        self._first_show_ready = True

    def _start_file_check(self, hwnd=None, trigger_method: str = "mouse"):
        """启动文件检测线程"""
        self._file_check_seq += 1  # type: ignore[attr-defined]
        request_started_at = time.monotonic()
        context = SelectionTriggerContext.capture(
            request_id=self._file_check_seq,  # type: ignore[attr-defined]
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
            self._selected_files = []  # type: ignore[var-annotated]
            self._selected_files_source_hwnd = 0
            self._selected_files_captured_at = time.monotonic()
            self._selected_files_status = "empty"
            self._refresh_selected_files_indicator()
            return

        current_thread = self.__dict__.get("_file_thread")
        if self._qthread_is_running(current_thread):
            self._pending_file_check_context = context
            logger.debug("文件选择检测线程仍在运行，已排队最新请求: id=%s", context.request_id)
            return

        self._start_file_selection_thread(context)

    def _qthread_is_running(self, thread) -> bool:
        try:
            return bool(thread is not None and thread.isRunning())
        except RuntimeError:
            return False
        except (AttributeError, TypeError):
            return False

    def _start_file_selection_thread(self, context: SelectionTriggerContext):
        if bool(getattr(self, "_closing", False)):
            return

        thread = FileSelectionThread(
            context,
        )
        thread.files_found.connect(self._on_files_found)
        # 先清空 self 上的引用，再 schedule deleteLater。
        # 不要把 QThread 自身的 deleteLater 挂到自己的 finished 信号上 —
        # 跟 icon_grid 同源问题，详见 test_icon_grid_file_shortcut_delete.py。
        thread.finished.connect(lambda current=thread: self._on_file_check_thread_finished(current))
        thread.start()
        # 保存引用防止被 GC
        self._file_thread = thread

    def _on_file_check_thread_finished(self, thread):
        if getattr(self, "_file_thread", None) is thread:
            self._file_thread = None

        context = getattr(self, "_pending_file_check_context", None)
        if context is None:
            return
        self._pending_file_check_context = None
        if bool(getattr(self, "_closing", False)):
            return
        if int(getattr(context, "request_id", 0) or 0) != int(getattr(self, "_file_check_seq", 0) or 0):
            return
        self._start_file_selection_thread(context)

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
        if (time.monotonic() - current_started_at) < float(self.SELECTED_FILES_CACHE_TTL_SECONDS):  # type: ignore[attr-defined]
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
        if (time.monotonic() - started_at) > self.SELECTED_FILES_CACHE_TTL_SECONDS:  # type: ignore[attr-defined]
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
        try:
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
        except (RuntimeError, AttributeError, TypeError) as exc:
            logger.debug("文件检测回调命中已销毁 widget: %s", exc, exc_info=True)
            return

    def _sync_all_folders(self):
        """同步所有文件夹 - 等同于配置窗口的手动同步功能"""
        sync_all_folders_for_data_manager(self.data_manager)

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
        self._schedule_folder_sync_refresh()

    def _reset_blank_area_refresh_state(self):
        self._blank_refresh_pending = False
        self._blank_refresh_worker_started = False
        self._blank_refresh_in_progress = False

    def _defer_blank_area_refresh_for_interaction(self, quiet_ms: int = _BLANK_REFRESH_INTERACTION_QUIET_MS):
        """Keep a double-click refresh queued while page scrolling/dragging stays active."""
        state = self.__dict__
        if not (
            bool(state.get("_blank_refresh_in_progress", False)) or bool(state.get("_blank_refresh_pending", False))
        ):
            return
        try:
            quiet_until = time.monotonic() + max(0, int(quiet_ms)) / 1000.0
            self._blank_refresh_not_before = max(
                float(state.get("_blank_refresh_not_before", 0.0) or 0.0),
                quiet_until,
            )
        except Exception as exc:
            logger.debug("延后空白区刷新失败: %s", exc, exc_info=True)

    def _blank_refresh_should_wait_for_ui(self) -> bool:
        """Return True while user-facing animation/input should stay first in line."""
        state = self.__dict__
        try:
            if time.monotonic() < float(state.get("_blank_refresh_not_before", 0.0) or 0.0):
                return True
        except Exception as exc:
            logger.debug("检查空白区刷新静默期失败: %s", exc, exc_info=True)

        timer = state.get("_indicator_timer")
        try:
            if timer is not None and timer.isActive():
                return True
        except Exception as exc:
            logger.debug("检查翻页动画状态失败: %s", exc, exc_info=True)

        return bool(
            state.get("_is_dragging", False)
            or state.get("_search_drag_selecting", False)
            or state.get("_pinned_window_drag_active", False)
        )

    def _blank_refresh_retry_delay_ms(self) -> int:
        state = self.__dict__
        try:
            wait_ms = int(max(0.0, float(state.get("_blank_refresh_not_before", 0.0) or 0.0) - time.monotonic()) * 1000)
        except Exception:
            wait_ms = 0
        return max(_BLANK_REFRESH_RETRY_DELAY_MS, min(360, wait_ms + 16))

    def _schedule_blank_area_refresh_worker(self, delay_ms: int | None = None):
        state = self.__dict__
        seq = int(state.get("_blank_refresh_generation", 0) or 0) + 1
        self._blank_refresh_generation = seq
        delay = _BLANK_REFRESH_INITIAL_DELAY_MS if delay_ms is None else max(0, int(delay_ms))
        QTimer.singleShot(delay, lambda seq=seq: self._maybe_start_folder_sync_worker(seq))

    def _maybe_start_folder_sync_worker(self, seq: int):
        state = self.__dict__
        if seq != int(state.get("_blank_refresh_generation", -1) or -1):
            return
        if not bool(state.get("_blank_refresh_pending", False)):
            return
        if bool(state.get("_closing", False)):
            self._reset_blank_area_refresh_state()
            return

        if state.get("_sync_worker") is not None or self._blank_refresh_should_wait_for_ui():
            self._schedule_blank_area_refresh_worker(self._blank_refresh_retry_delay_ms())
            return

        self._blank_refresh_pending = False
        self._blank_refresh_worker_started = True
        self._start_folder_sync_worker()

    def _is_cursor_inside_popup(self) -> bool:
        try:
            return bool(self.rect().contains(self.mapFromGlobal(QCursor.pos())))  # type: ignore[attr-defined]
        except Exception as exc:
            logger.debug("检查鼠标是否在弹窗内失败: %s", exc, exc_info=True)
            return True

    def _folder_sync_refresh_delay_ms(self) -> int:
        """Delay the GUI refresh just enough to keep hover/auto-hide responsive."""
        idle_delay = 16
        try:
            if not self.isVisible():  # type: ignore[attr-defined]
                return idle_delay
        except RuntimeError:
            return idle_delay
        except Exception as exc:
            logger.debug("检查弹窗可见状态失败: %s", exc, exc_info=True)
            return idle_delay

        if (
            self.__dict__.get("is_pinned", False)
            or self.__dict__.get("_executing", False)
            or self.__dict__.get("_is_dragging", False)
        ):
            return idle_delay

        settings = self.__dict__.get("settings", None)
        if not bool(getattr(settings, "popup_auto_close", True)):
            return idle_delay
        if self._is_cursor_inside_popup():
            return idle_delay

        delay = max(0, int(getattr(settings, "hover_leave_delay", 200) or 0))
        hide_timer = self.__dict__.get("_hide_timer")
        if hide_timer is not None:
            try:
                if not hide_timer.isActive():
                    hide_timer.start(delay)
            except Exception as exc:
                logger.debug("启动刷新前隐藏定时器失败: %s", exc, exc_info=True)
        return delay + 140

    def _schedule_folder_sync_refresh(self):
        seq = int(getattr(self, "_folder_sync_refresh_seq", 0) or 0) + 1
        self._folder_sync_refresh_seq = seq
        delay = self._folder_sync_refresh_delay_ms()
        logger.debug("同步线程结束，延迟 %s ms 执行弹窗刷新", delay)
        QTimer.singleShot(delay, lambda seq=seq: self._finish_folder_sync_refresh(seq))

    def _finish_folder_sync_refresh(self, seq: int):
        if seq != int(getattr(self, "_folder_sync_refresh_seq", -1) or -1):
            return

        try:
            if bool(getattr(self, "_closing", False)):
                self._blank_refresh_in_progress = False
                return

            try:
                visible = bool(self.isVisible())  # type: ignore[attr-defined]
            except RuntimeError:
                visible = False
            if not visible:
                logger.info("同步完成，弹窗已隐藏，跳过即时重绘，下次唤出时刷新")
                self._blank_refresh_in_progress = False
                return

            if bool(getattr(self, "_is_hiding", False)):
                QTimer.singleShot(140, lambda seq=seq: self._finish_folder_sync_refresh(seq))
                return

            if self._blank_refresh_should_wait_for_ui():
                QTimer.singleShot(
                    self._blank_refresh_retry_delay_ms(),
                    lambda seq=seq: self._finish_folder_sync_refresh(seq),
                )
                return

            self._refresh_after_folder_sync(sync_first=False)
        except Exception as e:
            logger.error(f"同步刷新收尾失败: {e}")
            self._reset_blank_area_refresh_state()

    def _refresh_after_folder_sync(self, sync_first: bool = True):
        """Refresh after folder sync while preserving transient search state."""
        try:
            if sync_first:
                self._sync_all_folders()
            self.refresh_data(  # type: ignore[attr-defined]
                refresh_selection=False,
                force=True,
                reposition=False,
                preserve_search_state=True,
                skip_effect=True,
            )
            if self.tray_app and getattr(self.tray_app, "config_window", None):  # type: ignore[attr-defined]
                if hasattr(self.tray_app.config_window, "_on_settings_panel_changed"):  # type: ignore[attr-defined]
                    self.tray_app.config_window._on_settings_panel_changed()  # type: ignore[attr-defined]
            logger.info(f"同步并刷新完成，页面数: {len(self.pages)}, Dock项: {len(self.dock_items)}")  # type: ignore[attr-defined]
        except Exception as e:
            logger.error(f"同步刷新处理失败: {e}")
        finally:
            self._reset_blank_area_refresh_state()

    def _run_blank_area_refresh(self):
        """在双击事件结束后执行空白区刷新，避免重入和窗口抖动"""
        if self._blank_refresh_in_progress:
            self._defer_blank_area_refresh_for_interaction()
            return

        self._blank_refresh_in_progress = True
        try:
            logger.info("左键双击空白区域，异步启动文件夹同步")
            # 立即提供无延迟的视觉反馈
            self._flash_icons()

            self._blank_refresh_pending = True
            self._blank_refresh_worker_started = False
            now = time.monotonic()
            self._blank_refresh_requested_at = now
            self._blank_refresh_not_before = now + (_BLANK_REFRESH_INITIAL_DELAY_MS / 1000.0)
            self._schedule_blank_area_refresh_worker(_BLANK_REFRESH_INITIAL_DELAY_MS)
        except Exception as e:
            logger.error(f"启动同步线程失败: {e}")
            self._reset_blank_area_refresh_state()

    def _start_folder_sync_worker(self):
        """延迟启动文件夹同步，避免与闪烁动画竞争 UI 线程。"""
        try:
            if bool(getattr(self, "_closing", False)):
                self._reset_blank_area_refresh_state()
                return
            if self._qthread_is_running(getattr(self, "_sync_worker", None)):
                self._blank_refresh_pending = True
                return

            self._sync_worker = FolderSyncWorker(self.data_manager)
            self._sync_worker.finished.connect(self.folder_sync_finished.emit)
            # 不要把 QThread 自身的 deleteLater 挂到自己的 finished 信号上 —
            # 跟 icon_grid 同源问题，详见 test_icon_grid_file_shortcut_delete.py。
            # 线程本身由 stop_qthread_nonblocking / 进程退出统一回收。
            self._sync_worker.finished.connect(
                lambda worker=self._sync_worker: (
                    setattr(self, "_sync_worker", None) if getattr(self, "_sync_worker", None) is worker else None
                )
            )
            self._sync_worker.start()
        except Exception as e:
            logger.error(f"启动同步线程失败: {e}")
            self._reset_blank_area_refresh_state()

    def stop_background_threads(self):
        self._pending_file_check_context = None
        for attr in ("_file_thread", "_sync_worker"):
            thread = getattr(self, attr, None)
            if thread is None:
                continue
            stopped = stop_qthread_nonblocking(
                thread,
                owner=f"LauncherPopup.{attr}",
                wait_ms=0,
                disconnect_thread_signals=("finished", "files_found"),
            )
            if stopped:
                setattr(self, attr, None)

    # ===== 拖放事件处理结束 =====
