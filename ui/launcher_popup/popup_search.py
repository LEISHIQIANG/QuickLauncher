"""Search bar editing, search logic, IME support and reveal animation for LauncherPopup."""

import logging
import time

from core.data_models import ShortcutItem, ShortcutType
from core.fuzzy_search import FuzzyMatchResult, search_shortcuts
from core.search_engines import build_search_url, parse_search_action
from core.slash_commands import find_matching_commands
from qt_compat import (
    QApplication,
    QBitmap,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPoint,
    QRect,
    QRectF,
    Qt,
    QtCompat,
    QTimer,
)
from ui.launcher_popup.popup_command_result import CompactResultPopupMenu
from ui.utils.window_effect import is_win10

logger = logging.getLogger(__name__)


class PopupSearchMixin:
    """Search text editing, IME input, search logic, reveal animation, and page preloading."""

    # ── IME support ──────────────────────────────────────────────────

    def inputMethodEvent(self, event):
        """输入法事件支持 (支持拼音输入法，测试安全)"""
        self._search_forced_active = True
        commit = ""
        preedit = ""

        if hasattr(event, "commitString"):
            commit = event.commitString()
        else:
            commit = getattr(event, "_commit", "")

        if hasattr(event, "preeditString"):
            preedit = event.preeditString()
        else:
            preedit = getattr(event, "_preedit", "")

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
            except Exception as exc:
                logger.debug("转发输入法事件: %s", exc, exc_info=True)

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
                return (
                    self.search_selection_anchor if self.search_selection_anchor is not None else self.search_cursor_pos
                )
            if query == Qt.ImCurrentSelection:
                bounds = self._search_selection_bounds()
                if bounds:
                    start, end = bounds
                    return self.search_query[start:end]
                return ""
        except Exception as exc:
            logger.debug("查询输入法属性失败: %s", exc, exc_info=True)
        try:
            return super().inputMethodQuery(query)
        except Exception:
            return None

    # ── Search text editing ──────────────────────────────────────────

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
        font.setPixelSize(max(10, font.pixelSize() + 2))
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
        x = int(
            text_rect.left()
            + self._search_text_width(prefix + query[:cursor] + preedit)
            - int(self.__dict__.get("_search_scroll_x", 0) or 0)
        )
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
            right = self._search_text_width(query[: i + 1]) if i < len(query) else left
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
        except Exception as exc:
            logger.debug("启动搜索光标定时器失败: %s", exc, exc_info=True)

    def _toggle_search_cursor(self):
        if not self._is_search_active():
            try:
                self._search_cursor_timer.stop()
            except Exception as exc:
                logger.debug("停止搜索光标定时器: %s", exc, exc_info=True)
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
        except Exception as exc:
            logger.debug("复制到剪贴板: %s", exc, exc_info=True)

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
        except Exception as exc:
            logger.debug("读取剪贴板: %s", exc, exc_info=True)
        return ""

    # ── Search logic ─────────────────────────────────────────────────

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
        if self.__dict__.get("_command_result") is not None and not self._search_query_matches_result_command():
            self.clear_command_result()

        is_active = bool(self.search_query) or self._search_forced_active
        self._start_search_reveal_animation(is_active)
        self._debounce_refresh_search()

    _SEARCH_DEBOUNCE_MS = 100

    def _debounce_refresh_search(self):
        """Debounce search: clear stale results immediately, search after typing pauses."""
        try:
            # Clear stale results so UI never shows mismatched data during typing
            self.search_results = []
            self.search_selected_index = -1
            self.update()
            # Lazy-init the debounce timer
            timer = getattr(self, "_search_debounce_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self._refresh_search_results)
                self._search_debounce_timer = timer
            timer.stop()
            timer.start(self._SEARCH_DEBOUNCE_MS)
        except RuntimeError:
            # QWidget not fully initialized (e.g. in test)
            self._refresh_search_results()

    def _refresh_search_results(self):
        """核心刷新搜索结果，支持 Web 搜索引擎，Slash 命令及本地 + Dock 图标混合"""
        query = self.search_query.strip()
        self._plugin_search_seq = int(self.__dict__.get("_plugin_search_seq", 0) or 0) + 1
        plugin_search_seq = self._plugin_search_seq
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
                    enabled=True,
                )
                results.append(
                    FuzzyMatchResult(
                        shortcut=shortcut,
                        folder_id="slash_commands",
                        folder_name=folder_name,
                        score=score_start - i,
                        original_index=i,
                        matched_fields=["command"],
                    )
                )

        # 1. 尝试解析 Web 搜索引擎快捷搜索 (例如 "g cats")
        action = parse_search_action(self.search_query)
        if action is not None:
            url = build_search_url(action)
            web_shortcut = ShortcutItem(
                id=f"web_search_{action.engine}",
                name=f"{action.engine}: {action.keyword}",
                type=ShortcutType.URL,
                url=url,
                enabled=True,
            )
            results.append(
                FuzzyMatchResult(
                    shortcut=web_shortcut,
                    folder_id="web_search",
                    folder_name="Web Search",
                    score=999.0,
                    original_index=0,
                    matched_fields=["url"],
                )
            )

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
                except Exception as exc:
                    logger.debug("获取设置: %s", exc, exc_info=True)

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
                            id=cid,
                            name=cmd_info.display_name or cid,
                            type=ShortcutType.COMMAND,
                            command=cmd_value,
                            command_type="builtin",
                            icon_path=cmd_info.icon_path,
                            enabled=True,
                        )
                        result = FuzzyMatchResult(
                            shortcut=shortcut,
                            folder_id="slash_commands",
                            folder_name="收藏命令",
                            score=300.0,
                            original_index=0,
                            matched_fields=["command"],
                        )
                        fav_results.append(result)

                results = fav_results
            else:
                append_command_results(matched_cmds, "Slash Commands", 100.0)

            self._start_plugin_search(cmd_query, plugin_search_seq)
        else:
            # 3. 本地快捷图标 + Dock 图标的拼音/Fuzzy混合检索
            search_folders = [f for f in (self.pages or []) if not getattr(f, "is_icon_repo", False)]

            dock_folder = getattr(self, "dock_folder", None)
            if dock_folder is not None:
                if dock_folder not in search_folders:
                    search_folders.append(dock_folder)
            elif getattr(self, "dock_items", None):
                from core.data_models import Folder

                temp_dock_folder = Folder(id="dock", name="Dock", is_dock=True, items=self.dock_items)
                search_folders.append(temp_dock_folder)

            sort_mode = getattr(self.settings, "sort_mode", "smart")
            local_results = search_shortcuts(search_folders, query, sort_mode=sort_mode)
            results.extend(local_results)

            if len(query) >= 2:
                try:
                    matched_cmds = find_matching_commands(query)
                    append_command_results(matched_cmds, "Commands", 80.0)
                except Exception:
                    logger.exception("命令搜索失败: %s", query)

        self.search_results = results
        if results:
            self.search_selected_index = 0
        else:
            self.search_selected_index = -1

        self.update()

    def _start_plugin_search(self, cmd_query: str, token: int):
        try:
            signal = self.plugin_search_results_ready
        except Exception:
            return

        # Cancel any previous in-flight search via the cancel token.
        old_token = getattr(self, "_plugin_search_cancel_token", None)
        if old_token is not None:
            old_token.cancel()

        from core.command_registry import SearchCancelToken

        cancel_token = SearchCancelToken()
        self._plugin_search_cancel_token = cancel_token

        def worker():
            payload = []
            try:
                from core.command_registry import execute_search_sources

                for src_id, src_info, src_results in execute_search_sources(cmd_query, cancel_token=cancel_token):
                    if cancel_token.cancelled:
                        return
                    for sr in src_results:
                        payload.append(
                            {
                                "source_id": src_id,
                                "plugin_id": src_info.get("plugin_id", "插件"),
                                "id": sr.get("id", src_id),
                                "title": sr.get("title", sr.get("name", src_id)),
                                "command": sr.get("command", ""),
                                "folder": sr.get("folder", src_info.get("plugin_id", "插件")),
                            }
                        )
            except Exception:
                logger.exception("插件搜索失败: %s", cmd_query)
            if cancel_token.cancelled:
                return
            try:
                signal.emit(token, cmd_query, payload)
            except RuntimeError:
                logger.debug("发送插件搜索信号失败", exc_info=True)

        # Use the shared search pool instead of a dedicated daemon thread.
        from core.command_registry import _get_search_pool

        _get_search_pool().submit(worker)

    def _on_plugin_search_results_ready(self, token: int, cmd_query: str, payload):
        if token != int(self.__dict__.get("_plugin_search_seq", 0) or 0):
            return
        if not str(getattr(self, "search_query", "") or "").startswith("/"):
            return
        if str(getattr(self, "search_query", "") or "")[1:] != cmd_query:
            return
        try:
            if hasattr(self, "isVisible") and not self.isVisible():
                return
        except Exception:
            return
        additions = []
        for sr in payload or []:
            shortcut = ShortcutItem(
                id=sr.get("id", sr.get("source_id", "")),
                name=sr.get("title", sr.get("id", "")),
                type=ShortcutType.COMMAND,
                command=sr.get("command", ""),
                command_type="builtin",
                enabled=True,
            )
            additions.append(
                FuzzyMatchResult(
                    shortcut=shortcut,
                    folder_id=f"plugin_{sr.get('plugin_id', '插件')}",
                    folder_name=sr.get("folder", sr.get("plugin_id", "插件")),
                    score=150.0,
                    original_index=0,
                    matched_fields=["name"],
                )
            )
        if not additions:
            return
        self.search_results = list(getattr(self, "search_results", []) or []) + additions
        if self.search_selected_index < 0:
            self.search_selected_index = 0
        self.update()

    # ── Search layout / geometry helpers ─────────────────────────────

    def _current_search_bar_height(self) -> int:
        """返回搜索框高度 (常量 34)"""
        return 34

    def _search_visible_height(self) -> int:
        """返回当前动画进度下的搜索框可见高度"""
        return int(self._search_reveal_progress * 34)

    def _body_y_offset(self) -> int:
        """返回由于搜索框显示而导致主体区域下移的Y偏移量"""
        if not hasattr(self, "_search_reveal_progress"):
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
        if not hasattr(self, "search_query"):
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
        old_anchor = getattr(self, "_search_body_anchor_y", 0)
        if old_anchor == 0:
            self._search_body_anchor_y = self.geometry().y()
            logger.debug(
                f"[ANCHOR] 记录基准点: y={self._search_body_anchor_y}, geometry={self.geometry()}, search_progress={getattr(self, '_search_reveal_progress', 'N/A')}"
            )
        else:
            logger.debug(f"[ANCHOR] 使用已有基准点: y={old_anchor}")

    def _set_fixed_geometry_atomically(self, left: int, top: int, width: int, height: int):
        """原子级设置窗口尺寸与位置，减少透明窗口重绘闪烁"""
        self.setGeometry(left, top, width, height)
        try:
            self._update_window_effect()
        except Exception as exc:
            logger.debug("更新窗口特效: %s", exc, exc_info=True)

    def _apply_search_geometry(
        self, skip_effect_update=False, repaint=True, restore_updates=True, progress_override=None
    ):
        """物理几何体位置/尺寸调整"""
        self._remember_search_body_anchor()
        base_y = self._search_body_anchor_y
        geom = self.geometry()
        x = geom.x()
        w = geom.width()

        progress = self._search_reveal_progress if progress_override is None else float(progress_override)
        y_offset = int(progress * 34)

        if hasattr(self, "_calculate_fixed_size"):
            calc_w, calc_h = self._calculate_fixed_size(y_offset_override=y_offset)
        else:
            calc_w = w
            calc_h = geom.height()

        target_h = calc_h
        target_y = base_y - y_offset

        if geom.y() != target_y or geom.height() != target_h or geom.width() != calc_w:
            logger.debug(
                f"[GEOM] 调整窗口: progress={self._search_reveal_progress:.3f}, "
                f"old=({geom.x()},{geom.y()},{geom.width()}x{geom.height()}), "
                f"new=({x},{target_y},{calc_w}x{target_h})"
            )

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

                # 更新窗口效果（只更新一次）
                if not skip_effect_update:
                    try:
                        self._geometry_adjusting = False
                        self._update_window_effect()
                        self._geometry_adjusting = True
                    except Exception as exc:
                        logger.debug("更新窗口特效: %s", exc, exc_info=True)

                # 启用更新并重绘
                if restore_updates:
                    self.setUpdatesEnabled(True)
                    if repaint:
                        self.repaint()
            finally:
                self._geometry_adjusting = False

    def _apply_search_mask(self, force: bool = False):
        """采用遮罩掩码裁剪顶部搜索区域"""
        if is_win10():
            self.clearMask()
            return

        if not self._is_search_layout_visible() and not force:
            logger.debug(f"[SEARCH_MASK] 清除搜索遮罩: window={self.width()}x{self.height()}")
            self.clearMask()
            return

        inset = self._search_visible_top_inset()
        w = self.width()
        h = self.height()
        r = self._get_paint_corner_radius()

        logger.debug(
            f"[SEARCH_MASK] 应用搜索遮罩: window={w}x{h}, inset={inset}, visible_y={inset}, visible_h={h - inset}, radius={r}"
        )

        mask = QBitmap(w, h)
        mask.fill(Qt.color0)

        painter = QPainter(mask)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)
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

    # ── Search reveal animation ──────────────────────────────────────

    def _start_search_reveal_animation(self, active: bool):
        """启动展开或收起动画"""
        self._remember_search_body_anchor()
        target = 1.0 if active else 0.0

        if abs(self._search_target_progress - target) < 1e-9 and abs(self._search_reveal_progress - target) < 1e-9:
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

            if "pytest" in sys.modules:
                self.repaint()
        except Exception as exc:
            logger.debug("pytest模式重绘检测失败: %s", exc, exc_info=True)

    def _finish_search_hide_geometry(self):
        """收尾隐藏动画并恢复尺寸"""
        self._search_hide_geometry_pending = False
        self._apply_search_geometry()
        self.clearMask()
        self.update()
        try:
            import sys

            if "pytest" in sys.modules:
                self.repaint()
        except Exception as exc:
            logger.debug("pytest模式重绘检测失败: %s", exc, exc_info=True)

    def _reset_search_state(self):
        """重置所有搜索状态"""
        self._plugin_search_seq = int(self.__dict__.get("_plugin_search_seq", 0) or 0) + 1
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
        except Exception as exc:
            logger.debug("重置搜索框几何和遮罩失败: %s", exc, exc_info=True)
        self.update()

    # ── Page animation preloading ────────────────────────────────────

    def _preload_animation_pages(self):
        """增量式预加载：不阻塞 UI 线程，分帧逐步加载图标和渲染 page pixmap"""
        if not self.pages:
            return
        # 停止已有的预加载定时器（如果有）
        old_timer = getattr(self, "_preload_batch_timer", None)
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
        deadline = time.perf_counter() + 0.008  # 8ms 预算，不影响 60fps

        # 阶段1：加载图标到 _icon_pixmap_cache
        items = getattr(self, "_preload_items_list", None)
        idx = getattr(self, "_preload_icon_idx", 0)
        if items and idx < len(items):
            while idx < len(items) and time.perf_counter() < deadline:
                try:
                    self._get_icon(items[idx])
                except Exception as exc:
                    logger.debug("预加载图标: %s", exc, exc_info=True)
                idx += 1
            self._preload_icon_idx = idx
            if idx < len(items):
                return  # 还有图标未加载，下一帧继续

        # 阶段2：预渲染 page pixmap（每帧渲染一页）
        page_queue = getattr(self, "_preload_page_queue", None)
        if page_queue:
            page_idx = page_queue.pop(0)
            theme = getattr(self.settings, "theme", "dark")
            text_color = QColor(255, 255, 255) if theme == "dark" else QColor(0, 0, 0)
            hover_color = QColor(255, 255, 255, 20) if theme == "dark" else QColor(0, 0, 0, 20)
            drop_highlight_color = QColor(0, 120, 215, 100)
            bg_mode = getattr(self.settings, "bg_mode", "acrylic")
            try:
                self._get_page_animation_pixmap(page_idx, text_color, hover_color, drop_highlight_color, bg_mode)
            except Exception as exc:
                logger.debug("预渲染页面动画缓存: %s", exc, exc_info=True)
            if page_queue:
                return  # 还有页面未渲染，下一帧继续

        # 全部完成，停止定时器并清理
        timer = getattr(self, "_preload_batch_timer", None)
        if timer:
            timer.stop()
        self._preload_items_list = None
        self._preload_page_queue = None

    def _warm_page_pixmap_cache(self, pages):
        """预热指定页面的绘图缓存"""
        theme = getattr(self.settings, "theme", "dark")
        text_color = QColor(255, 255, 255) if theme == "dark" else QColor(0, 0, 0)
        hover_color = QColor(255, 255, 255, 20) if theme == "dark" else QColor(0, 0, 0, 20)
        drop_highlight_color = QColor(0, 120, 215, 100)
        bg_mode = getattr(self.settings, "bg_mode", "acrylic")
        for page_idx in pages:
            try:
                self._get_page_animation_pixmap(page_idx, text_color, hover_color, drop_highlight_color, bg_mode)
            except Exception as exc:
                logger.debug("预渲染页面动画缓存: %s", exc, exc_info=True)

    def _request_page_animation_update(self):
        """请求页面切换动画的重绘区域"""
        dock_y = getattr(self, "dock_y", self.height())
        self.update(QRect(0, 0, self.width(), dock_y))
