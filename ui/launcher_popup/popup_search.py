"""Search bar editing, search logic, IME support and reveal animation for LauncherPopup."""

import logging
import time

from core.data_models import ShortcutItem, ShortcutType
from core.fuzzy_search import FuzzyMatchResult, search_shortcuts
from core.search_engines import build_search_url, parse_search_action
from core.slash_commands import find_matching_commands
from qt_compat import QApplication, QColor, QFont, QFontMetrics, QPoint, QRect, QRectF, Qt, QTimer
from ui.launcher_popup.popup_command_result import CompactResultPopupMenu
from ui.utils.interruptible_animation import set_precise_timer
from ui.utils.ui_scale import font_px, sp

logger = logging.getLogger(__name__)


class PopupSearchMixin:
    search_cursor_pos: int
    search_selection_anchor: int | None
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
        return sp(32)

    def _search_text_prefix(self) -> str:
        return ""

    def _search_font(self) -> QFont:
        base_font = self.__dict__.get("_label_font")
        base_pixel_size = base_font.pixelSize() if base_font is not None else -1
        if base_pixel_size <= 0:
            base_pixel_size = font_px(10)
        target_pixel_size = max(font_px(10), base_pixel_size + sp(2))
        cache_key = (base_pixel_size, target_pixel_size)
        cached = self.__dict__.get("_search_font_cache")
        if cached is not None and cached[0] == cache_key:
            return QFont(cached[1])

        font = QFont(base_font) if base_font is not None else QFont()
        font.setPixelSize(target_pixel_size)
        self._search_font_cache = (cache_key, QFont(font))
        self.__dict__.pop("_search_metrics_cache", None)
        self.__dict__.pop("_search_text_width_cache", None)
        return font

    def _search_metrics(self) -> QFontMetrics:
        font = self._search_font()
        cache_key = (
            font.family(),
            font.pixelSize(),
            font.weight(),
            font.italic(),
            font.bold(),
        )
        cached = self.__dict__.get("_search_metrics_cache")
        if cached is not None and cached[0] == cache_key:
            return cached[1]  # type: ignore[unused-ignore, no-any-return]
        metrics = QFontMetrics(font)
        self._search_metrics_cache = (cache_key, metrics)
        self.__dict__.pop("_search_text_width_cache", None)
        return metrics

    def _search_text_width(self, value: str) -> int:
        value = value or ""
        if QApplication.instance() is None:
            return sum(sp(14) if ord(ch) > 127 else sp(7) for ch in value)
        metrics = self._search_metrics()
        font_key = self.__dict__.get("_search_metrics_cache", (None,))[0]
        cache = self.__dict__.get("_search_text_width_cache")
        if cache is None or cache[0] != font_key:
            cache = (font_key, {})
            self._search_text_width_cache = cache  # type: ignore[var-annotated]
        widths = cache[1]  # type: ignore[var-annotated]
        cached = widths.get(value)
        if cached is not None:
            return cached  # type: ignore[no-any-return]
        if hasattr(metrics, "horizontalAdvance"):
            width = metrics.horizontalAdvance(value)
        else:
            width = metrics.width(value)
        widths[value] = width
        if len(widths) > 256:
            widths.clear()
            widths[value] = width
        return width

    def _search_bar_rect(self) -> QRectF:
        side_inset = sp(0)
        x = self.padding + side_inset  # type: ignore[attr-defined]
        w = self.width() - (self.padding + side_inset) * 2  # type: ignore[attr-defined]
        shadow_margin = int(self.__dict__.get("shadow_margin", 0) or 0)
        return QRectF(x, shadow_margin + sp(8), w, sp(24))

    def _search_text_rect(self) -> QRectF:
        return self._search_bar_rect().adjusted(sp(32), 0, -sp(14), 0)

    def _search_bar_contains(self, pos: QPoint) -> bool:
        try:
            if not self._is_search_bar_visible():
                return False
            return self._search_bar_rect().contains(pos)
        except Exception:
            return False

    def _page_header_rect(self) -> QRectF:
        return self._search_bar_rect()

    def _update_page_header_layout(self):
        pages = list(getattr(self, "pages", None) or [])
        rect = self._page_header_rect()

        # Cache key values to prevent redundant calculations
        self.__dict__["_page_tab_cached_width"] = rect.width()
        self.__dict__["_page_tab_cached_names"] = tuple(str(getattr(p, "name", "") or "") for p in pages)

        if not pages:
            self.__dict__["_page_tab_widths"] = []
            self.__dict__["_page_tab_x"] = []
            self.__dict__["_page_tab_total_width"] = 0.0
            return

        base_font = self.__dict__.get("_label_font")
        if hasattr(self, "_search_font"):
            font = self._search_font()
        else:
            font = QFont(base_font) if base_font is not None else QFont()
        if font.pixelSize() <= 0:
            font.setPixelSize(font_px(10))

        metrics = QFontMetrics(font)
        count = len(pages)

        pref_widths = []
        for p in pages:
            name = str(getattr(p, "name", "") or "")
            pref_w = (
                metrics.horizontalAdvance(name) if hasattr(metrics, "horizontalAdvance") else metrics.width(name)
            ) + sp(12)
            pref_widths.append(pref_w)

        total_pref_width = sum(pref_widths)

        tab_widths = []
        if total_pref_width <= rect.width():
            extra_padding = (rect.width() - total_pref_width) / count
            for w in pref_widths:
                tab_widths.append(w + extra_padding)
        else:
            tab_widths = pref_widths

        tab_x = []
        curr_x = 0.0
        for w in tab_widths:
            tab_x.append(curr_x)
            curr_x += w

        self.__dict__["_page_tab_widths"] = tab_widths
        self.__dict__["_page_tab_x"] = tab_x
        self.__dict__["_page_tab_total_width"] = curr_x

    def _get_page_header_scroll_for_pos(self, page_pos: float) -> float:
        import math

        pages = list(getattr(self, "pages", None) or [])
        rect = self._page_header_rect()
        page_names = tuple(str(getattr(p, "name", "") or "") for p in pages)

        if (
            not self.__dict__.get("_page_tab_widths")
            or self.__dict__.get("_page_tab_cached_width") != rect.width()
            or self.__dict__.get("_page_tab_cached_names") != page_names
        ):
            self._update_page_header_layout()

        tab_widths = self.__dict__.get("_page_tab_widths")
        tab_x = self.__dict__.get("_page_tab_x")
        total_width = self.__dict__.get("_page_tab_total_width", 0.0)

        if not pages or not tab_widths or not tab_x:
            return 0.0

        max_scroll = max(0.0, total_width - rect.width())
        if max_scroll <= 0.0:
            return 0.0

        n = len(pages)
        idx1 = int(math.floor(page_pos)) % n
        idx2 = (idx1 + 1) % n
        weight = page_pos - math.floor(page_pos)

        def get_center_scroll(idx):
            w = tab_widths[idx]
            x = tab_x[idx]
            center = x + w / 2.0
            scroll = center - rect.width() / 2.0
            return max(0.0, min(scroll, max_scroll))

        scroll1 = get_center_scroll(idx1)
        scroll2 = get_center_scroll(idx2)
        return scroll1 + (scroll2 - scroll1) * weight  # type: ignore[no-any-return]

    def _page_header_tab_rects(self) -> list[tuple[int, QRectF]]:
        pages = list(getattr(self, "pages", None) or [])
        if not pages:
            return []

        rect = self._page_header_rect()
        page_names = tuple(str(getattr(p, "name", "") or "") for p in pages)
        if (
            not self.__dict__.get("_page_tab_widths")
            or self.__dict__.get("_page_tab_cached_width") != rect.width()
            or self.__dict__.get("_page_tab_cached_names") != page_names
        ):
            self._update_page_header_layout()

        page_pos = float(
            self.__dict__.get("_page_position")  # type: ignore[arg-type]
            if self.__dict__.get("_page_position") is not None
            else self.__dict__.get("current_page", 0.0)
        )
        scroll_x = self._get_page_header_scroll_for_pos(page_pos)
        self.__dict__["_page_header_scroll_x"] = scroll_x

        rect = self._page_header_rect()
        tab_widths = self.__dict__.get("_page_tab_widths") or []
        tab_x = self.__dict__.get("_page_tab_x") or []
        res = []
        for index in range(len(pages)):
            if index < len(tab_widths) and index < len(tab_x):
                w = tab_widths[index]
                x = tab_x[index]
                shifted_left = rect.left() + x - scroll_x
                res.append((index, QRectF(shifted_left, rect.top(), w, rect.height())))
        return res

    def _page_header_contains(self, pos: QPoint) -> bool:
        try:
            return not self._is_search_bar_visible() and self._page_header_rect().contains(pos)
        except Exception:
            return False

    def _page_index_at_header(self, pos: QPoint) -> int:
        if not self._page_header_contains(pos):
            return -1
        for index, rect in self._page_header_tab_rects():
            if rect.contains(pos):
                return index
        return -1

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
        margin = sp(8)
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
        cursor_h = sp(16)
        y = int(text_rect.center().y() - cursor_h / 2)
        return QRect(x, y, max(1, sp(1.5)), cursor_h)  # type: ignore[arg-type]

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
            if timer is not None and self._is_search_bar_visible():
                timer.start()
        except Exception as exc:
            logger.debug("启动搜索光标定时器失败: %s", exc, exc_info=True)

    def _toggle_search_cursor(self):
        if not self._is_search_bar_visible():
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
        self.update()  # type: ignore[attr-defined]

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
        self._search_forced_active = False
        self._search_preedit_text = ""
        self._set_search_query("", cursor_pos=0, selection_anchor=None)

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

    def _set_search_query(
        self,
        query: str,
        cursor_pos: int | None = None,
        selection_anchor: int | None = None,
    ):
        """设置搜索查询文本，并刷新固定顶部栏与结果。"""
        self.search_query = query or ""
        if not self.search_query and not getattr(self, "_search_preedit_text", ""):
            self._search_forced_active = False
        if cursor_pos is None:
            self.search_cursor_pos = len(self.search_query)
        else:
            self.search_cursor_pos = self._clamp_search_pos(cursor_pos)
        self.search_selection_anchor = None if selection_anchor is None else self._clamp_search_pos(selection_anchor)
        self._ensure_search_cursor_visible()
        self._restart_search_cursor_blink()
        if self.__dict__.get("_command_result") is not None and not self._search_query_matches_result_command():  # type: ignore[attr-defined]
            self.clear_command_result()  # type: ignore[attr-defined]

        self._start_search_reveal_animation(self._is_search_bar_visible())
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

            # Include the Icon Repository (图标仓库)
            repo_folder = None
            data_manager = self.__dict__.get("data_manager")
            if data_manager is not None:
                repo_folder = data_manager.data.get_folder_by_id("icon_repo")
                if repo_folder is None:
                    repo_folder = getattr(data_manager, "_icon_repo_folder", None)
            if repo_folder is not None:
                if repo_folder not in search_folders:
                    search_folders.append(repo_folder)

            sort_mode = getattr(self.settings, "sort_mode", "smart")
            local_results = search_shortcuts(search_folders, query, sort_mode=sort_mode)
            results.extend(local_results)

        self.search_results = results
        if results:
            self.search_selected_index = 0
        else:
            self.search_selected_index = -1

        self.update()

    def _start_plugin_search(self, cmd_query: str, token: int):
        try:
            signal = self.plugin_search_results_ready  # type: ignore[attr-defined]
        except Exception:
            return

        # Cancel any previous in-flight search via the cancel token.
        old_token = getattr(self, "_plugin_search_cancel_token", None)
        if old_token is not None:
            old_token.cancel()
        old_future = getattr(self, "_plugin_search_future", None)
        if old_future is not None:
            old_future.cancel()

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

        # Coordinators wait for handler futures, so they must not occupy the
        # handler pool itself (otherwise enough simultaneous popups starve all
        # search-source work until the total timeout expires).
        from core.executor_manager import PLUGIN_SEARCH_COORDINATOR_EXECUTOR, get_executor

        self._plugin_search_future = get_executor(PLUGIN_SEARCH_COORDINATOR_EXECUTOR).submit(worker)

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
        self.update()  # type: ignore[attr-defined]

    # ── Search layout / geometry helpers ─────────────────────────────

    def _current_search_bar_height(self) -> int:
        """返回固定顶部栏高度。"""
        return self._search_bar_full_height()

    def _search_visible_height(self) -> int:
        """顶部栏始终完整可见。"""
        return self._current_search_bar_height()

    def _body_y_offset(self) -> int:
        """主体始终为固定顶部栏预留空间。"""
        return self._current_search_bar_height()

    def _search_visible_top_inset(self) -> int:
        """固定顶部栏不需要揭示裁剪。"""
        return 0

    def _background_top_inset(self) -> int:
        """固定布局始终绘制完整背景。"""
        return 0

    def _is_search_layout_visible(self) -> bool:
        """顶部标题栏布局始终可见。"""
        return True

    def _is_search_active(self) -> bool:
        """搜索模式是否处于激活状态（仅当有键入内容或命令结果时激活）"""
        if self.__dict__.get("_command_result", None) is not None:
            return self._search_query_matches_result_command()  # type: ignore[attr-defined, no-any-return]
        return bool(self.search_query or getattr(self, "_search_preedit_text", ""))

    def _is_search_bar_visible(self) -> bool:
        """搜索框胶囊是否在顶部显示"""
        return bool(
            self.search_query
            or getattr(self, "_search_preedit_text", "")
            or getattr(self, "_search_forced_active", False)
        )

    def _search_animation_update_rect(self) -> QRect:
        """返回用于重绘搜索栏区域的 QRect"""
        return QRect(0, 0, self.width(), self._current_search_bar_height() + self._get_paint_corner_radius() + sp(2))  # type: ignore[attr-defined]

    def _remember_search_body_anchor(self):
        """记录固定布局的位置，兼容刷新期间的旧状态字段。"""
        if not getattr(self, "_search_body_anchor_y", 0):
            self._search_body_anchor_y = self.geometry().y()

    def _set_fixed_geometry_atomically(self, left: int, top: int, width: int, height: int):
        """原子级设置窗口尺寸与位置，减少透明窗口重绘闪烁"""
        self.setGeometry(left, top, width, height)  # type: ignore[attr-defined]

    def _apply_search_geometry(
        self, skip_effect_update=False, repaint=True, restore_updates=True, progress_override=None
    ):
        """固定标题栏不再因搜索状态改变窗口几何。"""
        if repaint:
            self.update(self._search_animation_update_rect())

    def _apply_search_mask(self, force: bool = False):
        """固定顶部栏不再需要原生遮罩。"""
        if force or not self.__dict__.get("_search_mask_cleared", False):
            self.clearMask()  # type: ignore[attr-defined]
        self._search_mask_cleared = True
        self._search_mask_cache_key = None

    def _clear_search_mask_for_animation(self):
        """Avoid rebuilding native masks on every search animation frame."""
        if self.__dict__.get("_search_mask_cleared", False):
            return
        try:
            self.clearMask()
            self._search_mask_cleared = True
            self._search_mask_cache_key = None
        except Exception as exc:
            logger.debug("清除搜索动画遮罩失败: %s", exc, exc_info=True)

    # ── Search reveal animation ──────────────────────────────────────

    def _start_search_reveal_animation(self, active: bool):
        """在固定标题栏内切换标题和搜索状态。"""
        target = 1.0 if active else 0.0
        timer = self.__dict__.get("_search_anim_timer")
        if timer is not None:
            try:
                timer.stop()
            except Exception as exc:
                logger.debug("停止旧搜索动画定时器失败: %s", exc, exc_info=True)
        changed = abs(getattr(self, "_search_target_progress", 0.0) - target) > 1e-9
        self._search_target_progress = target
        self._search_reveal_progress = target
        self._search_hide_geometry_pending = False
        if changed:
            self.update(self._search_animation_update_rect())  # type: ignore[attr-defined]

    def _tick_search_reveal(self):
        """兼容旧定时器回调，立即收敛到标题/搜索目标状态。"""
        self._search_reveal_progress = self._search_target_progress
        self._search_hide_geometry_pending = False
        try:
            self._search_anim_timer.stop()
        except Exception as exc:
            logger.debug("停止搜索状态定时器失败: %s", exc, exc_info=True)
        self.update(self._search_animation_update_rect())

    def _finish_search_hide_geometry(self):
        """兼容旧调用；固定布局无需收缩窗口。"""
        self._search_hide_geometry_pending = False
        self._search_reveal_progress = 0.0
        self._search_target_progress = 0.0
        self.update(self._search_animation_update_rect())

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
        try:
            timer = self.__dict__.get("_search_anim_timer")
            if timer is not None:
                timer.stop()
        except Exception as exc:
            logger.debug("停止搜索展开动画失败: %s", exc, exc_info=True)
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
            self.clearMask()
        except Exception as exc:
            logger.debug("重置搜索框遮罩失败: %s", exc, exc_info=True)
        self.update()

    # ── Page animation preloading ────────────────────────────────────

    def _preload_animation_pages(self):
        """后台生成页面滑动快照；真实图标应在显示前完成预热。"""
        if not self.pages:
            return
        # 停止已有的预加载定时器（如果有）
        timer = getattr(self, "_preload_batch_timer", None)
        if timer is not None:
            timer.stop()

        # 页面快照覆盖全部页面，连续快速滚动也不会追上预热队列。
        items_list = []
        n = len(self.pages)
        priority_order = [self.current_page]
        if n > 1:
            priority_order.append((self.current_page + 1) % n)
        if n > 2:
            priority_order.append((self.current_page - 1) % n)
        for page_idx in range(n):
            if page_idx not in priority_order:
                priority_order.append(page_idx)

        seen_items = set()
        if not bool(self.__dict__.get("_all_page_icons_preloaded", False)):
            max_visible = self.cols * getattr(self, "fixed_rows", getattr(self.settings, "popup_max_rows", 8))
            for page_idx in priority_order:
                for item_entry in list(self._get_page_animation_items(page_idx))[:max_visible]:
                    if isinstance(item_entry, dict):
                        item = item_entry.get("item")
                    else:
                        item = item_entry
                    marker = id(item)
                    if item is not None and marker not in seen_items:
                        seen_items.add(marker)
                        items_list.append(item)

        dock_items = self.__dict__.get("dock_items", None)
        if dock_items:
            settings = self.__dict__.get("settings", None)
            dock_rows = max(1, int(getattr(settings, "dock_height_mode", 1) or 1))
            max_dock_items = self.cols * dock_rows
            for item in (dock_items or [])[:max_dock_items]:
                marker = id(item)
                if item is not None and marker not in seen_items:
                    seen_items.add(marker)
                    items_list.append(item)

        self._preload_items_list = items_list
        self._preload_icon_idx = 0
        self._preload_page_queue = list(priority_order)
        self._preload_page_idx = 0

        if timer is None:
            timer = QTimer(self)
            timer.setInterval(24)
            set_precise_timer(timer, owner="LauncherPopup._preload_batch_timer")
            timer.timeout.connect(self._preload_next_batch)
            self._preload_batch_timer = timer
        timer.start()

    def _preload_next_batch(self):
        """每次只处理极少量预热任务，避免一次 shell 图标提取拖住 UI。"""
        try:
            if not self.isVisible():
                timer = getattr(self, "_preload_batch_timer", None)
                if timer:
                    timer.stop()
                return
        except RuntimeError:
            return

        if (
            getattr(self, "_is_dragging", False)
            or getattr(self, "_search_drag_selecting", False)
            or getattr(self, "_pinned_window_drag_active", False)
        ):
            return

        timer = getattr(self, "_indicator_timer", None)
        try:
            if timer is not None and timer.isActive():
                return
        except Exception as exc:
            logger.debug("检查页面动画状态失败: %s", exc, exc_info=True)

        deadline = time.perf_counter() + 0.003
        max_icons_per_tick = 1

        # 阶段1：加载图标到 _icon_pixmap_cache
        items = getattr(self, "_preload_items_list", None)
        idx = getattr(self, "_preload_icon_idx", 0)
        if items and idx < len(items):
            processed = 0
            while idx < len(items) and processed < max_icons_per_tick and time.perf_counter() < deadline:
                try:
                    self._get_icon(items[idx])
                except Exception as exc:
                    logger.debug("预加载图标: %s", exc, exc_info=True)
                idx += 1
                processed += 1
            self._preload_icon_idx = idx
            if idx < len(items):
                return  # 还有图标未加载，下一帧继续

        # 阶段2：预渲染 page pixmap（每帧渲染一页）
        page_queue = getattr(self, "_preload_page_queue", None)
        page_idx_cursor = int(getattr(self, "_preload_page_idx", 0) or 0)
        if page_queue and page_idx_cursor < len(page_queue):
            page_idx = page_queue[page_idx_cursor]
            self._preload_page_idx = page_idx_cursor + 1
            theme = getattr(self.settings, "theme", "dark")
            text_color = QColor(255, 255, 255) if theme == "dark" else QColor(0, 0, 0)
            hover_color = QColor(255, 255, 255, 20) if theme == "dark" else QColor(0, 0, 0, 20)
            drop_highlight_color = QColor(0, 120, 215, 100)
            bg_mode = getattr(self.settings, "bg_mode", "acrylic")
            try:
                self._get_page_animation_pixmap(page_idx, text_color, hover_color, drop_highlight_color, bg_mode)
            except Exception as exc:
                logger.debug("预渲染页面动画缓存: %s", exc, exc_info=True)
            if self._preload_page_idx < len(page_queue):
                return  # 还有页面未渲染，下一帧继续

        # 全部完成，停止定时器并清理
        timer = getattr(self, "_preload_batch_timer", None)
        if timer:
            timer.stop()
        self._preload_items_list = None
        self._preload_page_queue = None
        self._preload_page_idx = 0

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
