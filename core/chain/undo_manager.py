"""Undo/redo system for action chain editing.

This module provides:
- Command pattern for undoable operations
- Undo/redo stack
- History tracking
- Batch operations
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .graph_models import ChainConnection, ChainGraph, ChainNode

__all__ = [
    "Command",
    "UndoManager",
    "AddNodeCommand",
    "RemoveNodeCommand",
    "MoveNodeCommand",
    "AddConnectionCommand",
    "RemoveConnectionCommand",
    "UpdateNodeParamCommand",
    "BatchCommand",
]

logger = logging.getLogger(__name__)


class Command(ABC):
    """Abstract base class for undoable commands."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Get a human-readable description of the command."""
        ...

    @abstractmethod
    def execute(self) -> None:
        """Execute the command."""
        ...

    @abstractmethod
    def undo(self) -> None:
        """Undo the command."""
        ...

    def redo(self) -> None:
        """Redo the command (same as execute by default)."""
        self.execute()


class AddNodeCommand(Command):
    """Command to add a node to the graph."""

    def __init__(self, graph: ChainGraph, node: ChainNode):
        self._graph = graph
        self._node = node

    @property
    def description(self) -> str:
        return f"Add node '{self._node.title}'"

    def execute(self) -> None:
        self._graph.add_node(self._node)

    def undo(self) -> None:
        self._graph.remove_node(self._node.id)


class RemoveNodeCommand(Command):
    """Command to remove a node from the graph."""

    def __init__(self, graph: ChainGraph, node_id: str):
        self._graph = graph
        self._node_id = node_id
        self._node: ChainNode | None = None
        self._connections: list[ChainConnection] = []

    @property
    def description(self) -> str:
        node = self._graph.get_node(self._node_id)
        title = node.title if node else self._node_id
        return f"Remove node '{title}'"

    def execute(self) -> None:
        # Save connections before removing
        self._connections = [
            conn for conn in self._graph.iter_connections()
            if conn.source_node_id == self._node_id or conn.target_node_id == self._node_id
        ]

        # Remove node (also removes connections)
        self._node = self._graph.remove_node(self._node_id)

    def undo(self) -> None:
        if self._node:
            self._graph.add_node(self._node)

            # Restore connections
            for conn in self._connections:
                try:
                    self._graph.add_connection(conn)
                except ValueError as exc:
                    logger.debug("撤销删除节点时跳过已失效连接: %s", exc, exc_info=True)


class MoveNodeCommand(Command):
    """Command to move a node on the canvas."""

    def __init__(self, graph: ChainGraph, node_id: str, new_x: float, new_y: float):
        self._graph = graph
        self._node_id = node_id
        self._new_x = new_x
        self._new_y = new_y
        self._old_x: float = 0.0
        self._old_y: float = 0.0

    @property
    def description(self) -> str:
        node = self._graph.get_node(self._node_id)
        title = node.title if node else self._node_id
        return f"Move node '{title}'"

    def execute(self) -> None:
        node = self._graph.get_node(self._node_id)
        if node:
            self._old_x = node.x
            self._old_y = node.y
            node.x = self._new_x
            node.y = self._new_y

    def undo(self) -> None:
        node = self._graph.get_node(self._node_id)
        if node:
            node.x = self._old_x
            node.y = self._old_y


class AddConnectionCommand(Command):
    """Command to add a connection to the graph."""

    def __init__(self, graph: ChainGraph, connection: ChainConnection):
        self._graph = graph
        self._connection = connection

    @property
    def description(self) -> str:
        return "Add connection"

    def execute(self) -> None:
        self._graph.add_connection(self._connection)

    def undo(self) -> None:
        self._graph.remove_connection(self._connection.id)


class RemoveConnectionCommand(Command):
    """Command to remove a connection from the graph."""

    def __init__(self, graph: ChainGraph, connection_id: str):
        self._graph = graph
        self._connection_id = connection_id
        self._connection: ChainConnection | None = None

    @property
    def description(self) -> str:
        return "Remove connection"

    def execute(self) -> None:
        self._connection = self._graph.remove_connection(self._connection_id)

    def undo(self) -> None:
        if self._connection:
            try:
                self._graph.add_connection(self._connection)
            except ValueError as exc:
                logger.debug("撤销删除连接时连接已失效: %s", exc, exc_info=True)


class UpdateNodeParamCommand(Command):
    """Command to update a node parameter."""

    def __init__(self, graph: ChainGraph, node_id: str, param_id: str, new_value: Any):
        self._graph = graph
        self._node_id = node_id
        self._param_id = param_id
        self._new_value = new_value
        self._old_value: Any = None

    @property
    def description(self) -> str:
        node = self._graph.get_node(self._node_id)
        title = node.title if node else self._node_id
        return f"Update parameter '{self._param_id}' on '{title}'"

    def execute(self) -> None:
        node = self._graph.get_node(self._node_id)
        if node:
            self._old_value = node.params.get(self._param_id)
            node.set_param(self._param_id, self._new_value)

    def undo(self) -> None:
        node = self._graph.get_node(self._node_id)
        if node:
            if self._old_value is None:
                node.params.pop(self._param_id, None)
            else:
                node.set_param(self._param_id, self._old_value)


class BatchCommand(Command):
    """Command that groups multiple commands together."""

    def __init__(self, commands: list[Command], description: str = "Batch operation"):
        self._commands = commands
        self._description = description

    @property
    def description(self) -> str:
        return self._description

    def execute(self) -> None:
        for cmd in self._commands:
            cmd.execute()

    def undo(self) -> None:
        # Undo in reverse order
        for cmd in reversed(self._commands):
            cmd.undo()

    def redo(self) -> None:
        # Redo in forward order
        for cmd in self._commands:
            cmd.redo()


@dataclass
class HistoryEntry:
    """An entry in the undo/redo history."""

    command: Command
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "description": self.command.description,
            "timestamp": self.timestamp,
        }


class UndoManager:
    """Manages undo/redo operations for a graph.

    This class maintains:
    - An undo stack (past states)
    - A redo stack (future states)
    - History tracking
    """

    def __init__(self, max_history: int = 100):
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self._max_history = max_history
        self._batch_commands: list[Command] = []
        self._batch_mode = False

        # Callbacks
        self._on_change: Callable[[], None] | None = None

    def set_on_change(self, callback: Callable[[], None] | None) -> None:
        """Set callback for when undo/redo state changes."""
        self._on_change = callback

    def _notify_change(self) -> None:
        """Notify that state has changed."""
        if self._on_change:
            self._on_change()

    # ── Command Execution ──────────────────────────────────────────────────

    def execute(self, command: Command) -> None:
        """Execute a command and add it to the undo stack.

        Args:
            command: The command to execute
        """
        command.execute()

        if self._batch_mode:
            self._batch_commands.append(command)
        else:
            self._push_undo(command)
            self._redo_stack.clear()
            self._notify_change()

    def _push_undo(self, command: Command) -> None:
        """Push a command to the undo stack."""
        self._undo_stack.append(command)

        # Trim history if needed
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)

    # ── Undo/Redo ──────────────────────────────────────────────────────────

    def can_undo(self) -> bool:
        """Check if there are commands to undo."""
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        """Check if there are commands to redo."""
        return len(self._redo_stack) > 0

    def undo(self) -> bool:
        """Undo the last command.

        Returns:
            True if a command was undone
        """
        if not self.can_undo():
            return False

        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)

        self._notify_change()
        return True

    def redo(self) -> bool:
        """Redo the last undone command.

        Returns:
            True if a command was redone
        """
        if not self.can_redo():
            return False

        command = self._redo_stack.pop()
        command.redo()
        self._undo_stack.append(command)

        self._notify_change()
        return True

    # ── Batch Operations ───────────────────────────────────────────────────

    def begin_batch(self) -> None:
        """Begin a batch of commands."""
        self._batch_mode = True
        self._batch_commands.clear()

    def end_batch(self, description: str = "Batch operation") -> None:
        """End a batch of commands."""
        self._batch_mode = False

        if self._batch_commands:
            batch = BatchCommand(self._batch_commands, description)
            self._push_undo(batch)
            self._redo_stack.clear()
            self._notify_change()

        self._batch_commands.clear()

    def cancel_batch(self) -> None:
        """Cancel the current batch."""
        self._batch_mode = False
        self._batch_commands.clear()

    # ── History ────────────────────────────────────────────────────────────

    def get_undo_history(self) -> list[str]:
        """Get descriptions of commands that can be undone."""
        return [cmd.description for cmd in reversed(self._undo_stack)]

    def get_redo_history(self) -> list[str]:
        """Get descriptions of commands that can be redone."""
        return [cmd.description for cmd in reversed(self._redo_stack)]

    def clear_history(self) -> None:
        """Clear all undo/redo history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._notify_change()

    @property
    def undo_count(self) -> int:
        """Get the number of commands that can be undone."""
        return len(self._undo_stack)

    @property
    def redo_count(self) -> int:
        """Get the number of commands that can be redone."""
        return len(self._redo_stack)
