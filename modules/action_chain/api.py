"""Public module API contracts for Action Chain."""

from __future__ import annotations

from typing import Any, Protocol

from core.command_registry import CommandResult


class ActionChainModuleAPI(Protocol):
    module_version: str
    schema_version: int
    api_version: str

    def is_available(self) -> bool:
        ...

    def availability_status(self) -> str:
        ...

    def open_editor(self, parent, chain_data: dict[str, Any] | None = None) -> dict[str, Any] | None:
        ...

    def execute_chain(self, chain_data: Any, context: dict[str, Any], cancel_event=None) -> CommandResult:
        ...

    def validate_chain(self, chain_data: Any) -> list[dict[str, Any]]:
        ...

    def migrate_chain_data(self, chain_data: dict[str, Any], from_schema: int) -> dict[str, Any]:
        ...

    def list_processors(self) -> list[dict[str, Any]]:
        ...

