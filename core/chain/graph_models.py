"""Action chain graph models.

This module implements the core graph data structures for action chains,
inspired by Grasshopper's visual programming model. It provides:
- ChainGraph: The main graph container
- ChainNode: Individual processing nodes
- ChainConnection: Connections between node ports
- ChainPort: Input/output ports on nodes

Key concepts:
- Nodes are connected via ports
- Data flows from output ports to input ports
- The graph supports topological sorting for execution
- Nodes can be disabled, cached, or marked as dirty
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .definitions import ChainPortDefinition, ChainProcessorDefinition

logger = logging.getLogger(__name__)

__all__ = [
    "NodeStatus",
    "PortDirection",
    "ChainPort",
    "ChainNode",
    "ChainConnection",
    "ChainGraph",
    "GraphValidationError",
    "CyclicGraphError",
]


class NodeStatus(str, Enum):
    """Status of a node in the graph."""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"
    DISABLED = "disabled"
    DIRTY = "dirty"  # Needs re-execution
    CACHED = "cached"  # Has cached result


class PortDirection(str, Enum):
    """Direction of a port."""
    INPUT = "input"
    OUTPUT = "output"


@dataclass
class ChainPort:
    """A port on a node that can send or receive data."""

    id: str
    label: str = ""
    direction: PortDirection = PortDirection.INPUT
    kind: str = "any"  # Base type (text, number, bool, json, list, file, folder, url)
    smart_type: str = ""  # Optional smart type for validation
    required: bool = False
    multiple: bool = False  # Can accept multiple connections
    default: Any = None
    description: str = ""
    role: str = "data"  # primary, data, control, parameter, status, diagnostic

    # Runtime state
    value: Any = None
    connected: bool = False

    def __post_init__(self):
        if not self.label:
            self.label = self.id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "label": self.label,
            "direction": self.direction.value,
            "kind": self.kind,
            "smart_type": self.smart_type,
            "required": self.required,
            "multiple": self.multiple,
            "default": self.default,
            "description": self.description,
            "role": self.role,
            "value": self.value,
            "connected": self.connected,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainPort:
        """Create from dictionary."""
        return cls(
            id=str(data.get("id") or ""),
            label=str(data.get("label") or ""),
            direction=PortDirection(data.get("direction", "input")),
            kind=str(data.get("kind") or "any"),
            smart_type=str(data.get("smart_type") or ""),
            required=bool(data.get("required", False)),
            multiple=bool(data.get("multiple", False)),
            default=data.get("default"),
            description=str(data.get("description") or ""),
            role=str(data.get("role") or "data"),
            value=data.get("value"),
            connected=bool(data.get("connected", False)),
        )

    @classmethod
    def from_definition(cls, port_def: ChainPortDefinition, direction: PortDirection) -> ChainPort:
        """Create from ChainPortDefinition."""
        return cls(
            id=port_def.id,
            label=port_def.label,
            direction=direction,
            kind=port_def.kind,
            required=port_def.required,
            multiple=port_def.multiple,
            default=port_def.default,
            description=port_def.description,
            role=port_def.role,
        )


@dataclass
class ChainNode:
    """A processing node in the action chain graph.

    Each node has:
    - A unique identifier
    - A processor type (e.g., "text_replace", "math_add")
    - Input and output ports
    - Position on the canvas
    - Runtime state (status, cached values)
    """

    id: str
    processor_id: str  # Type of processor (e.g., "text_replace")
    title: str = ""
    category: str = ""
    description: str = ""

    # Ports
    inputs: list[ChainPort] = field(default_factory=list)
    outputs: list[ChainPort] = field(default_factory=list)

    # Canvas position
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0

    # Runtime state
    status: NodeStatus = NodeStatus.IDLE
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    execution_time: float = 0.0

    # Configuration
    enabled: bool = True
    collapsed: bool = False
    color: str = ""
    notes: str = ""

    # Parameters (static values set by user)
    params: dict[str, Any] = field(default_factory=dict)

    # Cached results
    cached_outputs: dict[str, Any] = field(default_factory=dict)
    cache_valid: bool = False

    def __post_init__(self):
        if not self.title:
            self.title = self.processor_id
        if not self.id:
            self.id = str(uuid.uuid4())

    def __str__(self) -> str:
        return f"ChainNode({self.id}, {self.processor_id})"

    def __repr__(self) -> str:
        return f"ChainNode(id={self.id!r}, processor_id={self.processor_id!r}, status={self.status})"

    @property
    def is_source(self) -> bool:
        """Check if this node has no input connections."""
        return not any(inp.connected for inp in self.inputs)

    @property
    def is_sink(self) -> bool:
        """Check if this node has no output connections."""
        return not any(out.connected for out in self.outputs)

    @property
    def input_ports(self) -> list[ChainPort]:
        """Get input ports."""
        return [p for p in self.inputs if p.direction == PortDirection.INPUT]

    @property
    def output_ports(self) -> list[ChainPort]:
        """Get output ports."""
        return [p for p in self.outputs if p.direction == PortDirection.OUTPUT]

    def get_port(self, port_id: str, direction: PortDirection | None = None) -> ChainPort | None:
        """Get a port by ID and optional direction."""
        ports = self.inputs + self.outputs
        for port in ports:
            if port.id == port_id:
                if direction is None or port.direction == direction:
                    return port
        return None

    def get_input(self, port_id: str) -> ChainPort | None:
        """Get an input port by ID."""
        return self.get_port(port_id, PortDirection.INPUT)

    def get_output(self, port_id: str) -> ChainPort | None:
        """Get an output port by ID."""
        return self.get_port(port_id, PortDirection.OUTPUT)

    def set_param(self, key: str, value: Any) -> None:
        """Set a parameter value."""
        self.params[key] = value
        self.mark_dirty()

    def get_param(self, key: str, default: Any = None) -> Any:
        """Get a parameter value."""
        return self.params.get(key, default)

    def mark_dirty(self) -> None:
        """Mark node as needing re-execution."""
        self.cache_valid = False
        self.cached_outputs.clear()
        if self.status != NodeStatus.DISABLED:
            self.status = NodeStatus.DIRTY

    def mark_success(self, outputs: dict[str, Any] | None = None) -> None:
        """Mark node as successfully executed."""
        self.status = NodeStatus.SUCCESS
        self.error = ""
        if outputs:
            self.cached_outputs = outputs
            self.cache_valid = True

    def mark_failed(self, error: str) -> None:
        """Mark node as failed."""
        self.status = NodeStatus.FAILED
        self.error = error

    def disable(self) -> None:
        """Disable this node."""
        self.status = NodeStatus.DISABLED
        self.enabled = False

    def enable(self) -> None:
        """Enable this node."""
        self.enabled = True
        if self.status == NodeStatus.DISABLED:
            self.status = NodeStatus.DIRTY

    def clear_cache(self) -> None:
        """Clear cached results."""
        self.cached_outputs.clear()
        self.cache_valid = False
        if self.status == NodeStatus.CACHED:
            self.status = NodeStatus.DIRTY

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "processor_id": self.processor_id,
            "title": self.title,
            "category": self.category,
            "description": self.description,
            "inputs": [p.to_dict() for p in self.inputs],
            "outputs": [p.to_dict() for p in self.outputs],
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "status": self.status.value,
            "error": self.error,
            "warnings": list(self.warnings),
            "execution_time": self.execution_time,
            "enabled": self.enabled,
            "collapsed": self.collapsed,
            "color": self.color,
            "notes": self.notes,
            "params": dict(self.params),
            "cached_outputs": dict(self.cached_outputs),
            "cache_valid": self.cache_valid,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainNode:
        """Create from dictionary."""
        node = cls(
            id=str(data.get("id") or str(uuid.uuid4())),
            processor_id=str(data.get("processor_id") or ""),
            title=str(data.get("title") or ""),
            category=str(data.get("category") or ""),
            description=str(data.get("description") or ""),
            x=float(data.get("x") or 0),
            y=float(data.get("y") or 0),
            width=float(data.get("width") or 0),
            height=float(data.get("height") or 0),
            status=NodeStatus(data.get("status", "idle")),
            error=str(data.get("error") or ""),
            warnings=list(data.get("warnings") or []),
            execution_time=float(data.get("execution_time") or 0),
            enabled=bool(data.get("enabled", True)),
            collapsed=bool(data.get("collapsed", False)),
            color=str(data.get("color") or ""),
            notes=str(data.get("notes") or ""),
            params=dict(data.get("params") or {}),
            cached_outputs=dict(data.get("cached_outputs") or {}),
            cache_valid=bool(data.get("cache_valid", False)),
        )

        # Load ports
        for inp_data in data.get("inputs") or []:
            node.inputs.append(ChainPort.from_dict(inp_data))
        for out_data in data.get("outputs") or []:
            node.outputs.append(ChainPort.from_dict(out_data))

        return node

    @classmethod
    def from_definition(cls, definition: ChainProcessorDefinition,
                        node_id: str | None = None, x: float = 0, y: float = 0) -> ChainNode:
        """Create a node from a processor definition."""
        node = cls(
            id=node_id or str(uuid.uuid4()),
            processor_id=definition.id,
            title=definition.title,
            category=definition.category,
            description=definition.description,
            x=x,
            y=y,
        )

        # Create input ports
        for port_def in definition.inputs:
            port = ChainPort.from_definition(port_def, PortDirection.INPUT)
            node.inputs.append(port)

        # Create output ports
        for port_def in definition.outputs:
            port = ChainPort.from_definition(port_def, PortDirection.OUTPUT)
            node.outputs.append(port)

        # Set default params
        for param in definition.params:
            if param.default:
                node.params[param.id] = param.default

        return node


@dataclass
class ChainConnection:
    """A connection between two node ports.

    Connections define the data flow in the graph:
    - Data flows from source (output port) to target (input port)
    - Each connection has a unique ID
    - Connections can be enabled/disabled
    """

    id: str
    source_node_id: str  # Node that produces data
    source_port_id: str  # Output port ID
    target_node_id: str  # Node that consumes data
    target_port_id: str  # Input port ID

    # State
    enabled: bool = True
    valid: bool = True
    error: str = ""

    # Visual
    color: str = ""
    style: str = "solid"  # solid, dashed, dotted

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def __str__(self) -> str:
        return f"{self.source_node_id}.{self.source_port_id} -> {self.target_node_id}.{self.target_port_id}"

    def __repr__(self) -> str:
        return f"ChainConnection({self.id}, {self})"

    @property
    def source_key(self) -> str:
        """Get source identifier."""
        return f"{self.source_node_id}.{self.source_port_id}"

    @property
    def target_key(self) -> str:
        """Get target identifier."""
        return f"{self.target_node_id}.{self.target_port_id}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "source_node_id": self.source_node_id,
            "source_port_id": self.source_port_id,
            "target_node_id": self.target_node_id,
            "target_port_id": self.target_port_id,
            "enabled": self.enabled,
            "valid": self.valid,
            "error": self.error,
            "color": self.color,
            "style": self.style,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainConnection:
        """Create from dictionary."""
        return cls(
            id=str(data.get("id") or str(uuid.uuid4())),
            source_node_id=str(data.get("source_node_id") or data.get("source_node") or data.get("source") or ""),
            source_port_id=str(data.get("source_port_id") or data.get("source_port") or data.get("sourcePort") or "output"),
            target_node_id=str(data.get("target_node_id") or data.get("target_node") or data.get("target") or ""),
            target_port_id=str(data.get("target_port_id") or data.get("target_port") or data.get("targetPort") or "input"),
            enabled=bool(data.get("enabled", True)),
            valid=bool(data.get("valid", True)),
            error=str(data.get("error") or ""),
            color=str(data.get("color") or ""),
            style=str(data.get("style") or "solid"),
        )


class GraphValidationError(Exception):
    """Raised when graph validation fails."""
    pass


class CyclicGraphError(GraphValidationError):
    """Raised when a cycle is detected in the graph."""
    pass


@dataclass
class ChainGraph:
    """The main graph container for action chains.

    ChainGraph manages:
    - Nodes (processing units)
    - Connections (data flow between nodes)
    - Graph-level metadata and settings

    It provides methods for:
    - Adding/removing nodes and connections
    - Validating the graph structure
    - Topological sorting for execution
    - Serialization/deserialization
    """

    id: str = ""
    name: str = ""
    description: str = ""

    # Nodes and connections
    nodes: dict[str, ChainNode] = field(default_factory=dict)
    connections: dict[str, ChainConnection] = field(default_factory=dict)

    # Metadata
    version: str = "1.0"
    author: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: float = 0.0
    modified_at: float = 0.0

    # Settings
    auto_validate: bool = True
    stop_on_error: bool = True
    max_execution_time: float = 0.0  # 0 = no limit

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def __str__(self) -> str:
        return f"ChainGraph({self.name}, {len(self.nodes)} nodes, {len(self.connections)} connections)"

    def __repr__(self) -> str:
        return f"ChainGraph(id={self.id!r}, name={self.name!r})"

    # ── Node Operations ────────────────────────────────────────────────────

    def add_node(self, node: ChainNode) -> None:
        """Add a node to the graph."""
        if node.id in self.nodes:
            raise ValueError(f"Node with ID {node.id} already exists")
        self.nodes[node.id] = node

    def remove_node(self, node_id: str) -> ChainNode | None:
        """Remove a node and all its connections."""
        node = self.nodes.pop(node_id, None)
        if node is None:
            return None

        # Remove all connections to/from this node
        to_remove = [
            conn_id for conn_id, conn in self.connections.items()
            if conn.source_node_id == node_id or conn.target_node_id == node_id
        ]
        for conn_id in to_remove:
            del self.connections[conn_id]

        return node

    def get_node(self, node_id: str) -> ChainNode | None:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        """Check if a node exists."""
        return node_id in self.nodes

    def node_count(self) -> int:
        """Get the number of nodes."""
        return len(self.nodes)

    def iter_nodes(self) -> Iterator[ChainNode]:
        """Iterate over all nodes."""
        return iter(self.nodes.values())

    def get_nodes_by_processor(self, processor_id: str) -> list[ChainNode]:
        """Get all nodes of a specific processor type."""
        return [n for n in self.nodes.values() if n.processor_id == processor_id]

    def get_nodes_by_status(self, status: NodeStatus) -> list[ChainNode]:
        """Get all nodes with a specific status."""
        return [n for n in self.nodes.values() if n.status == status]

    def get_source_nodes(self) -> list[ChainNode]:
        """Get all source nodes (no input connections)."""
        return [n for n in self.nodes.values() if n.is_source]

    def get_sink_nodes(self) -> list[ChainNode]:
        """Get all sink nodes (no output connections)."""
        return [n for n in self.nodes.values() if n.is_sink]

    # ── Connection Operations ──────────────────────────────────────────────

    def add_connection(self, connection: ChainConnection) -> None:
        """Add a connection to the graph."""
        # Validate that nodes exist
        if connection.source_node_id not in self.nodes:
            raise ValueError(f"Source node {connection.source_node_id} not found")
        if connection.target_node_id not in self.nodes:
            raise ValueError(f"Target node {connection.target_node_id} not found")

        # Validate that ports exist
        source_node = self.nodes[connection.source_node_id]
        target_node = self.nodes[connection.target_node_id]

        source_port = source_node.get_output(connection.source_port_id)
        if source_port is None:
            raise ValueError(f"Output port {connection.source_port_id} not found on node {connection.source_node_id}")

        target_port = target_node.get_input(connection.target_port_id)
        if target_port is None:
            raise ValueError(f"Input port {connection.target_port_id} not found on node {connection.target_node_id}")

        # Check for existing connection to same input (unless multiple is allowed)
        if not target_port.multiple:
            existing = self.get_connection_to_input(connection.target_node_id, connection.target_port_id)
            if existing:
                raise ValueError(f"Input port {connection.target_port_id} already has a connection")

        # Check for self-connection
        if connection.source_node_id == connection.target_node_id:
            raise ValueError("Cannot connect a node to itself")

        self.connections[connection.id] = connection

        # Update port connection state
        source_port.connected = True
        target_port.connected = True

    def remove_connection(self, connection_id: str) -> ChainConnection | None:
        """Remove a connection."""
        conn = self.connections.pop(connection_id, None)
        if conn is None:
            return None

        # Update port connection state
        source_node = self.nodes.get(conn.source_node_id)
        target_node = self.nodes.get(conn.target_node_id)

        if source_node:
            port = source_node.get_output(conn.source_port_id)
            if port:
                # Check if port has other connections
                port.connected = self._port_has_connections(conn.source_node_id, conn.source_port_id, PortDirection.OUTPUT)

        if target_node:
            port = target_node.get_input(conn.target_port_id)
            if port:
                port.connected = False

        return conn

    def get_connection(self, connection_id: str) -> ChainConnection | None:
        """Get a connection by ID."""
        return self.connections.get(connection_id)

    def has_connection(self, connection_id: str) -> bool:
        """Check if a connection exists."""
        return connection_id in self.connections

    def connection_count(self) -> int:
        """Get the number of connections."""
        return len(self.connections)

    def iter_connections(self) -> Iterator[ChainConnection]:
        """Iterate over all connections."""
        return iter(self.connections.values())

    def get_connections_from_node(self, node_id: str) -> list[ChainConnection]:
        """Get all connections from a node."""
        return [c for c in self.connections.values() if c.source_node_id == node_id]

    def get_connections_to_node(self, node_id: str) -> list[ChainConnection]:
        """Get all connections to a node."""
        return [c for c in self.connections.values() if c.target_node_id == node_id]

    def get_connection_to_input(self, node_id: str, port_id: str) -> ChainConnection | None:
        """Get the connection to a specific input port."""
        for conn in self.connections.values():
            if conn.target_node_id == node_id and conn.target_port_id == port_id:
                return conn
        return None

    def get_connections_from_output(self, node_id: str, port_id: str) -> list[ChainConnection]:
        """Get all connections from a specific output port."""
        return [
            c for c in self.connections.values()
            if c.source_node_id == node_id and c.source_port_id == port_id
        ]

    def _port_has_connections(self, node_id: str, port_id: str, direction: PortDirection) -> bool:
        """Check if a port has any connections."""
        if direction == PortDirection.OUTPUT:
            return any(
                c.source_node_id == node_id and c.source_port_id == port_id
                for c in self.connections.values()
            )
        else:
            return any(
                c.target_node_id == node_id and c.target_port_id == port_id
                for c in self.connections.values()
            )

    # ── Graph Analysis ─────────────────────────────────────────────────────

    def get_dependencies(self, node_id: str) -> list[str]:
        """Get all nodes that a node depends on (upstream nodes)."""
        deps = set()
        for conn in self.connections.values():
            if conn.target_node_id == node_id:
                deps.add(conn.source_node_id)
        return list(deps)

    def get_dependents(self, node_id: str) -> list[str]:
        """Get all nodes that depend on a node (downstream nodes)."""
        deps = set()
        for conn in self.connections.values():
            if conn.source_node_id == node_id:
                deps.add(conn.target_node_id)
        return list(deps)

    def topological_sort(self) -> list[str]:
        """Sort nodes in topological order for execution.

        Returns:
            List of node IDs in execution order

        Raises:
            CyclicGraphError: If the graph contains a cycle
        """
        # Kahn's algorithm
        in_degree: dict[str, int] = {node_id: 0 for node_id in self.nodes}

        # Calculate in-degrees
        for conn in self.connections.values():
            if conn.enabled:
                in_degree[conn.target_node_id] += 1

        # Find nodes with no incoming edges
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node_id = queue.pop(0)
            result.append(node_id)

            # Reduce in-degree for downstream nodes
            for conn in self.connections.values():
                if conn.enabled and conn.source_node_id == node_id:
                    in_degree[conn.target_node_id] -= 1
                    if in_degree[conn.target_node_id] == 0:
                        queue.append(conn.target_node_id)

        # Check for cycles
        if len(result) != len(self.nodes):
            # Find nodes involved in cycle
            cycle_nodes = [node_id for node_id, degree in in_degree.items() if degree > 0]
            raise CyclicGraphError(
                f"Graph contains a cycle involving nodes: {cycle_nodes}"
            )

        return result

    def has_cycle(self) -> bool:
        """Check if the graph contains a cycle."""
        try:
            self.topological_sort()
            return False
        except CyclicGraphError:
            return True

    def validate(self) -> list[dict[str, Any]]:
        """Validate the graph structure.

        Returns:
            List of validation issues (empty if valid)
        """
        issues: list[dict[str, Any]] = []

        # Check for empty graph
        if not self.nodes:
            issues.append({
                "level": "warning",
                "code": "graph.empty",
                "message": "Graph has no nodes",
            })
            return issues

        # Check for cycles
        try:
            self.topological_sort()
        except CyclicGraphError as e:
            issues.append({
                "level": "error",
                "code": "graph.cycle",
                "message": str(e),
            })

        # Validate each node
        for node in self.nodes.values():
            node_issues = self._validate_node(node)
            issues.extend(node_issues)

        # Validate connections
        for conn in self.connections.values():
            conn_issues = self._validate_connection(conn)
            issues.extend(conn_issues)

        # Check for disconnected nodes
        for node in self.nodes.values():
            if node.is_source and node.is_sink and len(self.nodes) > 1:
                issues.append({
                    "level": "warning",
                    "code": "node.disconnected",
                    "message": f"Node '{node.title}' is disconnected",
                    "node_id": node.id,
                })

        return issues

    def _validate_node(self, node: ChainNode) -> list[dict[str, Any]]:
        """Validate a single node."""
        issues: list[dict[str, Any]] = []

        # Check required inputs
        for port in node.inputs:
            if port.required and not port.connected:
                # Check if there's a default value
                if port.default is None:
                    issues.append({
                        "level": "error",
                        "code": "port.required",
                        "message": f"Required input '{port.label}' on node '{node.title}' is not connected",
                        "node_id": node.id,
                        "port_id": port.id,
                    })

        return issues

    def _validate_connection(self, conn: ChainConnection) -> list[dict[str, Any]]:
        """Validate a single connection."""
        issues: list[dict[str, Any]] = []

        # Check that nodes exist
        if conn.source_node_id not in self.nodes:
            issues.append({
                "level": "error",
                "code": "connection.source_missing",
                "message": f"Source node {conn.source_node_id} not found",
                "connection_id": conn.id,
            })

        if conn.target_node_id not in self.nodes:
            issues.append({
                "level": "error",
                "code": "connection.target_missing",
                "message": f"Target node {conn.target_node_id} not found",
                "connection_id": conn.id,
            })

        return issues

    # ── Graph Operations ───────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all nodes and connections."""
        self.nodes.clear()
        self.connections.clear()

    def mark_all_dirty(self) -> None:
        """Mark all nodes as needing re-execution."""
        for node in self.nodes.values():
            if node.enabled:
                node.mark_dirty()

    def clear_all_caches(self) -> None:
        """Clear all cached results."""
        for node in self.nodes.values():
            node.clear_cache()

    def get_execution_plan(self) -> list[list[str]]:
        """Get an execution plan with parallel groups.

        Returns:
            List of groups, where each group contains node IDs that can be executed in parallel
        """
        # Topological sort
        sorted_nodes = self.topological_sort()

        # Calculate levels
        levels: dict[str, int] = {}
        for node_id in sorted_nodes:
            deps = self.get_dependencies(node_id)
            if not deps:
                levels[node_id] = 0
            else:
                levels[node_id] = max(levels.get(dep, 0) for dep in deps) + 1

        # Group by level
        max_level = max(levels.values()) if levels else 0
        groups: list[list[str]] = []
        for level in range(max_level + 1):
            group = [node_id for node_id, level_num in levels.items() if level_num == level]
            if group:
                groups.append(group)

        return groups

    def clone(self) -> ChainGraph:
        """Create a deep copy of the graph."""
        data = self.to_dict()
        return ChainGraph.from_dict(data)

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "connections": {conn_id: conn.to_dict() for conn_id, conn in self.connections.items()},
            "version": self.version,
            "author": self.author,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "auto_validate": self.auto_validate,
            "stop_on_error": self.stop_on_error,
            "max_execution_time": self.max_execution_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainGraph:
        """Create from dictionary."""
        graph = cls(
            id=str(data.get("id") or str(uuid.uuid4())),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            version=str(data.get("version") or "1.0"),
            author=str(data.get("author") or ""),
            tags=list(data.get("tags") or []),
            created_at=float(data.get("created_at") or 0),
            modified_at=float(data.get("modified_at") or 0),
            auto_validate=bool(data.get("auto_validate", True)),
            stop_on_error=bool(data.get("stop_on_error", True)),
            max_execution_time=float(data.get("max_execution_time") or 0),
        )

        # Load nodes
        for node_id, node_data in data.get("nodes", {}).items():
            node = ChainNode.from_dict(node_data)
            graph.nodes[node_id] = node

        # Load connections
        for conn_id, conn_data in data.get("connections", {}).items():
            conn = ChainConnection.from_dict(conn_data)
            graph.connections[conn_id] = conn

        return graph

    def to_json(self) -> str:
        """Convert to JSON string."""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> ChainGraph:
        """Create from JSON string."""
        import json
        data = json.loads(json_str)
        return cls.from_dict(data)

    # ── Legacy Compatibility ───────────────────────────────────────────────

    def to_canvas_dict(self) -> dict[str, Any]:
        """Convert to legacy canvas format for backward compatibility."""
        nodes_data = []
        try:
            execution_order = self.topological_sort()
        except Exception:
            execution_order = list(self.nodes.keys())

        for index, node_id in enumerate(execution_order, start=1):
            node = self.nodes[node_id]
            args = {
                key: value
                for key, value in node.params.items()
                if key not in {"shortcut_id", "input_binding", "stop_on_error", "delay_ms"}
            }
            node_data = {
                "id": node.id,
                "node_type": "shortcut" if node.processor_id == "shortcut" else "processor",
                "shortcut_id": str(node.params.get("shortcut_id") or "") if node.processor_id == "shortcut" else "",
                "processor_id": "" if node.processor_id == "shortcut" else node.processor_id,
                "source": str(node.params.get("source") or ""),
                "x": node.x,
                "y": node.y,
                "order": index,
                "width": node.width,
                "height": node.height,
                "title": node.title,
                "args": args,
                "enabled": node.enabled,
                "stop_on_error": bool(node.params.get("stop_on_error", self.stop_on_error)),
                "delay_ms": int(node.params.get("delay_ms") or 0),
                "collapsed": node.collapsed,
                "color": node.color,
            }
            nodes_data.append(node_data)

        connections_data = []
        for conn in self.connections.values():
            conn_data = {
                "id": conn.id,
                "source_node": conn.source_node_id,
                "source_port": conn.source_port_id,
                "target_node": conn.target_node_id,
                "target_port": conn.target_port_id,
                "enabled": conn.enabled,
            }
            connections_data.append(conn_data)

        return {
            "version": 1,
            "nodes": nodes_data,
            "connections": connections_data,
            "name": self.name,
            "description": self.description,
        }

    @classmethod
    def from_canvas_dict(cls, data: dict[str, Any],
                         processor_lookup: dict[str, ChainProcessorDefinition] | None = None) -> ChainGraph:
        """Create from legacy canvas format."""
        graph = cls(
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
        )

        # Load nodes
        for node_data in data.get("nodes", []):
            node_type = str(node_data.get("node_type") or "").strip().lower()
            if node_type == "shortcut":
                processor_id = "shortcut"
            else:
                processor_id = str(node_data.get("type") or node_data.get("processor_id") or "")

            # Try to get processor definition
            definition = None
            if processor_lookup and processor_id in processor_lookup:
                definition = processor_lookup[processor_id]

            if definition:
                node = ChainNode.from_definition(
                    definition,
                    node_id=str(node_data.get("id") or ""),
                    x=float(node_data.get("x") or 0),
                    y=float(node_data.get("y") or 0),
                )
            else:
                node = ChainNode(
                    id=str(node_data.get("id") or str(uuid.uuid4())),
                    processor_id=processor_id,
                    title=str(node_data.get("title") or processor_id),
                    x=float(node_data.get("x") or 0),
                    y=float(node_data.get("y") or 0),
                    width=float(node_data.get("width") or 0),
                    height=float(node_data.get("height") or 0),
                )

            # Load params
            node.params = dict(node_data.get("params") or node_data.get("args") or {})
            if processor_id == "shortcut":
                node.params["shortcut_id"] = str(node_data.get("shortcut_id") or node.params.get("shortcut_id") or "")
            if "source" in node_data:
                node.params["source"] = str(node_data.get("source") or "")
            node.params["stop_on_error"] = bool(node_data.get("stop_on_error", True))
            node.params["delay_ms"] = int(node_data.get("delay_ms") or 0)
            node.enabled = bool(node_data.get("enabled", True))
            node.collapsed = bool(node_data.get("collapsed", False))
            node.color = str(node_data.get("color") or "")

            graph.add_node(node)

        # Load connections
        for conn_data in data.get("connections", []):
            conn = ChainConnection.from_dict(conn_data)
            source_node = graph.get_node(conn.source_node_id)
            if source_node and source_node.get_output(conn.source_port_id) is None:
                source_node.outputs.append(
                    ChainPort(id=conn.source_port_id, direction=PortDirection.OUTPUT)
                )
            target_node = graph.get_node(conn.target_node_id)
            if target_node and target_node.get_input(conn.target_port_id) is None:
                target_node.inputs.append(
                    ChainPort(id=conn.target_port_id, direction=PortDirection.INPUT, multiple=True)
                )

            try:
                graph.add_connection(conn)
            except ValueError as exc:
                logger.debug("跳过无效图连接: %s", exc, exc_info=True)

        return graph
