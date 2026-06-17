"""View-model for the P1-06 icon-grid refactor.

The :mod:`ui.config_window.icon_grid` file owns the drag / drop
icon editor used by the configuration window.  The legacy
:class:`IconGrid` widget mixes the icon data, the drag state, the
selection state and the QWidget painting in a single 2500+ LOC
class.  The :class:`IconGridViewModel` is the first step of the
P1-06 split: it owns the *data* (icons + selection + drag payload)
and exposes it through :pyattr:`pyqtSignal` members so the view
layer can sync without ever touching the storage directly.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from core.data_models import ShortcutItem
from qt_compat import pyqtSignal
from ui.view_models.base import ListViewModel
from ui.view_models.observable import ObservableList

logger = logging.getLogger(__name__)


def _icon_sort_key(item: dict[str, Any]) -> tuple:
    """Stable sort key for the icon grid.

    Mirrors the legacy :py:meth:`IconGrid._resort_icons` heuristic:
    folders first, then shortcuts with a user-supplied order, then
    by ``name`` for stability.
    """

    if not isinstance(item, dict):
        return (3, "", 0)
    if item.get("type") == "folder":
        return (0, str(item.get("name") or "").lower(), 0)
    order = item.get("order", 0)
    try:
        order_value = int(order)
    except (TypeError, ValueError):
        order_value = 0
    return (1, str(item.get("name") or "").lower(), order_value)


class IconGridViewModel(ListViewModel):
    """Business state for the icon-grid editor.

    The view-model holds the canonical icon list (an
    :class:`ObservableList` so the view can react to mutations),
    the current selection, and the drag payload.  It does not own
    any QWidget state.
    """

    #: Emitted when the selection changes.  The payload is the
    #: sorted list of currently selected ``item_id`` strings.
    selection_changed = pyqtSignal(object)

    #: Emitted when a drag-and-drop operation starts.  The payload
    #: is a list of dragged item ids.
    drag_started = pyqtSignal(object)

    #: Emitted when the drag operation ends (success or cancel).
    drag_ended = pyqtSignal()

    #: Emitted when the items list is re-sorted.
    sort_changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: ObservableList = ObservableList()
        self._items.changed.connect(self._on_items_changed)
        self._selection: list[str] = []
        self._drag_payload: list[str] = []
        self._search_query: str = ""

    # ── item accessors ────────────────────────────────────────────────

    def get_items(self) -> list:
        """Return a snapshot of the current items list."""
        return list(self._items)

    def set_items(self, items: Iterable[dict]) -> None:
        self._items.clear()
        for item in items:
            if not isinstance(item, dict):
                # Skip garbage so the view-model never has to
                # forward non-mapping payloads to the view layer.
                continue
            self._items.append(dict(item))
        self._selection = []
        self.selection_changed.emit(list(self._selection))

    def append_item(self, item: dict) -> None:
        self._items.append(dict(item))
        self._notify_item_inserted(len(self._items) - 1)

    def remove_item(self, item_id: str) -> bool:
        for index, item in enumerate(list(self._items)):
            if str(item.get("id") or "") == str(item_id):
                del self._items[index]
                self._selection = [s for s in self._selection if s != str(item_id)]
                if self._drag_payload:
                    self._drag_payload = [p for p in self._drag_payload if p != str(item_id)]
                self._notify_item_removed(index)
                self.selection_changed.emit(list(self._selection))
                return True
        return False

    def update_item(self, item_id: str, **changes: Any) -> bool:
        for index, item in enumerate(list(self._items)):
            if str(item.get("id") or "") == str(item_id):
                item.update(changes)
                self._notify_item_updated(index)
                return True
        return False

    def find_item(self, item_id: str) -> dict | None:
        for item in self._items:
            if str(item.get("id") or "") == str(item_id):
                return item  # type: ignore[no-any-return]
        return None

    def item_count(self) -> int:
        return len(self._items)

    # ── selection ─────────────────────────────────────────────────────

    def get_selection(self) -> list[str]:
        return list(self._selection)

    def set_selection(self, item_ids: Iterable[str]) -> None:
        self._selection = [str(i) for i in item_ids]
        self.selection_changed.emit(list(self._selection))

    def add_to_selection(self, item_id: str) -> None:
        item_id = str(item_id)
        if item_id in self._selection:
            return
        self._selection.append(item_id)
        self.selection_changed.emit(list(self._selection))

    def remove_from_selection(self, item_id: str) -> None:
        item_id = str(item_id)
        if item_id not in self._selection:
            return
        self._selection = [s for s in self._selection if s != item_id]
        self.selection_changed.emit(list(self._selection))

    def clear_selection(self) -> None:
        if not self._selection:
            return
        self._selection = []
        self.selection_changed.emit(list(self._selection))

    def is_selected(self, item_id: str) -> bool:
        return str(item_id) in self._selection

    # ── drag-and-drop ─────────────────────────────────────────────────

    def begin_drag(self, item_ids: Iterable[str]) -> None:
        self._drag_payload = [str(i) for i in item_ids]
        self.drag_started.emit(list(self._drag_payload))

    def end_drag(self) -> None:
        if not self._drag_payload:
            return
        self._drag_payload = []
        self.drag_ended.emit()

    def get_drag_payload(self) -> list[str]:
        return list(self._drag_payload)

    def move_items(self, item_ids: Iterable[str], target_index: int) -> int:
        """Move ``item_ids`` to ``target_index`` while preserving order.

        Returns the number of items that were actually moved.
        """
        ids = [str(i) for i in item_ids]
        if not ids:
            return 0
        current = list(self._items)
        id_to_item = {str(item.get("id") or ""): item for item in current}
        moving = [id_to_item[i] for i in ids if i in id_to_item]
        if not moving:
            return 0
        remaining = [item for item in current if str(item.get("id") or "") not in ids]
        # Clamp target_index into the remaining list bounds.
        if target_index < 0:
            target_index = 0
        if target_index > len(remaining):
            target_index = len(remaining)
        new_items = remaining[:target_index] + moving + remaining[target_index:]
        self._items.clear()
        for item in new_items:
            self._items.append(item)
        self._notify_items_reset()
        return len(moving)

    # ── search ────────────────────────────────────────────────────────

    def set_search_query(self, query: str) -> None:
        query = str(query or "")
        if query == self._search_query:
            return
        self._search_query = query
        self.emit_state({"search_query": query})

    def get_search_query(self) -> str:
        return self._search_query

    def filter_items(self, query: str | None = None) -> list:
        if query is None:
            query = self._search_query
        query = str(query or "").strip().lower()
        if not query:
            return list(self._items)
        return [
            item
            for item in self._items
            if query in str(item.get("name") or "").lower()
            or query in str(item.get("id") or "").lower()
            or query in str(item.get("type") or "").lower()
        ]

    # ── sort ──────────────────────────────────────────────────────────

    def sort_items(self, key: Any | None = None) -> None:
        items = sorted(self._items, key=key or _icon_sort_key)
        self._items.clear()
        for item in items:
            self._items.append(item)
        self._notify_items_reset()
        self.sort_changed.emit()

    # ── shortcut helpers ──────────────────────────────────────────────

    def shortcuts_in(self) -> list[ShortcutItem]:
        """Return the current items as :class:`ShortcutItem` instances.

        Used by callers that need the icon grid to talk to the
        :class:`ShortcutService` without poking into the data
        manager.  Items that cannot be parsed as shortcuts are
        skipped.
        """
        result: list[ShortcutItem] = []
        for item in self._items:
            shortcut = self._to_shortcut(item)
            if shortcut is not None:
                result.append(shortcut)
        return result

    @staticmethod
    def _to_shortcut(item: dict) -> ShortcutItem | None:
        if not isinstance(item, dict):
            return None
        try:
            return ShortcutItem(
                id=str(item.get("id") or ""),
                name=str(item.get("name") or ""),
                type=item.get("type", "shortcut"),
                command=str(item.get("command") or ""),
                command_type=str(item.get("command_type") or "cmd"),
                icon_path=str(item.get("icon_path") or ""),
                order=int(item.get("order", 0) or 0),
            )
        except Exception:  # noqa: BLE001 - defensive
            logger.debug("Could not convert grid item to ShortcutItem: %r", item, exc_info=True)
            return None

    # ── lifecycle ─────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Release any background resources."""
        self._items.clear()
        self._selection = []
        self._drag_payload = []
        super().shutdown()

    def _on_items_changed(self, payload: dict | None = None) -> None:
        """Bridge the :class:`ObservableList.changed` signal.

        Re-emits the granular :pyattr:`item_inserted`,
        :pyattr:`item_removed` and :pyattr:`item_updated` events
        and the bulk :pyattr:`items_changed` notification.  Callers
        that subscribed to the view-model don't need to know about
        the underlying observable.
        """
        if not isinstance(payload, dict):
            self.items_changed.emit()
            self.emit_state({"items_dirty": True})
            return
        op = payload.get("op")
        if op == "add":
            self.item_inserted.emit(int(payload.get("index", -1)))
        elif op == "remove":
            self.item_removed.emit(int(payload.get("index", -1)))
        elif op == "update":
            self.item_updated.emit(int(payload.get("index", -1)))
        # Always notify bulk subscribers as well.
        self.items_changed.emit()
        self.emit_state({"items_dirty": True})


__all__ = ["IconGridViewModel"]
