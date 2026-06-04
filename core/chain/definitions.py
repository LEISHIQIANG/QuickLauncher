"""Action chain processor definitions.

This module contains all the dataclass definitions for action chain processors,
including port definitions, parameter definitions, safety definitions, and
processor definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ChainPortDefinition",
    "ChainParamDefinition",
    "ChainProcessorSafety",
    "ChainProcessorExample",
    "ChainProcessorDefinition",
    "KNOWN_PROCESSOR_PORT_KINDS",
    "KNOWN_PROCESSOR_PARAM_KINDS",
    "KNOWN_PROCESSOR_SAFETY_LEVELS",
    "KNOWN_PROCESSOR_PORT_ROLES",
]

KNOWN_PROCESSOR_PORT_KINDS = {"any", "text", "json", "file", "folder", "url", "list", "number", "bool"}
KNOWN_PROCESSOR_PARAM_KINDS = KNOWN_PROCESSOR_PORT_KINDS | {"textarea", "choice", "password"}
KNOWN_PROCESSOR_SAFETY_LEVELS = {"safe", "caution", "dangerous"}
KNOWN_PROCESSOR_PORT_ROLES = {
    "primary",
    "data",
    "status",
    "diagnostic",
    "collection",
    "metadata",
    "stream",
    "control",
    "parameter",
}


@dataclass(frozen=True)
class ChainPortDefinition:
    """Definition of a processor port (input or output)."""

    id: str
    label: str = ""
    kind: str = "text"
    required: bool = False
    multiple: bool = False
    default: str = ""
    description: str = ""
    role: str = "data"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "required": self.required,
            "multiple": self.multiple,
            "default": self.default,
            "description": self.description,
            "role": self.role,
        }


@dataclass(frozen=True)
class ChainParamDefinition:
    """Definition of a processor parameter."""

    id: str
    label: str
    kind: str = "text"
    default: str = ""
    choices: list[str] = field(default_factory=list)
    multiline: bool = False
    required: bool = False
    placeholder: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "default": self.default,
            "choices": list(self.choices),
            "multiline": self.multiline,
            "required": self.required,
            "placeholder": self.placeholder,
            "description": self.description,
        }


@dataclass(frozen=True)
class ChainProcessorSafety:
    """Safety classification for a processor."""

    level: str = "safe"
    reads_files: bool = False
    writes_files: bool = False
    network: bool = False
    executes_code: bool = False
    requires_confirmation: bool = False
    capability: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "reads_files": self.reads_files,
            "writes_files": self.writes_files,
            "network": self.network,
            "executes_code": self.executes_code,
            "requires_confirmation": self.requires_confirmation,
            "capability": self.capability,
        }


@dataclass(frozen=True)
class ChainProcessorExample:
    """Example usage of a processor."""

    title: str
    args: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "args": dict(self.args), "expected": dict(self.expected)}


@dataclass(frozen=True, init=False)
class ChainProcessorDefinition:
    """Complete definition of a processor."""

    id: str
    title: str
    inputs: list[ChainPortDefinition]
    outputs: list[ChainPortDefinition]
    source: str
    category: str
    description: str
    params: list[ChainParamDefinition]
    safety: ChainProcessorSafety
    examples: list[ChainProcessorExample]

    def __init__(
        self,
        id: str,
        title: str,
        inputs: list[str | ChainPortDefinition] | None = None,
        outputs: list[str | ChainPortDefinition] | None = None,
        source: str = "",
        *,
        category: str = "",
        description: str = "",
        params: list[ChainParamDefinition] | None = None,
        safety: ChainProcessorSafety | None = None,
        examples: list[ChainProcessorExample] | None = None,
    ):
        from .registry import (
            _default_example,
            _param_definition,
            _port_definition,
            _processor_category,
            _processor_description,
            _processor_safety,
        )

        processor_id = str(id or "").strip()
        input_defs = [_port_definition(processor_id, value, "input") for value in list(inputs or [])]
        output_defs = [_port_definition(processor_id, value, "output") for value in list(outputs or ["output"])]
        param_defs = list(params) if params is not None else [_param_definition(processor_id, port) for port in input_defs]
        example_defs = list(examples) if examples is not None else [_default_example(str(title or processor_id), param_defs)]
        object.__setattr__(self, "id", processor_id)
        object.__setattr__(self, "title", str(title or processor_id))
        object.__setattr__(self, "inputs", input_defs)
        object.__setattr__(self, "outputs", output_defs)
        object.__setattr__(self, "source", str(source or ""))
        object.__setattr__(self, "category", category or _processor_category(processor_id))
        object.__setattr__(self, "description", description or _processor_description(processor_id, str(title or processor_id)))
        object.__setattr__(self, "params", param_defs)
        object.__setattr__(self, "safety", safety or _processor_safety(processor_id))
        object.__setattr__(self, "examples", example_defs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "description": self.description,
            "inputs": [port.to_dict() for port in self.inputs],
            "outputs": [port.to_dict() for port in self.outputs],
            "params": [param.to_dict() for param in self.params],
            "safety": self.safety.to_dict(),
            "examples": [example.to_dict() for example in self.examples],
            "source": self.source,
        }
