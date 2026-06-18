"""Mouse, keyboard, wheel events, page switching, and auto-close for LauncherPopup."""

import logging
import time
from typing import Any, cast

from qt_compat import (
    QApplication,
    QCursor,
    QFont,
    QFontMetrics,
    QPoint,
    QRect,
    Qt,
    QtCompat,
    QTimer,
)
from ui.utils.ui_scale import sp

logger = logging.getLogger(__name__)

_WHEEL_PAGE_THRESHOLD = 1.0
_WHEEL_BURST_RESET_SECONDS = 0.28
_WHEEL_PAGE_MIN_INTERVAL_SECONDS = 0.105
_WHEEL_MAX_EVENT_STEPS = 1.0
_PIXEL_DELTA_PER_PAGE = 120.0
_LAST_PAGE_INDEX_SAVE_DELAY_MS = 450


class PopupEventsMixin:
    """Mouse, keyboard, wheel events, page switching, and auto-close."""

    def _get_event_pos(self, event):
        """获取事件位置"""
        if hasattr(event, "position"):
            # Newer Qt event API
            return event.position().toPoint()
        else:
            # PyQt5
            return event.pos()

    def _get_event_global_pos(self, event):
        """获取事件全局位置"""
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        if hasattr(event, "globalPos"):
            return event.globalPos()
        return self.mapToGlobal(self._get_event_pos(event))

    def _reset_pinned_window_drag(self, *, restore_cursor: bool = False) -> None:
        """清理固定窗口拖动状态。"""
        self._pinned_window_drag_pending = False
        self._pinned_window_drag_active = False
        self._pinned_window_drag_start_global = None
        self._pinned_window_drag_window_pos = None
        self._pinned_window_drag_offset = None
        if restore_cursor:
            try:
                self.setCursor(QtCompat.ArrowCursor)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.debug("恢复固定窗口拖动光标失败: %s", exc, exc_info=True)

    def _begin_pinned_window_drag(self, event, pos: QPoint) -> bool:
        """在固定状态下准备通过左键拖动窗口。"""
        if event.button() != QtCompat.LeftButton:
            return False
        if not self.__dict__.get("is_pinned", False) or self.__dict__.get("_executing", False):
            return False
        if self._search_bar_contains(pos) or self._is_click_on_result_panel(pos):  # type: ignore[attr-defined]
            return False

        global_pos = self._get_event_global_pos(event)
        try:
            window_pos = self.pos()  # type: ignore[attr-defined]
        except Exception as exc:
            logger.debug("获取固定窗口位置失败: %s", exc, exc_info=True)
            window_pos = QPoint(0, 0)

        self._pinned_window_drag_pending = True
        self._pinned_window_drag_active = False
        self._pinned_window_drag_start_global = global_pos
        self._pinned_window_drag_window_pos = window_pos
        self._pinned_window_drag_offset = global_pos - window_pos
        return True

    def _event_left_button_held(self, event) -> bool:
        if not hasattr(event, "buttons"):
            return True
        try:
            return bool(event.buttons() & QtCompat.LeftButton)
        except Exception as exc:
            logger.debug("检查鼠标左键状态失败: %s", exc, exc_info=True)
            return True

    def _update_pinned_window_drag(self, event) -> bool:
        """如果正在拖动固定窗口，则移动窗口并消费事件。"""
        if not (
            self.__dict__.get("_pinned_window_drag_pending", False)
            or self.__dict__.get("_pinned_window_drag_active", False)
        ):
            return False

        if not self._event_left_button_held(event):
            self._reset_pinned_window_drag(restore_cursor=True)
            return False

        global_pos = self._get_event_global_pos(event)
        start_global = self.__dict__.get("_pinned_window_drag_start_global", None)
        if start_global is None:
            self._reset_pinned_window_drag(restore_cursor=True)
            return False

        if not self.__dict__.get("_pinned_window_drag_active", False):
            try:
                drag_distance = QApplication.startDragDistance()
            except Exception as exc:
                logger.debug("获取拖动阈值失败: %s", exc, exc_info=True)
                drag_distance = 4
            if (global_pos - start_global).manhattanLength() < drag_distance:
                return False

            self._pinned_window_drag_active = True
            self.hover_index = -1
            self.dock_hover_index = -1
            try:
                self.setCursor(Qt.SizeAllCursor)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.debug("设置固定窗口拖动光标失败: %s", exc, exc_info=True)

        offset = self.__dict__.get("_pinned_window_drag_offset", None)
        if offset is None:
            self._reset_pinned_window_drag(restore_cursor=True)
            return False

        try:
            self.move(global_pos - offset)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.debug("移动固定窗口失败: %s", exc, exc_info=True)
            return False

        event.accept()
        return True

    def _get_clicked_item_at(self, pos: QPoint):
        """返回指定位置命中的项目，没有命中则返回 None"""
        if self._search_bar_contains(pos):  # type: ignore[attr-defined]
            return None

        if pos.y() >= self.dock_y and self.dock_items:  # type: ignore[attr-defined]
            dock_height_mode = getattr(self.settings, "dock_height_mode", 1)
            visible_count = len(self.dock_items)  # type: ignore[attr-defined]
            if dock_height_mode == 1:
                visible_count = min(visible_count, self.cols)  # type: ignore[attr-defined]
            max_cols = self.cols  # type: ignore[attr-defined]
            line_width = (
                max_cols * self.cell_size  # type: ignore[attr-defined]
                if (dock_height_mode > 1 and visible_count > max_cols)
                else min(visible_count, max_cols) * self.cell_size  # type: ignore[attr-defined]
            )
            start_x = (self.width() - line_width) // 2  # type: ignore[attr-defined]
            display_rows = self._dock_display_rows(visible_count, max_cols)  # type: ignore[attr-defined]
            dock_row_stride = self._get_dock_row_stride(display_rows)  # type: ignore[attr-defined]

            if start_x <= pos.x() < start_x + line_width:
                dock_col = (pos.x() - start_x) // self.cell_size  # type: ignore[attr-defined]
                first_icon_y = self._dock_first_icon_y(display_rows)  # type: ignore[attr-defined]
                card_pad = sp(2)
                card_y = first_icon_y - card_pad
                dock_row = (pos.y() - card_y) // dock_row_stride
                if 0 <= dock_col < max_cols and 0 <= dock_row < dock_height_mode:
                    idx = dock_row * max_cols + dock_col
                    if 0 <= idx < visible_count:
                        return self.dock_items[idx]  # type: ignore[attr-defined]

        if self.padding <= pos.x() and self.padding <= pos.y() < self.content_height:  # type: ignore[attr-defined]
            # 从窗口底部算起，与图标绘制逻辑一致
            bottom_margin = self._dock_outer_bottom_gap()  # type: ignore[attr-defined]
            indicator_height = sp(16) if len(self.pages) > 1 else 0  # type: ignore[attr-defined]
            indicator_spacing = sp(4) if len(self.pages) > 1 else 0  # type: ignore[attr-defined]
            dock_height = self.dock_height if (self.dock_items and self.dock_height > 0) else 0  # type: ignore[attr-defined]
            shadow_margin = int(self.__dict__.get("shadow_margin", 0) or 0)
            icons_bottom = (
                self.height() - shadow_margin - bottom_margin - dock_height - indicator_height - indicator_spacing  # type: ignore[attr-defined]
            )

            if pos.y() <= icons_bottom:
                col = (pos.x() - self.padding) // self.cell_size  # type: ignore[attr-defined]
                row_from_bottom = (icons_bottom - pos.y()) // self.cell_h  # type: ignore[attr-defined]
                row = self.fixed_rows - 1 - row_from_bottom  # type: ignore[attr-defined]

                if 0 <= col < self.cols and row < self.fixed_rows:  # type: ignore[attr-defined]
                    index = row * self.cols + col  # type: ignore[attr-defined]
                    if getattr(self, "search_query", ""):
                        if 0 <= index < len(self.search_results):  # type: ignore[attr-defined]
                            return self.search_results[index].shortcut  # type: ignore[attr-defined]
                    elif self.pages and self.current_page < len(self.pages):  # type: ignore[attr-defined, has-type]
                        items = self.pages[self.current_page].items  # type: ignore[attr-defined, has-type]
                        if 0 <= index < len(items):
                            return items[index]

        return None

    def _main_item_update_rect(self, index: int):
        """Return a conservative repaint rect for a main/search grid item."""
        try:
            index = int(index)
            if index < 0:
                return None
            cols = max(1, int(self.cols))  # type: ignore[attr-defined]
            row = index // cols
            if row >= int(self.fixed_rows):  # type: ignore[attr-defined]
                return None
            col = index % cols
            bottom_margin = sp(6)
            indicator_height = sp(16) if len(self.pages) > 1 else 0  # type: ignore[attr-defined]
            indicator_spacing = sp(4) if len(self.pages) > 1 else 0  # type: ignore[attr-defined]
            dock_height = self.dock_height if (self.dock_items and self.dock_height > 0) else 0  # type: ignore[attr-defined]
            shadow_margin = int(self.__dict__.get("shadow_margin", 0) or 0)
            icons_bottom = (
                self.height() - shadow_margin - bottom_margin - dock_height - indicator_height - indicator_spacing  # type: ignore[attr-defined]
            )
            x = int(self.padding + col * self.cell_size)  # type: ignore[attr-defined]
            y = int(icons_bottom - (self.fixed_rows - row) * self.cell_h)  # type: ignore[attr-defined]
            pad = sp(3)
            return QRect(x - pad, y - pad, int(self.cell_size) + pad * 2, int(self.cell_h) + pad * 2).intersected(  # type: ignore[attr-defined]
                self.rect()  # type: ignore[attr-defined]
            )
        except Exception as exc:
            logger.debug("计算主网格刷新区域失败: %s", exc, exc_info=True)
            return None

    def _dock_item_update_rect(self, index: int):
        """Return a conservative repaint rect for a dock item."""
        try:
            index = int(index)
            if index < 0 or not self.dock_items:  # type: ignore[attr-defined]
                return None
            dock_height_mode = getattr(self.settings, "dock_height_mode", 1)
            visible_count = len(self.dock_items)  # type: ignore[attr-defined]
            if dock_height_mode == 1:
                visible_count = min(visible_count, self.cols)  # type: ignore[attr-defined]
            if index >= visible_count:
                return None
            max_cols = max(1, int(self.cols))  # type: ignore[attr-defined]
            line_width = (
                max_cols * self.cell_size  # type: ignore[attr-defined]
                if (dock_height_mode > 1 and visible_count > max_cols)
                else min(visible_count, max_cols) * self.cell_size  # type: ignore[attr-defined]
            )
            start_x = (self.width() - line_width) // 2  # type: ignore[attr-defined]
            row = index // max_cols
            col = index % max_cols
            if row >= dock_height_mode:
                return None
            x = int(start_x + col * self.cell_size)  # type: ignore[attr-defined]
            display_rows = self._dock_display_rows(visible_count, max_cols)  # type: ignore[attr-defined]
            dock_row_stride = self._get_dock_row_stride(display_rows)  # type: ignore[attr-defined]
            icon_y = int(self._dock_first_icon_y(display_rows) + row * dock_row_stride)  # type: ignore[attr-defined]
            card_pad = sp(2)
            card_size = int(self.icon_size + card_pad * 2)  # type: ignore[attr-defined]
            card_x = int(x + (self.cell_size - card_size) // 2)  # type: ignore[attr-defined]
            card_y = int(icon_y - card_pad)

            if self._dock_shows_text(display_rows):  # type: ignore[attr-defined]
                if hasattr(self, "_label_font") and self._label_font:
                    fm = QFontMetrics(self._label_font)
                else:
                    fm = QFontMetrics(QFont())
                text_h = fm.height()
                text_spacing = sp(1)
                item_h = card_size + text_spacing + text_h
            else:
                item_h = card_size

            repaint_pad = sp(4)
            host = cast(Any, self)
            return QRect(
                card_x - repaint_pad,
                card_y - repaint_pad,
                card_size + repaint_pad * 2,
                item_h + repaint_pad * 2,
            ).intersected(host.rect())
        except Exception as exc:
            logger.debug("计算Dock刷新区域失败: %s", exc, exc_info=True)
            return None

    def _update_hover_regions(self, old_hover: int, old_dock_hover: int, new_hover: int, new_dock_hover: int):
        """Repaint only hover regions that changed; fall back to a full update on unusual geometry."""
        rects = []  # type: ignore[var-annotated]
        if old_hover != new_hover:
            rects.extend((self._main_item_update_rect(old_hover), self._main_item_update_rect(new_hover)))
        if old_dock_hover != new_dock_hover:
            rects.extend((self._dock_item_update_rect(old_dock_hover), self._dock_item_update_rect(new_dock_hover)))

        applied = False
        for rect in rects:
            if rect is not None and not rect.isNull():
                self.update(rect)  # type: ignore[attr-defined]
                applied = True
        if not applied:
            self.update()  # type: ignore[attr-defined]

    def _is_click_on_result_panel(self, pos) -> bool:
        """判断鼠标位置是否在命令结果展示面板内"""
        if self.__dict__.get("_command_result") is None:
            return False
        # 获取结果面板区域的顶部和底部
        shadow_margin = int(self.__dict__.get("shadow_margin", 0) or 0)
        y_top = (self._body_y_offset() if hasattr(self, "_body_y_offset") else sp(38)) + shadow_margin
        y_bottom = self.__dict__.get("dock_y")
        if y_bottom is None:
            y_bottom = self.height() - shadow_margin - sp(6)  # type: ignore[attr-defined]
        return y_top <= pos.y() < y_bottom  # type: ignore[no-any-return]

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
        except Exception as exc:
            logger.debug("检查结果文本框焦点失败: %s", exc, exc_info=True)

        try:
            if self._search_selection_bounds():  # type: ignore[attr-defined]
                return True
        except Exception as exc:
            logger.debug("检查搜索选择边界失败: %s", exc, exc_info=True)

        return self._search_query_matches_result_command()

    def mouseMoveEvent(self, event):
        """鼠标移动"""
        pos = self._get_event_pos(event)
        if self._update_pinned_window_drag(event):
            return

        if getattr(self, "_search_drag_selecting", False):
            cursor = self._search_pos_from_point(pos)
            self.search_cursor_pos = cursor
            self.search_selection_anchor = getattr(self, "_search_drag_anchor", cursor)
            self._restart_search_cursor_blink()
            self.update()
            event.accept()
            return

        try:
            if self._search_bar_contains(pos):
                cursor = Qt.IBeamCursor
            elif hasattr(self, "_page_header_contains") and self._page_header_contains(pos):
                cursor = QtCompat.PointingHandCursor
            else:
                cursor = QtCompat.ArrowCursor
            self.setCursor(cursor)
        except Exception as exc:
            logger.debug("设置光标样式失败: %s", exc, exc_info=True)

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
            dock_height_mode = getattr(self.settings, "dock_height_mode", 1)
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
            display_rows = self._dock_display_rows(visible_count, max_cols)
            dock_row_stride = self._get_dock_row_stride(display_rows)

            if start_x <= pos.x() < start_x + line_width:
                dock_col = (pos.x() - start_x) // self.cell_size
                first_icon_y = self._dock_first_icon_y(display_rows)
                card_pad = sp(2)
                card_y = first_icon_y - card_pad
                dock_row = (pos.y() - card_y) // dock_row_stride
                if 0 <= dock_col < max_cols and 0 <= dock_row < dock_height_mode:
                    idx = dock_row * max_cols + dock_col
                    if 0 <= idx < visible_count:
                        new_dock_hover = idx

        elif self.padding <= pos.x() and self.padding <= pos.y() < self.content_height:
            if hasattr(self, "clear_result_button_feedback"):
                self.clear_result_button_feedback()
            # 从窗口底部算起，与图标绘制逻辑一致
            bottom_margin = self._dock_outer_bottom_gap()
            indicator_height = sp(16) if len(self.pages) > 1 else 0
            indicator_spacing = sp(4) if len(self.pages) > 1 else 0
            dock_height = self.dock_height if (self.dock_items and self.dock_height > 0) else 0
            shadow_margin = int(self.__dict__.get("shadow_margin", 0) or 0)
            icons_bottom = (
                self.height() - shadow_margin - bottom_margin - dock_height - indicator_height - indicator_spacing
            )

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
            old_hover = self.hover_index
            old_dock_hover = self.dock_hover_index
            self.hover_index = new_hover
            self.dock_hover_index = new_dock_hover
            self._update_hover_regions(old_hover, old_dock_hover, new_hover, new_dock_hover)

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
            if self.__dict__.get("_command_result") is not None and not self._search_query_matches_result_command():
                self.clear_command_result()
            self._text_shortcut_target = "search"
            self._search_forced_active = True
            self._start_search_reveal_animation(True)
            try:
                self.setFocus()
            except Exception as exc:
                logger.debug("设置焦点失败: %s", exc, exc_info=True)
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
        if event.button() == QtCompat.LeftButton and hasattr(self, "_page_index_at_header"):
            page_index = self._page_index_at_header(pos)
            if page_index >= 0:
                self._switch_to_page(page_index)
                event.accept()
                return
        if self._begin_pinned_window_drag(event, pos):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        pos = self._get_event_pos(event)

        # ===== 固定窗口拖动释放 =====
        if event.button() == QtCompat.LeftButton:
            if self.__dict__.get("_pinned_window_drag_active", False):
                self._reset_pinned_window_drag(restore_cursor=True)
                event.accept()
                return
            if self.__dict__.get("_pinned_window_drag_pending", False):
                self._reset_pinned_window_drag()

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
                # Record search selection for learning
                if getattr(self, "search_results", None):
                    try:
                        from core.search_history import record_search_selection

                        record_search_selection(self.search_query, getattr(clicked_item, "id", ""))
                    except Exception as exc:
                        logger.debug("记录搜索选择失败: %s", exc, exc_info=True)

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

        QTimer.singleShot(16, self._run_blank_area_refresh)
        event.accept()

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

            if hasattr(self, "_defer_blank_area_refresh_for_interaction"):
                self._defer_blank_area_refresh_for_interaction()

            if len(self.pages) <= 1:
                event.accept()
                return

            direction = self._consume_wheel_page_direction(event)
            if direction:
                self._queue_page_switch(direction)

            self.hover_index = -1
            if hasattr(self, "_request_page_animation_update"):
                self._request_page_animation_update()
            else:
                self.update()
            event.accept()
            return

        elif modifiers == QtCompat.ControlModifier:
            change = 5 if delta > 0 else -5
            new_alpha = max(0, min(100, self.settings.bg_alpha + change))
            if new_alpha != self.settings.bg_alpha:
                self.data_manager.update_settings(bg_alpha=new_alpha, immediate=False)
                self.settings = self.data_manager.get_settings()
                self.update()
            event.accept()
            return

        elif modifiers == QtCompat.ShiftModifier:
            change = 0.1 if delta > 0 else -0.1
            new_alpha = max(0.2, min(1.0, self.settings.icon_alpha + change))
            if abs(new_alpha - self.settings.icon_alpha) > 1e-9:
                self.data_manager.update_settings(icon_alpha=new_alpha, immediate=False)
                self.settings = self.data_manager.get_settings()
                self.update()
            event.accept()
            return

        super().wheelEvent(event)

    def _normalized_page_wheel_delta(self, event) -> float:
        """Return wheel movement in page-switch units, independent of system line settings."""
        pixel_delta = 0
        if hasattr(event, "pixelDelta"):
            try:
                point = event.pixelDelta()
                if point is not None and not point.isNull():
                    pixel_delta = point.y()
            except Exception as exc:
                logger.debug("读取滚轮 pixelDelta 失败: %s", exc, exc_info=True)
        if pixel_delta:
            value = float(pixel_delta) / _PIXEL_DELTA_PER_PAGE
        else:
            angle_delta = 0
            try:
                angle_delta = event.angleDelta().y()
            except Exception as exc:
                logger.debug("读取滚轮 angleDelta 失败: %s", exc, exc_info=True)
            value = float(angle_delta) / 120.0
        if value > 0:
            return min(_WHEEL_MAX_EVENT_STEPS, value)
        if value < 0:
            return max(-_WHEEL_MAX_EVENT_STEPS, value)
        return 0.0

    def _consume_wheel_page_direction(self, event, now: float | None = None) -> int:
        """Accumulate wheel input and return one controlled page step when ready."""
        value = self._normalized_page_wheel_delta(event)
        if abs(value) < 0.001:
            return 0

        now = time.monotonic() if now is None else float(now)
        direction = -1 if value > 0 else 1
        last_time = float(getattr(self, "_last_wheel_time", 0.0) or 0.0)
        last_direction = int(getattr(self, "_last_wheel_direction", 0) or 0)

        if not last_time or now - last_time > _WHEEL_BURST_RESET_SECONDS or last_direction != direction:
            self._wheel_accumulator = 0.0

        self._last_wheel_time = now
        self._last_wheel_direction = direction
        self._wheel_accumulator = max(
            -_WHEEL_PAGE_THRESHOLD,
            min(_WHEEL_PAGE_THRESHOLD, float(getattr(self, "_wheel_accumulator", 0.0) or 0.0) + value),
        )

        if abs(self._wheel_accumulator) < _WHEEL_PAGE_THRESHOLD:
            return 0

        last_commit = float(getattr(self, "_last_wheel_page_time", 0.0) or 0.0)
        if last_commit and now - last_commit < _WHEEL_PAGE_MIN_INTERVAL_SECONDS:
            return 0

        self._last_wheel_page_time = now
        self._wheel_accumulator = 0.0
        return direction

    def _page_animation_target_base(self) -> float:
        target = float(getattr(self, "_target_page", getattr(self, "_page_position", self.current_page)))  # type: ignore[arg-type, has-type]
        position = float(getattr(self, "_page_position", target))
        if not getattr(self, "_indicator_timer", None) or not self._indicator_timer.isActive():  # type: ignore[attr-defined]
            return round(position)
        return target

    def _schedule_last_page_index_save(self, delay_ms: int = _LAST_PAGE_INDEX_SAVE_DELAY_MS):
        self._pending_last_page_index = int(getattr(self, "current_page", 0) or 0)
        timer = self.__dict__.get("_last_page_save_timer")
        if timer is None:
            try:
                timer = QTimer(self)  # type: ignore[unused-ignore, arg-type]
            except RuntimeError:
                return
            timer.setSingleShot(True)
            timer.timeout.connect(self._persist_last_page_index)
            self._last_page_save_timer = timer
        timer.start(max(0, int(delay_ms)))

    def _persist_last_page_index(self):
        state = self.__dict__
        pending = state.get("_pending_last_page_index")
        if pending is None:
            return
        if state.get("_sync_worker") is not None or bool(state.get("_blank_refresh_pending", False)):
            self._schedule_last_page_index_save()
            return

        page_index = int(pending)
        self._pending_last_page_index = None
        try:
            self.data_manager.update_settings(last_page_index=page_index, immediate=False)
        except TypeError:
            self.data_manager.update_settings(last_page_index=page_index)
        except Exception as exc:
            logger.debug("延迟保存弹窗页码失败: %s", exc, exc_info=True)

    def _queue_page_switch(self, direction: int):
        if len(self.pages) <= 1 or direction == 0:  # type: ignore[attr-defined]
            return

        old_page = self.current_page  # type: ignore[has-type]
        self.current_page = (self.current_page + direction) % len(self.pages)  # type: ignore[attr-defined, has-type]
        if self.current_page != old_page:
            if hasattr(self, "_defer_blank_area_refresh_for_interaction"):
                self._defer_blank_area_refresh_for_interaction()
            self._target_page = self._page_animation_target_base() + direction
            self._schedule_last_page_index_save()
            if not self._indicator_timer.isActive():  # type: ignore[attr-defined]
                self._page_anim_last_ts = 0.0
                self._indicator_timer.start()  # type: ignore[attr-defined]

    def _switch_to_page(self, page_index: int):
        if not self.pages:  # type: ignore[attr-defined]
            return
        page_index = max(0, min(int(page_index), len(self.pages) - 1))  # type: ignore[attr-defined]
        if page_index == self.current_page:
            return

        current = int(self.current_page)
        count = len(self.pages)  # type: ignore[attr-defined]
        forward = (page_index - current) % count
        backward = forward - count
        direction = forward if abs(forward) <= abs(backward) else backward
        if direction == 0:
            return

        if hasattr(self, "_defer_blank_area_refresh_for_interaction"):
            self._defer_blank_area_refresh_for_interaction()
        self.current_page = page_index
        self._target_page = self._page_animation_target_base() + direction
        self.hover_index = -1
        self._schedule_last_page_index_save()
        if not self._indicator_timer.isActive():  # type: ignore[attr-defined]
            self._page_anim_last_ts = 0.0
            self._indicator_timer.start()  # type: ignore[attr-defined]
        self.update()  # type: ignore[attr-defined]

    def _finish_page_animation(self):
        if not self.pages:
            return
        page = float(self.current_page % len(self.pages))
        self._page_position = page
        self._page_offset = page
        self._target_page = page
        self._indicator_pos = page

    def keyPressEvent(self, event):
        """按键事件 - 支持平滑 caret、拼音搜索、以及 slash(/) 命令"""
        key = event.key()
        if key == Qt.Key_Tab:
            current_default = bool(getattr(self.settings, "search_default_active", False))
            new_default = not current_default
            try:
                self.data_manager.update_settings(search_default_active=new_default)
                self.settings = self.data_manager.get_settings()
            except Exception as exc:
                logger.debug("保存Tab切换状态失败: %s", exc, exc_info=True)
                self.settings.search_default_active = new_default
            self._search_forced_active = new_default
            self._start_search_reveal_animation(new_default)
            self.update()
            event.accept()
            return

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
            if key in (
                Qt.Key_Left,
                Qt.Key_Right,
                Qt.Key_Up,
                Qt.Key_Down,
                Qt.Key_Home,
                Qt.Key_End,
                Qt.Key_PageUp,
                Qt.Key_PageDown,
            ):
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
            if not is_printable and key not in (Qt.Key_Backspace, Qt.Key_Delete) and not allow_search_edit_shortcut:
                event.accept()
                return
            if not self._search_query_matches_result_command():
                self.clear_command_result()

        key = event.key()
        text = event.text()

        # 1. ESC 键清除搜索或隐藏窗口
        if key in (Qt.Key_Escape, 16777216):  # 16777216 is Qt.Key_Escape
            if self._is_search_active():
                self._reset_search_state()
                if bool(getattr(self.settings, "search_default_active", False)):
                    self._search_forced_active = True
                    self._start_search_reveal_animation(True)
                event.accept()
                return
            else:
                if getattr(self, "_search_forced_active", False) and not bool(
                    getattr(self.settings, "search_default_active", False)
                ):
                    self._search_forced_active = False
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

        # 2. 如果搜索为非激活状态（即查询内容为空时）
        is_printable = bool(text) and ord(text) >= 32 if len(text) == 1 else False

        if not self._is_search_active():
            if key == Qt.Key_Left:
                self._switch_page(-1)
                event.accept()
                return
            elif key == Qt.Key_Right:
                self._switch_page(1)
                event.accept()
                return

            # 只要搜索未激活且按下可打印按键，就直接录入并启动搜索。
            # 为了防止误触并保持测试兼容，当搜索栏胶囊不可见时，首个空格键不启动搜索；其他可打印字符（数字、字母、符号等）均直接启动。
            if is_printable:
                if text == " " and not self._is_search_bar_visible():
                    pass
                else:
                    self._insert_or_replace_text(text)
                    event.accept()
                    return
            elif self._is_search_bar_visible() and key in (Qt.Key_Backspace, Qt.Key_Delete):
                event.accept()
                return

            try:
                super().keyPressEvent(event)
            except Exception as exc:
                logger.debug("处理按键事件失败: %s", exc, exc_info=True)
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
            self._move_search_cursor(
                self._previous_search_boundary(self.search_cursor_pos) if ctrl else self.search_cursor_pos - 1,
                keep_selection=shift,
            )
            event.accept()
            return

        elif key == Qt.Key_Right:
            self._move_search_cursor(
                self._next_search_boundary(self.search_cursor_pos) if ctrl else self.search_cursor_pos + 1,
                keep_selection=shift,
            )
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
                # Record search selection for learning
                try:
                    from core.search_history import record_search_selection

                    record_search_selection(self.search_query, getattr(shortcut, "id", ""))
                except Exception as exc:
                    logger.debug("记录搜索选择失败: %s", exc, exc_info=True)
                if hasattr(self, "_execute_item"):
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
            except Exception as exc:
                logger.debug("处理按键事件失败: %s", exc, exc_info=True)

    def _switch_page(self, direction: int):
        """切换页面"""
        if len(self.pages) <= 1:  # type: ignore[attr-defined]
            return

        self._queue_page_switch(direction)
        self.hover_index = -1
        self.update()  # type: ignore[attr-defined]

    def enterEvent(self, event):
        """鼠标进入"""
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开"""
        old_hover = self.hover_index
        old_dock_hover = self.dock_hover_index
        self.hover_index = -1
        self.dock_hover_index = -1
        self._update_hover_regions(old_hover, old_dock_hover, -1, -1)

    def _check_close(self):
        """检查是否应该关闭 (Fallback)"""
        if self.is_pinned or self._executing or self._is_dragging:
            if self._hide_timer.isActive():
                self._hide_timer.stop()
            return

        cursor_pos = self.mapFromGlobal(QCursor.pos())
        inside = self.rect().contains(cursor_pos)

        auto_close = getattr(self.settings, "popup_auto_close", True)

        if auto_close:
            if inside:
                if self._hide_timer.isActive():
                    self._hide_timer.stop()
                return
            if not self._hide_timer.isActive():
                delay = getattr(self.settings, "hover_leave_delay", 200)
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
                    if hasattr(self, "_defer_lifecycle_callback"):
                        self._defer_lifecycle_callback(
                            50,
                            self.hide,
                            generation=int(getattr(self, "_lifecycle_generation", 0) or 0),
                        )
                    else:
                        QTimer.singleShot(50, self.hide)
            except Exception as exc:
                logger.debug("检查鼠标按键状态失败: %s", exc, exc_info=True)

    def focusOutEvent(self, event):
        """失去焦点"""
        if not self.is_pinned and not self._executing and not self._is_dragging:
            auto_close = getattr(self.settings, "popup_auto_close", True)
            if auto_close:
                if hasattr(self, "_defer_lifecycle_callback"):
                    self._defer_lifecycle_callback(
                        100,
                        self._check_close,
                        generation=int(getattr(self, "_lifecycle_generation", 0) or 0),
                    )
                else:
                    QTimer.singleShot(100, self._check_close)

    # ===== 搜索与 slash(/) 命令辅助方法 =====
