"""QuickLauncher Plugin SDK v1.

This package intentionally has no imports from ``core`` or ``ui``. Host
adapters translate these DTOs once at the plugin boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from .worker_protocol import PROTOCOL_VERSION

API_VERSION = "1.0"
PREVIOUS_API_VERSION = "0.9"
COMMAND_INTERACTION_DIRECT = "direct"
COMMAND_INTERACTION_PANEL = "panel"


class Capability(StrEnum):
    COMMANDS = "commands"
    SEARCH = "search"
    PROCESSORS = "processors"
    HOST_CALLS = "host_calls"
    PROGRESS = "progress"
    CANCELLATION = "cancellation"


class SDKErrorCode(StrEnum):
    INCOMPATIBLE_VERSION = "incompatible_version"
    MISSING_CAPABILITY = "missing_capability"
    PERMISSION_DENIED = "permission_denied"
    INVALID_REGISTRATION = "invalid_registration"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    WORKER_UNAVAILABLE = "worker_unavailable"


@dataclass(frozen=True)
class CompatibilityResult:
    compatible: bool
    missing_capabilities: frozenset[str] = frozenset()
    error_code: SDKErrorCode | None = None


def negotiate_api(
    plugin_version: str,
    plugin_capabilities: set[str] | frozenset[str],
    required_capabilities: set[str] | frozenset[str] = frozenset(),
) -> CompatibilityResult:
    if plugin_version not in {API_VERSION, PREVIOUS_API_VERSION}:
        return CompatibilityResult(False, error_code=SDKErrorCode.INCOMPATIBLE_VERSION)
    missing = frozenset(str(item) for item in required_capabilities) - frozenset(
        str(item) for item in plugin_capabilities
    )
    if missing:
        return CompatibilityResult(False, missing, SDKErrorCode.MISSING_CAPABILITY)
    return CompatibilityResult(True)


class PluginHost(Protocol):
    """Stable surface supplied to plugin ``register(api)`` functions."""

    def register_command(self, id: str, title: str, handler: Callable[..., Any], **kwargs: Any) -> bool: ...

    def register_search_source(
        self, source_id: str, handler: Callable[..., Any] | None = None, **kwargs: Any
    ) -> Any: ...

    def register_chain_processor(self, definition: dict[str, Any], handler: Callable[..., Any]) -> bool: ...

    def register_module(self, module_id: str, manifest_path: str = "module.json") -> bool: ...


@dataclass(frozen=True)
class CommandParam:
    name: str
    type: str = "text"
    required: bool = False
    default: str = ""
    choices: list[str] = field(default_factory=list)
    sensitive: bool = False
    label: str = ""
    placeholder: str = ""
    help: str = ""
    multiline: bool = False
    remember: bool = True
    source: str = ""
    validator: str = ""
    pattern: str = ""
    min_value: str = ""
    max_value: str = ""
    advanced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


@dataclass(frozen=True)
class CommandAction:
    type: str = "copy"
    label: str = ""
    value: str = ""
    enabled: bool = True
    danger: bool = False
    primary: bool = False
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


@dataclass(frozen=True)
class CommandResult:
    success: bool = True
    message: str = ""
    display_type: str = "text"
    payload: dict[str, Any] = field(default_factory=dict)
    actions: list[CommandAction | dict[str, Any]] = field(default_factory=list)
    error: str = ""
    is_async: bool = False
    progress: float = 0.0
    cancellable: bool = False

    def to_dict(self) -> dict[str, Any]:
        actions = [action.to_dict() if isinstance(action, CommandAction) else dict(action) for action in self.actions]
        return {
            "success": self.success,
            "message": self.message,
            "display_type": self.display_type,
            "payload": dict(self.payload),
            "actions": actions,
            "error": self.error,
            "is_async": self.is_async,
            "progress": self.progress,
            "cancellable": self.cancellable,
        }


__all__ = [
    "API_VERSION",
    "PREVIOUS_API_VERSION",
    "Capability",
    "CompatibilityResult",
    "COMMAND_INTERACTION_DIRECT",
    "COMMAND_INTERACTION_PANEL",
    "CommandAction",
    "CommandParam",
    "CommandResult",
    "PluginHost",
    "PROTOCOL_VERSION",
    "SDKErrorCode",
    "negotiate_api",
]
