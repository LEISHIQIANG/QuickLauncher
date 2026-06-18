"""Tests for action chain graph models and runtime."""

from __future__ import annotations

import threading
import time

import pytest

from core.chain.graph_editor import (
    GraphEditor,
)
from core.chain.graph_executor import (
    GraphExecutor,
    LegacyAdapter,
)
from core.chain.graph_models import (
    ChainConnection,
    ChainGraph,
    ChainNode,
    ChainPort,
    CyclicGraphError,
    NodeStatus,
    PortDirection,
)
from core.chain.graph_runtime import GraphRuntime
from core.chain.processor_registry import ProcessorRegistry, get_registry


class TestChainPort:
    """Tests for ChainPort."""

    def test_create_port(self):
        port = ChainPort(id="input", label="Input", direction=PortDirection.INPUT)
        assert port.id == "input"
        assert port.label == "Input"
        assert port.direction == PortDirection.INPUT
        assert port.kind == "any"
        assert port.required is False

    def test_port_to_dict(self):
        port = ChainPort(id="output", label="Output", direction=PortDirection.OUTPUT, kind="text")
        data = port.to_dict()
        assert data["id"] == "output"
        assert data["direction"] == "output"
        assert data["kind"] == "text"

    def test_port_from_dict(self):
        data = {"id": "input", "label": "Input", "direction": "input", "kind": "number", "required": True}
        port = ChainPort.from_dict(data)
        assert port.id == "input"
        assert port.kind == "number"
        assert port.required is True


class TestChainNode:
    """Tests for ChainNode."""

    def test_create_node(self):
        node = ChainNode(id="node1", processor_id="text_replace")
        assert node.id == "node1"
        assert node.processor_id == "text_replace"
        assert node.status == NodeStatus.IDLE
        assert node.enabled is True

    def test_node_ports(self):
        node = ChainNode(id="node1", processor_id="test")
        node.inputs.append(ChainPort(id="input", direction=PortDirection.INPUT))
        node.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        assert len(node.inputs) == 1
        assert len(node.outputs) == 1
        assert node.get_input("input") is not None
        assert node.get_output("output") is not None

    def test_node_status(self):
        node = ChainNode(id="node1", processor_id="test")
        assert node.status == NodeStatus.IDLE

        node.mark_success({"output": "value"})
        assert node.status == NodeStatus.SUCCESS
        assert node.cache_valid is True
        assert node.cached_outputs == {"output": "value"}

        node.mark_failed("Error message")
        assert node.status == NodeStatus.FAILED
        assert node.error == "Error message"

    def test_node_dirty(self):
        node = ChainNode(id="node1", processor_id="test")
        node.mark_success({"output": "value"})
        assert node.cache_valid is True

        node.mark_dirty()
        assert node.status == NodeStatus.DIRTY
        assert node.cache_valid is False

    def test_node_to_dict(self):
        node = ChainNode(id="node1", processor_id="text_replace", title="Replace Text")
        data = node.to_dict()
        assert data["id"] == "node1"
        assert data["processor_id"] == "text_replace"
        assert data["title"] == "Replace Text"


class TestChainConnection:
    """Tests for ChainConnection."""

    def test_create_connection(self):
        conn = ChainConnection(
            id="conn1",
            source_node_id="node1",
            source_port_id="output",
            target_node_id="node2",
            target_port_id="input",
        )
        assert conn.id == "conn1"
        assert conn.source_node_id == "node1"
        assert conn.target_node_id == "node2"
        assert conn.enabled is True

    def test_connection_from_dict_accepts_canvas_keys(self):
        conn = ChainConnection.from_dict(
            {
                "id": "conn1",
                "source_node": "node1",
                "source_port": "output",
                "target_node": "node2",
                "target_port": "input",
            }
        )
        assert conn.source_node_id == "node1"
        assert conn.source_port_id == "output"
        assert conn.target_node_id == "node2"
        assert conn.target_port_id == "input"

    def test_connection_keys(self):
        conn = ChainConnection(
            id="conn1",
            source_node_id="node1",
            source_port_id="output",
            target_node_id="node2",
            target_port_id="input",
        )
        assert conn.source_key == "node1.output"
        assert conn.target_key == "node2.input"


class TestChainGraph:
    """Tests for ChainGraph."""

    def test_create_graph(self):
        graph = ChainGraph(id="graph1", name="Test Graph")
        assert graph.id == "graph1"
        assert graph.name == "Test Graph"
        assert len(graph.nodes) == 0
        assert len(graph.connections) == 0

    def test_add_node(self):
        graph = ChainGraph()
        node = ChainNode(id="node1", processor_id="text_replace")
        graph.add_node(node)

        assert graph.has_node("node1")
        assert graph.node_count() == 1
        assert graph.get_node("node1") is node

    def test_remove_node(self):
        graph = ChainGraph()
        node = ChainNode(id="node1", processor_id="text_replace")
        graph.add_node(node)

        removed = graph.remove_node("node1")
        assert removed is node
        assert graph.node_count() == 0

    def test_add_connection(self):
        graph = ChainGraph()

        node1 = ChainNode(id="node1", processor_id="text_input")
        node1.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        node2 = ChainNode(id="node2", processor_id="text_replace")
        node2.inputs.append(ChainPort(id="input", direction=PortDirection.INPUT))

        graph.add_node(node1)
        graph.add_node(node2)

        conn = ChainConnection(
            id="conn1",
            source_node_id="node1",
            source_port_id="output",
            target_node_id="node2",
            target_port_id="input",
        )
        graph.add_connection(conn)

        assert graph.connection_count() == 1

    def test_topological_sort(self):
        graph = ChainGraph()

        # Create a linear graph: node1 -> node2 -> node3
        node1 = ChainNode(id="node1", processor_id="text_input")
        node1.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        node2 = ChainNode(id="node2", processor_id="text_replace")
        node2.inputs.append(ChainPort(id="input", direction=PortDirection.INPUT))
        node2.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        node3 = ChainNode(id="node3", processor_id="panel_node")
        node3.inputs.append(ChainPort(id="input", direction=PortDirection.INPUT))

        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)

        graph.add_connection(
            ChainConnection(
                id="conn1",
                source_node_id="node1",
                source_port_id="output",
                target_node_id="node2",
                target_port_id="input",
            )
        )
        graph.add_connection(
            ChainConnection(
                id="conn2",
                source_node_id="node2",
                source_port_id="output",
                target_node_id="node3",
                target_port_id="input",
            )
        )

        order = graph.topological_sort()
        assert order == ["node1", "node2", "node3"]

    def test_cycle_detection(self):
        graph = ChainGraph()

        node1 = ChainNode(id="node1", processor_id="test")
        node1.inputs.append(ChainPort(id="input", direction=PortDirection.INPUT))
        node1.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        node2 = ChainNode(id="node2", processor_id="test")
        node2.inputs.append(ChainPort(id="input", direction=PortDirection.INPUT))
        node2.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        graph.add_node(node1)
        graph.add_node(node2)

        # Create cycle: node1 -> node2 -> node1
        graph.add_connection(
            ChainConnection(
                id="conn1",
                source_node_id="node1",
                source_port_id="output",
                target_node_id="node2",
                target_port_id="input",
            )
        )
        graph.add_connection(
            ChainConnection(
                id="conn2",
                source_node_id="node2",
                source_port_id="output",
                target_node_id="node1",
                target_port_id="input",
            )
        )

        assert graph.has_cycle()

        with pytest.raises(CyclicGraphError):
            graph.topological_sort()

    def test_graph_validation(self):
        graph = ChainGraph()

        node = ChainNode(id="node1", processor_id="test")
        node.inputs.append(ChainPort(id="required_input", direction=PortDirection.INPUT, required=True))
        graph.add_node(node)

        issues = graph.validate()
        assert len(issues) > 0
        assert any(i["code"] == "port.required" for i in issues)

    def test_graph_to_dict(self):
        graph = ChainGraph(id="graph1", name="Test")
        node = ChainNode(id="node1", processor_id="text_input")
        graph.add_node(node)

        data = graph.to_dict()
        assert data["id"] == "graph1"
        assert "node1" in data["nodes"]

    def test_graph_from_dict(self):
        data = {
            "id": "graph1",
            "name": "Test",
            "nodes": {
                "node1": {
                    "id": "node1",
                    "processor_id": "text_input",
                    "title": "Text Input",
                }
            },
            "connections": {},
        }
        graph = ChainGraph.from_dict(data)
        assert graph.id == "graph1"
        assert graph.has_node("node1")

    def test_graph_from_canvas_dict_accepts_ui_schema_without_lookup(self):
        canvas = {
            "version": 1,
            "nodes": [
                {
                    "id": "node1",
                    "node_type": "processor",
                    "processor_id": "text_input",
                    "args": {"text": "Hello"},
                    "x": 0,
                    "y": 80,
                    "order": 1,
                },
                {
                    "id": "node2",
                    "node_type": "processor",
                    "processor_id": "panel_node",
                    "x": 240,
                    "y": 80,
                    "order": 2,
                },
            ],
            "connections": [
                {
                    "id": "conn1",
                    "source_node": "node1",
                    "source_port": "output",
                    "target_node": "node2",
                    "target_port": "input",
                }
            ],
        }

        graph = ChainGraph.from_canvas_dict(canvas)

        assert graph.node_count() == 2
        assert graph.connection_count() == 1
        assert graph.get_node("node1").get_output("output") is not None
        assert graph.get_node("node2").get_input("input") is not None
        assert graph.get_node("node1").params["text"] == "Hello"


class TestGraphRuntime:
    """Tests for GraphRuntime."""

    def test_runtime_execution(self):
        graph = ChainGraph()

        # Simple graph with text_input -> panel_node
        node1 = ChainNode(id="node1", processor_id="text_input")
        node1.params["text"] = "Hello World"
        node1.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        node2 = ChainNode(id="node2", processor_id="panel_node")
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

        executor = GraphExecutor()
        result = executor.execute(graph)

        assert result.success
        assert result.node_results["node1"].status == NodeStatus.SUCCESS
        assert result.node_results["node2"].status == NodeStatus.SUCCESS

    def test_runtime_timeout_uses_run_start_time(self):
        graph = ChainGraph()
        node = ChainNode(id="node1", processor_id="text_input")
        node.params["text"] = "Hello"
        node.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))
        graph.add_node(node)

        runtime = GraphRuntime()
        result = runtime.execute(graph, timeout=5.0)

        assert result.status == "completed"
        assert result.node_results["node1"].status == NodeStatus.SUCCESS

    def test_parallel_runtime_timeout_returns_with_daemon_workers(self):
        from core.chain.parallel_runtime import ParallelGraphRuntime

        graph = ChainGraph()
        graph.add_node(ChainNode(id="slow1", processor_id="slow"))
        graph.add_node(ChainNode(id="slow2", processor_id="slow"))
        release = threading.Event()
        worker_daemon_flags = []

        def slow_handler(_node, _inputs, _context):
            worker_daemon_flags.append(threading.current_thread().daemon)
            release.wait(1.0)
            return {"output": "late"}

        runtime = ParallelGraphRuntime(max_workers=2)
        runtime.register_processor("slow", slow_handler)
        started = time.monotonic()
        result = runtime.execute(graph, timeout=0.05, parallel=True)
        elapsed = time.monotonic() - started
        release.set()

        assert result.status == "failed"
        assert result.error == "Execution timed out"
        assert elapsed < 0.5
        assert worker_daemon_flags and all(worker_daemon_flags)


class TestLegacyAdapter:
    """Tests for LegacyAdapter."""

    def test_steps_to_graph(self):
        steps = [
            {"id": "step1", "node_type": "processor", "processor_id": "text_input", "params": {"text": "Hello"}},
            {"id": "step2", "node_type": "processor", "processor_id": "panel_node"},
        ]

        graph = LegacyAdapter.steps_to_graph(steps)
        assert graph.node_count() == 2
        assert graph.has_node("step1")
        assert graph.has_node("step2")

    def test_graph_to_steps(self):
        graph = ChainGraph()
        node1 = ChainNode(id="node1", processor_id="text_input")
        node2 = ChainNode(id="node2", processor_id="panel_node")
        graph.add_node(node1)
        graph.add_node(node2)

        steps = LegacyAdapter.graph_to_steps(graph)
        assert len(steps) == 2

    def test_steps_graph_roundtrip_preserves_legacy_args(self):
        steps = [
            {
                "id": "step1",
                "node_type": "processor",
                "processor_id": "text_input",
                "args": {"text": "Hello"},
            },
            {
                "id": "step2",
                "node_type": "processor",
                "processor_id": "panel_node",
                "input_binding": "1.output",
            },
        ]

        graph = LegacyAdapter.steps_to_graph(steps)
        roundtrip = LegacyAdapter.graph_to_steps(graph)

        assert roundtrip[0]["args"] == {"text": "Hello"}
        assert "params" not in roundtrip[0]
        assert roundtrip[1]["input_binding"] == "1.output"

    def test_graph_to_canvas_uses_ui_canvas_schema(self):
        from ui.config_window.chain_canvas import compile_canvas_to_steps

        graph = ChainGraph()
        node1 = ChainNode(id="node1", processor_id="text_input", title="文本输入")
        node1.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))
        node1.params["text"] = "Hello"
        node2 = ChainNode(id="node2", processor_id="panel_node", title="看板")
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

        canvas = LegacyAdapter.graph_to_canvas(graph)

        assert canvas["version"] == 1
        assert canvas["nodes"][0]["node_type"] == "processor"
        assert canvas["nodes"][0]["processor_id"] == "text_input"
        assert canvas["nodes"][0]["args"] == {"text": "Hello"}
        assert canvas["connections"][0]["source_node"] == "node1"
        assert canvas["connections"][0]["source_port"] == "output"
        assert canvas["connections"][0]["target_node"] == "node2"
        assert canvas["connections"][0]["target_port"] == "input"

        compiled = compile_canvas_to_steps(canvas)
        assert compiled[0]["args"] == {"text": "Hello"}
        assert compiled[1]["input_binding"] == "1.output"


class TestGraphEditor:
    """Tests for GraphEditor."""

    def test_editor_add_node(self):
        graph = ChainGraph()
        editor = GraphEditor(graph)

        # This requires processors to be registered
        get_registry()

        node = editor.add_processor_node("text_input", 100, 200)
        # May be None if processor not registered
        if node:
            assert node.x == 100
            assert node.y == 200

    def test_editor_connect(self):
        graph = ChainGraph()
        editor = GraphEditor(graph)

        node1 = ChainNode(id="node1", processor_id="test")
        node1.outputs.append(ChainPort(id="output", direction=PortDirection.OUTPUT))

        node2 = ChainNode(id="node2", processor_id="test")
        node2.inputs.append(ChainPort(id="input", direction=PortDirection.INPUT))

        graph.add_node(node1)
        graph.add_node(node2)

        conn = editor.connect("node1", "output", "node2", "input")
        assert conn is not None
        assert graph.connection_count() == 1


class TestProcessorRegistry:
    """Tests for ProcessorRegistry."""

    def test_registry_operations(self):
        registry = ProcessorRegistry()

        from core.chain.definitions import ChainProcessorDefinition

        definition = ChainProcessorDefinition(
            id="test_processor",
            title="Test Processor",
            inputs=["input"],
            outputs=["output"],
        )

        assert registry.register(definition) is True
        assert registry.has_processor("test_processor")
        assert registry.get_definition("test_processor") is definition

    def test_registry_search(self):
        registry = ProcessorRegistry()

        from core.chain.definitions import ChainProcessorDefinition

        registry.register(ChainProcessorDefinition(id="text_replace", title="文本替换"))
        registry.register(ChainProcessorDefinition(id="math_add", title="加法"))

        results = registry.search("文本")
        assert len(results) == 1
        assert results[0].id == "text_replace"
