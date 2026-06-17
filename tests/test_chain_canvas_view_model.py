"""Tests for the P1-06 Stage 2 :class:`ChainCanvasViewModel`."""

from __future__ import annotations

import pytest

from core.data_models import ShortcutItem
from ui.view_models.chain_canvas_view_model import (
    ChainCanvasViewModel,
    canvas_from_steps,
    compile_canvas_to_steps,
    empty_canvas,
)

pytestmark = pytest.mark.ui


def _shortcut(sid: str, name: str = "") -> ShortcutItem:
    return ShortcutItem(id=sid, name=name or sid, command="echo hi", command_type="cmd")


def test_default_state_is_empty():
    vm = ChainCanvasViewModel()
    assert vm.get_canvas() == empty_canvas()
    assert vm.get_selection() == []
    assert vm.can_undo() is False
    assert vm.can_redo() is False
    assert vm.get_run_status() == ""


def test_add_shortcut_node_emits_canvas_changed_and_selects():
    vm = ChainCanvasViewModel()
    events = []
    vm.canvas_changed.connect(lambda: events.append("canvas"))
    vm.selection_changed.connect(lambda sel: events.append(("selection", sel)))

    node_id = vm.add_shortcut_node(_shortcut("alpha"), x=12, y=34)

    assert node_id
    assert len(vm.get_canvas()["nodes"]) == 1
    assert vm.get_canvas()["nodes"][0]["shortcut_id"] == "alpha"
    assert vm.get_canvas()["nodes"][0]["x"] == 12
    assert events[0] == "canvas"
    # ``selection_changed`` mirrors the legacy ``ChainCanvasWidget``
    # signal — it emits the first selected node id (str) only.
    assert events[1] == ("selection", node_id)


def test_add_processor_node_uses_default_title():
    vm = ChainCanvasViewModel()
    node_id = vm.add_processor_node("text_trim", x=5, y=6)
    node = next(n for n in vm.get_canvas()["nodes"] if n["id"] == node_id)
    assert node["node_type"] == "processor"
    assert node["processor_id"] == "text_trim"
    # title is populated from the processor registry (not empty)
    assert node["title"]


def test_add_python_cell_uses_source():
    vm = ChainCanvasViewModel()
    node_id = vm.add_processor_node(
        "python_cell",
        source="print('hi')",
    )
    node = next(n for n in vm.get_canvas()["nodes"] if n["id"] == node_id)
    assert node["source"] == "print('hi')"


def test_remove_nodes_drops_nodes_and_connections():
    vm = ChainCanvasViewModel()
    a = vm.add_shortcut_node(_shortcut("a"))
    b = vm.add_shortcut_node(_shortcut("b"))
    c = vm.add_shortcut_node(_shortcut("c"))
    # Manually inject a connection so we can verify cascade-removal.
    vm._canvas["connections"].append(
        {
            "source_node": a,
            "source_port": "output",
            "target_node": c,
            "target_port": "input",
        }
    )
    removed = vm.remove_nodes([a, b])
    assert removed == 2
    remaining = {n["id"] for n in vm.get_canvas()["nodes"]}
    assert remaining == {c}
    assert vm.get_canvas()["connections"] == []


def test_remove_unknown_nodes_is_noop():
    vm = ChainCanvasViewModel()
    vm.add_shortcut_node(_shortcut("a"))
    before = vm.get_canvas()
    removed = vm.remove_nodes(["nonexistent"])
    assert removed == 0
    # The empty-undo-stack guard pops the dummy history we just pushed.
    assert before == vm.get_canvas()


def test_undo_redo_round_trip():
    vm = ChainCanvasViewModel()
    vm.add_shortcut_node(_shortcut("a"))
    assert vm.can_undo() is True
    assert vm.can_redo() is False

    assert vm.undo() is True
    assert vm.get_canvas()["nodes"] == []
    assert vm.can_redo() is True

    assert vm.redo() is True
    assert vm.get_canvas()["nodes"][0]["shortcut_id"] == "a"


def test_set_canvas_resets_history_and_selection():
    vm = ChainCanvasViewModel()
    vm.add_shortcut_node(_shortcut("a"))
    vm.set_canvas(empty_canvas())
    assert vm.get_canvas() == empty_canvas()
    assert vm.get_selection() == []
    assert vm.can_undo() is False
    assert vm.can_redo() is False


def test_set_run_status_emits_change_only_once():
    vm = ChainCanvasViewModel()
    seen = []
    vm.run_status_changed.connect(lambda s: seen.append(s))
    vm.set_run_status("Running")
    vm.set_run_status("Running")
    vm.set_run_status("Done")
    assert seen == ["Running", "Done"]


def test_compile_canvas_to_steps_round_trip():
    steps = [
        {
            "id": "step_1",
            "name": "Echo",
            "node_type": "shortcut",
            "shortcut_id": "a",
            "enabled": True,
            "delay_ms": 0,
            "input_binding": "",
            "param_bindings": {},
            "args": {},
            "processor_id": "",
            "source": "",
            "stop_on_error": True,
            "order": 1,
        },
        {
            "id": "step_2",
            "name": "Trim",
            "node_type": "processor",
            "processor_id": "text_trim",
            "params": {"chars": " "},
            "enabled": True,
            "delay_ms": 0,
            "input_binding": "",
            "param_bindings": {},
            "args": {},
            "shortcut_id": "",
            "source": "",
            "stop_on_error": True,
            "order": 2,
        },
    ]
    canvas = canvas_from_steps(steps, {"a": _shortcut("a", "Echo")})
    new_steps = compile_canvas_to_steps(canvas)
    assert [s["node_type"] for s in new_steps] == ["shortcut", "processor"]
    assert new_steps[0]["shortcut_id"] == "a"
    assert new_steps[1]["processor_id"] == "text_trim"


def test_connect_and_remove_connection():
    vm = ChainCanvasViewModel()
    sa = _shortcut("a")
    sb = _shortcut("b")
    a = vm.add_shortcut_node(sa)
    b = vm.add_shortcut_node(sb)
    # Register the shortcut map so the canvas validator can resolve
    # port specs.  Without this the view-model falls back to a
    # permissive programmatic-connect path.
    vm.set_shortcuts({"a": sa, "b": sb})
    # The canvas validator requires source.order < target.order; set
    # the orders directly on the view-model state.
    nodes = vm._canvas["nodes"]  # noqa: SLF001 - test hook
    nodes[0]["order"] = 1
    nodes[1]["order"] = 2
    key = vm.connect_ports(a, "output", b, "input")
    assert key is not None
    assert len(vm.get_canvas()["connections"]) == 1

    assert vm.remove_connection(a, "output", b, "input") is True
    assert vm.get_canvas()["connections"] == []


def test_selected_node_returns_first():
    vm = ChainCanvasViewModel()
    a = vm.add_shortcut_node(_shortcut("a"))
    node = vm.selected_node()
    assert node is not None
    assert node["id"] == a


def test_history_limit_caps_stack():
    vm = ChainCanvasViewModel()
    # Override the limit for the test.
    vm._history_limit = 3
    for i in range(5):
        vm.add_shortcut_node(_shortcut(f"node-{i}"))
    # After 5 mutations with limit 3 we should still be able to undo
    # 3 times.  The 4th undo must be a no-op.
    assert vm.undo() is True
    assert vm.undo() is True
    assert vm.undo() is True
    assert vm.undo() is False
