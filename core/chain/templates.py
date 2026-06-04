"""Action chain templates and sub-chain system.

This module provides:
- Chain templates: Reusable chain patterns
- Sub-chain support: Use one chain as a node in another
- Template library: Built-in and user-defined templates
- Import/export: Share templates between users
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .definitions import (
    ChainPortDefinition,
    ChainProcessorDefinition,
    ChainProcessorExample,
    ChainProcessorSafety,
)
from .graph_models import ChainGraph

__all__ = [
    "ChainTemplate",
    "SubChainDefinition",
    "TemplateLibrary",
    "get_template_library",
    "register_template",
    "get_template",
    "list_templates",
    "create_sub_chain_processor",
]

logger = logging.getLogger(__name__)


@dataclass
class ChainTemplate:
    """A reusable chain template."""

    id: str
    name: str
    description: str = ""
    category: str = ""
    author: str = ""
    version: str = "1.0"
    tags: list[str] = field(default_factory=list)

    # The actual chain graph
    graph: ChainGraph | None = None

    # Template metadata
    created_at: float = 0.0
    modified_at: float = 0.0
    usage_count: int = 0

    # Parameters that can be customized when using the template
    parameters: list[TemplateParameter] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "author": self.author,
            "version": self.version,
            "tags": list(self.tags),
            "graph": self.graph.to_dict() if self.graph else None,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "usage_count": self.usage_count,
            "parameters": [p.to_dict() for p in self.parameters],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainTemplate:
        """Create from dictionary."""
        graph_data = data.get("graph")
        graph = ChainGraph.from_dict(graph_data) if graph_data else None

        return cls(
            id=str(data.get("id") or str(uuid.uuid4())),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            category=str(data.get("category") or ""),
            author=str(data.get("author") or ""),
            version=str(data.get("version") or "1.0"),
            tags=list(data.get("tags") or []),
            graph=graph,
            created_at=float(data.get("created_at") or 0),
            modified_at=float(data.get("modified_at") or 0),
            usage_count=int(data.get("usage_count") or 0),
            parameters=[TemplateParameter.from_dict(p) for p in data.get("parameters") or []],
        )

    def instantiate(self, param_values: dict[str, Any] | None = None) -> ChainGraph:
        """Create a new graph instance from this template.

        Args:
            param_values: Values for template parameters

        Returns:
            A new ChainGraph instance
        """
        if not self.graph:
            raise ValueError("Template has no graph")

        # Clone the graph
        graph = self.graph.clone()
        graph.id = str(uuid.uuid4())
        graph.name = f"{self.name} (Instance)"

        # Apply parameter values
        if param_values and self.parameters:
            self._apply_parameters(graph, param_values)

        self.usage_count += 1

        return graph

    def _apply_parameters(self, graph: ChainGraph, param_values: dict[str, Any]) -> None:
        """Apply parameter values to the graph."""
        for param in self.parameters:
            if param.id in param_values:
                value = param_values[param.id]

                # Find nodes that use this parameter
                for node in graph.nodes.values():
                    if param.target_node_id and node.id == param.target_node_id:
                        node.set_param(param.target_param_id, value)
                    elif param.target_param_id:
                        # Try to find by param name
                        if param.target_param_id in node.params:
                            node.set_param(param.target_param_id, value)


@dataclass
class TemplateParameter:
    """A parameter in a template that can be customized."""

    id: str
    name: str
    description: str = ""
    kind: str = "text"  # text, number, bool, json, list, file, folder, url
    default: Any = None
    required: bool = False

    # Target in the graph
    target_node_id: str = ""
    target_param_id: str = ""

    # Validation
    choices: list[str] = field(default_factory=list)
    min_value: float | None = None
    max_value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "default": self.default,
            "required": self.required,
            "target_node_id": self.target_node_id,
            "target_param_id": self.target_param_id,
            "choices": list(self.choices),
            "min_value": self.min_value,
            "max_value": self.max_value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemplateParameter:
        """Create from dictionary."""
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            kind=str(data.get("kind") or "text"),
            default=data.get("default"),
            required=bool(data.get("required", False)),
            target_node_id=str(data.get("target_node_id") or ""),
            target_param_id=str(data.get("target_param_id") or ""),
            choices=list(data.get("choices") or []),
            min_value=data.get("min_value"),
            max_value=data.get("max_value"),
        )


@dataclass
class SubChainDefinition:
    """Definition for using a chain as a sub-chain (processor node).

    This allows one chain to be used as a node in another chain.
    """

    chain_id: str
    chain_name: str
    description: str = ""

    # Input/output port definitions
    inputs: list[ChainPortDefinition] = field(default_factory=list)
    outputs: list[ChainPortDefinition] = field(default_factory=list)

    # The actual chain graph
    graph: ChainGraph | None = None

    # Metadata
    version: str = "1.0"
    author: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chain_id": self.chain_id,
            "chain_name": self.chain_name,
            "description": self.description,
            "inputs": [p.to_dict() for p in self.inputs],
            "outputs": [p.to_dict() for p in self.outputs],
            "graph": self.graph.to_dict() if self.graph else None,
            "version": self.version,
            "author": self.author,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubChainDefinition:
        """Create from dictionary."""
        graph_data = data.get("graph")
        graph = ChainGraph.from_dict(graph_data) if graph_data else None

        return cls(
            chain_id=str(data.get("chain_id") or ""),
            chain_name=str(data.get("chain_name") or ""),
            description=str(data.get("description") or ""),
            inputs=[ChainPortDefinition.from_dict(p) for p in data.get("inputs") or []],
            outputs=[ChainPortDefinition.from_dict(p) for p in data.get("outputs") or []],
            graph=graph,
            version=str(data.get("version") or "1.0"),
            author=str(data.get("author") or ""),
        )

    def to_processor_definition(self) -> ChainProcessorDefinition:
        """Convert to a processor definition for use in the registry."""
        return ChainProcessorDefinition(
            id=f"subchain.{self.chain_id}",
            title=self.chain_name,
            inputs=self.inputs or [ChainPortDefinition(id="input", label="输入", kind="any")],
            outputs=self.outputs or [ChainPortDefinition(id="output", label="输出", kind="any")],
            source="subchain",
            category="子链",
            description=self.description or f"子链: {self.chain_name}",
            safety=ChainProcessorSafety(level="safe"),
            examples=[ChainProcessorExample(title=f"{self.chain_name} 示例")],
        )


class TemplateLibrary:
    """Library for managing chain templates."""

    def __init__(self, templates_dir: str | Path | None = None):
        self._templates: dict[str, ChainTemplate] = {}
        self._sub_chains: dict[str, SubChainDefinition] = {}
        self._templates_dir = Path(templates_dir) if templates_dir else None

        # Load built-in templates
        self._load_builtin_templates()

    def _load_builtin_templates(self) -> None:
        """Load built-in templates."""
        # Basic text processing template
        self.register_template(ChainTemplate(
            id="builtin.text_processing",
            name="文本处理流程",
            description="基本的文本处理流程：输入 -> 替换 -> 输出",
            category="文本",
            author="QuickLauncher",
            tags=["文本", "基础"],
        ))

        # File processing template
        self.register_template(ChainTemplate(
            id="builtin.file_processing",
            name="文件处理流程",
            description="基本的文件处理流程：读取 -> 处理 -> 写入",
            category="文件",
            author="QuickLauncher",
            tags=["文件", "基础"],
        ))

        # HTTP request template
        self.register_template(ChainTemplate(
            id="builtin.http_request",
            name="HTTP请求流程",
            description="基本的HTTP请求流程：构建URL -> 请求 -> 解析响应",
            category="网络",
            author="QuickLauncher",
            tags=["HTTP", "网络"],
        ))

    # ── Template Operations ────────────────────────────────────────────────

    def register_template(self, template: ChainTemplate) -> bool:
        """Register a template."""
        if not template.id:
            return False

        self._templates[template.id] = template
        return True

    def unregister_template(self, template_id: str) -> bool:
        """Unregister a template."""
        if template_id in self._templates:
            del self._templates[template_id]
            return True
        return False

    def get_template(self, template_id: str) -> ChainTemplate | None:
        """Get a template by ID."""
        return self._templates.get(template_id)

    def list_templates(self) -> list[ChainTemplate]:
        """List all templates."""
        return list(self._templates.values())

    def search_templates(self, query: str) -> list[ChainTemplate]:
        """Search templates by query."""
        query = query.lower().strip()
        if not query:
            return self.list_templates()

        results = []
        for template in self._templates.values():
            if (query in template.name.lower() or
                query in template.description.lower() or
                query in template.category.lower() or
                any(query in tag.lower() for tag in template.tags)):
                results.append(template)

        return results

    def get_templates_by_category(self, category: str) -> list[ChainTemplate]:
        """Get templates by category."""
        return [t for t in self._templates.values() if t.category == category]

    # ── Sub-chain Operations ───────────────────────────────────────────────

    def register_sub_chain(self, sub_chain: SubChainDefinition) -> bool:
        """Register a sub-chain."""
        if not sub_chain.chain_id:
            return False

        self._sub_chains[sub_chain.chain_id] = sub_chain
        return True

    def unregister_sub_chain(self, chain_id: str) -> bool:
        """Unregister a sub-chain."""
        if chain_id in self._sub_chains:
            del self._sub_chains[chain_id]
            return True
        return False

    def get_sub_chain(self, chain_id: str) -> SubChainDefinition | None:
        """Get a sub-chain by ID."""
        return self._sub_chains.get(chain_id)

    def list_sub_chains(self) -> list[SubChainDefinition]:
        """List all sub-chains."""
        return list(self._sub_chains.values())

    def get_sub_chain_processor_definitions(self) -> list[ChainProcessorDefinition]:
        """Get processor definitions for all sub-chains."""
        return [sc.to_processor_definition() for sc in self._sub_chains.values()]

    # ── Import/Export ──────────────────────────────────────────────────────

    def export_template(self, template_id: str) -> str:
        """Export a template to JSON string."""
        template = self._templates.get(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        return json.dumps(template.to_dict(), ensure_ascii=False, indent=2)

    def import_template(self, json_str: str) -> ChainTemplate:
        """Import a template from JSON string."""
        data = json.loads(json_str)
        template = ChainTemplate.from_dict(data)

        # Generate new ID if it conflicts
        if template.id in self._templates:
            template.id = f"{template.id}_{uuid.uuid4().hex[:8]}"

        self.register_template(template)
        return template

    def export_sub_chain(self, chain_id: str) -> str:
        """Export a sub-chain to JSON string."""
        sub_chain = self._sub_chains.get(chain_id)
        if not sub_chain:
            raise ValueError(f"Sub-chain not found: {chain_id}")

        return json.dumps(sub_chain.to_dict(), ensure_ascii=False, indent=2)

    def import_sub_chain(self, json_str: str) -> SubChainDefinition:
        """Import a sub-chain from JSON string."""
        data = json.loads(json_str)
        sub_chain = SubChainDefinition.from_dict(data)

        # Generate new ID if it conflicts
        if sub_chain.chain_id in self._sub_chains:
            sub_chain.chain_id = f"{sub_chain.chain_id}_{uuid.uuid4().hex[:8]}"

        self.register_sub_chain(sub_chain)
        return sub_chain

    # ── File Operations ────────────────────────────────────────────────────

    def load_from_directory(self, directory: str | Path) -> int:
        """Load templates from a directory."""
        directory = Path(directory)
        if not directory.exists():
            return 0

        count = 0
        for file_path in directory.glob("*.json"):
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                # Determine if it's a template or sub-chain
                if "chain_id" in data:
                    sub_chain = SubChainDefinition.from_dict(data)
                    self.register_sub_chain(sub_chain)
                else:
                    template = ChainTemplate.from_dict(data)
                    self.register_template(template)

                count += 1
            except Exception as e:
                logger.warning("Failed to load template from %s: %s", file_path, e)

        return count

    def save_to_directory(self, directory: str | Path) -> int:
        """Save all templates to a directory."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        count = 0

        # Save templates
        for template in self._templates.values():
            file_path = directory / f"template_{template.id}.json"
            try:
                with file_path.open("w", encoding="utf-8") as f:
                    json.dump(template.to_dict(), f, ensure_ascii=False, indent=2)
                count += 1
            except Exception as e:
                logger.warning("Failed to save template %s: %s", template.id, e)

        # Save sub-chains
        for sub_chain in self._sub_chains.values():
            file_path = directory / f"subchain_{sub_chain.chain_id}.json"
            try:
                with file_path.open("w", encoding="utf-8") as f:
                    json.dump(sub_chain.to_dict(), f, ensure_ascii=False, indent=2)
                count += 1
            except Exception as e:
                logger.warning("Failed to save sub-chain %s: %s", sub_chain.chain_id, e)

        return count


# ── Global Library ─────────────────────────────────────────────────────────

_global_library: TemplateLibrary | None = None


def get_template_library() -> TemplateLibrary:
    """Get the global template library."""
    global _global_library
    if _global_library is None:
        _global_library = TemplateLibrary()
    return _global_library


def register_template(template: ChainTemplate) -> bool:
    """Register a template with the global library."""
    return get_template_library().register_template(template)


def get_template(template_id: str) -> ChainTemplate | None:
    """Get a template from the global library."""
    return get_template_library().get_template(template_id)


def list_templates() -> list[ChainTemplate]:
    """List all templates in the global library."""
    return get_template_library().list_templates()


def search_templates(query: str) -> list[ChainTemplate]:
    """Search templates in the global library."""
    return get_template_library().search_templates(query)


def register_sub_chain(sub_chain: SubChainDefinition) -> bool:
    """Register a sub-chain with the global library."""
    return get_template_library().register_sub_chain(sub_chain)


def get_sub_chain(chain_id: str) -> SubChainDefinition | None:
    """Get a sub-chain from the global library."""
    return get_template_library().get_sub_chain(chain_id)


def list_sub_chains() -> list[SubChainDefinition]:
    """List all sub-chains in the global library."""
    return get_template_library().list_sub_chains()


def create_sub_chain_processor(chain_id: str) -> ChainProcessorDefinition | None:
    """Create a processor definition for a sub-chain."""
    sub_chain = get_sub_chain(chain_id)
    if sub_chain:
        return sub_chain.to_processor_definition()
    return None
