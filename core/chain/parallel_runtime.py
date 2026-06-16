"""Enhanced graph runtime with parallel execution support.

This module extends the base graph runtime with:
- Parallel execution of independent nodes
- Better caching with dependency tracking
- Execution planning and optimization
- Performance monitoring
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any

from .graph_models import (
    ChainGraph,
    ChainNode,
    CyclicGraphError,
    NodeStatus,
)
from .graph_runtime import (
    CancelledError,
    ExecutionResult,
    GraphExecutionContext,
    GraphRuntime,
    NodeExecutionResult,
)

__all__ = [
    "ParallelGraphRuntime",
    "ExecutionPlan",
    "ParallelExecutionResult",
    "execute_graph_parallel",
]

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPlan:
    """Execution plan with parallel groups."""

    groups: list[list[str]] = field(default_factory=list)
    dependencies: dict[str, set[str]] = field(default_factory=dict)
    total_nodes: int = 0
    max_parallelism: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups": self.groups,
            "dependencies": {k: list(v) for k, v in self.dependencies.items()},
            "total_nodes": self.total_nodes,
            "max_parallelism": self.max_parallelism,
        }


@dataclass
class ParallelExecutionResult(ExecutionResult):
    """Extended execution result with parallel execution info."""

    execution_plan: ExecutionPlan | None = None
    parallel_groups_executed: int = 0
    max_parallelism_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update(
            {
                "execution_plan": self.execution_plan.to_dict() if self.execution_plan else None,
                "parallel_groups_executed": self.parallel_groups_executed,
                "max_parallelism_used": self.max_parallelism_used,
            }
        )
        return result


class ParallelGraphRuntime(GraphRuntime):
    """Graph runtime with parallel execution support.

    This runtime can execute independent nodes in parallel, improving
    performance for graphs with multiple independent branches.
    """

    def __init__(self, max_workers: int = 4):
        super().__init__()
        self._max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None

    def execute(
        self,
        graph: ChainGraph,
        cancel_event: threading.Event | None = None,
        max_steps: int = 0,
        timeout: float = 0.0,
        use_cache: bool = True,
        parallel: bool = True,
    ) -> ParallelExecutionResult:
        """Execute a graph with optional parallel execution.

        Args:
            graph: The graph to execute
            cancel_event: Event to signal cancellation
            max_steps: Maximum number of steps to execute (0 = unlimited)
            timeout: Maximum execution time in seconds (0 = unlimited)
            use_cache: Whether to use cached results
            parallel: Whether to enable parallel execution

        Returns:
            ParallelExecutionResult with execution details
        """
        result = ParallelExecutionResult(
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

        # Create execution plan
        if parallel:
            plan = self._create_execution_plan(graph)
            result.execution_plan = plan
        else:
            plan = None

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
            if parallel and plan and plan.max_parallelism > 1:
                self._execute_parallel(graph, context, result, plan, use_cache)
            else:
                self._execute_sequential(graph, context, result, use_cache)

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

    def _create_execution_plan(self, graph: ChainGraph) -> ExecutionPlan:
        """Create an execution plan with parallel groups."""
        plan = ExecutionPlan()
        plan.total_nodes = len(graph.nodes)

        # Get execution groups
        plan.groups = graph.get_execution_plan()

        # Calculate dependencies
        for node_id in graph.nodes:
            plan.dependencies[node_id] = set(graph.get_dependencies(node_id))

        # Calculate max parallelism
        plan.max_parallelism = max(len(group) for group in plan.groups) if plan.groups else 0

        return plan

    def _execute_parallel(
        self,
        graph: ChainGraph,
        context: GraphExecutionContext,
        result: ParallelExecutionResult,
        plan: ExecutionPlan,
        use_cache: bool,
    ) -> None:
        """Execute graph with parallel execution of independent nodes."""
        result.status = "running"

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            self._executor = executor

            for _group_idx, group in enumerate(plan.groups):
                # Check cancellation
                context.check_cancelled()

                # Check timeout
                if context.is_timed_out():
                    result.status = "failed"
                    result.error = "Execution timed out"
                    break

                # Check max steps
                if context.max_steps > 0 and context.current_step >= context.max_steps:
                    result.status = "failed"
                    result.error = f"Maximum steps ({context.max_steps}) exceeded"
                    break

                # Execute group in parallel
                if len(group) == 1:
                    # Single node - execute directly
                    node_id = group[0]
                    self._execute_single_node(node_id, graph, context, result, use_cache)
                else:
                    # Multiple nodes - execute in parallel
                    self._execute_node_group(group, graph, context, result, use_cache, executor)

                result.parallel_groups_executed += 1
                result.max_parallelism_used = max(result.max_parallelism_used, len(group))

            # Update result status
            if result.status == "running":
                result.status = "completed"

            self._executor = None

    def _execute_sequential(
        self, graph: ChainGraph, context: GraphExecutionContext, result: ExecutionResult, use_cache: bool
    ) -> None:
        """Execute graph sequentially (fallback)."""
        result.status = "running"

        # Get execution order
        execution_order = graph.topological_sort()
        context.total_steps = len(execution_order)

        for node_id in execution_order:
            # Check cancellation
            context.check_cancelled()

            # Check timeout
            if context.is_timed_out():
                result.status = "failed"
                result.error = "Execution timed out"
                break

            # Check max steps
            if context.max_steps > 0 and context.current_step >= context.max_steps:
                result.status = "failed"
                result.error = f"Maximum steps ({context.max_steps}) exceeded"
                break

            # Execute node
            self._execute_single_node(node_id, graph, context, result, use_cache)

        # Update result status
        if result.status == "running":
            result.status = "completed"

    def _execute_single_node(
        self, node_id: str, graph: ChainGraph, context: GraphExecutionContext, result: ExecutionResult, use_cache: bool
    ) -> None:
        """Execute a single node."""
        node = graph.get_node(node_id)
        if node is None:
            return

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
            return

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
            return

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
            else:
                # Mark downstream nodes as skipped
                self._skip_downstream_nodes(graph, node_id, result, context)

        context.current_step += 1

    def _execute_node_group(
        self,
        group: list[str],
        graph: ChainGraph,
        context: GraphExecutionContext,
        result: ExecutionResult,
        use_cache: bool,
        executor: ThreadPoolExecutor,
    ) -> None:
        """Execute a group of independent nodes in parallel."""
        futures: dict[str, Future] = {}

        # Submit all nodes in the group
        for node_id in group:
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

            # Submit node execution
            future = executor.submit(self._execute_node_thread_safe, node, context)
            futures[node_id] = future

        pending: dict[Future, str] = {future: node_id for node_id, future in futures.items()}
        while pending:
            context.check_cancelled()
            if context.is_timed_out():
                self._signal_group_cancel(context)
                result.status = "failed"
                result.error = "Execution timed out"
                break

            wait_timeout = self._group_wait_timeout(context)
            done, _not_done = wait(pending.keys(), timeout=wait_timeout, return_when=FIRST_COMPLETED)
            if not done:
                continue

            for future in done:
                node_id = pending.pop(future)
                self._collect_node_future(future, node_id, graph, context, result)
                node_result = result.node_results.get(node_id)  # type: ignore[assignment]
                if node_result is None:
                    continue
                if node_result.status == NodeStatus.FAILED:
                    if graph.stop_on_error:
                        node = graph.get_node(node_id)
                        title = node.title if node else node_id
                        result.status = "failed"
                        result.error = f"Node '{title}' failed: {node_result.error}"
                        self._signal_group_cancel(context)
                        return
                    self._skip_downstream_nodes(graph, node_id, result, context)

    def _group_wait_timeout(self, context: GraphExecutionContext) -> float:
        if context.timeout <= 0:
            return 0.1
        elapsed = time.time() - context.started_at
        remaining = max(0.0, context.timeout - elapsed)
        return min(0.1, remaining)

    def _signal_group_cancel(self, context: GraphExecutionContext) -> None:
        if context.cancel_event is not None:
            context.cancel_event.set()

    def _collect_node_future(
        self,
        future: Future,
        node_id: str,
        graph: ChainGraph,
        context: GraphExecutionContext,
        result: ExecutionResult,
    ) -> None:
        try:
            node_result = future.result()
            result.node_results[node_id] = node_result

            node = graph.get_node(node_id)
            if node:
                node.status = node_result.status
                node.execution_time = node_result.execution_time
                if node_result.error:
                    node.error = node_result.error

            context.current_step += 1
        except Exception as e:
            logger.error("Node %s execution failed: %s", node_id, e)
            node_result = NodeExecutionResult(
                node_id=node_id,
                processor_id="",
                status=NodeStatus.FAILED,
                error=str(e),
            )
            result.node_results[node_id] = node_result
            context.current_step += 1

    def _execute_node_thread_safe(self, node: ChainNode, context: GraphExecutionContext) -> NodeExecutionResult:
        """Execute a node in a thread-safe manner."""
        # Create a copy of input values for thread safety
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

        start_time = time.time()

        try:
            context.check_cancelled()
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

                # Set output values in context (thread-safe)
                for port_id, value in outputs.items():
                    context.set_port_value(node.id, port_id, value)

                    # Create typed output
                    port = node.get_output(port_id)
                    if port:
                        from .values import make_chain_value

                        typed_value = make_chain_value(value, port.kind)
                        node_result.typed_outputs[port_id] = typed_value  # type: ignore[assignment]

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


def execute_graph_parallel(
    graph: ChainGraph,
    cancel_event: threading.Event | None = None,
    max_steps: int = 0,
    timeout: float = 0.0,
    use_cache: bool = True,
    max_workers: int = 4,
) -> ParallelExecutionResult:
    """Convenience function to execute a graph with parallel execution.

    Args:
        graph: The graph to execute
        cancel_event: Event to signal cancellation
        max_steps: Maximum number of steps to execute
        timeout: Maximum execution time in seconds
        use_cache: Whether to use cached results
        max_workers: Maximum number of parallel workers

    Returns:
        ParallelExecutionResult with execution details
    """
    runtime = ParallelGraphRuntime(max_workers=max_workers)
    return runtime.execute(graph, cancel_event, max_steps, timeout, use_cache, parallel=True)
