"""Pure conversions between persisted chain steps and editor canvas data."""

from __future__ import annotations

import uuid
from typing import Any

from core.chain_processors import DEFAULT_PYTHON_CELL_SOURCE, processor_title, python_cell_metadata
from core.data_models import ShortcutItem, normalize_chain_step_delay_ms
from extensions.action_chain.contracts import binding_key


def canvas_from_steps(steps: list[dict], shortcuts: dict[str, ShortcutItem]) -> dict:
    canvas = ShortcutItem._chain_canvas_from_steps(steps)
    real_ids = {node["id"] for node in canvas.get("nodes", [])}
    for node in canvas.get("nodes", []):
        if node.get("node_type") == "processor":
            if str(node.get("processor_id") or "") == "python_cell":
                node["title"] = python_cell_metadata(str(node.get("source") or DEFAULT_PYTHON_CELL_SOURCE))["title"]
            else:
                node["title"] = processor_title(str(node.get("processor_id") or ""))
        else:
            shortcut = shortcuts.get(str(node.get("shortcut_id") or ""))
            node["title"] = getattr(shortcut, "name", "") or str(node.get("shortcut_id") or "")
    canvas["connections"] = [
        connection
        for connection in canvas.get("connections", [])
        if connection.get("source_node") in real_ids and connection.get("target_node") in real_ids
    ]
    return canvas


def compile_canvas_to_steps(canvas: dict) -> list[dict]:
    nodes = sorted(canvas.get("nodes") or [], key=lambda n: (int(n.get("order", 0) or 0), float(n.get("x", 0) or 0)))
    index_by_node = {str(node.get("id")): index for index, node in enumerate(nodes, start=1)}
    incoming: dict[str, list[dict]] = {}
    for connection in list(canvas.get("connections") or []):
        incoming.setdefault(str(connection.get("target_node") or ""), []).append(connection)

    steps = []
    for index, node in enumerate(nodes, start=1):
        node_id = str(node.get("id") or uuid.uuid4())
        node_type = str(node.get("node_type") or "shortcut")
        step: dict[str, Any] = {
            "id": node_id,
            "node_type": node_type,
            "enabled": bool(node.get("enabled", True)),
            "stop_on_error": bool(node.get("stop_on_error", True)),
            "delay_ms": normalize_chain_step_delay_ms(node.get("delay_ms", 0)),
            "input_binding": "",
            "param_bindings": {},
            "args": {str(k): str(v) for k, v in dict(node.get("args") or {}).items() if str(k).strip()},
        }
        if node_type == "processor":
            step["processor_id"] = str(node.get("processor_id") or "")
            step["shortcut_id"] = ""
            step["source"] = str(node.get("source") or "")
        else:
            step["shortcut_id"] = str(node.get("shortcut_id") or "")
            step["processor_id"] = ""
            step["source"] = ""
        for connection in incoming.get(node_id, []):
            source_index = index_by_node.get(str(connection.get("source_node") or ""))
            source_port = str(connection.get("source_port") or "").strip()
            target_port = str(connection.get("target_port") or "").strip()
            if not source_index or not source_port or not target_port or source_index >= index:
                continue
            binding = binding_key(source_index, source_port)
            if target_port == "input":
                step["input_binding"] = append_binding(step.get("input_binding"), binding)
            else:
                param_bindings = step["param_bindings"]
                args = step["args"]
                assert isinstance(param_bindings, dict)
                assert isinstance(args, dict)
                param_bindings[target_port] = append_binding(param_bindings.get(target_port), binding)
                args.pop(target_port, None)
        step["order"] = index
        steps.append(step)
    return ShortcutItem._normalize_chain_steps(steps)


def append_binding(existing, binding: str):
    if not existing:
        return binding
    if isinstance(existing, list):
        return existing + [binding]
    return [str(existing), binding]
