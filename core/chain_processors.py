"""Compatibility facade for action-chain processor nodes.

The processor definitions and execution dispatcher live in
``core.chain.registry``.  This module intentionally keeps the historical
``core.chain_processors`` import path available, but it no longer owns a
separate registry or duplicate implementation.
"""

from __future__ import annotations

from core.chain.definitions import (
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
from core.chain.registry import (
    ANY_OUTPUTS,
    BOOL_OUTPUTS,
    DEFAULT_PYTHON_CELL_SOURCE,
    EXTERNAL_PROCESSOR_DEFINITIONS,
    EXTERNAL_PROCESSOR_HANDLERS,
    EXTERNAL_PROCESSOR_OWNERS,
    FILE_OUTPUTS,
    FOLDER_OUTPUTS,
    HTTP_OUTPUTS,
    JSON_OUTPUTS,
    LIST_OUTPUTS,
    NUMBER_OUTPUTS,
    PROCESSOR_DEFINITIONS,
    TEXT_OUTPUTS,
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
    "ChainPortDefinition",
    "ChainParamDefinition",
    "ChainProcessorSafety",
    "ChainProcessorExample",
    "ChainProcessorDefinition",
    "KNOWN_PROCESSOR_PORT_KINDS",
    "KNOWN_PROCESSOR_PARAM_KINDS",
    "KNOWN_PROCESSOR_SAFETY_LEVELS",
    "KNOWN_PROCESSOR_PORT_ROLES",
    "ChainProcessorHandler",
    "PROCESSOR_DEFINITIONS",
    "EXTERNAL_PROCESSOR_DEFINITIONS",
    "EXTERNAL_PROCESSOR_HANDLERS",
    "EXTERNAL_PROCESSOR_OWNERS",
    "DEFAULT_PYTHON_CELL_SOURCE",
    "TEXT_OUTPUTS",
    "BOOL_OUTPUTS",
    "LIST_OUTPUTS",
    "NUMBER_OUTPUTS",
    "FILE_OUTPUTS",
    "FOLDER_OUTPUTS",
    "JSON_OUTPUTS",
    "ANY_OUTPUTS",
    "HTTP_OUTPUTS",
    "processor_definitions",
    "processor_definition",
    "processor_input_ports",
    "processor_output_ports",
    "processor_title",
    "register_external_processor",
    "unregister_external_processors",
    "python_cell_metadata",
    "execute_chain_processor",
]
