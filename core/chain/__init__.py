"""Action chain core module.

This package contains the core components of the action chain system:
- definitions: Processor definition dataclasses
- registry: Processor registration and lookup
- processor_registry: Enhanced processor registry with categories
- processor_loader: Processor discovery and loading
- contracts: Port contracts and validation
- values: Typed value system
- runtime: Execution runtime and context
- graph_models: Graph data structures (ChainGraph, ChainNode, ChainConnection)
- graph_runtime: Graph execution engine
- graph_executor: Graph executor adapter for integrating with legacy system
- graph_editor: Graph editing operations and utilities
- data_structures: Item/List/Tree data structures (Grasshopper-inspired)
- list_operations: List manipulation operations
- smart_types: Intelligent type recognition and validation
- port_types: Enhanced port type system
- type_converter: Unified type conversion system
- templates: Chain templates and sub-chain system
- undo_manager: Undo/redo system for graph editing
- additional_processors: Additional processor definitions
"""

from __future__ import annotations

# Import key classes and functions for easy access
from .definitions import (
    ChainPortDefinition,
    ChainParamDefinition,
    ChainProcessorSafety,
    ChainProcessorExample,
    ChainProcessorDefinition,
    KNOWN_PROCESSOR_PORT_KINDS,
    KNOWN_PROCESSOR_PARAM_KINDS,
    KNOWN_PROCESSOR_SAFETY_LEVELS,
    KNOWN_PROCESSOR_PORT_ROLES,
)

from .values import (
    ChainValueKind,
    ChainValue,
    make_chain_value,
    chain_value_to_dict,
    typed_mapping,
    value_to_text,
    preview_text,
    infer_kind,
    raw_value,
)

from .contracts import (
    ChainPortSpec,
    ChainConnectionIssue,
    input_port_specs_for_node,
    output_port_specs_for_node,
    validate_canvas_connection,
    validate_canvas,
    validate_step_bindings,
    binding_key,
)

from .runtime import (
    ChainRunContext,
    ChainNodeRunSnapshot,
    CancelledError,
)

from .graph_models import (
    NodeStatus,
    PortDirection,
    ChainPort,
    ChainNode,
    ChainConnection,
    ChainGraph,
    GraphValidationError,
    CyclicGraphError,
)

from .graph_runtime import (
    GraphRuntime,
    GraphExecutionContext,
    ExecutionResult,
    NodeExecutionResult,
    execute_graph,
)

from .processor_registry import (
    ProcessorRegistry,
    ProcessorCategory,
    get_registry,
    register_processor,
    get_processor,
    list_processors,
    get_processors_by_category,
    search_processors,
)

from .templates import (
    ChainTemplate,
    SubChainDefinition,
    TemplateLibrary,
    get_template_library,
    register_template,
    get_template,
    list_templates,
    search_templates,
    register_sub_chain,
    get_sub_chain,
    list_sub_chains,
    create_sub_chain_processor,
)

from .undo_manager import (
    Command,
    UndoManager,
    AddNodeCommand,
    RemoveNodeCommand,
    MoveNodeCommand,
    AddConnectionCommand,
    RemoveConnectionCommand,
    UpdateNodeParamCommand,
    BatchCommand,
)

from .unified_registry import (
    get_all_processors,
    get_processor_full,
    search_all_processors,
    execute_processor,
    validate_processor_definition,
    get_processor_documentation,
    get_registry_statistics,
    sync_builtin_processors,
)

from .parallel_runtime import (
    ParallelGraphRuntime,
    ExecutionPlan,
    ParallelExecutionResult,
    execute_graph_parallel,
)

from .enhanced_processors import (
    # Text processors
    text_trim,
    text_contains,
    text_startswith,
    text_endswith,
    text_regex_replace,
    text_count,
    text_reverse,
    text_center,
    text_ljust,
    text_rjust,
    
    # Logic processors
    switch_case,
    try_catch,
    assert_type,
    is_empty,
    is_numeric,
    is_json,
    
    # Math processors
    math_abs,
    math_ceil,
    math_floor,
    math_round,
    math_clamp,
    math_random,
    
    # List processors
    list_count,
    list_sum,
    list_min,
    list_max,
    list_avg,
    list_find,
    list_remove,
    
    # File processors
    file_copy,
    file_move,
    file_delete,
    file_size,
    file_modified,
    file_list_dir,
    
    # JSON processors
    json_merge,
    json_flatten,
    json_keys,
    json_values,
    json_length,
    json_to_csv,
)

from .enhanced_definitions import (
    ENHANCED_PROCESSOR_DEFINITIONS,
    get_enhanced_definitions,
)

from .enhanced_integration import (
    register_enhanced_processors,
    execute_enhanced_processor,
)

from .extended_processors import (
    # Date/Time
    datetime_now,
    datetime_format,
    datetime_parse,
    datetime_add,
    datetime_diff,
    datetime_part,
    timestamp_now,
    timestamp_to_datetime,
    datetime_to_timestamp,
    
    # Encoding/Decoding
    base64_encode,
    base64_decode,
    url_encode,
    url_decode,
    html_encode,
    html_decode,
    hex_encode,
    hex_decode,
    
    # System info
    sys_platform,
    sys_version,
    sys_hostname,
    sys_username,
    sys_cpu_count,
    sys_current_dir,
    sys_home_dir,
    sys_temp_dir,
    
    # Network
    net_ip_address,
    net_ping,
    net_port_check,
    net_url_parse,
    
    # Validation
    validate_email,
    validate_url,
    validate_ip,
    validate_phone,
    validate_regex,
    validate_range,
    validate_length,
    
    # Hash
    hash_md5,
    hash_sha1,
    hash_sha256,
    hash_sha512,
    hash_crc32,
    hash_uuid,
    
    # Color
    color_hex_to_rgb,
    color_rgb_to_hex,
    color_brightness,
    color_complementary,
    color_random,
    
    # Set operations
    set_union,
    set_intersection,
    set_difference,
    set_unique,
    
    # Dict operations
    dict_keys,
    dict_values,
    dict_merge,
    dict_get,
    dict_set,
    dict_filter,
    
    # String formatting
    str_format,
    str_pad_left,
    str_pad_right,
    str_truncate,
    str_repeat,
    
    # Compression
    compress_gzip,
    decompress_gzip,
    compress_zlib,
    decompress_zlib,
    
    # Environment
    env_get,
    env_set,
    env_list,
    env_expand,
    
    # Math extended
    math_sin,
    math_cos,
    math_tan,
    math_sqrt,
    math_log,
    math_factorial,
    math_gcd,
    math_lcm,
    math_fibonacci,
)

from .extended_definitions import (
    EXTENDED_PROCESSOR_DEFINITIONS,
    get_extended_definitions,
)

from .extended_integration import (
    register_extended_processors,
    execute_extended_processor,
)

__all__ = [
    # Definitions
    "ChainPortDefinition",
    "ChainParamDefinition",
    "ChainProcessorSafety",
    "ChainProcessorExample",
    "ChainProcessorDefinition",
    "KNOWN_PROCESSOR_PORT_KINDS",
    "KNOWN_PROCESSOR_PARAM_KINDS",
    "KNOWN_PROCESSOR_SAFETY_LEVELS",
    "KNOWN_PROCESSOR_PORT_ROLES",
    
    # Values
    "ChainValueKind",
    "ChainValue",
    "make_chain_value",
    "chain_value_to_dict",
    "typed_mapping",
    "value_to_text",
    "preview_text",
    "infer_kind",
    "raw_value",
    
    # Contracts
    "ChainPortSpec",
    "ChainConnectionIssue",
    "input_port_specs_for_node",
    "output_port_specs_for_node",
    "validate_canvas_connection",
    "validate_canvas",
    "validate_step_bindings",
    "binding_key",
    
    # Runtime
    "ChainRunContext",
    "ChainNodeRunSnapshot",
    "CancelledError",
    
    # Graph Models
    "NodeStatus",
    "PortDirection",
    "ChainPort",
    "ChainNode",
    "ChainConnection",
    "ChainGraph",
    "GraphValidationError",
    "CyclicGraphError",
    
    # Graph Runtime
    "GraphRuntime",
    "GraphExecutionContext",
    "ExecutionResult",
    "NodeExecutionResult",
    "execute_graph",
    
    # Processor Registry
    "ProcessorRegistry",
    "ProcessorCategory",
    "get_registry",
    "register_processor",
    "get_processor",
    "list_processors",
    "get_processors_by_category",
    "search_processors",
    
    # Templates
    "ChainTemplate",
    "SubChainDefinition",
    "TemplateLibrary",
    "get_template_library",
    "register_template",
    "get_template",
    "list_templates",
    "search_templates",
    "register_sub_chain",
    "get_sub_chain",
    "list_sub_chains",
    "create_sub_chain_processor",
    
    # Undo Manager
    "Command",
    "UndoManager",
    "AddNodeCommand",
    "RemoveNodeCommand",
    "MoveNodeCommand",
    "AddConnectionCommand",
    "RemoveConnectionCommand",
    "UpdateNodeParamCommand",
    "BatchCommand",
    
    # Unified Registry
    "get_all_processors",
    "get_processor_full",
    "search_all_processors",
    "execute_processor",
    "validate_processor_definition",
    "get_processor_documentation",
    "get_registry_statistics",
    "sync_builtin_processors",
    
    # Parallel Runtime
    "ParallelGraphRuntime",
    "ExecutionPlan",
    "ParallelExecutionResult",
    "execute_graph_parallel",
    
    # Enhanced Processors
    "text_trim",
    "text_contains",
    "text_startswith",
    "text_endswith",
    "text_regex_replace",
    "text_count",
    "text_reverse",
    "text_center",
    "text_ljust",
    "text_rjust",
    "switch_case",
    "try_catch",
    "assert_type",
    "is_empty",
    "is_numeric",
    "is_json",
    "math_abs",
    "math_ceil",
    "math_floor",
    "math_round",
    "math_clamp",
    "math_random",
    "list_count",
    "list_sum",
    "list_min",
    "list_max",
    "list_avg",
    "list_find",
    "list_remove",
    "file_copy",
    "file_move",
    "file_delete",
    "file_size",
    "file_modified",
    "file_list_dir",
    "json_merge",
    "json_flatten",
    "json_keys",
    "json_values",
    "json_length",
    "json_to_csv",
    
    # Enhanced Definitions & Integration
    "ENHANCED_PROCESSOR_DEFINITIONS",
    "get_enhanced_definitions",
    "register_enhanced_processors",
    "execute_enhanced_processor",
    
    # Submodules (for direct import)
    "definitions",
    "registry",
    "processor_registry",
    "processor_loader",
    "contracts",
    "values",
    "runtime",
    "graph_models",
    "graph_runtime",
    "graph_executor",
    "graph_editor",
    "data_structures",
    "list_operations",
    "smart_types",
    "port_types",
    "type_converter",
    "templates",
    "undo_manager",
    "additional_processors",
    "unified_registry",
    "parallel_runtime",
    "enhanced_processors",
    "enhanced_definitions",
    "enhanced_integration",
]
