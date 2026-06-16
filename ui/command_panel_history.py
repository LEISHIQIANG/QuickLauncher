"""Command result history rendering and menu.

Extracted from :class:`ui.command_panel_window.CommandPanelWindow` in 1.6.3.6
to keep the history dropdown / popup menu logic in a focused file.

Public API on :class:`CommandPanelWindow` is unchanged.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from qt_compat import QListWidgetItem, Qt
from ui.styles.style import PopupMenu
from ui.utils.ui_scale import scale_qss, sp

if TYPE_CHECKING:
    from .command_panel_window import CommandPanelWindow

logger = logging.getLogger(__name__)


def refresh_history(panel: CommandPanelWindow) -> None:
    """Rebuild the history list widget from :attr:`result_store`."""
    if panel.result_store is None:
        return
    items = panel.result_store.list()
    panel.history_list.clear()
    for item in items:
        title = item.command_title or item.command_id or "命令结果"
        state = "成功" if item.result.success else "失败"
        duration = getattr(item, "duration", 0.0) or 0.0
        row = QListWidgetItem(f"{state}  {title}  {duration:.2f}s")
        row.setData(int(Qt.UserRole), item.id)  # type: ignore[attr-defined]
        panel.history_list.addItem(row)
    visible = bool(items)
    panel.history_label.setVisible(False)
    if hasattr(panel, "history_toggle_btn"):
        panel.history_toggle_btn.setText("")
        panel.history_toggle_btn.setEnabled(visible)
        panel.history_toggle_btn.setVisible(True)
    panel.history_list.setVisible(False)


def toggle_history(panel: CommandPanelWindow) -> None:
    show_history_menu(panel)


def show_history_menu(panel: CommandPanelWindow) -> None:
    panel._hide_command_suggestions()
    if panel.result_store is None:
        return
    items = panel.result_store.list()
    if not items:
        return
    menu = PopupMenu(theme=panel._theme, radius=8, parent=None)
    _compact_history_menu(panel, menu)
    width = _history_menu_width(panel)
    menu.setMinimumWidth(width)
    menu.setMaximumWidth(width)
    menu.setFixedWidth(width)
    for item in items:
        label = history_menu_label(item)
        menu.add_action(
            label,
            lambda result_id=item.id: panel.show_result(str(result_id)),
            enabled=True,
        )
    panel._history_menu = menu
    anchor = getattr(panel, "command_input_group", panel.command_input)
    menu.popup(anchor.mapToGlobal(anchor.rect().bottomLeft()))


def _compact_history_menu(panel: CommandPanelWindow, menu: PopupMenu) -> None:
    if panel._theme == "dark":
        text = "rgba(255,255,255,0.85)"
        hover = "rgba(255,255,255,0.10)"
        pressed = "rgba(255,255,255,0.16)"
        disabled = "rgba(255,255,255,110)"
    else:
        text = "rgba(28,28,30,0.85)"
        hover = "rgba(0,0,0,0.06)"
        pressed = "rgba(0,0,0,0.10)"
        disabled = "rgba(60,60,67,120)"
    compact_style = scale_qss(
        "QPushButton{background:transparent;border:none;padding:4px 10px;margin:0px;"
        f"border-radius:6px;color:{text};font-size:11px;text-align:left;"
        "font-family:'Segoe UI','Microsoft YaHei UI',sans-serif;font-weight:400;}"
        f"QPushButton:hover{{background:{hover};color:{text};}}"
        f"QPushButton:pressed{{background:{pressed};}}"
        f"QPushButton:disabled{{color:{disabled};}}"
    )
    try:
        menu._layout.setContentsMargins(sp(6), sp(6), sp(6), sp(6))
        menu._layout.setSpacing(sp(2))
        menu._btn_style_dark = compact_style
        menu._btn_style_light = compact_style
    except Exception as exc:
        logger.debug("设置历史菜单布局失败: %s", exc, exc_info=True)


def _history_menu_width(panel: CommandPanelWindow) -> int:
    anchor = getattr(panel, "command_input_group", panel.command_input)
    return max(sp(220), int(anchor.width()))


def history_menu_label(item) -> str:
    text = item.raw_input or item.command_title or item.command_id or "命令"
    text = " ".join(str(text).split())
    return text if len(text) <= 56 else f"{text[:53]}..."


def on_history_item_clicked(panel: CommandPanelWindow, item) -> None:
    result_id = item.data(int(Qt.UserRole))  # type: ignore[attr-defined]
    if result_id:
        panel.show_result(str(result_id))


__all__ = [
    "refresh_history",
    "toggle_history",
    "show_history_menu",
    "history_menu_label",
    "on_history_item_clicked",
]
