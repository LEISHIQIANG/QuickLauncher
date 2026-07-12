"""Command panel result renderers.

Extracted from :class:`ui.command_panel_window.CommandPanelWindow` in 1.6.3.3
to keep the 8 ``_render_*`` mode implementations (text/log/json/table/kv/list/
progress/qr/confirm) in a focused file. The panel still owns the widgets;
each renderer is a free function that takes the panel as its first
argument.

Public API on :class:`CommandPanelWindow` is unchanged: callers continue to
invoke ``panel._render_result(result)`` and friends.
"""

# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

from core.command_registry import CommandResult
from qt_compat import (
    QFont,
    QHeaderView,
    QListWidgetItem,
    QPixmap,
    QPlainTextEdit,
    QSize,
    Qt,
    QTableWidgetItem,
    QTextOption,
)
from ui.utils.ui_scale import font_px, sp

if TYPE_CHECKING:
    from .command_panel_window import CommandPanelWindow

logger = logging.getLogger(__name__)


# ── result dispatch ──────────────────────────────────────────────


def render_result(panel: CommandPanelWindow, result: CommandResult) -> None:
    """Dispatch a :class:`CommandResult` to the right renderer."""
    from core.command_result_actions import enrich_result_actions

    payload = result.payload if isinstance(result.payload, dict) else {}
    live_update = bool(payload.get("running"))
    if not live_update:
        result = enrich_result_actions(result)
    panel._current_result = result
    message = result.message or result.error or ("完成" if result.success else "执行失败")
    display_type = (result.display_type or "text").lower()
    if display_type in ("text", "log"):
        render_text_like(panel, result, message, display_type)
    elif display_type == "json":
        render_json(panel, result, message)
    elif display_type == "table":
        render_table(panel, result, message)
    elif display_type == "kv":
        render_kv(panel, result, message)
    elif display_type == "list":
        render_list(panel, result, message)
    elif display_type == "progress":
        render_progress(panel, result, message)
    elif display_type == "qr":
        render_qr(panel, result, message)
    elif display_type == "confirm":
        render_confirm(panel, result, message)
    else:
        render_text_like(panel, result, message, "text")
    # A streaming update changes only result content.  Rebinding and relaying
    # out action buttons for every chunk is unnecessary and can destabilize
    # the translucent Win11 window.  Actions are enriched and rendered once,
    # when the final result arrives.  The buttons themselves must also remain
    # parented from construction; see the first-show flash incident record in
    # docs/ui/20260621_命令面板首次捕获小窗闪烁故障复盘.md.
    if not live_update:
        render_actions(panel, result)
    panel._apply_size_for_result(result, panel._current_definition)


# ── per-mode renderers ───────────────────────────────────────────


def _set_result_text_preserving_scroll(
    panel: CommandPanelWindow,
    message: str,
    *,
    live_update: bool = False,
) -> None:
    """Replace the text widget contents while preserving the user's scroll position."""
    scrollbar = panel.text.verticalScrollBar()
    old_value = scrollbar.value()
    old_max = scrollbar.maximum()
    was_at_bottom = old_value >= max(0, old_max - 2)
    preserve_position = (live_update or panel._running) and old_max > 0 and not was_at_bottom

    panel.text.setPlainText(message)

    if preserve_position:
        scrollbar.setValue(min(old_value, scrollbar.maximum()))
    elif live_update or panel._running:
        scrollbar.setValue(scrollbar.maximum())


def render_text_like(
    panel: CommandPanelWindow,
    result: CommandResult,
    message: str,
    display_type: str,
) -> None:
    panel._show_widget("text")
    payload = result.payload if isinstance(result.payload, dict) else {}
    font_family = "Consolas" if display_type == "log" or payload.get("monospace") else "Microsoft YaHei UI"
    font = QFont(font_family, font_px(9))
    exact_match = font.exactMatch()
    if not exact_match and font_family == "Consolas":
        font = QFont("Courier New", font_px(9))
    panel.text.setFont(font)
    panel.text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
    panel.text.setWordWrapMode(QTextOption.WrapAnywhere)
    panel.text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # type: ignore[unused-ignore, attr-defined]
    _set_result_text_preserving_scroll(panel, message, live_update=bool(payload.get("running")))
    panel._rendered_text = message


def render_table(
    panel: CommandPanelWindow,
    result: CommandResult,
    message: str,
) -> None:
    panel._show_widget("table")
    payload = result.payload if isinstance(result.payload, dict) else {}
    rows = payload.get("rows") or []
    columns = payload.get("columns") or []
    if rows and not isinstance(rows[0], list | tuple | dict):
        rows = [[row] for row in rows]
    if rows and isinstance(rows[0], dict):
        if not columns:
            columns = list(rows[0].keys())
        matrix = [[row.get(col, "") for col in columns] for row in rows]
    else:
        matrix = [list(row) if isinstance(row, list | tuple) else [row] for row in rows]
        if not columns:
            col_count = max([len(row) for row in matrix] or [1])
            columns = [f"列 {idx + 1}" for idx in range(col_count)]
    panel.table.clear()
    panel.table.setColumnCount(len(columns) or 1)
    panel.table.setRowCount(len(matrix))
    panel.table.setHorizontalHeaderLabels([str(col) for col in (columns or ["结果"])])
    for row_idx, row in enumerate(matrix):
        for col_idx, value in enumerate(row[: panel.table.columnCount()]):
            panel.table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
    panel.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    panel.table.verticalHeader().setVisible(False)
    export_rows = ["\t".join(str(col) for col in (columns or ["结果"]))]
    export_rows.extend("\t".join(str(value) for value in row) for row in matrix)
    panel._rendered_text = "\n".join(export_rows)
    if not matrix and message:
        render_text_like(panel, result, message, "text")


def render_json(
    panel: CommandPanelWindow,
    result: CommandResult,
    message: str,
) -> None:
    payload = result.payload if isinstance(result.payload, dict) else {}
    formatted = str(payload.get("formatted") or "")
    if not formatted and "data" in payload:
        try:
            formatted = json.dumps(payload.get("data"), ensure_ascii=False, indent=2, sort_keys=True)
        except Exception:
            formatted = str(payload.get("data"))
    render_text_like(panel, result, formatted or message, "log")


def render_kv(
    panel: CommandPanelWindow,
    result: CommandResult,
    message: str,
) -> None:
    payload = result.payload if isinstance(result.payload, dict) else {}
    items = payload.get("items")
    if items is None:
        items = [[key, value] for key, value in payload.items() if key != "window_size"]
    result.payload = {**payload, "columns": ["名称", "值"], "rows": items}
    render_table(panel, result, message)


def render_list(
    panel: CommandPanelWindow,
    result: CommandResult,
    message: str,
) -> None:
    panel._show_widget("list")
    payload = result.payload if isinstance(result.payload, dict) else {}
    items = payload.get("items") or []
    panel.list_widget.clear()
    fm = panel.list_widget.fontMetrics()
    line_height = fm.height()
    vertical_padding = sp(16)  # 8px padding top + 8px padding bottom + 1px border
    for item in items:
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("name") or "")
            status = str(item.get("status") or "")
            detail = str(item.get("detail") or item.get("output_summary") or item.get("error") or "")
            duration = item.get("duration", "")
            duration_text = f" ({duration:.2f}s)" if isinstance(duration, int | float) else ""
            text = f"[{status.upper() or 'INFO'}] {title}{duration_text}"
            if detail:
                text += f"\n{detail}"
        else:
            text = str(item)
        qlwi = QListWidgetItem(text)
        line_count = text.count("\n") + 1
        qlwi.setSizeHint(QSize(0, line_count * line_height + vertical_padding))
        panel.list_widget.addItem(qlwi)
    panel._rendered_text = "\n".join(panel.list_widget.item(i).text() for i in range(panel.list_widget.count()))
    if not items:
        panel.text.setPlainText(message)
        panel._show_widget("text")
        panel._rendered_text = message


def render_progress(
    panel: CommandPanelWindow,
    result: CommandResult,
    message: str,
) -> None:
    panel._show_widget("progress")
    payload = result.payload if isinstance(result.payload, dict) else {}
    title = str(payload.get("title") or message or "执行中")
    detail = str(payload.get("detail") or "")
    progress = result.progress
    current = payload.get("current")
    total = payload.get("total")
    if total:
        try:
            progress = float(current or 0) / float(total)
        except Exception as exc:
            logger.debug("计算进度值失败: %s", exc, exc_info=True)
    progress = max(0.0, min(1.0, float(progress or 0.0)))
    panel.progress_title.setText(title)
    panel.progress_detail.setText(detail)
    panel.progress_bar.setValue(int(progress * 1000))
    panel._rendered_text = "\n".join(part for part in [title, detail, f"{progress * 100:.0f}%"] if part)


def render_qr(
    panel: CommandPanelWindow,
    result: CommandResult,
    message: str,
) -> None:
    payload = result.payload if isinstance(result.payload, dict) else {}
    image_path = payload.get("image_path")
    if image_path and os.path.exists(str(image_path)):
        panel._show_widget("qr")
        pixmap = QPixmap(str(image_path))
        if not pixmap.isNull():
            panel.qr_label.setPixmap(
                pixmap.scaled(QSize(sp(220), sp(220)), Qt.KeepAspectRatio, Qt.SmoothTransformation)  # type: ignore[unused-ignore, attr-defined]
            )
            panel.qr_label.setText("")
            panel._rendered_text = message
            return
    render_text_like(panel, result, message, "text")


def render_confirm(
    panel: CommandPanelWindow,
    result: CommandResult,
    message: str,
) -> None:
    payload = result.payload if isinstance(result.payload, dict) else {}
    detail = str(payload.get("detail") or payload.get("description") or "")
    body = "\n\n".join(part for part in [message, detail] if part)

    # Show confirmation dialog instead of just text
    shortcut = panel._current_shortcut or payload.get("shortcut")
    if payload.get("requires_confirmation") and shortcut is not None:
        try:
            from ui.styles.themed_messagebox import ThemedMessageBox

            reply = ThemedMessageBox.question(
                panel,
                "确认危险命令",
                body,
                ThemedMessageBox.Yes | ThemedMessageBox.No,
            )
            if reply == ThemedMessageBox.Yes:
                if panel._current_shortcut is not None:
                    panel._current_context_meta["destructive_confirmed"] = True
                    panel._execute_current_shortcut_request()
                    return
                # Re-execute from stored result with confirmation scoped to
                # this invocation instead of mutating the shortcut object.
                panel._rerun_with_shortcut(shortcut, context_meta={"destructive_confirmed": True})
                return
            else:
                panel._rendered_text = "已取消执行。"
                panel.text.setPlainText("已取消执行。")
                panel._update_subtitle("已取消")
                return
        except Exception:
            logger.debug("confirmation dialog failed, falling back to text", exc_info=True)

    render_text_like(panel, result, body or "Confirm action", "text")


def render_actions(panel: CommandPanelWindow, result: CommandResult) -> None:
    panel._all_actions = list(result.actions or [])
    for btn in panel.action_buttons:
        btn.hide()
        try:
            btn.clicked.disconnect()
        except Exception as exc:
            logger.debug("断开按钮信号: %s", exc, exc_info=True)
    primary_actions = sorted(
        panel._all_actions,
        key=lambda a: (not bool(getattr(a, "primary", False)), bool(getattr(a, "danger", False))),
    )
    extra_count = len(primary_actions) - len(panel.action_buttons)
    display_count = len(primary_actions) if extra_count == 1 else len(panel.action_buttons)
    for btn, action in zip(panel.action_buttons, primary_actions[:display_count]):
        btn.setText(action.label or panel._action_default_label(action.type))
        btn.setEnabled(bool(getattr(action, "enabled", True)))
        btn.setProperty(
            "command_action_role",
            ("danger" if getattr(action, "danger", False) else "primary" if getattr(action, "primary", False) else ""),
        )
        panel.style_buttons(btn)
        panel._style_action_button(btn, action)
        panel._neutralize_button_default(btn)
        btn.clicked.connect(lambda _checked=False, a=action: panel._execute_action(a))
        btn.show()
    panel.more_btn.setVisible(extra_count > 1)
    panel._relayout_footer_buttons()


__all__ = [
    "render_result",
    "render_text_like",
    "render_table",
    "render_json",
    "render_kv",
    "render_list",
    "render_progress",
    "render_qr",
    "render_confirm",
    "render_actions",
]
