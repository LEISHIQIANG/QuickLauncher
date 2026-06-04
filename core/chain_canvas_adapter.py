"""Canvas-to-steps adapter for action-chain runtime entrypoints."""

from __future__ import annotations

import copy
import logging
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)


def chain_data_field(chain_data: Any, name: str, default: Any = None) -> Any:
    if isinstance(chain_data, dict):
        return chain_data.get(name, default)
    return getattr(chain_data, name, default)


def validation_steps(chain_data: Any, canvas: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    canonical = canonical_canvas(canvas if canvas is not None else chain_data_field(chain_data, "chain_canvas", {}) or {})
    if canonical.get("nodes"):
        try:
            from core.chain.graph_executor import LegacyAdapter
            from core.chain.graph_models import ChainGraph

            graph = ChainGraph.from_canvas_dict(canonical)
            return LegacyAdapter.graph_to_steps(graph)
        except Exception:
            logger.debug("Failed to derive action-chain steps from canvas", exc_info=True)
    return list(chain_data_field(chain_data, "chain_steps", []) or [])


def runtime_chain_data(chain_data: Any) -> Any:
    canonical = canonical_canvas(chain_data_field(chain_data, "chain_canvas", {}) or {})
    if not canonical.get("nodes"):
        return chain_data
    steps = validation_steps(chain_data, canonical)
    if not steps:
        return chain_data
    if isinstance(chain_data, dict):
        data = dict(chain_data)
        data["chain_steps"] = steps
        data["chain_canvas"] = canonical
        return SimpleNamespace(**data)
    runtime_chain = copy.copy(chain_data)
    try:
        runtime_chain.chain_steps = steps
        runtime_chain.chain_canvas = canonical
    except Exception:
        return chain_data
    return runtime_chain


def runtime_steps(chain_data: Any) -> list[dict[str, Any]]:
    return list(chain_data_field(runtime_chain_data(chain_data), "chain_steps", []) or [])


def canonical_canvas(canvas: Any) -> dict[str, Any]:
    if not isinstance(canvas, dict):
        return {}
    nodes = []
    for index, raw in enumerate(list(canvas.get("nodes") or []), start=1):
        if not isinstance(raw, dict):
            continue
        node_type = str(raw.get("node_type") or "").strip().lower()
        processor_id = str(raw.get("processor_id") or raw.get("type") or "").strip()
        shortcut_id = str(raw.get("shortcut_id") or "").strip()
        if node_type not in {"shortcut", "processor"}:
            node_type = "shortcut" if shortcut_id and not processor_id else "processor"
        order = _safe_int(raw.get("order"), index)
        x = _safe_float(raw.get("x"), float((index - 1) * 240))
        y = _safe_float(raw.get("y"), 80.0)
        args = raw.get("args", raw.get("params", {}))
        if not isinstance(args, dict):
            args = {}
        nodes.append(
            {
                "id": str(raw.get("id") or f"node-{index}"),
                "node_type": node_type,
                "shortcut_id": shortcut_id,
                "processor_id": "" if node_type == "shortcut" else processor_id,
                "source": str(raw.get("source") or ""),
                "title": str(raw.get("title") or ""),
                "x": x,
                "y": y,
                "order": max(1, order),
                "enabled": bool(raw.get("enabled", True)),
                "stop_on_error": bool(raw.get("stop_on_error", True)),
                "delay_ms": _safe_int(raw.get("delay_ms"), 0),
                "args": {str(k).strip(): str(v) for k, v in args.items() if str(k).strip()},
            }
        )
    nodes.sort(key=lambda item: (int(item.get("order", 0) or 0), float(item.get("x", 0) or 0)))

    connections = []
    for raw in list(canvas.get("connections") or []):
        if not isinstance(raw, dict):
            continue
        connections.append(
            {
                "id": str(raw.get("id") or ""),
                "source_node": str(raw.get("source_node") or raw.get("source_node_id") or raw.get("source") or "").strip(),
                "source_port": str(raw.get("source_port") or raw.get("source_port_id") or raw.get("sourcePort") or "").strip(),
                "target_node": str(raw.get("target_node") or raw.get("target_node_id") or raw.get("target") or "").strip(),
                "target_port": str(raw.get("target_port") or raw.get("target_port_id") or raw.get("targetPort") or "").strip(),
            }
        )
    return {"version": 1, "nodes": nodes, "connections": connections}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
