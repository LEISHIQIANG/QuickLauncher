"""View-model layer for the P1-06 chain-canvas refactor.

The legacy :mod:`ui.config_window.chain_canvas` file mixes graph
state, undo / redo history, node / port creation logic and a
:class:`QGraphicsView` widget in a single 2500+ LOC module.  The
:class:`ChainCanvasViewModel` is the first step of the P1-06 split:
it owns the *graph* (nodes + connections) and the *undo / redo*
state, exposing them through :pyattr:`pyqtSignal` members so the
view layer can sync without ever touching the storage directly.

The class is deliberately small and contains no QGraphics code.
It is meant to be the foundation on which future PRs add node /
port / connection APIs (Stage 2 of the P1-06 plan).
"""

from __future__ import annotations

import copy
import logging
import uuid
from collections.abc import Iterable
from typing import Any

from core.chain_contracts import validate_canvas_connection
from core.chain_processors import processor_title
from core.data_models import ShortcutItem
from qt_compat import pyqtSignal
from ui.view_models.base import ListViewModel

logger = logging.getLogger(__name__)


def _new_node_id() -> str:
    return uuid.uuid4().hex


def _clone_canvas(canvas: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(canvas)


def canvas_from_steps(steps: list[dict], shortcuts: dict[str, ShortcutItem]) -> dict[str, Any]:
    """Reconstruct a canvas dict from a list of chain steps.

    This is a thin re-export of the historical implementation that
    lived in :mod:`ui.config_window.chain_canvas`.  The view-model
    uses it to bootstrap an in-memory canvas from the persisted
    step list.
    """
    from ui.config_window.chain_canvas import canvas_from_steps as _impl

    return _impl(steps, shortcuts)


def compile_canvas_to_steps(canvas: dict[str, Any]) -> list[dict[str, Any]]:
    """Serialise a canvas dict into a list of chain steps.

    Delegates to the historical implementation in
    :mod:`ui.config_window.chain_canvas` so the on-disk format
    stays byte-identical.
    """
    from ui.config_window.chain_canvas import compile_canvas_to_steps as _impl

    return _impl(canvas)


def empty_canvas() -> dict[str, Any]:
    """Return a fresh, empty canvas payload."""
    return {"nodes": [], "connections": []}


class ChainCanvasViewModel(ListViewModel):
    """Business state for the chain canvas editor.

    The view-model holds the canonical :pyattr:`canvas` payload, the
    :pyattr:`selection`, and the undo / redo history.  It emits
    :pyattr:`canvas_changed`, :pyattr:`selection_changed` and
    :pyattr:`run_status_changed` signals.  The QGraphicsView
    subscribes to those signals and re-renders the relevant items.
    """

    #: The whole canvas was replaced (load / reset).
    canvas_replaced = pyqtSignal()

    #: Nodes / connections were added, removed or re-ordered.
    canvas_changed = pyqtSignal()

    #: The current node selection changed.  The signal payload is
    #: the first selected node id (string) — matches the legacy
    #: :pyattr:`ChainCanvasWidget.selection_changed` so the existing
    #: signal connections in :mod:`ui.config_window.chain_dialog`
    #: keep working.
    selection_changed = pyqtSignal(str)

    #: The undo / redo history state changed.
    undo_state_changed = pyqtSignal()

    #: The "running" status text changed (e.g. "Running…", "Done").
    run_status_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._canvas: dict[str, Any] = empty_canvas()
        self._selection: list[str] = []
        self._undo_stack: list[dict[str, Any]] = []
        self._redo_stack: list[dict[str, Any]] = []
        self._run_status: str = ""
        self._shortcuts: dict[str, ShortcutItem] = {}
        self._history_limit: int = 100

    # ── shortcuts binding ────────────────────────────────────────────

    def set_shortcuts(self, shortcuts: dict[str, ShortcutItem]) -> None:
        """Update the shortcut map used for port-spec validation."""
        self._shortcuts = dict(shortcuts or {})

    def get_shortcuts(self) -> dict[str, ShortcutItem]:
        return dict(self._shortcuts)

    # ── canvas accessors ─────────────────────────────────────────────

    def get_canvas(self) -> dict[str, Any]:
        return self._canvas

    def set_canvas(self, canvas: dict[str, Any]) -> None:
        self._canvas = _clone_canvas(canvas)
        self._selection = []
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.canvas_replaced.emit()
        self.emit_state({"canvas_reset": True})
        self._notify_items_reset()

    # ── selection ─────────────────────────────────────────────────────

    def get_selection(self) -> list[str]:
        return list(self._selection)

    def set_selection(self, node_ids: Iterable[str]) -> None:
        self._selection = list(node_ids)
        # Emit a single-string payload to stay compatible with the
        # legacy ``selection_changed(str)`` signal that the rest of
        # the chain dialog connects to.
        first = self._selection[0] if self._selection else ""
        self.selection_changed.emit(first)
        self.emit_state({"selection": list(self._selection)})

    # ── node operations ──────────────────────────────────────────────

    def add_shortcut_node(self, shortcut: ShortcutItem, *, x: float = 0.0, y: float = 0.0) -> str:
        node_id = _new_node_id()
        node = {
            "id": node_id,
            "node_type": "shortcut",
            "shortcut_id": getattr(shortcut, "id", ""),
            "title": getattr(shortcut, "name", ""),
            "x": float(x),
            "y": float(y),
            "enabled": True,
        }
        self._push_history()
        self._canvas.setdefault("nodes", []).append(node)
        self.canvas_changed.emit()
        self.set_selection([node_id])
        self.emit_state({"node_added": node_id})
        self._notify_item_inserted(len(self._canvas["nodes"]) - 1)
        return node_id

    def add_processor_node(
        self,
        processor_id: str,
        *,
        title: str = "",
        params: dict[str, Any] | None = None,
        x: float = 0.0,
        y: float = 0.0,
        source: str | None = None,
    ) -> str:
        node_id = _new_node_id()
        node = {
            "id": node_id,
            "node_type": "processor",
            "processor_id": processor_id,
            "title": title or processor_title(processor_id),
            "x": float(x),
            "y": float(y),
            "params": dict(params or {}),
            "enabled": True,
        }
        if processor_id == "python_cell" and source is not None:
            node["source"] = source
        self._push_history()
        self._canvas.setdefault("nodes", []).append(node)
        self.canvas_changed.emit()
        self.set_selection([node_id])
        self.emit_state({"node_added": node_id})
        self._notify_item_inserted(len(self._canvas["nodes"]) - 1)
        return node_id

    def remove_nodes(self, node_ids: Iterable[str]) -> int:
        ids = {str(i) for i in node_ids}
        if not ids:
            return 0
        nodes = self._canvas.get("nodes", [])
        new_nodes = [n for n in nodes if str(n.get("id")) not in ids]
        new_conns = [
            c
            for c in self._canvas.get("connections", [])
            if str(c.get("source_node")) not in ids and str(c.get("target_node")) not in ids
        ]
        removed_count = len(nodes) - len(new_nodes)
        if removed_count <= 0:
            return 0
        # Only push history *after* we know something was actually
        # removed so the undo stack stays clean.
        self._push_history()
        self._canvas["nodes"] = new_nodes
        self._canvas["connections"] = new_conns
        self._selection = [s for s in self._selection if s not in ids]
        self.canvas_changed.emit()
        self.emit_state({"nodes_removed": sorted(ids)})
        self._notify_items_reset()
        return removed_count

    def selected_node(self) -> dict[str, Any] | None:
        if not self._selection:
            return None
        target = self._selection[0]
        for node in self._canvas.get("nodes", []):
            if str(node.get("id")) == target:
                return node  # type: ignore[no-any-return]
        return None

    # ── connection operations ────────────────────────────────────────

    def connect_ports(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
    ) -> str | None:
        # The :func:`validate_canvas_connection` helper requires the
        # full node list *and* the shortcut map.  When no shortcut
        # map has been registered with :func:`set_shortcuts` we skip
        # the port-spec validation and accept the call as long as
        # both endpoints exist — the legacy widget was permissive
        # about programmatic connections.
        nodes = {
            str(node.get("id") or ""): node for node in list(self._canvas.get("nodes") or []) if isinstance(node, dict)
        }
        if source_node not in nodes or target_node not in nodes:
            return None
        if self._shortcuts:
            issue = validate_canvas_connection(
                self._canvas,
                self._shortcuts,
                source_node,
                source_port,
                target_node,
                target_port,
            )
            if issue is not None and issue is not False:
                return None
        connection = {
            "source_node": source_node,
            "source_port": source_port,
            "target_node": target_node,
            "target_port": target_port,
        }
        self._push_history()
        self._canvas.setdefault("connections", []).append(connection)
        self.canvas_changed.emit()
        self.emit_state({"connection_added": connection})
        return f"{source_node}.{source_port}->{target_node}.{target_port}"

    def remove_connection(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
    ) -> bool:
        conns = self._canvas.get("connections", [])
        for index, conn in enumerate(list(conns)):
            if (
                str(conn.get("source_node")) == source_node
                and str(conn.get("source_port")) == source_port
                and str(conn.get("target_node")) == target_node
                and str(conn.get("target_port")) == target_port
            ):
                self._push_history()
                del conns[index]
                self._canvas["connections"] = conns
                self.canvas_changed.emit()
                self.emit_state({"connection_removed": (source_node, source_port, target_node, target_port)})
                return True
        return False

    # ── run status ────────────────────────────────────────────────────

    def set_run_status(self, status: str) -> None:
        if status == self._run_status:
            return
        self._run_status = str(status or "")
        self.run_status_changed.emit(self._run_status)
        self.emit_state({"run_status": self._run_status})

    def get_run_status(self) -> str:
        return self._run_status

    # ── undo / redo ───────────────────────────────────────────────────

    def _push_history(self) -> None:
        self._undo_stack.append(_clone_canvas(self._canvas))
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self.undo_state_changed.emit()
        self.emit_state({"history": True})

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(_clone_canvas(self._canvas))
        self._canvas = self._undo_stack.pop()
        self.canvas_changed.emit()
        self._notify_items_reset()
        self.undo_state_changed.emit()
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(_clone_canvas(self._canvas))
        self._canvas = self._redo_stack.pop()
        self.canvas_changed.emit()
        self._notify_items_reset()
        self.undo_state_changed.emit()
        return True

    # ── finalisation ─────────────────────────────────────────────────

    def to_steps(self) -> list[dict[str, Any]]:
        return compile_canvas_to_steps(self._canvas)


__all__ = [
    "ChainCanvasViewModel",
    "canvas_from_steps",
    "compile_canvas_to_steps",
    "empty_canvas",
]
