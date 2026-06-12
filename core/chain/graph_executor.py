"""Graph executor adapter for integrating new graph runtime with existing system.

This module provides adapters and utilities to:
- Convert between legacy chain format and new graph format
- Execute graphs using the new runtime engine
- Maintain backward compatibility with existing chain_steps format
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from .graph_models import (
    ChainConnection,
    ChainGraph,
    ChainNode,
    ChainPort,
    PortDirection,
)
from .graph_runtime import (
    ExecutionResult,
    GraphExecutionContext,
    GraphRuntime,
    NodeExecutionResult,
)
from .processor_registry import get_registry

__all__ = [
    "GraphExecutor",
    "LegacyAdapter",
    "execute_chain_graph",
    "convert_steps_to_graph",
    "convert_graph_to_steps",
]

logger = logging.getLogger(__name__)


class LegacyAdapter:
    """Adapter for converting between legacy chain format and new graph format."""

    @staticmethod
    def steps_to_graph(
        steps: list[dict[str, Any]], canvas: dict[str, Any] | None = None, shortcut_map: dict[str, Any] | None = None
    ) -> ChainGraph:
        """Convert legacy chain_steps to ChainGraph.

        Args:
            steps: List of step dictionaries from chain_steps
            canvas: Optional canvas data with positions
            shortcut_map: Optional map of shortcut IDs to shortcut objects

        Returns:
            ChainGraph instance
        """
        graph = ChainGraph()

        # Create nodes from steps
        for index, step in enumerate(steps):
            node_id = str(step.get("id") or f"step-{index+1}")
            node_type = str(step.get("node_type") or "shortcut").strip().lower()

            if node_type == "processor":
                processor_id = str(step.get("processor_id") or "")
                node = LegacyAdapter._create_processor_node(node_id, processor_id, step, index)
            else:
                # Shortcut node
                shortcut_id = str(step.get("shortcut_id") or "")
                node = LegacyAdapter._create_shortcut_node(node_id, shortcut_id, step, index, shortcut_map)

            # Get position from canvas if available
            if canvas:
                LegacyAdapter._apply_canvas_position(node, canvas, node_id)

            graph.add_node(node)

        # Create connections from param_bindings
        for index, step in enumerate(steps):
            target_node_id = str(step.get("id") or f"step-{index+1}")
            input_binding = step.get("input_binding", "")
            for binding in _binding_items(input_binding):
                source_index, source_port = _parse_legacy_binding(binding, index + 1)
                if source_index is not None and 1 <= source_index <= len(steps):
                    source_step = steps[source_index - 1]
                    source_node_id = str(source_step.get("id") or f"step-{source_index}")
                    connection = ChainConnection(
                        id=f"conn-{source_node_id}.{source_port}-{target_node_id}.input",
                        source_node_id=source_node_id,
                        source_port_id=source_port,
                        target_node_id=target_node_id,
                        target_port_id="input",
                    )
                    try:
                        graph.add_connection(connection)
                    except ValueError as exc:
                        logger.debug("跳过无效的旧版链路连接: %s", exc, exc_info=True)

            bindings = step.get("param_bindings") or {}

            for port_id, binding in bindings.items():
                for binding_item in _binding_items(binding):
                    source_index, source_port = _parse_legacy_binding(binding_item, index + 1)
                    if source_index is None or not (1 <= source_index <= len(steps)):
                        continue
                    source_step = steps[source_index - 1]
                    source_node_id = str(source_step.get("id") or f"step-{source_index}")

                    connection = ChainConnection(
                        id=f"conn-{source_node_id}.{source_port}-{target_node_id}.{port_id}",
                        source_node_id=source_node_id,
                        source_port_id=source_port,
                        target_node_id=target_node_id,
                        target_port_id=port_id,
                    )

                    try:
                        graph.add_connection(connection)
                    except ValueError as exc:
                        logger.debug("跳过无效的旧版参数绑定连接: %s", exc, exc_info=True)

        return graph

    @staticmethod
    def _create_processor_node(node_id: str, processor_id: str, step: dict, index: int) -> ChainNode:
        """Create a processor node from step data."""
        registry = get_registry()
        definition = registry.get_definition(processor_id)

        if definition:
            node = ChainNode.from_definition(definition, node_id)
        else:
            node = ChainNode(
                id=node_id,
                processor_id=processor_id,
                title=str(step.get("title") or processor_id),
            )

        # Apply step settings
        node.enabled = bool(step.get("enabled", True))
        node.params = dict(step.get("params") or {})
        node.params.update(dict(step.get("args") or {}))
        node.params["stop_on_error"] = bool(step.get("stop_on_error", True))
        node.params["delay_ms"] = int(step.get("delay_ms") or 0)
        if step.get("source"):
            node.params["source"] = str(step.get("source") or "")

        return node

    @staticmethod
    def _create_shortcut_node(
        node_id: str, shortcut_id: str, step: dict, index: int, shortcut_map: dict[str, Any] | None
    ) -> ChainNode:
        """Create a shortcut node from step data."""
        shortcut = (shortcut_map or {}).get(shortcut_id)

        node = ChainNode(
            id=node_id,
            processor_id="shortcut",
            title=str(getattr(shortcut, "name", "") or step.get("title") or f"快捷方式 {index}"),
            category="快捷方式",
        )

        # Add standard ports
        node.inputs.append(
            ChainPort(
                id="input",
                label="输入",
                direction=PortDirection.INPUT,
                kind="any",
            )
        )
        node.outputs.append(
            ChainPort(
                id="output",
                label="输出",
                direction=PortDirection.OUTPUT,
                kind="text",
            )
        )

        # Store shortcut reference
        node.params["shortcut_id"] = shortcut_id
        node.params["stop_on_error"] = bool(step.get("stop_on_error", True))
        node.params["delay_ms"] = int(step.get("delay_ms") or 0)

        return node

    @staticmethod
    def _apply_canvas_position(node: ChainNode, canvas: dict[str, Any], node_id: str) -> None:
        """Apply canvas position to node."""
        nodes_data = canvas.get("nodes") or []

        for node_data in nodes_data:
            if str(node_data.get("id") or "") == node_id:
                node.x = float(node_data.get("x") or 0)
                node.y = float(node_data.get("y") or 0)
                node.width = float(node_data.get("width") or 0)
                node.height = float(node_data.get("height") or 0)
                break

    @staticmethod
    def graph_to_steps(graph: ChainGraph) -> list[dict[str, Any]]:
        """Convert ChainGraph to legacy chain_steps format.

        Args:
            graph: ChainGraph instance

        Returns:
            List of step dictionaries
        """
        steps = []

        # Get execution order
        try:
            execution_order = graph.topological_sort()
        except Exception:
            # If topological sort fails, use node insertion order
            execution_order = list(graph.nodes.keys())

        # Build node index map
        node_index_map = {node_id: idx + 1 for idx, node_id in enumerate(execution_order)}

        for node_id in execution_order:
            node = graph.get_node(node_id)
            if not node:
                continue

            step = {
                "id": node.id,
                "title": node.title,
                "enabled": node.enabled,
            }

            # Determine node type
            if node.processor_id == "shortcut":
                step["node_type"] = "shortcut"
                step["shortcut_id"] = node.params.get("shortcut_id", "")
            else:
                step["node_type"] = "processor"
                step["processor_id"] = node.processor_id

            step["stop_on_error"] = bool(node.params.get("stop_on_error", graph.stop_on_error))
            step["delay_ms"] = int(node.params.get("delay_ms") or 0)

            # Add args (excluding internal graph/adapter metadata)
            params = {
                k: v
                for k, v in node.params.items()
                if k not in ("shortcut_id", "input_binding", "stop_on_error", "delay_ms", "source")
            }
            if params:
                step["args"] = params
            if "source" in node.params:
                step["source"] = str(node.params.get("source") or "")

            # Build param_bindings from connections
            param_bindings = {}
            for conn in graph.get_connections_to_node(node_id):
                source_index = node_index_map.get(conn.source_node_id)
                if source_index is not None:
                    binding = _legacy_binding_key(source_index, conn.source_port_id)
                    if conn.target_port_id == "input":
                        step["input_binding"] = _append_legacy_binding(step.get("input_binding", ""), binding)
                    else:
                        param_bindings[conn.target_port_id] = _append_legacy_binding(
                            param_bindings.get(conn.target_port_id, ""),
                            binding,
                        )

            if param_bindings:
                step["param_bindings"] = param_bindings

            steps.append(step)

        return steps

    @staticmethod
    def graph_to_canvas(graph: ChainGraph) -> dict[str, Any]:
        """Convert ChainGraph to legacy canvas format.

        Args:
            graph: ChainGraph instance

        Returns:
            Canvas dictionary
        """
        return graph.to_canvas_dict()


class GraphExecutor:
    """Executor for running action chain graphs.

    This class provides a high-level interface for executing graphs,
    with support for:
    - Legacy format conversion
    - Progress callbacks
    - Cancellation
    - Timeout
    """

    def __init__(self):
        self._runtime = GraphRuntime()
        self._register_builtin_handlers()

    def _register_builtin_handlers(self) -> None:
        """Register built-in processor handlers."""
        # Register handlers for common processors
        self._runtime.register_processor("text_input", self._handle_text_input)
        self._runtime.register_processor("num_input", self._handle_num_input)
        self._runtime.register_processor("bool_value", self._handle_bool_value)
        self._runtime.register_processor("panel_node", self._handle_panel_node)
        self._runtime.register_processor("logger_node", self._handle_logger_node)
        self._runtime.register_processor("sleep_node", self._handle_sleep_node)

        # Text processors
        self._runtime.register_processor("text_replace", self._handle_text_replace)
        self._runtime.register_processor("text_slice", self._handle_text_slice)
        self._runtime.register_processor("text_case", self._handle_text_case)
        self._runtime.register_processor("text_join", self._handle_text_join)
        self._runtime.register_processor("text_len", self._handle_text_len)
        self._runtime.register_processor("text_split", self._handle_text_split)
        self._runtime.register_processor("text_lines", self._handle_text_lines)
        self._runtime.register_processor("text_template", self._handle_text_template)
        self._runtime.register_processor("regex_extract", self._handle_regex_extract)

        # Math processors
        self._runtime.register_processor("math_add", self._handle_math_add)
        self._runtime.register_processor("math_sub", self._handle_math_sub)
        self._runtime.register_processor("math_mul", self._handle_math_mul)
        self._runtime.register_processor("math_div", self._handle_math_div)
        self._runtime.register_processor("math_mod", self._handle_math_mod)
        self._runtime.register_processor("math_pow", self._handle_math_pow)

        # Logic processors
        self._runtime.register_processor("bool_not", self._handle_bool_not)
        self._runtime.register_processor("bool_and", self._handle_bool_and)
        self._runtime.register_processor("bool_or", self._handle_bool_or)
        self._runtime.register_processor("compare_value", self._handle_compare_value)
        self._runtime.register_processor("if_else", self._handle_if_else)

        # List processors
        self._runtime.register_processor("list_create", self._handle_list_create)
        self._runtime.register_processor("list_item", self._handle_list_item)
        self._runtime.register_processor("list_len", self._handle_list_len)
        self._runtime.register_processor("list_join", self._handle_list_join)
        self._runtime.register_processor("list_concat", self._handle_list_concat)

    # ── Built-in Handlers ──────────────────────────────────────────────────

    def _handle_text_input(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        return {"output": str(inputs.get("text") or node.params.get("text") or "")}

    def _handle_num_input(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        value = inputs.get("number") or node.params.get("number") or "0"
        try:
            return {"output": float(value)}
        except (ValueError, TypeError):
            return {"output": 0}

    def _handle_bool_value(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        value = inputs.get("value") or node.params.get("value") or "false"
        return {
            "output": str(value).lower() in ("true", "1", "yes"),
            "not": str(value).lower() not in ("true", "1", "yes"),
        }

    def _handle_panel_node(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        return {"output": str(inputs.get("input") or "")}

    def _handle_logger_node(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        text = str(inputs.get("text") or "")
        level = str(inputs.get("level") or node.params.get("level") or "info")
        logger.log(logging.INFO if level == "info" else logging.WARNING, "%s", text)
        return {"output": text}

    def _handle_sleep_node(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        ms = int(inputs.get("ms") or node.params.get("ms") or 1000)
        time.sleep(ms / 1000.0)
        return {"output": str(ms), "ms": ms}

    def _handle_text_replace(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        text = str(inputs.get("text") or "")
        find = str(inputs.get("find") or node.params.get("find") or "")
        replace = str(inputs.get("replace") or node.params.get("replace") or "")
        result = text.replace(find, replace) if find else text
        return {"output": result}

    def _handle_text_slice(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        text = str(inputs.get("text") or "")
        start = int(inputs.get("start") or node.params.get("start") or 0)
        end = int(inputs.get("end") or node.params.get("end") or len(text))
        return {"output": text[start:end]}

    def _handle_text_case(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        text = str(inputs.get("text") or "")
        mode = str(inputs.get("mode") or node.params.get("mode") or "upper")
        if mode == "upper":
            return {"output": text.upper()}
        elif mode == "lower":
            return {"output": text.lower()}
        elif mode == "title":
            return {"output": text.title()}
        elif mode == "trim":
            return {"output": text.strip()}
        return {"output": text}

    def _handle_text_join(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        delimiter = str(inputs.get("delimiter") or node.params.get("delimiter") or "")
        parts = []
        for key in ("a", "b", "c", "d", "e"):
            value = inputs.get(key) or node.params.get(key)
            if value is not None:
                parts.append(str(value))
        return {"output": delimiter.join(parts)}

    def _handle_text_len(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        text = str(inputs.get("text") or "")
        return {"output": len(text)}

    def _handle_text_split(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        text = str(inputs.get("text") or "")
        delimiter = str(inputs.get("delimiter") or node.params.get("delimiter") or "")
        parts = text.split(delimiter) if delimiter else list(text)
        return {
            "output": parts,
            "count": len(parts),
            "first": parts[0] if parts else "",
            "last": parts[-1] if parts else "",
        }

    def _handle_text_lines(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        text = str(inputs.get("text") or "")
        lines = text.splitlines()
        return {
            "output": lines,
            "count": len(lines),
            "first": lines[0] if lines else "",
            "last": lines[-1] if lines else "",
        }

    def _handle_text_template(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        template = str(inputs.get("template") or node.params.get("template") or "{output}")
        replacements = {}
        for key in ("input", "a", "b", "c"):
            value = inputs.get(key) or node.params.get(key)
            if value is not None:
                replacements[key] = str(value)
        result = template
        for key, value in replacements.items():
            result = result.replace(f"{{{key}}}", value)
        return {"output": result}

    def _handle_regex_extract(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        import re

        text = str(inputs.get("text") or "")
        pattern = str(inputs.get("pattern") or node.params.get("pattern") or "")
        group = int(inputs.get("group") or node.params.get("group") or 0)
        try:
            match = re.search(pattern, text)
            if match:
                return {"output": match.group(group)}
        except Exception as exc:
            logger.debug("正则处理器执行失败，返回空输出: %s", exc, exc_info=True)
        return {"output": ""}

    def _handle_math_add(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        a = float(inputs.get("a") or node.params.get("a") or 0)
        b = float(inputs.get("b") or node.params.get("b") or 0)
        return {"output": a + b}

    def _handle_math_sub(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        a = float(inputs.get("a") or node.params.get("a") or 0)
        b = float(inputs.get("b") or node.params.get("b") or 0)
        return {"output": a - b}

    def _handle_math_mul(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        a = float(inputs.get("a") or node.params.get("a") or 0)
        b = float(inputs.get("b") or node.params.get("b") or 0)
        return {"output": a * b}

    def _handle_math_div(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        a = float(inputs.get("a") or node.params.get("a") or 0)
        b = float(inputs.get("b") or node.params.get("b") or 1)
        if b == 0:
            return {"output": None}
        return {"output": a / b}

    def _handle_math_mod(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        a = float(inputs.get("a") or node.params.get("a") or 0)
        b = float(inputs.get("b") or node.params.get("b") or 1)
        if b == 0:
            return {"output": None}
        return {"output": a % b}

    def _handle_math_pow(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        base = float(inputs.get("base") or node.params.get("base") or 0)
        exp = float(inputs.get("exp") or node.params.get("exp") or 1)
        return {"output": base**exp}

    def _handle_bool_not(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        value = bool(inputs.get("value"))
        return {"output": not value, "not": not value}

    def _handle_bool_and(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        a = bool(inputs.get("a"))
        b = bool(inputs.get("b"))
        return {"output": a and b}

    def _handle_bool_or(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        a = bool(inputs.get("a"))
        b = bool(inputs.get("b"))
        return {"output": a or b}

    def _handle_compare_value(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        a = inputs.get("a")
        b = inputs.get("b")
        operator = str(inputs.get("operator") or node.params.get("operator") or "等于")

        if operator == "等于":
            result = str(a) == str(b)
        elif operator == "不等于":
            result = str(a) != str(b)
        elif operator == "大于":
            try:
                result = float(a) > float(b)
            except (ValueError, TypeError):
                result = str(a) > str(b)
        elif operator == "小于":
            try:
                result = float(a) < float(b)
            except (ValueError, TypeError):
                result = str(a) < str(b)
        elif operator == "包含":
            result = str(b) in str(a)
        elif operator == "不包含":
            result = str(b) not in str(a)
        else:
            result = False

        return {"output": result}

    def _handle_if_else(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        condition = bool(inputs.get("condition"))
        true_value = inputs.get("true_value")
        false_value = inputs.get("false_value")
        return {"output": true_value if condition else false_value}

    def _handle_list_create(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        items = []
        for key in ("a", "b", "c", "d", "e"):
            value = inputs.get(key) or node.params.get(key)
            if value is not None:
                items.append(value)
        return {
            "output": items,
            "count": len(items),
            "first": items[0] if items else None,
            "last": items[-1] if items else None,
        }

    def _handle_list_item(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        lst = inputs.get("list") or []
        index = int(inputs.get("index") or node.params.get("index") or 0)
        if isinstance(lst, list) and 0 <= index < len(lst):
            return {"output": lst[index]}
        return {"output": None}

    def _handle_list_len(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        lst = inputs.get("list") or []
        return {"output": len(lst) if isinstance(lst, list) else 0}

    def _handle_list_join(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        lst = inputs.get("list") or []
        delimiter = str(inputs.get("delimiter") or node.params.get("delimiter") or ",")
        if isinstance(lst, list):
            return {"output": delimiter.join(str(item) for item in lst)}
        return {"output": str(lst)}

    def _handle_list_concat(
        self, node: ChainNode, inputs: dict[str, Any], context: GraphExecutionContext
    ) -> dict[str, Any]:
        result = []
        for key in ("a", "b", "c"):
            lst = inputs.get(key) or []
            if isinstance(lst, list):
                result.extend(lst)
            elif lst is not None:
                result.append(lst)
        return {"output": result, "count": len(result)}

    # ── Execution Methods ──────────────────────────────────────────────────

    def execute(
        self,
        graph: ChainGraph,
        cancel_event: threading.Event | None = None,
        max_steps: int = 0,
        timeout: float = 0.0,
        use_cache: bool = True,
        on_node_start: Any = None,
        on_node_complete: Any = None,
    ) -> ExecutionResult:
        """Execute a graph.

        Args:
            graph: The graph to execute
            cancel_event: Event to signal cancellation
            max_steps: Maximum number of steps
            timeout: Maximum execution time
            use_cache: Whether to use cached results
            on_node_start: Callback when node starts
            on_node_complete: Callback when node completes

        Returns:
            ExecutionResult
        """
        return self._runtime.execute(graph, cancel_event, max_steps, timeout, use_cache)

    def execute_steps(
        self,
        steps: list[dict[str, Any]],
        canvas: dict[str, Any] | None = None,
        shortcut_map: dict[str, Any] | None = None,
        **kwargs,
    ) -> ExecutionResult:
        """Execute legacy chain_steps format.

        Args:
            steps: List of step dictionaries
            canvas: Optional canvas data
            shortcut_map: Optional shortcut map
            **kwargs: Additional execution options

        Returns:
            ExecutionResult
        """
        graph = LegacyAdapter.steps_to_graph(steps, canvas, shortcut_map)
        return self.execute(graph, **kwargs)

    def execute_node(
        self, graph: ChainGraph, node_id: str, cancel_event: threading.Event | None = None
    ) -> NodeExecutionResult:
        """Execute a single node and its dependencies."""
        return self._runtime.execute_node(graph, node_id, cancel_event)


# ── Convenience Functions ──────────────────────────────────────────────────

_global_executor: GraphExecutor | None = None


def get_executor() -> GraphExecutor:
    """Get the global graph executor."""
    global _global_executor
    if _global_executor is None:
        _global_executor = GraphExecutor()
    return _global_executor


def execute_chain_graph(graph: ChainGraph, **kwargs) -> ExecutionResult:
    """Execute a chain graph."""
    return get_executor().execute(graph, **kwargs)


def convert_steps_to_graph(
    steps: list[dict[str, Any]], canvas: dict[str, Any] | None = None, shortcut_map: dict[str, Any] | None = None
) -> ChainGraph:
    """Convert legacy steps to graph."""
    return LegacyAdapter.steps_to_graph(steps, canvas, shortcut_map)


def convert_graph_to_steps(graph: ChainGraph) -> list[dict[str, Any]]:
    """Convert graph to legacy steps."""
    return LegacyAdapter.graph_to_steps(graph)


def _binding_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _parse_legacy_binding(binding: str, current_index: int) -> tuple[int | None, str]:
    binding = str(binding or "").strip()
    if binding.startswith("prev."):
        source_index = current_index - 1
        port = binding[5:]
    elif "." in binding:
        raw_index, port = binding.split(".", 1)
        try:
            source_index = int(raw_index)
        except (TypeError, ValueError):
            return None, ""
    else:
        return None, ""
    if port.startswith("outputs."):
        port = port[8:]
    return source_index, port or "output"


def _legacy_binding_key(source_index: int, source_port: str) -> str:
    source_port = str(source_port or "output").strip() or "output"
    direct_ports = {"success", "output", "stdout", "stderr", "exit_code", "error", "files.0", "folders.0", "urls.0"}
    if source_port in direct_ports:
        return f"{source_index}.{source_port}"
    return f"{source_index}.outputs.{source_port}"


def _append_legacy_binding(existing: Any, binding: str) -> str | list[str]:
    if not existing:
        return binding
    if isinstance(existing, list):
        return [*existing, binding]
    return [str(existing), binding]
