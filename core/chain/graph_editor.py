"""Graph editing operations for action chains.

This module provides convenient utilities for editing chain graphs:
- Auto-layout algorithms
- Node alignment and distribution
- Connection routing helpers
- Graph analysis utilities
"""

from __future__ import annotations

import math

from .graph_models import (
    ChainConnection,
    ChainGraph,
    ChainNode,
    ChainPort,
    PortDirection,
)

__all__ = [
    "GraphEditor",
    "auto_layout",
    "align_nodes",
    "distribute_nodes",
    "center_nodes",
    "get_bounds",
    "find_nearest_port",
    "can_connect",
    "get_connection_points",
]


class GraphEditor:
    """Utility class for graph editing operations."""

    def __init__(self, graph: ChainGraph):
        self._graph = graph

    @property
    def graph(self) -> ChainGraph:
        """Get the graph."""
        return self._graph

    # ── Node Operations ────────────────────────────────────────────────────

    def add_processor_node(
        self, processor_id: str, x: float = 0, y: float = 0, node_id: str | None = None
    ) -> ChainNode | None:
        """Add a processor node to the graph.

        Args:
            processor_id: Processor type ID
            x: X position
            y: Y position
            node_id: Optional node ID

        Returns:
            Created node or None if processor not found
        """
        from .processor_registry import get_registry

        registry = get_registry()
        definition = registry.get_definition(processor_id)

        if not definition:
            return None

        node = ChainNode.from_definition(definition, node_id, x, y)
        self._graph.add_node(node)
        return node

    def duplicate_node(self, node_id: str, offset_x: float = 50, offset_y: float = 50) -> ChainNode | None:
        """Duplicate a node.

        Args:
            node_id: ID of node to duplicate
            offset_x: X offset for new node
            offset_y: Y offset for new node

        Returns:
            New node or None if original not found
        """
        original = self._graph.get_node(node_id)
        if not original:
            return None

        import uuid

        new_node = ChainNode(
            id=str(uuid.uuid4()),
            processor_id=original.processor_id,
            title=f"{original.title} (副本)",
            category=original.category,
            description=original.description,
            x=original.x + offset_x,
            y=original.y + offset_y,
            width=original.width,
            height=original.height,
            enabled=original.enabled,
            params=dict(original.params),
        )

        # Copy ports
        for port in original.inputs:
            new_node.inputs.append(
                ChainPort(
                    id=port.id,
                    label=port.label,
                    direction=port.direction,
                    kind=port.kind,
                    smart_type=port.smart_type,
                    required=port.required,
                    multiple=port.multiple,
                    default=port.default,
                    description=port.description,
                    role=port.role,
                )
            )

        for port in original.outputs:
            new_node.outputs.append(
                ChainPort(
                    id=port.id,
                    label=port.label,
                    direction=port.direction,
                    kind=port.kind,
                    smart_type=port.smart_type,
                    required=port.required,
                    multiple=port.multiple,
                    default=port.default,
                    description=port.description,
                    role=port.role,
                )
            )

        self._graph.add_node(new_node)
        return new_node

    def move_node(self, node_id: str, x: float, y: float) -> bool:
        """Move a node to a new position."""
        node = self._graph.get_node(node_id)
        if not node:
            return False

        node.x = x
        node.y = y
        return True

    def move_nodes(self, node_ids: list[str], dx: float, dy: float) -> int:
        """Move multiple nodes by a delta."""
        count = 0
        for node_id in node_ids:
            node = self._graph.get_node(node_id)
            if node:
                node.x += dx
                node.y += dy
                count += 1
        return count

    # ── Connection Operations ──────────────────────────────────────────────

    def connect(
        self, source_node_id: str, source_port_id: str, target_node_id: str, target_port_id: str
    ) -> ChainConnection | None:
        """Create a connection between two nodes.

        Args:
            source_node_id: Source node ID
            source_port_id: Source output port ID
            target_node_id: Target node ID
            target_port_id: Target input port ID

        Returns:
            Created connection or None if invalid
        """
        import uuid

        connection = ChainConnection(
            id=str(uuid.uuid4()),
            source_node_id=source_node_id,
            source_port_id=source_port_id,
            target_node_id=target_node_id,
            target_port_id=target_port_id,
        )

        try:
            self._graph.add_connection(connection)
            return connection
        except ValueError:
            return None

    def disconnect(self, connection_id: str) -> bool:
        """Remove a connection."""
        return self._graph.remove_connection(connection_id) is not None

    def disconnect_port(self, node_id: str, port_id: str, direction: PortDirection) -> int:
        """Disconnect all connections to/from a port."""
        to_remove = []

        for conn in self._graph.iter_connections():
            if direction == PortDirection.INPUT:
                if conn.target_node_id == node_id and conn.target_port_id == port_id:
                    to_remove.append(conn.id)
            else:
                if conn.source_node_id == node_id and conn.source_port_id == port_id:
                    to_remove.append(conn.id)

        for conn_id in to_remove:
            self._graph.remove_connection(conn_id)

        return len(to_remove)

    # ── Layout Operations ──────────────────────────────────────────────────

    def auto_layout(self, direction: str = "horizontal", spacing_x: float = 200, spacing_y: float = 100) -> None:
        """Auto-layout the graph nodes.

        Args:
            direction: Layout direction ("horizontal" or "vertical")
            spacing_x: Horizontal spacing between nodes
            spacing_y: Vertical spacing between nodes
        """
        auto_layout(self._graph, direction, spacing_x, spacing_y)

    def align_left(self, node_ids: list[str]) -> None:
        """Align nodes to the leftmost position."""
        nodes = [self._graph.get_node(nid) for nid in node_ids]
        nodes = [n for n in nodes if n is not None]

        if not nodes:
            return

        min_x = min(n.x for n in nodes)  # type: ignore[union-attr]
        for node in nodes:
            node.x = min_x  # type: ignore[union-attr]

    def align_right(self, node_ids: list[str]) -> None:
        """Align nodes to the rightmost position."""
        nodes = [self._graph.get_node(nid) for nid in node_ids]
        nodes = [n for n in nodes if n is not None]

        if not nodes:
            return

        max_x = max(n.x + n.width for n in nodes)  # type: ignore[union-attr]
        for node in nodes:
            node.x = max_x - node.width  # type: ignore[union-attr]

    def align_top(self, node_ids: list[str]) -> None:
        """Align nodes to the topmost position."""
        nodes = [self._graph.get_node(nid) for nid in node_ids]
        nodes = [n for n in nodes if n is not None]

        if not nodes:
            return

        min_y = min(n.y for n in nodes)  # type: ignore[union-attr]
        for node in nodes:
            node.y = min_y  # type: ignore[union-attr]

    def align_bottom(self, node_ids: list[str]) -> None:
        """Align nodes to the bottommost position."""
        nodes = [self._graph.get_node(nid) for nid in node_ids]
        nodes = [n for n in nodes if n is not None]

        if not nodes:
            return

        max_y = max(n.y + n.height for n in nodes)  # type: ignore[union-attr]
        for node in nodes:
            node.y = max_y - node.height  # type: ignore[union-attr]

    def distribute_horizontal(self, node_ids: list[str]) -> None:
        """Distribute nodes evenly horizontally."""
        nodes = [self._graph.get_node(nid) for nid in node_ids]
        nodes = [n for n in nodes if n is not None]
        distribute_nodes(nodes, "horizontal")  # type: ignore[arg-type]

    def distribute_vertical(self, node_ids: list[str]) -> None:
        """Distribute nodes evenly vertically."""
        nodes = [self._graph.get_node(nid) for nid in node_ids]
        nodes = [n for n in nodes if n is not None]
        distribute_nodes(nodes, "vertical")  # type: ignore[arg-type]

    def center_nodes(self, node_ids: list[str], center_x: float = 400, center_y: float = 300) -> None:
        """Center nodes around a point."""
        nodes = [self._graph.get_node(nid) for nid in node_ids]
        nodes = [n for n in nodes if n is not None]
        center_nodes(nodes, center_x, center_y)  # type: ignore[arg-type]

    # ── Analysis Operations ────────────────────────────────────────────────

    def get_upstream_nodes(self, node_id: str) -> list[str]:
        """Get all upstream nodes (recursive)."""
        visited = set()
        queue = [node_id]

        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            for dep_id in self._graph.get_dependencies(current_id):
                if dep_id not in visited:
                    queue.append(dep_id)

        visited.discard(node_id)
        return list(visited)

    def get_downstream_nodes(self, node_id: str) -> list[str]:
        """Get all downstream nodes (recursive)."""
        visited = set()
        queue = [node_id]

        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            for dep_id in self._graph.get_dependents(current_id):
                if dep_id not in visited:
                    queue.append(dep_id)

        visited.discard(node_id)
        return list(visited)

    def find_path(self, start_node_id: str, end_node_id: str) -> list[str] | None:
        """Find a path between two nodes."""
        from collections import deque

        if start_node_id == end_node_id:
            return [start_node_id]

        visited = set()
        queue = deque([(start_node_id, [start_node_id])])

        while queue:
            current_id, path = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)

            for dep_id in self._graph.get_dependents(current_id):
                if dep_id == end_node_id:
                    return path + [dep_id]
                if dep_id not in visited:
                    queue.append((dep_id, path + [dep_id]))

        return None

    def get_node_depth(self, node_id: str) -> int:
        """Get the depth of a node in the graph."""
        upstream = self.get_upstream_nodes(node_id)
        return len(upstream)

    def get_graph_bounds(self) -> tuple[float, float, float, float]:
        """Get the bounding box of all nodes."""
        return get_bounds(list(self._graph.nodes.values()))


# ── Layout Algorithms ──────────────────────────────────────────────────────


def auto_layout(
    graph: ChainGraph, direction: str = "horizontal", spacing_x: float = 200, spacing_y: float = 100
) -> None:
    """Auto-layout graph nodes based on topological order.

    Args:
        graph: The graph to layout
        direction: Layout direction ("horizontal" or "vertical")
        spacing_x: Horizontal spacing
        spacing_y: Vertical spacing
    """
    try:
        execution_order = graph.topological_sort()
    except Exception:
        # If topological sort fails, use insertion order
        execution_order = list(graph.nodes.keys())

    # Calculate levels (depth from source nodes)
    levels: dict[str, int] = {}
    for node_id in execution_order:
        deps = graph.get_dependencies(node_id)
        if not deps:
            levels[node_id] = 0
        else:
            levels[node_id] = max(levels.get(dep, 0) for dep in deps) + 1

    # Group nodes by level
    level_groups: dict[int, list[str]] = {}
    for node_id, level in levels.items():
        if level not in level_groups:
            level_groups[level] = []
        level_groups[level].append(node_id)

    # Position nodes
    if direction == "horizontal":
        _layout_horizontal(graph, level_groups, spacing_x, spacing_y)
    else:
        _layout_vertical(graph, level_groups, spacing_x, spacing_y)


def _layout_horizontal(
    graph: ChainGraph, level_groups: dict[int, list[str]], spacing_x: float, spacing_y: float
) -> None:
    """Layout nodes horizontally (left to right)."""
    x = 50.0

    for level in sorted(level_groups.keys()):
        node_ids = level_groups[level]
        y = 50.0

        for node_id in node_ids:
            node = graph.get_node(node_id)
            if node:
                node.x = x
                node.y = y
                y += (node.height or 60) + spacing_y

        # Find max width in this level
        max_width = max((graph.get_node(nid).width or 150 for nid in node_ids if graph.get_node(nid)), default=150)  # type: ignore[union-attr]
        x += max_width + spacing_x


def _layout_vertical(graph: ChainGraph, level_groups: dict[int, list[str]], spacing_x: float, spacing_y: float) -> None:
    """Layout nodes vertically (top to bottom)."""
    y = 50.0

    for level in sorted(level_groups.keys()):
        node_ids = level_groups[level]
        x = 50.0

        for node_id in node_ids:
            node = graph.get_node(node_id)
            if node:
                node.x = x
                node.y = y
                x += (node.width or 150) + spacing_x

        # Find max height in this level
        max_height = max((graph.get_node(nid).height or 60 for nid in node_ids if graph.get_node(nid)), default=60)  # type: ignore[union-attr]
        y += max_height + spacing_y


def align_nodes(nodes: list[ChainNode], alignment: str = "left") -> None:
    """Align nodes.

    Args:
        nodes: List of nodes to align
        alignment: Alignment type ("left", "right", "top", "bottom", "center_h", "center_v")
    """
    if not nodes:
        return

    if alignment == "left":
        min_x = min(n.x for n in nodes)
        for node in nodes:
            node.x = min_x
    elif alignment == "right":
        max_x = max(n.x + n.width for n in nodes)
        for node in nodes:
            node.x = max_x - node.width
    elif alignment == "top":
        min_y = min(n.y for n in nodes)
        for node in nodes:
            node.y = min_y
    elif alignment == "bottom":
        max_y = max(n.y + n.height for n in nodes)
        for node in nodes:
            node.y = max_y - node.height
    elif alignment == "center_h":
        center_x = sum(n.x + n.width / 2 for n in nodes) / len(nodes)
        for node in nodes:
            node.x = center_x - node.width / 2
    elif alignment == "center_v":
        center_y = sum(n.y + n.height / 2 for n in nodes) / len(nodes)
        for node in nodes:
            node.y = center_y - node.height / 2


def distribute_nodes(nodes: list[ChainNode], direction: str = "horizontal") -> None:
    """Distribute nodes evenly.

    Args:
        nodes: List of nodes to distribute
        direction: Distribution direction ("horizontal" or "vertical")
    """
    if len(nodes) < 3:
        return

    if direction == "horizontal":
        nodes.sort(key=lambda n: n.x)
        total_width = sum(n.width for n in nodes)
        total_space = nodes[-1].x + nodes[-1].width - nodes[0].x
        gap = (total_space - total_width) / (len(nodes) - 1)

        x = nodes[0].x
        for node in nodes:
            node.x = x
            x += node.width + gap
    else:
        nodes.sort(key=lambda n: n.y)
        total_height = sum(n.height for n in nodes)
        total_space = nodes[-1].y + nodes[-1].height - nodes[0].y
        gap = (total_space - total_height) / (len(nodes) - 1)

        y = nodes[0].y
        for node in nodes:
            node.y = y
            y += node.height + gap


def center_nodes(nodes: list[ChainNode], center_x: float = 400, center_y: float = 300) -> None:
    """Center nodes around a point."""
    if not nodes:
        return

    # Calculate current center
    min_x = min(n.x for n in nodes)
    max_x = max(n.x + n.width for n in nodes)
    min_y = min(n.y for n in nodes)
    max_y = max(n.y + n.height for n in nodes)

    current_center_x = (min_x + max_x) / 2
    current_center_y = (min_y + max_y) / 2

    # Calculate offset
    dx = center_x - current_center_x
    dy = center_y - current_center_y

    # Apply offset
    for node in nodes:
        node.x += dx
        node.y += dy


def get_bounds(nodes: list[ChainNode]) -> tuple[float, float, float, float]:
    """Get the bounding box of nodes.

    Returns:
        Tuple of (min_x, min_y, max_x, max_y)
    """
    if not nodes:
        return (0, 0, 0, 0)

    min_x = min(n.x for n in nodes)
    min_y = min(n.y for n in nodes)
    max_x = max(n.x + n.width for n in nodes)
    max_y = max(n.y + n.height for n in nodes)

    return (min_x, min_y, max_x, max_y)


def find_nearest_port(
    graph: ChainGraph, x: float, y: float, port_direction: PortDirection | None = None, max_distance: float = 50.0
) -> tuple[ChainNode, ChainPort] | None:
    """Find the nearest port to a point."""
    best_node = None
    best_port = None
    best_distance = max_distance

    for node in graph.nodes.values():
        ports = node.inputs + node.outputs

        for port in ports:
            if port_direction and port.direction != port_direction:
                continue

            # Calculate port position
            if port.direction == PortDirection.INPUT:
                port_x = node.x
                port_y = node.y + 30  # Approximate
            else:
                port_x = node.x + node.width
                port_y = node.y + 30

            # Calculate distance
            distance = math.sqrt((x - port_x) ** 2 + (y - port_y) ** 2)

            if distance < best_distance:
                best_distance = distance
                best_node = node
                best_port = port

    if best_node and best_port:
        return (best_node, best_port)

    return None


def can_connect(
    graph: ChainGraph, source_node_id: str, source_port_id: str, target_node_id: str, target_port_id: str
) -> tuple[bool, str]:
    """Check if two ports can be connected.

    Returns:
        Tuple of (can_connect, reason)
    """
    # Check nodes exist
    source_node = graph.get_node(source_node_id)
    target_node = graph.get_node(target_node_id)

    if not source_node:
        return False, "Source node not found"
    if not target_node:
        return False, "Target node not found"

    # Check ports exist
    source_port = source_node.get_output(source_port_id)
    target_port = target_node.get_input(target_port_id)

    if not source_port:
        return False, "Source port not found"
    if not target_port:
        return False, "Target port not found"

    # Check for self-connection
    if source_node_id == target_node_id:
        return False, "Cannot connect node to itself"

    # Check if target port already has connection (unless multiple)
    if not target_port.multiple:
        existing = graph.get_connection_to_input(target_node_id, target_port_id)
        if existing:
            return False, "Target port already has a connection"

    # Check for cycles (simplified)
    # A full cycle check would require path finding

    return True, ""


def get_connection_points(graph: ChainGraph, connection: ChainConnection) -> tuple[float, float, float, float] | None:
    """Get the start and end points of a connection.

    Returns:
        Tuple of (start_x, start_y, end_x, end_y) or None
    """
    source_node = graph.get_node(connection.source_node_id)
    target_node = graph.get_node(connection.target_node_id)

    if not source_node or not target_node:
        return None

    # Find source port
    source_port = source_node.get_output(connection.source_port_id)
    if not source_port:
        return None

    # Find target port
    target_port = target_node.get_input(connection.target_port_id)
    if not target_port:
        return None

    # Calculate positions (simplified - would need port index for accurate positioning)
    source_idx = source_node.outputs.index(source_port) if source_port in source_node.outputs else 0
    target_idx = target_node.inputs.index(target_port) if target_port in target_node.inputs else 0

    start_x = source_node.x + source_node.width
    start_y = source_node.y + 30 + source_idx * 20
    end_x = target_node.x
    end_y = target_node.y + 30 + target_idx * 20

    return (start_x, start_y, end_x, end_y)
