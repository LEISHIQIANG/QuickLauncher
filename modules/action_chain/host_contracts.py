"""Host API contracts for the action-chain module boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class HostShortcut:
    id: str
    name: str
    type: str
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class ActionChainHostAPI(Protocol):
    host_version: str
    api_version: str

    def list_shortcuts(self) -> list[dict[str, Any]]:
        ...

    def get_shortcut(self, shortcut_id: str) -> Any | None:
        ...

    def execute_shortcut(self, shortcut_id: str, invocation: dict[str, Any], cancel_event=None) -> dict[str, Any]:
        ...

    def get_settings(self) -> dict[str, Any]:
        ...

    def get_theme(self) -> str:
        ...

    def show_toast(self, message: str, level: str = "info") -> None:
        ...

    def choose_file(self, options: dict[str, Any]) -> str:
        ...

    def choose_folder(self, options: dict[str, Any]) -> str:
        ...

    def log_event(self, event: dict[str, Any]) -> None:
        ...

    def check_permission(self, capability: str) -> bool:
        ...

    def request_confirmation(self, request: dict[str, Any]) -> bool:
        ...

