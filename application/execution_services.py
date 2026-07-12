"""Explicit runtime dependencies shared by execution entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionServices:
    data_manager: Any = None
    plugin_manager: Any = None
    command_registry: Any = None
