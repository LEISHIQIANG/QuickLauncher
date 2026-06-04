"""Enhanced processor registry for action chains.

This module provides a comprehensive processor registry system with:
- Processor registration and lookup
- Category management
- Processor discovery
- Validation
- Documentation generation
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from .definitions import (
    ChainProcessorDefinition,
    ChainPortDefinition,
    ChainParamDefinition,
    ChainProcessorSafety,
    ChainProcessorExample,
    KNOWN_PROCESSOR_PORT_KINDS,
    KNOWN_PROCESSOR_PARAM_KINDS,
    KNOWN_PROCESSOR_SAFETY_LEVELS,
    KNOWN_PROCESSOR_PORT_ROLES,
)

__all__ = [
    "ProcessorRegistry",
    "ProcessorCategory",
    "get_registry",
    "register_processor",
    "get_processor",
    "list_processors",
    "get_processors_by_category",
]

logger = logging.getLogger(__name__)


@dataclass
class ProcessorCategory:
    """A category of processors."""
    
    id: str
    name: str
    description: str = ""
    icon: str = ""
    order: int = 0
    processors: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "order": self.order,
            "processors": list(self.processors),
        }


class ProcessorRegistry:
    """Central registry for action chain processors.
    
    This class manages:
    - Processor definitions
    - Processor handlers
    - Categories
    - Validation
    """
    
    def __init__(self):
        self._definitions: dict[str, ChainProcessorDefinition] = {}
        self._handlers: dict[str, Callable] = {}
        self._categories: dict[str, ProcessorCategory] = {}
        self._owners: dict[str, str] = {}  # processor_id -> owner
        
        # Initialize default categories
        self._init_default_categories()
    
    def _init_default_categories(self) -> None:
        """Initialize default processor categories."""
        default_categories = [
            ProcessorCategory(
                id="input_debug",
                name="输入与调试",
                description="输入数据和调试工具",
                icon="debug",
                order=0,
            ),
            ProcessorCategory(
                id="text",
                name="文本处理",
                description="文本操作和转换",
                icon="text",
                order=1,
            ),
            ProcessorCategory(
                id="logic",
                name="逻辑控制",
                description="条件判断和逻辑运算",
                icon="logic",
                order=2,
            ),
            ProcessorCategory(
                id="math_list",
                name="数学与列表",
                description="数学运算和列表操作",
                icon="math",
                order=3,
            ),
            ProcessorCategory(
                id="network",
                name="网络与结构化",
                description="HTTP请求和JSON处理",
                icon="network",
                order=4,
            ),
            ProcessorCategory(
                id="file",
                name="文件与路径",
                description="文件系统操作",
                icon="file",
                order=5,
            ),
            ProcessorCategory(
                id="image",
                name="图像处理",
                description="图像操作和转换",
                icon="image",
                order=6,
            ),
            ProcessorCategory(
                id="plugin",
                name="插件电池",
                description="插件提供的处理器",
                icon="plugin",
                order=100,
            ),
        ]
        
        for category in default_categories:
            self._categories[category.id] = category
    
    # ── Registration ───────────────────────────────────────────────────────
    
    def register(self, definition: ChainProcessorDefinition,
                 handler: Callable | None = None,
                 owner: str = "") -> bool:
        """Register a processor.
        
        Args:
            definition: Processor definition
            handler: Processor handler function
            owner: Owner identifier (for external processors)
            
        Returns:
            True if registration was successful
        """
        try:
            # Validate definition
            self._validate_definition(definition)
            
            processor_id = definition.id
            
            # Check for conflicts
            if processor_id in self._definitions:
                existing_owner = self._owners.get(processor_id)
                if existing_owner and existing_owner != owner:
                    logger.warning("Processor %s already registered by %s", processor_id, existing_owner)
                    return False
            
            # Register
            self._definitions[processor_id] = definition
            if handler:
                self._handlers[processor_id] = handler
            if owner:
                self._owners[processor_id] = owner
            
            # Add to category
            category_id = self._get_category_id(definition.category)
            if category_id in self._categories:
                if processor_id not in self._categories[category_id].processors:
                    self._categories[category_id].processors.append(processor_id)
            
            return True
            
        except Exception as e:
            logger.error("Failed to register processor %s: %s", definition.id, e)
            return False
    
    def unregister(self, processor_id: str) -> bool:
        """Unregister a processor."""
        if processor_id not in self._definitions:
            return False
        
        definition = self._definitions[processor_id]
        
        # Remove from category
        category_id = self._get_category_id(definition.category)
        if category_id in self._categories:
            if processor_id in self._categories[category_id].processors:
                self._categories[category_id].processors.remove(processor_id)
        
        # Remove
        del self._definitions[processor_id]
        self._handlers.pop(processor_id, None)
        self._owners.pop(processor_id, None)
        
        return True
    
    def unregister_owner(self, owner: str) -> list[str]:
        """Unregister all processors from an owner."""
        removed = []
        for processor_id, proc_owner in list(self._owners.items()):
            if proc_owner == owner:
                if self.unregister(processor_id):
                    removed.append(processor_id)
        return removed
    
    # ── Lookup ─────────────────────────────────────────────────────────────
    
    def get_definition(self, processor_id: str) -> ChainProcessorDefinition | None:
        """Get a processor definition by ID."""
        return self._definitions.get(processor_id)
    
    def get_handler(self, processor_id: str) -> Callable | None:
        """Get a processor handler by ID."""
        return self._handlers.get(processor_id)
    
    def has_processor(self, processor_id: str) -> bool:
        """Check if a processor is registered."""
        return processor_id in self._definitions
    
    def list_all(self) -> list[ChainProcessorDefinition]:
        """List all registered processors."""
        return list(self._definitions.values())
    
    def list_ids(self) -> list[str]:
        """List all registered processor IDs."""
        return list(self._definitions.keys())
    
    def iter_definitions(self) -> Iterator[ChainProcessorDefinition]:
        """Iterate over all processor definitions."""
        return iter(self._definitions.values())
    
    # ── Category Operations ────────────────────────────────────────────────
    
    def get_category(self, category_id: str) -> ProcessorCategory | None:
        """Get a category by ID."""
        return self._categories.get(category_id)
    
    def list_categories(self) -> list[ProcessorCategory]:
        """List all categories."""
        return sorted(self._categories.values(), key=lambda c: c.order)
    
    def get_processors_by_category(self, category_id: str) -> list[ChainProcessorDefinition]:
        """Get all processors in a category."""
        category = self._categories.get(category_id)
        if not category:
            return []
        
        return [
            self._definitions[pid]
            for pid in category.processors
            if pid in self._definitions
        ]
    
    def get_category_for_processor(self, processor_id: str) -> ProcessorCategory | None:
        """Get the category for a processor."""
        definition = self._definitions.get(processor_id)
        if not definition:
            return None
        
        category_id = self._get_category_id(definition.category)
        return self._categories.get(category_id)
    
    def _get_category_id(self, category_name: str) -> str:
        """Get category ID from name."""
        # Map category names to IDs
        name_to_id = {
            "输入与调试": "input_debug",
            "文本": "text",
            "逻辑": "logic",
            "数学与列表": "math_list",
            "网络与结构化": "network",
            "文件与路径": "file",
            "图像": "image",
            "插件电池": "plugin",
            "通用": "plugin",
        }
        return name_to_id.get(category_name, "plugin")
    
    # ── Search ─────────────────────────────────────────────────────────────
    
    def search(self, query: str) -> list[ChainProcessorDefinition]:
        """Search processors by query string.
        
        Searches in:
        - Processor ID
        - Title
        - Description
        - Category
        """
        query = query.lower().strip()
        if not query:
            return self.list_all()
        
        results = []
        for definition in self._definitions.values():
            if (query in definition.id.lower() or
                query in definition.title.lower() or
                query in definition.description.lower() or
                query in definition.category.lower()):
                results.append(definition)
        
        return results
    
    # ── Validation ─────────────────────────────────────────────────────────
    
    def _validate_definition(self, definition: ChainProcessorDefinition) -> None:
        """Validate a processor definition."""
        if not definition.id:
            raise ValueError("Processor ID is required")
        
        if not definition.title:
            raise ValueError("Processor title is required")
        
        if not definition.outputs:
            raise ValueError("Processor must have at least one output")
        
        # Validate ports
        input_ids = set()
        for port in definition.inputs:
            if port.id in input_ids:
                raise ValueError(f"Duplicate input port: {port.id}")
            input_ids.add(port.id)
            
            if port.kind not in KNOWN_PROCESSOR_PORT_KINDS:
                raise ValueError(f"Unknown port kind: {port.kind}")
            
            if port.role not in KNOWN_PROCESSOR_PORT_ROLES:
                raise ValueError(f"Unknown port role: {port.role}")
        
        output_ids = set()
        for port in definition.outputs:
            if port.id in output_ids:
                raise ValueError(f"Duplicate output port: {port.id}")
            output_ids.add(port.id)
            
            if port.kind not in KNOWN_PROCESSOR_PORT_KINDS:
                raise ValueError(f"Unknown port kind: {port.kind}")
            
            if port.role not in KNOWN_PROCESSOR_PORT_ROLES:
                raise ValueError(f"Unknown port role: {port.role}")
        
        # Validate params
        param_ids = set()
        for param in definition.params:
            if param.id in param_ids:
                raise ValueError(f"Duplicate param: {param.id}")
            param_ids.add(param.id)
            
            if param.kind not in KNOWN_PROCESSOR_PARAM_KINDS:
                raise ValueError(f"Unknown param kind: {param.kind}")
        
        # Validate safety
        if definition.safety.level not in KNOWN_PROCESSOR_SAFETY_LEVELS:
            raise ValueError(f"Unknown safety level: {definition.safety.level}")
    
    # ── Documentation ──────────────────────────────────────────────────────
    
    def generate_documentation(self, processor_id: str) -> str:
        """Generate documentation for a processor."""
        definition = self._definitions.get(processor_id)
        if not definition:
            return ""
        
        lines = []
        lines.append(f"# {definition.title}")
        lines.append("")
        lines.append(f"**ID:** `{definition.id}`")
        lines.append(f"**Category:** {definition.category}")
        lines.append(f"**Safety Level:** {definition.safety.level}")
        lines.append("")
        lines.append("## Description")
        lines.append("")
        lines.append(definition.description)
        lines.append("")
        
        # Inputs
        if definition.inputs:
            lines.append("## Inputs")
            lines.append("")
            lines.append("| ID | Label | Type | Required | Description |")
            lines.append("|-----|-------|------|----------|-------------|")
            for port in definition.inputs:
                required = "Yes" if port.required else "No"
                lines.append(f"| `{port.id}` | {port.label} | {port.kind} | {required} | {port.description} |")
            lines.append("")
        
        # Outputs
        if definition.outputs:
            lines.append("## Outputs")
            lines.append("")
            lines.append("| ID | Label | Type | Description |")
            lines.append("|-----|-------|------|-------------|")
            for port in definition.outputs:
                lines.append(f"| `{port.id}` | {port.label} | {port.kind} | {port.description} |")
            lines.append("")
        
        # Parameters
        if definition.params:
            lines.append("## Parameters")
            lines.append("")
            lines.append("| ID | Label | Type | Default | Description |")
            lines.append("|-----|-------|------|---------|-------------|")
            for param in definition.params:
                default = param.default if param.default else "-"
                lines.append(f"| `{param.id}` | {param.label} | {param.kind} | {default} | {param.description} |")
            lines.append("")
        
        # Examples
        if definition.examples:
            lines.append("## Examples")
            lines.append("")
            for example in definition.examples:
                lines.append(f"### {example.title}")
                lines.append("")
                if example.args:
                    lines.append("**Arguments:**")
                    lines.append("```json")
                    import json
                    lines.append(json.dumps(example.args, indent=2, ensure_ascii=False))
                    lines.append("```")
                if example.expected:
                    lines.append("**Expected Output:**")
                    lines.append("```json")
                    lines.append(json.dumps(example.expected, indent=2, ensure_ascii=False))
                    lines.append("```")
                lines.append("")
        
        # Safety
        lines.append("## Safety")
        lines.append("")
        lines.append(f"- **Level:** {definition.safety.level}")
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
    
    def generate_index(self) -> str:
        """Generate an index of all processors."""
        lines = []
        lines.append("# Action Chain Processors")
        lines.append("")
        
        for category in self.list_categories():
            processors = self.get_processors_by_category(category.id)
            if not processors:
                continue
            
            lines.append(f"## {category.name}")
            lines.append("")
            if category.description:
                lines.append(category.description)
                lines.append("")
            
            lines.append("| ID | Title | Description |")
            lines.append("|-----|-------|-------------|")
            for proc in processors:
                lines.append(f"| `{proc.id}` | {proc.title} | {proc.description} |")
            lines.append("")
        
        return "\n".join(lines)
    
    # ── Statistics ─────────────────────────────────────────────────────────
    
    def get_statistics(self) -> dict[str, Any]:
        """Get registry statistics."""
        return {
            "total_processors": len(self._definitions),
            "total_categories": len(self._categories),
            "processors_by_category": {
                cat_id: len(cat.processors)
                for cat_id, cat in self._categories.items()
            },
            "processors_by_safety": {
                level: sum(1 for d in self._definitions.values() if d.safety.level == level)
                for level in KNOWN_PROCESSOR_SAFETY_LEVELS
            },
            "external_processors": sum(1 for owner in self._owners.values() if owner),
        }


# ── Global Registry ───────────────────────────────────────────────────────

_global_registry: ProcessorRegistry | None = None


def get_registry() -> ProcessorRegistry:
    """Get the global processor registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ProcessorRegistry()
    return _global_registry


def register_processor(definition: ChainProcessorDefinition,
                       handler: Callable | None = None,
                       owner: str = "") -> bool:
    """Register a processor with the global registry."""
    return get_registry().register(definition, handler, owner)


def get_processor(processor_id: str) -> ChainProcessorDefinition | None:
    """Get a processor definition from the global registry."""
    return get_registry().get_definition(processor_id)


def list_processors() -> list[ChainProcessorDefinition]:
    """List all processors in the global registry."""
    return get_registry().list_all()


def get_processors_by_category(category_id: str) -> list[ChainProcessorDefinition]:
    """Get processors by category from the global registry."""
    return get_registry().get_processors_by_category(category_id)


def search_processors(query: str) -> list[ChainProcessorDefinition]:
    """Search processors in the global registry."""
    return get_registry().search(query)
