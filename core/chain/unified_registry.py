"""Unified processor registry facade.

This module provides a unified interface to the processor registry system,
combining the functionality of:
- processor_registry.py: Enhanced registry with categories and search
- registry.py: Built-in processor definitions and execution

It serves as the primary API for processor operations.
"""

from __future__ import annotations

import logging
from typing import Any

from .definitions import (
    KNOWN_PROCESSOR_PARAM_KINDS,
    KNOWN_PROCESSOR_PORT_KINDS,
    KNOWN_PROCESSOR_PORT_ROLES,
    KNOWN_PROCESSOR_SAFETY_LEVELS,
    ChainParamDefinition,
    ChainPortDefinition,
    ChainProcessorDefinition,
    ChainProcessorExample,
    ChainProcessorSafety,
)
from .processor_registry import (
    ProcessorCategory,
    ProcessorRegistry,
    get_processor,
    get_processors_by_category,
    get_registry,
    list_processors,
    register_processor,
    search_processors,
)

# Import from registry.py for backward compatibility
from .registry import (
    DEFAULT_PYTHON_CELL_SOURCE,
    EXTERNAL_PROCESSOR_DEFINITIONS,
    EXTERNAL_PROCESSOR_HANDLERS,
    EXTERNAL_PROCESSOR_OWNERS,
    PROCESSOR_DEFINITIONS,
    ChainProcessorHandler,
    execute_chain_processor,
    processor_definition,
    processor_definitions,
    processor_input_ports,
    processor_output_ports,
    processor_title,
    python_cell_metadata,
    register_external_processor,
    unregister_external_processors,
)

__all__ = [
    # From definitions
    "ChainProcessorDefinition",
    "ChainPortDefinition",
    "ChainParamDefinition",
    "ChainProcessorSafety",
    "ChainProcessorExample",
    "KNOWN_PROCESSOR_PORT_KINDS",
    "KNOWN_PROCESSOR_PARAM_KINDS",
    "KNOWN_PROCESSOR_SAFETY_LEVELS",
    "KNOWN_PROCESSOR_PORT_ROLES",
    # From processor_registry
    "ProcessorRegistry",
    "ProcessorCategory",
    "get_registry",
    "register_processor",
    "get_processor",
    "list_processors",
    "get_processors_by_category",
    "search_processors",
    # From registry (backward compatibility)
    "PROCESSOR_DEFINITIONS",
    "EXTERNAL_PROCESSOR_DEFINITIONS",
    "EXTERNAL_PROCESSOR_HANDLERS",
    "EXTERNAL_PROCESSOR_OWNERS",
    "ChainProcessorHandler",
    "DEFAULT_PYTHON_CELL_SOURCE",
    "processor_definitions",
    "processor_definition",
    "processor_input_ports",
    "processor_output_ports",
    "processor_title",
    "register_external_processor",
    "unregister_external_processors",
    "python_cell_metadata",
    "execute_chain_processor",
    # Unified API
    "get_all_processors",
    "get_processor_full",
    "search_all_processors",
    "execute_processor",
    "validate_processor_definition",
    "get_processor_documentation",
    "get_registry_statistics",
]

logger = logging.getLogger(__name__)


def get_all_processors() -> list[ChainProcessorDefinition]:
    """Get all registered processors (built-in + external).

    Returns:
        List of all processor definitions
    """
    return processor_definitions()


def get_processor_full(processor_id: str) -> ChainProcessorDefinition | None:
    """Get a processor definition by ID.

    Args:
        processor_id: The processor ID

    Returns:
        Processor definition or None
    """
    return processor_definition(processor_id)


def search_all_processors(query: str) -> list[ChainProcessorDefinition]:
    """Search processors by query string.

    Searches in:
    - Processor ID
    - Title
    - Description
    - Category

    Args:
        query: Search query string

    Returns:
        List of matching processor definitions
    """
    normalized = str(query or "").strip().lower()
    definitions = processor_definitions()
    if not normalized:
        return definitions
    return [
        definition
        for definition in definitions
        if (
            normalized in definition.id.lower()
            or normalized in definition.title.lower()
            or normalized in definition.description.lower()
            or normalized in definition.category.lower()
        )
    ]


def execute_processor(processor_id: str, args: dict[str, Any], source: str = "") -> Any:
    """Execute a processor with the given arguments.

    Args:
        processor_id: The processor ID
        args: Input arguments
        source: Source code (for python_cell)

    Returns:
        CommandResult with execution results
    """
    return execute_chain_processor(processor_id, args, source)


def validate_processor_definition(definition: ChainProcessorDefinition) -> list[str]:
    """Validate a processor definition.

    Args:
        definition: The processor definition to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    if not definition.id:
        errors.append("Processor ID is required")

    if not definition.title:
        errors.append("Processor title is required")

    if not definition.outputs:
        errors.append("Processor must have at least one output")

    # Validate ports
    input_ids = set()
    for port in definition.inputs:
        if port.id in input_ids:
            errors.append(f"Duplicate input port: {port.id}")
        input_ids.add(port.id)

        if port.kind not in KNOWN_PROCESSOR_PORT_KINDS:
            errors.append(f"Unknown port kind: {port.kind}")

        if port.role not in KNOWN_PROCESSOR_PORT_ROLES:
            errors.append(f"Unknown port role: {port.role}")

    output_ids = set()
    for port in definition.outputs:
        if port.id in output_ids:
            errors.append(f"Duplicate output port: {port.id}")
        output_ids.add(port.id)

        if port.kind not in KNOWN_PROCESSOR_PORT_KINDS:
            errors.append(f"Unknown port kind: {port.kind}")

        if port.role not in KNOWN_PROCESSOR_PORT_ROLES:
            errors.append(f"Unknown port role: {port.role}")

    # Validate params
    param_ids = set()
    for param in definition.params:
        if param.id in param_ids:
            errors.append(f"Duplicate param: {param.id}")
        param_ids.add(param.id)

        if param.kind not in KNOWN_PROCESSOR_PARAM_KINDS:
            errors.append(f"Unknown param kind: {param.kind}")

    # Validate safety
    if definition.safety.level not in KNOWN_PROCESSOR_SAFETY_LEVELS:
        errors.append(f"Unknown safety level: {definition.safety.level}")

    return errors


def get_processor_documentation(processor_id: str) -> str:
    """Generate documentation for a processor.

    Args:
        processor_id: The processor ID

    Returns:
        Markdown documentation string
    """
    definition = processor_definition(processor_id)
    if definition is None:
        return ""
    lines = [
        f"# {definition.title}",
        "",
        f"**ID:** `{definition.id}`",
        f"**Category:** {definition.category}",
        f"**Safety Level:** {definition.safety.level}",
        "",
        "## Description",
        "",
        definition.description,
        "",
    ]
    if definition.inputs:
        lines.extend(
            [
                "## Inputs",
                "",
                "| ID | Label | Type | Required | Description |",
                "|-----|-------|------|----------|-------------|",
            ]
        )
        for port in definition.inputs:
            required = "Yes" if port.required else "No"
            lines.append(f"| `{port.id}` | {port.label} | {port.kind} | {required} | {port.description} |")
        lines.append("")
    if definition.outputs:
        lines.extend(
            [
                "## Outputs",
                "",
                "| ID | Label | Type | Description |",
                "|-----|-------|------|-------------|",
            ]
        )
        for port in definition.outputs:
            lines.append(f"| `{port.id}` | {port.label} | {port.kind} | {port.description} |")
        lines.append("")
    if definition.params:
        lines.extend(
            [
                "## Parameters",
                "",
                "| ID | Label | Type | Default | Description |",
                "|-----|-------|------|---------|-------------|",
            ]
        )
        for param in definition.params:
            default = param.default if param.default else "-"
            lines.append(f"| `{param.id}` | {param.label} | {param.kind} | {default} | {param.description} |")
        lines.append("")
    if definition.examples:
        import json

        lines.extend(["## Examples", ""])
        for example in definition.examples:
            lines.extend([f"### {example.title}", ""])
            if example.args:
                lines.extend(
                    ["**Arguments:**", "```json", json.dumps(example.args, indent=2, ensure_ascii=False), "```"]
                )
            if example.expected:
                lines.extend(
                    [
                        "**Expected Output:**",
                        "```json",
                        json.dumps(example.expected, indent=2, ensure_ascii=False),
                        "```",
                    ]
                )
            lines.append("")
    lines.extend(["## Safety", "", f"- **Level:** {definition.safety.level}"])
    if definition.safety.reads_files:
        lines.append("- Reads files")
    if definition.safety.writes_files:
        lines.append("- Writes files")
    if definition.safety.network:
        lines.append("- Uses network")
    if definition.safety.executes_code:
        lines.append("- Executes code")
    if definition.safety.requires_confirmation:
        lines.append("- Requires confirmation")
    lines.append("")
    return "\n".join(lines)


def get_registry_statistics() -> dict[str, Any]:
    """Get registry statistics.

    Returns:
        Dictionary with registry statistics
    """
    definitions = processor_definitions()
    categories: dict[str, int] = {}
    safety: dict[str, int] = {level: 0 for level in KNOWN_PROCESSOR_SAFETY_LEVELS}
    for definition in definitions:
        categories[definition.category] = categories.get(definition.category, 0) + 1
        safety[definition.safety.level] = safety.get(definition.safety.level, 0) + 1
    return {
        "total_processors": len(definitions),
        "total_categories": len(categories),
        "processors_by_category": categories,
        "processors_by_safety": safety,
        "external_processors": len(EXTERNAL_PROCESSOR_DEFINITIONS),
    }


def sync_builtin_processors() -> None:
    """Synchronize built-in processors with the registry.

    This ensures all built-in processors from registry.py are registered
    in the enhanced processor_registry.py system.
    """
    registry = get_registry()

    for proc_id, definition in PROCESSOR_DEFINITIONS.items():
        if not registry.has_processor(proc_id):
            # Get handler from registry.py
            handler = EXTERNAL_PROCESSOR_HANDLERS.get(proc_id)
            registry.register(definition, handler, owner="builtin")

    for proc_id, definition in EXTERNAL_PROCESSOR_DEFINITIONS.items():
        if not registry.has_processor(proc_id):
            handler = EXTERNAL_PROCESSOR_HANDLERS.get(proc_id)
            owner = EXTERNAL_PROCESSOR_OWNERS.get(proc_id, "external")
            registry.register(definition, handler, owner=owner)


# Auto-sync on module load
try:
    sync_builtin_processors()
except Exception as e:
    logger.warning("Failed to sync builtin processors: %s", e)
