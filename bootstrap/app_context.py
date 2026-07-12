"""Explicit application context created only by the composition root."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.ports.ui_actions import UIActions
from application.state import StateStore
from bootstrap.lifecycle import LifecycleManager


@dataclass(frozen=True)
class AppContext:
    lifecycle: LifecycleManager
    state_store: StateStore
    ui_actions: UIActions
    command_registry: Any
    data_manager: Any
    plugin_manager: Any | None = None

    def start(self) -> None:
        self.lifecycle.start()

    def shutdown(self) -> list[str]:
        return self.lifecycle.shutdown()
