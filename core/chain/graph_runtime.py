"""Action chain graph runtime engine.

This module provides the runtime engine for executing action chain graphs.
It handles:
- Graph execution with topological ordering
- Data flow between nodes
- Error handling and propagation
- Execution context and state management
- Cancellation and timeout support
- Node-level caching
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .graph_models import (
    ChainGraph,
    ChainNode,
    CyclicGraphError,
    NodeStatus,
)
from .runtime import ChainValue
from .smart_types import recognize_type

__all__ = [
    "GraphRuntime",
    "GraphExecutionContext",
    "ExecutionResult",
    "NodeExecutionResult",
    "execute_graph",
]


logger = logging.getLogger(__name__)


@dataclass
class NodeExecutionResult:
    """Result of executing a single node."""

    node_id: str
    processor_id: str
    status: NodeStatus
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    typed_inputs: dict[str, ChainValue] = field(default_factory=dict)
    typed_outputs: dict[str, ChainValue] = field(default_factory=dict)
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    execution_time: float = 0.0
    skipped: bool = False
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "node_id": self.node_id,
            "processor_id": self.processor_id,
            "status": self.status.value,
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "typed_inputs": {k: v.to_dict() for k, v in self.typed_inputs.items()},
            "typed_outputs": {k: v.to_dict() for k, v in self.typed_outputs.items()},
            "error": self.error,
            "warnings": list(self.warnings),
            "execution_time": self.execution_time,
            "skipped": self.skipped,
            "cached": self.cached,
        }


@dataclass
class ExecutionResult:
    """Result of executing an entire graph."""

    graph_id: str
    run_id: str
    status: str = "pending"  # pending, running, completed, failed, cancelled
    node_results: dict[str, NodeExecutionResult] = field(default_factory=dict)
    total_execution_time: float = 0.0
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    started_at: float = 0.0
    completed_at: float = 0.0

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.status == "completed"

    @property
    def failed(self) -> bool:
        """Check if execution failed."""
        return self.status in ("failed", "cancelled")

    def get_node_result(self, node_id: str) -> NodeExecutionResult | None:
        """Get result for a specific node."""
        return self.node_results.get(node_id)

    def get_failed_nodes(self) -> list[NodeExecutionResult]:
        """Get all failed node results."""
        return [r for r in self.node_results.values() if r.status == NodeStatus.FAILED]

    def get_output_values(self, node_id: str) -> dict[str, Any]:
        """Get output values for a node."""
        result = self.node_results.get(node_id)
        if result:
            return result.outputs
        return {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "graph_id": self.graph_id,
            "run_id": self.run_id,
            "status": self.status,
            "node_results": {k: v.to_dict() for k, v in self.node_results.items()},
            "total_execution_time": self.total_execution_time,
            "error": self.error,
            "warnings": list(self.warnings),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class GraphExecutionContext:
    """Context for graph execution."""

    graph: ChainGraph
    run_id: str = ""
    cancel_event: threading.Event | None = None
    max_steps: int = 0
    timeout: float = 0.0  # 0 = no timeout

    # Runtime state
    current_step: int = 0
    total_steps: int = 0
    started_at: float = 0.0

    # Node values (data flow)
    port_values: dict[str, Any] = field(default_factory=dict)  # "node_id.port_id" -> value
    typed_port_values: dict[str, ChainValue] = field(default_factory=dict)

    # Execution callbacks
    on_node_start: Callable[[str], None] | None = None
    on_node_complete: Callable[[str, NodeExecutionResult], None] | None = None
    on_error: Callable[[str, str], None] | None = None

    def __post_init__(self):
        if not self.run_id:
            self.run_id = str(uuid.uuid4())
        self.total_steps = len(self.graph.nodes)

    def is_cancelled(self) -> bool:
        """Check if execution has been cancelled."""
        if self.cancel_event is None:
            return False
        return self.cancel_event.is_set()

    def check_cancelled(self) -> None:
        """Raise if execution has been cancelled."""
        if self.is_cancelled():
            raise CancelledError("Graph execution cancelled")

    def is_timed_out(self) -> bool:
        """Check if execution has timed out."""
        if self.timeout <= 0:
            return False
        return (time.time() - self.started_at) > self.timeout

    def get_port_value(self, node_id: str, port_id: str) -> Any:
        """Get a port value."""
        key = f"{node_id}.{port_id}"
        return self.port_values.get(key)

    def set_port_value(self, node_id: str, port_id: str, value: Any) -> None:
        """Set a port value."""
        key = f"{node_id}.{port_id}"
        self.port_values[key] = value

        # Also set typed value
        detected_type, confidence = recognize_type(value)
        typed_value = ChainValue(
            kind=detected_type.value if detected_type else "any",
            value=value,
            text=str(value) if value is not None else "",
            preview=str(value)[:100] if value is not None else "",
        )
        self.typed_port_values[key] = typed_value

    def get_typed_port_value(self, node_id: str, port_id: str) -> ChainValue | None:
        """Get a typed port value."""
        key = f"{node_id}.{port_id}"
        return self.typed_port_values.get(key)

    def get_input_values(self, node: ChainNode) -> dict[str, Any]:
        """Get all input values for a node."""
        values = {}
        for port in node.inputs:
            # First check if there's a connection
            conn = self.graph.get_connection_to_input(node.id, port.id)
            if conn and conn.enabled:
                # Get value from source node's output
                source_key = f"{conn.source_node_id}.{conn.source_port_id}"
                value = self.port_values.get(source_key)
                values[port.id] = value
            elif port.default is not None:
                # Use default value
                values[port.id] = port.default
            elif port.id in node.params:
                # Use parameter value
                values[port.id] = node.params[port.id]
            else:
                values[port.id] = None

        return values

    def get_input_typed_values(self, node: ChainNode) -> dict[str, ChainValue]:
        """Get all typed input values for a node."""
        values = {}
        for port in node.inputs:
            conn = self.graph.get_connection_to_input(node.id, port.id)
            if conn and conn.enabled:
                source_key = f"{conn.source_node_id}.{conn.source_port_id}"
                typed_value = self.typed_port_values.get(source_key)
                if typed_value:
                    values[port.id] = typed_value
                else:
                    # Create typed value from raw value
                    raw_value = self.port_values.get(source_key)
                    values[port.id] = _create_chain_value(raw_value, port.kind)
            else:
                default = port.default if port.default is not None else node.params.get(port.id)
                values[port.id] = _create_chain_value(default, port.kind)

        return values

    def elapsed(self) -> float:
        """Get elapsed time since execution started."""
        return time.time() - self.started_at


class CancelledError(Exception):
    """Raised when execution is cancelled."""

    pass


class GraphRuntime:
    """Runtime engine for executing action chain graphs.

    This class handles:
    - Validating the graph before execution
    - Topological sorting for execution order
    - Data flow between connected nodes
    - Error handling and propagation
    - Cancellation and timeout support
    """

    def __init__(self):
        self._processor_handlers: dict[str, Callable] = {}

    def register_processor(self, processor_id: str, handler: Callable) -> None:
        """Register a processor handler."""
        self._processor_handlers[processor_id] = handler

    def execute(
        self,
        graph: ChainGraph,
        cancel_event: threading.Event | None = None,
        max_steps: int = 0,
        timeout: float = 0.0,
        use_cache: bool = True,
    ) -> ExecutionResult:
        """Execute a graph.

        Args:
            graph: The graph to execute
            cancel_event: Event to signal cancellation
            max_steps: Maximum number of steps to execute (0 = unlimited)
            timeout: Maximum execution time in seconds (0 = unlimited)
            use_cache: Whether to use cached results

        Returns:
            ExecutionResult with execution details
        """
        result = ExecutionResult(
            graph_id=graph.id,
            run_id=str(uuid.uuid4()),
            started_at=time.time(),
        )

        # Validate graph
        issues = graph.validate()
        errors = [i for i in issues if i.get("level") == "error"]
        if errors:
            result.status = "failed"
            result.error = f"Graph validation failed: {len(errors)} error(s)"
            result.completed_at = time.time()
            return result

        # Create execution context
        context = GraphExecutionContext(
            graph=graph,
            run_id=result.run_id,
            cancel_event=cancel_event or threading.Event(),
            max_steps=max_steps,
            timeout=timeout,
        )
        context.started_at = result.started_at

        try:
            # Get execution order
            execution_order = graph.topological_sort()
            context.total_steps = len(execution_order)

            # Update result status
            result.status = "running"

            # Execute nodes in order
            for node_id in execution_order:
                # Check cancellation
                context.check_cancelled()

                # Check timeout
                if context.is_timed_out():
                    result.status = "failed"
                    result.error = "Execution timed out"
                    break

                # Check max steps
                if max_steps > 0 and context.current_step >= max_steps:
                    result.status = "failed"
                    result.error = f"Maximum steps ({max_steps}) exceeded"
                    break

                # Get node
                node = graph.get_node(node_id)
                if node is None:
                    continue

                # Skip disabled nodes
                if not node.enabled:
                    node_result = NodeExecutionResult(
                        node_id=node_id,
                        processor_id=node.processor_id,
                        status=NodeStatus.SKIPPED,
                        skipped=True,
                    )
                    result.node_results[node_id] = node_result
                    context.current_step += 1
                    continue

                # Check if we can use cached result
                if use_cache and node.cache_valid and node.cached_outputs:
                    node_result = NodeExecutionResult(
                        node_id=node_id,
                        processor_id=node.processor_id,
                        status=NodeStatus.CACHED,
                        outputs=dict(node.cached_outputs),
                        cached=True,
                    )
                    result.node_results[node_id] = node_result

                    # Set output values in context
                    for port_id, value in node.cached_outputs.items():
                        context.set_port_value(node_id, port_id, value)

                    context.current_step += 1
                    continue

                # Execute node
                node_result = self._execute_node(node, context)
                result.node_results[node_id] = node_result

                # Update node status
                node.status = node_result.status
                node.execution_time = node_result.execution_time
                if node_result.error:
                    node.error = node_result.error

                # Handle failure
                if node_result.status == NodeStatus.FAILED:
                    if graph.stop_on_error:
                        result.status = "failed"
                        result.error = f"Node '{node.title}' failed: {node_result.error}"
                        break
                    else:
                        # Mark downstream nodes as skipped
                        self._skip_downstream_nodes(graph, node_id, result, context)

                context.current_step += 1

            # Update result
            if result.status == "running":
                result.status = "completed"

        except CyclicGraphError as e:
            result.status = "failed"
            result.error = f"Graph contains cycles: {e}"
        except CancelledError:
            result.status = "cancelled"
            result.error = "Execution cancelled by user"
        except Exception as e:
            result.status = "failed"
            result.error = f"Execution failed: {e}"
            logger.exception("Graph execution failed")

        result.completed_at = time.time()
        result.total_execution_time = result.completed_at - result.started_at

        return result

    def _execute_node(self, node: ChainNode, context: GraphExecutionContext) -> NodeExecutionResult:
        """Execute a single node."""
        start_time = time.time()

        # Get input values
        input_values = context.get_input_values(node)
        typed_inputs = context.get_input_typed_values(node)

        # Create result with initial status
        node_result = NodeExecutionResult(
            node_id=node.id,
            processor_id=node.processor_id,
            status=NodeStatus.RUNNING,
            inputs=input_values,
            typed_inputs=typed_inputs,
        )

        try:
            # Get processor handler
            handler = self._get_processor_handler(node.processor_id)

            if handler is None:
                # No handler found, try to use default behavior
                outputs = self._default_handler(node, input_values)
            else:
                # Execute handler
                outputs = handler(node, input_values, context)

            # Process outputs
            if isinstance(outputs, dict):
                node_result.outputs = outputs
                node_result.status = NodeStatus.SUCCESS

                # Set output values in context
                for port_id, value in outputs.items():
                    context.set_port_value(node.id, port_id, value)

                    # Create typed output
                    port = node.get_output(port_id)
                    if port:
                        typed_value = _create_chain_value(value, port.kind)
                        node_result.typed_outputs[port_id] = typed_value

                # Cache results
                node.cached_outputs = outputs
                node.cache_valid = True

            else:
                # Single output
                node_result.outputs = {"output": outputs}
                node_result.status = NodeStatus.SUCCESS
                context.set_port_value(node.id, "output", outputs)

                # Cache results
                node.cached_outputs = {"output": outputs}
                node.cache_valid = True

        except Exception as e:
            node_result.status = NodeStatus.FAILED
            node_result.error = str(e)
            logger.error("Node %s failed: %s", node.id, e)

        node_result.execution_time = time.time() - start_time

        return node_result

    def _get_processor_handler(self, processor_id: str) -> Callable | None:
        """Get the handler for a processor."""
        # Check registered handlers
        if processor_id in self._processor_handlers:
            return self._processor_handlers[processor_id]

        # Try to import from registry
        try:
            from .registry import get_processor_handler  # type: ignore[attr-defined]

            return get_processor_handler(processor_id)  # type: ignore[no-any-return]
        except ImportError as exc:
            logger.debug("无法从 registry 导入处理器 %s: %s", processor_id, exc, exc_info=True)

        return None

    def _default_handler(self, node: ChainNode, inputs: dict[str, Any]) -> dict[str, Any]:
        """Default handler for nodes without a specific handler."""
        # Simple pass-through for unknown processors
        outputs = {}
        for port in node.outputs:
            if port.id == "output":
                outputs[port.id] = inputs.get("input") or inputs.get("value")
            else:
                outputs[port.id] = None
        return outputs

    def _skip_downstream_nodes(
        self, graph: ChainGraph, failed_node_id: str, result: ExecutionResult, context: GraphExecutionContext
    ) -> None:
        """Mark downstream nodes as skipped after a failure."""
        # BFS to find all downstream nodes
        visited = set()
        queue = [failed_node_id]

        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)

            # Get downstream nodes
            dependents = graph.get_dependents(node_id)
            for dep_id in dependents:
                if dep_id not in visited and dep_id not in result.node_results:
                    # Mark as skipped
                    dep_node = graph.get_node(dep_id)
                    if dep_node:
                        node_result = NodeExecutionResult(
                            node_id=dep_id,
                            processor_id=dep_node.processor_id,
                            status=NodeStatus.SKIPPED,
                            skipped=True,
                        )
                        result.node_results[dep_id] = node_result
                        dep_node.status = NodeStatus.SKIPPED
                    queue.append(dep_id)

    def execute_node(
        self, graph: ChainGraph, node_id: str, cancel_event: threading.Event | None = None
    ) -> NodeExecutionResult:
        """Execute a single node and its dependencies.

        This method executes only the specified node and all its upstream dependencies.
        """
        # Get all upstream nodes
        upstream_nodes = self._get_upstream_nodes(graph, node_id)

        # Create a sub-graph with only these nodes
        sub_graph = ChainGraph()
        for nid in upstream_nodes + [node_id]:
            node = graph.get_node(nid)
            if node:
                sub_graph.add_node(node)

        # Add connections between these nodes
        for conn in graph.iter_connections():
            if conn.source_node_id in sub_graph.nodes and conn.target_node_id in sub_graph.nodes:
                sub_graph.add_connection(conn)

        # Execute the sub-graph
        result = self.execute(sub_graph, cancel_event=cancel_event)

        # Return only the result for the requested node
        return result.node_results.get(
            node_id,
            NodeExecutionResult(
                node_id=node_id,
                processor_id="",
                status=NodeStatus.FAILED,
                error="Node not found in execution result",
            ),
        )

    def _get_upstream_nodes(self, graph: ChainGraph, node_id: str) -> list[str]:
        """Get all upstream nodes (recursive dependencies)."""
        visited = set()
        queue = [node_id]

        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            # Get dependencies
            deps = graph.get_dependencies(current_id)
            for dep_id in deps:
                if dep_id not in visited:
                    queue.append(dep_id)

        # Remove the target node itself
        visited.discard(node_id)
        return list(visited)


def _create_chain_value(value: Any, kind: str) -> ChainValue:
    """Create a ChainValue from a raw value."""
    if value is None:
        return ChainValue(kind=kind, value=None, text="", preview="")

    # Detect type
    detected_type, confidence = recognize_type(value)

    # Create preview
    preview = str(value)
    if len(preview) > 100:
        preview = preview[:100] + "..."

    return ChainValue(
        kind=kind,
        value=value,
        text=str(value),
        preview=preview,
        metadata={"detected_type": detected_type.value if detected_type else "any"},
    )


def execute_graph(
    graph: ChainGraph,
    cancel_event: threading.Event | None = None,
    max_steps: int = 0,
    timeout: float = 0.0,
    use_cache: bool = True,
) -> ExecutionResult:
    """Convenience function to execute a graph.

    Args:
        graph: The graph to execute
        cancel_event: Event to signal cancellation
        max_steps: Maximum number of steps to execute
        timeout: Maximum execution time in seconds
        use_cache: Whether to use cached results

    Returns:
        ExecutionResult with execution details
    """
    runtime = GraphRuntime()
    return runtime.execute(graph, cancel_event, max_steps, timeout, use_cache)
