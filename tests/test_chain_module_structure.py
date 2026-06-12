"""Tests for the enhanced action chain module structure.

This module tests:
- Unified registry API
- Contracts module
- Values module
- Parallel runtime
"""

from __future__ import annotations

import pytest

from core.chain import (
    ChainConnection,
    ChainConnectionIssue,
    # Graph Models
    ChainGraph,
    ChainNode,
    ChainPort,
    # Contracts
    ChainPortSpec,
    ChainValue,
    # Values
    ChainValueKind,
    ParallelGraphRuntime,
    PortDirection,
    get_all_processors,
    get_processor_documentation,
    get_processor_full,
    get_registry_statistics,
    infer_kind,
    make_chain_value,
    search_all_processors,
    validate_processor_definition,
    value_to_text,
)


class TestUnifiedRegistry:
    """Tests for the unified registry API."""

    def test_get_all_processors(self):
        """Test getting all processors."""
        processors = get_all_processors()
        assert len(processors) > 0

        # Check that all processors have required fields
        for proc in processors:
            assert proc.id
            assert proc.title
            assert proc.category
            assert proc.description

    def test_get_processor_full(self):
        """Test getting a specific processor."""
        # Get a known processor
        proc = get_processor_full("text_input")
        assert proc is not None
        assert proc.id == "text_input"
        assert proc.title == "文本输入"

        # Get a non-existent processor
        proc = get_processor_full("non_existent_processor")
        assert proc is None

    def test_search_all_processors(self):
        """Test searching processors."""
        # Search by title
        results = search_all_processors("文本")
        assert len(results) > 0
        assert any("文本" in proc.title for proc in results)

        # Search by category
        results = search_all_processors("逻辑")
        assert len(results) > 0
        assert any(proc.category == "逻辑" for proc in results)

    def test_validate_processor_definition(self):
        """Test processor definition validation."""
        # Valid definition
        from core.chain.definitions import ChainProcessorDefinition

        valid_def = ChainProcessorDefinition(
            id="test_processor",
            title="Test Processor",
            inputs=["input"],
            outputs=["output"],
        )
        errors = validate_processor_definition(valid_def)
        assert len(errors) == 0

        # Invalid definition (no ID)
        invalid_def = ChainProcessorDefinition(
            id="",
            title="Test Processor",
            inputs=["input"],
            outputs=["output"],
        )
        errors = validate_processor_definition(invalid_def)
        assert len(errors) > 0

    def test_get_registry_statistics(self):
        """Test getting registry statistics."""
        stats = get_registry_statistics()
        assert "total_processors" in stats
        assert "total_categories" in stats
        assert "processors_by_category" in stats
        assert "processors_by_safety" in stats
        assert stats["total_processors"] > 0

    def test_unified_registry_sees_external_processors_without_resync(self):
        """External processors registered through the main registry stay visible."""
        from core.chain.registry import register_external_processor, unregister_external_processors

        owner = "test_plugin"
        try:
            assert register_external_processor(
                {
                    "id": "echo",
                    "title": "测试回显",
                    "category": "插件电池",
                    "description": "用于验证统一 registry 的插件电池。",
                    "inputs": [{"id": "input", "kind": "text"}],
                    "outputs": [{"id": "output", "kind": "text"}],
                    "safety": {"level": "safe", "capability": "chain.processor.test_plugin_echo"},
                },
                lambda args: {"outputs": {"output": args.get("input", "")}},
                owner=owner,
            )

            processor_id = "test_plugin_echo"
            assert any(proc.id == processor_id for proc in get_all_processors())
            assert any(proc.id == processor_id for proc in search_all_processors("测试回显"))
            assert processor_id in get_processor_documentation(processor_id)
            assert get_registry_statistics()["external_processors"] >= 1
        finally:
            unregister_external_processors(owner)


class TestValues:
    """Tests for the values module."""

    def test_chain_value_creation(self):
        """Test creating ChainValue instances."""
        # Simple text value
        value = make_chain_value("hello", ChainValueKind.TEXT)
        assert value.kind == ChainValueKind.TEXT
        assert value.value == "hello"
        assert value.text == "hello"

        # Number value
        value = make_chain_value(42, ChainValueKind.NUMBER)
        assert value.kind == ChainValueKind.NUMBER
        assert value.value == 42

        # Bool value
        value = make_chain_value(True, ChainValueKind.BOOL)
        assert value.kind == ChainValueKind.BOOL
        assert value.value is True

    def test_chain_value_auto_detection(self):
        """Test automatic type detection."""
        # List value
        value = make_chain_value([1, 2, 3])
        assert value.kind == ChainValueKind.LIST

        # Dict value
        value = make_chain_value({"key": "value"})
        assert value.kind == ChainValueKind.JSON

    def test_value_to_text(self):
        """Test value to text conversion."""
        assert value_to_text("hello") == "hello"
        assert value_to_text(42) == "42"
        assert value_to_text(True) == "true"
        assert value_to_text(False) == "false"
        assert value_to_text([1, 2, 3]) == "1\n2\n3"

    def test_infer_kind(self):
        """Test kind inference."""
        assert infer_kind("hello") == ChainValueKind.TEXT
        assert infer_kind(42) == ChainValueKind.NUMBER
        assert infer_kind(True) == ChainValueKind.BOOL
        assert infer_kind([1, 2, 3]) == ChainValueKind.LIST
        assert infer_kind({"key": "value"}) == ChainValueKind.JSON

    def test_chain_value_serialization(self):
        """Test ChainValue serialization."""
        value = make_chain_value("hello", ChainValueKind.TEXT)
        data = value.to_dict()

        assert data["kind"] == ChainValueKind.TEXT
        assert data["value"] == "hello"
        assert data["text"] == "hello"

        # Recreate from dict
        restored = ChainValue.from_dict(data)
        assert restored.kind == value.kind
        assert restored.value == value.value


class TestContracts:
    """Tests for the contracts module."""

    def test_chain_port_spec(self):
        """Test ChainPortSpec creation."""
        spec = ChainPortSpec(
            id="input",
            direction="input",
            kind="text",
            multiple=False,
            label="Input",
            description="Test input",
            role="primary",
        )

        assert spec.id == "input"
        assert spec.direction == "input"
        assert spec.kind == "text"
        assert spec.multiple is False

        # Test serialization
        data = spec.to_dict()
        assert data["id"] == "input"
        assert data["kind"] == "text"

    def test_chain_connection_issue(self):
        """Test ChainConnectionIssue creation."""
        issue = ChainConnectionIssue(
            code="type_mismatch",
            message="Types are incompatible",
            connection_id="conn-1",
        )

        assert issue.code == "type_mismatch"
        assert issue.message == "Types are incompatible"

        # Test serialization
        data = issue.to_dict()
        assert data["code"] == "type_mismatch"


class TestParallelRuntime:
    """Tests for the parallel runtime."""

    def test_parallel_runtime_creation(self):
        """Test creating a parallel runtime."""
        runtime = ParallelGraphRuntime(max_workers=4)
        assert runtime._max_workers == 4

    def test_parallel_execution(self):
        """Test parallel execution of a graph."""
        # Create a simple graph
        graph = ChainGraph(name="Test Graph")

        # Add nodes
        node1 = ChainNode(id="node1", processor_id="text_input")
        node1.params["text"] = "Hello"
        node1.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        node2 = ChainNode(id="node2", processor_id="text_input")
        node2.params["text"] = "World"
        node2.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        node3 = ChainNode(id="node3", processor_id="text_join")
        node3.inputs.append(ChainPort(id="a", direction=PortDirection.INPUT))
        node3.inputs.append(ChainPort(id="b", direction=PortDirection.INPUT))
        node3.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)

        # Add connections
        graph.add_connection(
            ChainConnection(
                id="conn1",
                source_node_id="node1",
                source_port_id="output",
                target_node_id="node3",
                target_port_id="a",
            )
        )
        graph.add_connection(
            ChainConnection(
                id="conn2",
                source_node_id="node2",
                source_port_id="output",
                target_node_id="node3",
                target_port_id="b",
            )
        )

        # Execute with parallel runtime
        runtime = ParallelGraphRuntime(max_workers=2)
        result = runtime.execute(graph, parallel=True)

        assert result.status == "completed"
        assert result.execution_plan is not None
        assert result.execution_plan.max_parallelism >= 2

    def test_execution_plan(self):
        """Test execution plan creation."""
        graph = ChainGraph(name="Test Graph")

        # Create a linear graph
        node1 = ChainNode(id="node1", processor_id="test")
        node1.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        node2 = ChainNode(id="node2", processor_id="test")
        node2.inputs.append(ChainPort(id="input", direction=PortDirection.INPUT))
        node2.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        graph.add_node(node1)
        graph.add_node(node2)

        graph.add_connection(
            ChainConnection(
                id="conn1",
                source_node_id="node1",
                source_port_id="output",
                target_node_id="node2",
                target_port_id="input",
            )
        )

        runtime = ParallelGraphRuntime()
        plan = runtime._create_execution_plan(graph)

        assert plan.total_nodes == 2
        assert len(plan.groups) == 2  # Two groups: [node1], [node2]
        assert plan.max_parallelism == 1  # Linear graph, no parallelism


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
