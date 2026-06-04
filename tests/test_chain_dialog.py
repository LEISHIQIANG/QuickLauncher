import pytest

from core.chain_processors import execute_chain_processor, processor_title
from core.data_models import Folder, ShortcutItem, ShortcutType
from qt_compat import QCheckBox, QComboBox, QSpinBox, QTextEdit, QWidget
from ui.config_window.base_dialog import BaseDialog
from ui.config_window.chain_canvas import (
    _node_port_tooltip,
    compile_canvas_to_steps,
    node_input_ports,
    node_output_labels,
    node_output_ports,
)
from ui.config_window.chain_dialog import ChainDialog

pytestmark = pytest.mark.ui


class _Settings:
    theme = "dark"


class _DataManager:
    def __init__(self, items, folders=None):
        self.data = type("Data", (), {"folders": folders or [Folder(id="f", name="F", items=items)]})()

    def get_settings(self):
        return _Settings()


class _Parent(QWidget):
    def __init__(self, items, folders=None):
        super().__init__()
        self.data_manager = _DataManager(items, folders=folders)


def test_chain_dialog_is_base_dialog(qapp):
    """ChainDialog 应继承 BaseDialog，保持一致的对话框风格。"""
    first = ShortcutItem(id="one", name="One", type=ShortcutType.FILE)
    parent = _Parent([first])
    dialog = ChainDialog(parent)
    assert isinstance(dialog, BaseDialog)
    dialog.close()


def test_chain_dialog_includes_icon_repo_items(qapp):
    normal = ShortcutItem(id="normal", name="Normal", type=ShortcutType.FILE)
    repo_item = ShortcutItem(id="repo", name="Repo", type=ShortcutType.URL)
    parent = _Parent(
        [],
        folders=[
            Folder(id="f", name="F", items=[normal]),
            Folder(id="icon_repo", name="图标仓库", is_system=True, is_icon_repo=True, items=[repo_item]),
        ],
    )
    dialog = ChainDialog(parent)

    assert {item.id for item in dialog._available} == {"normal", "repo"}
    dialog.close()


def test_chain_dialog_add_remove_reorder_and_save(qapp):
    first = ShortcutItem(id="one", name="One", type=ShortcutType.FILE)
    second = ShortcutItem(id="two", name="Two", type=ShortcutType.URL)
    parent = _Parent([first, second])
    dialog = ChainDialog(parent)

    # 通过内部方法添加步骤
    dialog._add_step(first)
    dialog._add_step(second)
    assert len(dialog._steps) == 2

    # 上移第二步
    dialog._selected_index = 1
    dialog._move_step(-1)
    shortcut = dialog.get_shortcut()
    assert shortcut.type == ShortcutType.CHAIN
    assert [step["shortcut_id"] for step in shortcut.chain_steps] == ["two", "one"]

    # 修改第一步的设置
    dialog._selected_index = 0
    dialog._steps[0]["enabled"] = False
    dialog._steps[0]["stop_on_error"] = False
    dialog._steps[0]["delay_ms"] = 25
    shortcut = dialog.get_shortcut()
    assert shortcut.chain_steps[0]["enabled"] is False
    assert shortcut.chain_steps[0]["stop_on_error"] is False
    assert shortcut.chain_steps[0]["delay_ms"] == 25

    # 删除第一步
    dialog._selected_index = 0
    dialog._remove_step()
    assert len(dialog._steps) == 1


def test_chain_dialog_edits_existing_chain(qapp):
    target = ShortcutItem(id="target", name="Target", type=ShortcutType.FILE)
    chain = ShortcutItem(
        id="chain",
        name="Existing",
        type=ShortcutType.CHAIN,
        chain_steps=[{"shortcut_id": "target", "enabled": True, "stop_on_error": True, "delay_ms": 10}],
    )
    parent = _Parent([target, chain])
    dialog = ChainDialog(parent, chain)

    updated = dialog.get_shortcut()

    assert updated.id == "chain"
    assert updated.name == "Existing"
    assert updated.chain_steps[0]["shortcut_id"] == "target"
    assert updated.chain_steps[0]["delay_ms"] == 10


def test_chain_dialog_risk_analysis(qapp):
    """风险分析应检测快捷方式风险和处理节点 safety。"""
    admin_item = ShortcutItem(id="admin", name="Admin", type=ShortcutType.COMMAND, run_as_admin=True)
    parent = _Parent([admin_item])
    dialog = ChainDialog(parent)
    dialog._add_step(admin_item)
    # 直接添加一个引用不存在快捷方式的步骤
    dialog._steps.append(
        {"id": "x", "shortcut_id": "nonexistent", "enabled": True, "stop_on_error": True, "delay_ms": 0}
    )
    dialog._steps.extend(
        [
            {"node_type": "processor", "processor_id": "python_cell"},
            {"node_type": "processor", "processor_id": "http_get"},
            {"node_type": "processor", "processor_id": "file_write_text"},
        ]
    )
    risks = dialog._analyze_risks()
    assert any("管理员" in r for r in risks)
    assert any("不存在" in r for r in risks)
    assert any("执行脚本代码" in r for r in risks)
    assert any("访问网络" in r for r in risks)
    assert any("写入本地文件" in r for r in risks)
    assert any("二次确认" in r for r in risks)


def test_chain_dialog_get_shortcut_normalizes(qapp):
    """get_shortcut 应对步骤进行规范化处理。"""
    item = ShortcutItem(id="a", name="A", type=ShortcutType.FILE)
    parent = _Parent([item])
    dialog = ChainDialog(parent)
    dialog._steps = [
        {"shortcut_id": "a", "enabled": True, "stop_on_error": True, "delay_ms": 5},
        {"shortcut_id": "", "enabled": True, "stop_on_error": True, "delay_ms": 0},  # 空 id 应被过滤
    ]
    result = dialog.get_shortcut()
    assert result.type == ShortcutType.CHAIN
    assert len(result.chain_steps) == 1
    assert result.chain_steps[0]["shortcut_id"] == "a"


def test_chain_dialog_adds_canvas_node_for_shortcut(qapp):
    item = ShortcutItem(id="a", name="A", type=ShortcutType.FILE)
    parent = _Parent([item])
    dialog = ChainDialog(parent)
    dialog._add_step(item)

    shortcut = dialog.get_shortcut()

    assert len(shortcut.chain_canvas["nodes"]) == 1
    assert shortcut.chain_canvas["nodes"][0]["shortcut_id"] == "a"
    assert shortcut.chain_steps[0]["shortcut_id"] == "a"


def test_existing_chain_opens_as_canvas(qapp):
    item = ShortcutItem(id="a", name="A", type=ShortcutType.FILE)
    chain = ShortcutItem(
        id="chain",
        name="Chain",
        type=ShortcutType.CHAIN,
        chain_steps=[{"shortcut_id": "a", "enabled": True, "stop_on_error": False, "delay_ms": 0}],
    )
    parent = _Parent([item, chain])
    dialog = ChainDialog(parent, chain)

    shortcut = dialog.get_shortcut()

    assert len(shortcut.chain_canvas["nodes"]) == 1
    assert shortcut.chain_canvas["nodes"][0]["shortcut_id"] == "a"
    assert shortcut.chain_steps[0]["stop_on_error"] is False


def test_canvas_compiles_connections_to_step_bindings(qapp):
    canvas = {
        "version": 1,
        "nodes": [
            {"id": "n1", "node_type": "shortcut", "shortcut_id": "first", "order": 1, "x": 0, "y": 0},
            {
                "id": "n2",
                "node_type": "shortcut",
                "shortcut_id": "second",
                "order": 2,
                "x": 200,
                "y": 0,
                "args": {"port": "443", "host": "static"},
            },
        ],
        "connections": [
            {"source_node": "n1", "source_port": "stdout", "target_node": "n2", "target_port": "input"},
            {"source_node": "n1", "source_port": "output", "target_node": "n2", "target_port": "host"},
        ],
    }

    steps = compile_canvas_to_steps(canvas)

    assert steps[1]["input_binding"] == "1.stdout"
    assert steps[1]["param_bindings"] == {"host": "1.output"}
    assert steps[1]["args"] == {"port": "443"}


def test_shortcut_nodes_expose_standard_outputs_in_canvas():
    item = ShortcutItem(id="a", name="A", type=ShortcutType.COMMAND, capture_output=True)
    ports = node_output_ports({"node_type": "shortcut", "shortcut_id": "a"}, {"a": item})
    assert "success" in ports
    assert "stdout" in ports
    assert node_output_ports({"node_type": "processor", "processor_id": "text_template"}) == ["output", "length", "empty"]


def test_shortcut_standard_output_labels_are_data_oriented():
    item = ShortcutItem(id="a", name="A", type=ShortcutType.COMMAND, capture_output=True)
    labels = node_output_labels({"node_type": "shortcut", "shortcut_id": "a"}, {"a": item})

    assert labels["success"] == "成功状态"
    assert labels["output"] == "主输出"
    assert labels["error"] == "错误信息"
    assert labels["stdout"] == "标准输出"
    assert labels["stderr"] == "标准错误"
    assert labels["files.0"] == "结果文件[0]"
    assert labels["folders.0"] == "结果文件夹[0]"
    assert labels["urls.0"] == "结果 URL[0]"


def test_standard_output_tooltip_includes_type_role_and_description():
    node = {"node_type": "processor", "processor_id": "list_join"}

    tooltip = _node_port_tooltip(node, "output", "output")

    assert "数据类型: 字符串" in tooltip
    assert "端口角色: 主数据" in tooltip
    assert "主输出" in tooltip


def test_http_processors_expose_status_and_headers_outputs():
    ports = node_output_ports({"node_type": "processor", "processor_id": "http_get"})

    assert "output" in ports
    assert "status_code" in ports
    assert "headers" in ports


def test_processor_canvas_ports_read_definition_schema():
    from core.chain_contracts import input_port_specs_for_node, output_port_specs_for_node

    inputs = {spec.id: spec for spec in input_port_specs_for_node({"node_type": "processor", "processor_id": "sleep_node"}, {})}
    outputs = {spec.id: spec for spec in output_port_specs_for_node({"node_type": "processor", "processor_id": "sleep_node"}, {})}

    assert inputs["ms"].kind == "number"
    assert inputs["ms"].label == "毫秒"
    assert outputs["ms"].kind == "number"


def test_file_shortcut_exposes_normal_input_and_open_file_port():
    item = ShortcutItem(id="app", name="App", type=ShortcutType.FILE)
    ports = node_input_ports({"node_type": "shortcut", "shortcut_id": "app"}, {"app": item})

    assert ports[:2] == ["input", "open_file"]


def test_canvas_compiles_open_file_port_to_file_binding():
    canvas = {
        "nodes": [
            {"id": "n1", "node_type": "processor", "processor_id": "file_path_input", "order": 1, "x": 0, "y": 0},
            {"id": "n2", "node_type": "shortcut", "shortcut_id": "app", "order": 2, "x": 220, "y": 0},
        ],
        "connections": [
            {"source_node": "n1", "source_port": "path", "target_node": "n2", "target_port": "open_file"},
        ],
    }

    steps = compile_canvas_to_steps(canvas)

    assert steps[1]["input_binding"] == ""
    assert steps[1]["param_bindings"] == {"open_file": "1.outputs.path"}


def test_python_cell_ports_come_from_source():
    node = {
        "node_type": "processor",
        "processor_id": "python_cell",
        "source": 'TITLE="T"\nINPUTS=["a","b"]\nOUTPUTS=["x","y"]\ndef process(inputs):\n    return {"x": "1"}\n',
    }

    assert node_input_ports(node, {}) == ["a", "b"]
    assert node_output_ports(node) == ["x", "y"]


def test_programming_processors_are_chinese_and_execute():
    assert processor_title("sleep_node") == "等待"
    assert processor_title("bool_and") == "逻辑与"
    assert processor_title("loop_repeat") == "循环重复"

    assert execute_chain_processor("bool_and", {"a": "true", "b": "false"}).message == "false"
    assert execute_chain_processor("bool_not", {"value": "false"}).message == "true"
    assert execute_chain_processor("compare_value", {"a": "3", "operator": "大于", "b": "2"}).message == "true"
    assert execute_chain_processor("if_else", {"condition": "true", "true_value": "甲", "false_value": "乙"}).message == "甲"
    assert execute_chain_processor("loop_repeat", {"input": "甲", "count": "3", "delimiter": ","}).message == "甲,甲,甲"


def test_canvas_compiles_custom_output_and_multi_input_bindings():
    canvas = {
        "nodes": [
            {"id": "n1", "node_type": "processor", "processor_id": "python_cell", "order": 1, "x": 0, "y": 0},
            {"id": "n2", "node_type": "processor", "processor_id": "python_cell", "order": 2, "x": 220, "y": 0},
            {"id": "n3", "node_type": "processor", "processor_id": "python_cell", "order": 3, "x": 440, "y": 0},
        ],
        "connections": [
            {"source_node": "n1", "source_port": "foo", "target_node": "n3", "target_port": "input"},
            {"source_node": "n2", "source_port": "bar", "target_node": "n3", "target_port": "input"},
        ],
    }

    steps = compile_canvas_to_steps(canvas)

    assert steps[2]["input_binding"] == ["1.outputs.foo", "2.outputs.bar"]


def test_canvas_compile_ignores_backward_connections():
    canvas = {
        "nodes": [
            {"id": "n1", "node_type": "processor", "processor_id": "text_input", "order": 1, "x": 0, "y": 0},
            {"id": "n2", "node_type": "processor", "processor_id": "text_template", "order": 2, "x": 220, "y": 0},
        ],
        "connections": [
            {"source_node": "n2", "source_port": "output", "target_node": "n1", "target_port": "text"},
        ],
    }

    steps = compile_canvas_to_steps(canvas)

    assert steps[0]["input_binding"] == ""
    assert steps[0]["param_bindings"] == {}


def test_canvas_rejects_invalid_connections(qapp):
    parent = _Parent([])
    dialog = ChainDialog(parent)
    widget = dialog.canvas_widget
    widget.canvas = {
        "nodes": [
            {"id": "n1", "node_type": "processor", "processor_id": "bool_value", "order": 1, "x": 0, "y": 0},
            {"id": "n2", "node_type": "processor", "processor_id": "math_add", "order": 2, "x": 220, "y": 0},
        ],
        "connections": [],
    }
    widget._render()

    widget._connect("n2", "output", "n1", "value")
    assert widget.canvas["connections"] == []

    widget._connect("n1", "output", "n2", "a")
    assert widget.canvas["connections"] == []


def test_canvas_rejects_implicit_text_to_number_connection(qapp):
    parent = _Parent([])
    dialog = ChainDialog(parent)
    widget = dialog.canvas_widget
    widget.canvas = {
        "nodes": [
            {"id": "n1", "node_type": "processor", "processor_id": "text_input", "order": 1, "x": 0, "y": 0},
            {"id": "n2", "node_type": "processor", "processor_id": "math_add", "order": 2, "x": 220, "y": 0},
        ],
        "connections": [],
    }
    widget._render()

    widget._connect("n1", "output", "n2", "a")

    assert widget.canvas["connections"] == []


def test_canvas_accepts_explicit_number_and_list_typed_connections(qapp):
    parent = _Parent([])
    dialog = ChainDialog(parent)
    widget = dialog.canvas_widget
    widget.canvas = {
        "nodes": [
            {"id": "len", "node_type": "processor", "processor_id": "text_len", "order": 1, "x": 0, "y": 0},
            {"id": "add", "node_type": "processor", "processor_id": "math_add", "order": 2, "x": 220, "y": 0},
            {"id": "counter", "node_type": "processor", "processor_id": "loop_counter", "order": 3, "x": 440, "y": 0},
            {"id": "join", "node_type": "processor", "processor_id": "list_join", "order": 4, "x": 660, "y": 0},
        ],
        "connections": [],
    }
    widget._render()

    widget._connect("len", "output", "add", "a")
    widget._connect("counter", "output", "join", "list")

    assert [
        (connection["source_node"], connection["source_port"], connection["target_node"], connection["target_port"])
        for connection in widget.canvas["connections"]
    ] == [
        ("len", "output", "add", "a"),
        ("counter", "output", "join", "list"),
    ]


def test_double_click_non_script_processor_does_not_change_processor_id(qapp):
    parent = _Parent([])
    dialog = ChainDialog(parent)
    dialog._add_processor_node("text_template")
    node = dialog.canvas_widget.canvas["nodes"][0]

    dialog.canvas_widget._edit_node_source(str(node["id"]))

    assert node["processor_id"] == "text_template"


def test_panel_node_shows_runtime_input_preview(qapp):
    parent = _Parent([])
    dialog = ChainDialog(parent)
    dialog._add_processor_node("panel_node")
    node_id = dialog.canvas_widget.canvas["nodes"][0]["id"]

    dialog.canvas_widget.set_run_status([{"status": "ok", "detail": "上游输入内容"}])

    node_item = dialog.canvas_widget.node_items[node_id]
    assert node_item.preview_item is not None
    assert "上游输入内容" in node_item.preview_item.toPlainText()


def test_panel_node_preview_keeps_more_debug_content(qapp):
    parent = _Parent([])
    dialog = ChainDialog(parent)
    dialog._add_processor_node("panel_node")
    node_id = dialog.canvas_widget.canvas["nodes"][0]["id"]
    long_text = "\n".join(f"第{i}行-" + "甲" * 30 for i in range(1, 18))

    dialog.canvas_widget.set_run_status([{"status": "ok", "detail": long_text}])

    node_item = dialog.canvas_widget.node_items[node_id]
    preview = node_item.preview_item.toPlainText()
    assert node_item.rect().width() >= 300
    assert "第1行" in preview
    assert "第12行" in preview
    assert "第17行" in preview
    assert node_item.preview_item.max_scroll_offset > 0


def test_panel_node_preview_scrolls_independently(qapp):
    parent = _Parent([])
    dialog = ChainDialog(parent)
    dialog._add_processor_node("panel_node")
    node_id = dialog.canvas_widget.canvas["nodes"][0]["id"]
    long_text = "\n".join(f"line {i}" for i in range(1, 40))

    dialog.canvas_widget.set_run_status([{"status": "ok", "detail": long_text}])

    panel = dialog.canvas_widget.node_items[node_id].preview_item
    start_y = panel.text_item.pos().y()
    panel.set_scroll_offset(80)
    assert panel.scroll_offset > 0
    assert panel.text_item.pos().y() < start_y


def test_chain_dialog_run_status_updates(qapp):
    """测试运行测试时以及结果返回时，电池节点的运行状态更新正确。"""
    item1 = ShortcutItem(id="a", name="A", type=ShortcutType.FILE)
    item2 = ShortcutItem(id="b", name="B", type=ShortcutType.FILE)
    parent = _Parent([item1, item2])
    dialog = ChainDialog(parent)
    dialog._add_step(item1)
    dialog._add_step(item2)

    # 模拟 canvas_widget 已创建
    assert hasattr(dialog, "canvas_widget")
    canvas = dialog.canvas_widget.get_canvas()
    assert len(canvas["nodes"]) == 2

    # 直接模拟 _on_test_result 的 payload 传入
    from core.command_registry import CommandResult
    mock_result = CommandResult(
        success=False,
        message="Test failed",
        payload={
            "duration": 0.5,
            "items": [
                {"status": "ok", "title": "A", "duration": 0.2},
                {"status": "failed", "title": "B", "duration": 0.3, "detail": "error occurred"},
            ]
        }
    )

    dialog._on_test_result(mock_result)

    # 检查 canvas 节点的状态是否正确更新
    updated_canvas = dialog.canvas_widget.canvas
    nodes = sorted(updated_canvas.get("nodes", []), key=lambda n: int(n.get("order", 0) or 0))
    assert nodes[0]["status"] == "ok"
    assert nodes[1]["status"] == "failed"

    # 测试清除状态
    dialog.canvas_widget.set_run_status([])
    cleared_canvas = dialog.canvas_widget.canvas
    for node in cleared_canvas.get("nodes", []):
        assert node.get("status", "") == ""

    # 再次模拟状态已设为 failed/ok
    dialog.canvas_widget.set_run_status([{"status": "ok"}, {"status": "failed"}])
    nodes = sorted(dialog.canvas_widget.canvas.get("nodes", []), key=lambda n: int(n.get("order", 0) or 0))
    assert nodes[0]["status"] == "ok"
    assert nodes[1]["status"] == "failed"

    # 模拟启动测试，清除状态
    import unittest.mock as mock
    with mock.patch("ui.config_window.chain_dialog._ChainTestThread") as mock_thread_class:
        mock_thread = mock.Mock()
        mock_thread_class.return_value = mock_thread
        dialog._run_test()

    # 检查状态已被清除
    nodes = sorted(dialog.canvas_widget.canvas.get("nodes", []), key=lambda n: int(n.get("order", 0) or 0))
    assert nodes[0]["status"] == ""
    assert nodes[1]["status"] == ""


def test_chain_canvas_run_status_prefers_node_snapshots(qapp):
    item1 = ShortcutItem(id="a", name="A", type=ShortcutType.FILE)
    item2 = ShortcutItem(id="b", name="B", type=ShortcutType.FILE)
    parent = _Parent([item1, item2])
    dialog = ChainDialog(parent)
    dialog._add_step(item1)
    dialog._add_step(item2)
    nodes = sorted(dialog.canvas_widget.canvas["nodes"], key=lambda n: int(n.get("order", 0) or 0))
    first_id = nodes[0]["id"]
    second_id = nodes[1]["id"]

    dialog.canvas_widget.set_run_status(
        [{"node_id": second_id, "status": "failed", "detail": "old order should not win"}],
        {
            first_id: {
                "node_id": first_id,
                "status": "ok",
                "duration": 0.01,
                "message": "first ok",
                "inputs": {"input": "alpha"},
                "outputs": {"output": "beta"},
                "error": "",
            },
            second_id: {
                "node_id": second_id,
                "status": "failed",
                "duration": 0.02,
                "message": "second failed",
                "inputs": {"input": "gamma"},
                "outputs": {"error": "boom"},
                "error": "boom",
            },
        },
    )

    nodes = sorted(dialog.canvas_widget.canvas["nodes"], key=lambda n: int(n.get("order", 0) or 0))
    assert nodes[0]["status"] == "ok"
    assert nodes[0]["last_output"] == "beta"
    assert nodes[1]["status"] == "failed"
    assert nodes[1]["last_run_snapshot"]["inputs"]["input"] == "gamma"

    dialog.canvas_widget.select_node(first_id)
    dialog._refresh_properties()
    assert "alpha" in dialog.property_panel.run_text.toPlainText()
    assert "beta" in dialog.property_panel.run_text.toPlainText()


def test_chain_connection_tooltip_shows_last_value(qapp):
    parent = _Parent([])
    dialog = ChainDialog(parent)
    dialog._add_processor_node("text_input")
    dialog._add_processor_node("text_template")
    nodes = sorted(dialog.canvas_widget.canvas["nodes"], key=lambda n: int(n.get("order", 0) or 0))
    first_id = nodes[0]["id"]
    second_id = nodes[1]["id"]
    dialog.canvas_widget.canvas["connections"] = [
        {
            "id": "c1",
            "source_node": first_id,
            "source_port": "output",
            "target_node": second_id,
            "target_port": "input",
        }
    ]

    dialog.canvas_widget.set_run_status(
        [],
        {
            first_id: {
                "node_id": first_id,
                "status": "ok",
                "duration": 0.01,
                "message": "ok",
                "inputs": {},
                "outputs": {"output": "beta"},
                "typed_outputs": {"output": {"kind": "text", "value": "beta", "text": "beta", "preview": "beta"}},
                "error": "",
            },
            second_id: {
                "node_id": second_id,
                "status": "ok",
                "duration": 0.01,
                "message": "ok",
                "inputs": {"input": "beta"},
                "outputs": {"output": "beta!"},
                "error": "",
            },
        },
    )

    assert dialog.canvas_widget.connection_items
    tooltip = dialog.canvas_widget.connection_items[0].toolTip()
    assert "output ->" in tooltip
    assert "beta" in tooltip
    assert "字符串" in tooltip


def test_property_panel_uses_processor_schema_controls(qapp):
    parent = _Parent([])
    dialog = ChainDialog(parent)

    dialog._add_processor_node("sleep_node")
    dialog._refresh_properties()
    assert isinstance(dialog.property_panel._edits["ms"], QSpinBox)
    assert dialog.property_panel._edits["ms"].value() == 1000
    dialog.property_panel._edits["ms"].setValue(250)
    assert dialog.canvas_widget.selected_node()["args"]["ms"] == "250"

    dialog._add_processor_node("bool_value")
    dialog._refresh_properties()
    assert isinstance(dialog.property_panel._edits["value"], QCheckBox)
    dialog.property_panel._edits["value"].setChecked(True)
    assert dialog.canvas_widget.selected_node()["args"]["value"] == "true"

    dialog._add_processor_node("file_write_text")
    dialog._refresh_properties()
    assert isinstance(dialog.property_panel._edits["mode"], QComboBox)
    assert dialog.property_panel._edits["mode"].currentText() == "overwrite"
    assert isinstance(dialog.property_panel._edits["text"], QTextEdit)


def test_quick_add_search_adds_processor_and_shortcut(qapp):
    item = ShortcutItem(id="open-docs", name="打开文档", type=ShortcutType.FILE)
    parent = _Parent([item])
    dialog = ChainDialog(parent)

    dialog.quick_add_edit.setText("等待")
    assert "等待" in dialog.quick_add_hint.text()
    dialog._quick_add_first_match()
    assert dialog.canvas_widget.canvas["nodes"][0]["processor_id"] == "sleep_node"

    dialog.quick_add_edit.setText("打开文档")
    assert "打开文档" in dialog.quick_add_hint.text()
    dialog._quick_add_first_match()
    nodes = sorted(dialog.canvas_widget.canvas["nodes"], key=lambda n: int(n.get("order", 0) or 0))
    assert nodes[1]["shortcut_id"] == "open-docs"


def test_chain_canvas_realtime_line_following(qapp):
    """测试在画布中拖拽/移动电池节点时，相连的线条能够实时跟随更新路径。"""
    item1 = ShortcutItem(id="a", name="A", type=ShortcutType.FILE)
    item2 = ShortcutItem(id="b", name="B", type=ShortcutType.FILE)
    parent = _Parent([item1, item2])
    dialog = ChainDialog(parent)
    dialog._add_step(item1)
    dialog._add_step(item2)

    canvas_widget = dialog.canvas_widget
    canvas_widget.canvas["connections"] = [{
        "id": "c1",
        "source_node": canvas_widget.canvas["nodes"][0]["id"],
        "source_port": "stdout",
        "target_node": canvas_widget.canvas["nodes"][1]["id"],
        "target_port": "input",
    }]
    # 渲染
    canvas_widget._render()

    # 确保连接项和节点项正确被加入 scene
    assert len(canvas_widget.connection_items) == 1
    connection_item = canvas_widget.connection_items[0]

    # 获取移动前，连接线源端和目标端的 scene Pos
    old_path = connection_item.path()
    assert not old_path.isEmpty()

    # 查找源节点并移动它的位置
    node_id = canvas_widget.canvas["nodes"][0]["id"]
    node_item = canvas_widget.node_items[node_id]

    # 触发移动
    from qt_compat import QPointF
    node_item.setPos(QPointF(100.0, 150.0))

    # 检查连接线路径已发生实时变更
    new_path = connection_item.path()
    assert new_path != old_path


def test_chain_canvas_keyboard_selection_and_deletion(qapp):
    """测试画布的键盘快捷操作：Ctrl+A全选、Ctrl+Shift+I反选、Ctrl+D取消全选、Delete多选删除。"""
    item1 = ShortcutItem(id="a", name="A", type=ShortcutType.FILE)
    item2 = ShortcutItem(id="b", name="B", type=ShortcutType.FILE)
    item3 = ShortcutItem(id="c", name="C", type=ShortcutType.FILE)
    parent = _Parent([item1, item2, item3])
    dialog = ChainDialog(parent)
    dialog._add_step(item1)
    dialog._add_step(item2)
    dialog._add_step(item3)

    canvas_widget = dialog.canvas_widget
    node_items = list(canvas_widget.node_items.values())
    assert len(node_items) == 3

    # 模拟 QKeyEvent
    from qt_compat import Qt
    class FakeEvent:
        def __init__(self, key, modifiers):
            self._key = key
            self._modifiers = modifiers
        def key(self): return self._key
        def modifiers(self): return self._modifiers
        def accept(self): pass

    # 1. 初始状态下：应该选中最新的那个节点（第3个）
    assert node_items[0].isSelected() is False
    assert node_items[1].isSelected() is False
    assert node_items[2].isSelected() is True

    # 2. Ctrl + A: 全选
    ev_all = FakeEvent(Qt.Key_A, Qt.ControlModifier)
    handled = canvas_widget.handle_key_press(ev_all)
    assert handled is True
    assert all(item.isSelected() for item in node_items)

    # 3. Ctrl + D: 取消全选
    ev_none = FakeEvent(Qt.Key_D, Qt.ControlModifier)
    handled = canvas_widget.handle_key_press(ev_none)
    assert handled is True
    assert all(not item.isSelected() for item in node_items)

    # 4. 手动选择第1个节点，然后 Ctrl + Shift + I 反选
    node_items[0].setSelected(True)
    assert node_items[0].isSelected() is True
    assert node_items[1].isSelected() is False
    assert node_items[2].isSelected() is False

    ev_invert = FakeEvent(Qt.Key_I, Qt.ControlModifier | Qt.ShiftModifier)
    handled = canvas_widget.handle_key_press(ev_invert)
    assert handled is True
    assert node_items[0].isSelected() is False
    assert node_items[1].isSelected() is True
    assert node_items[2].isSelected() is True

    # 5. 按 Delete 键：删除所有被选中的节点（第2、3个）
    ev_del = FakeEvent(Qt.Key_Delete, Qt.NoModifier)
    handled = canvas_widget.handle_key_press(ev_del)
    assert handled is True

    # 检查只剩第1个节点
    assert len(canvas_widget.canvas["nodes"]) == 1
    assert canvas_widget.canvas["nodes"][0]["shortcut_id"] == "a"


def test_chain_canvas_copy_paste_selected_subgraph(qapp):
    parent = _Parent([])
    dialog = ChainDialog(parent)
    dialog._add_processor_node("text_input")
    first = dialog.canvas_widget.canvas["nodes"][0]
    first["args"] = {"text": "hello"}
    first["status"] = "ok"
    first["last_output"] = "hello"
    dialog._add_processor_node("text_template")
    second = dialog.canvas_widget.canvas["nodes"][1]
    second["args"] = {"template": "{input} world"}
    dialog.canvas_widget.canvas["connections"] = [
        {
            "id": "c1",
            "source_node": first["id"],
            "source_port": "output",
            "target_node": second["id"],
            "target_port": "input",
        }
    ]
    dialog.canvas_widget._render()

    dialog.canvas_widget.node_items[first["id"]].setSelected(True)
    dialog.canvas_widget.node_items[second["id"]].setSelected(True)
    assert dialog.canvas_widget.copy_selected_nodes() is True
    assert dialog.canvas_widget.paste_copied_nodes() is True

    nodes = sorted(dialog.canvas_widget.canvas["nodes"], key=lambda n: int(n.get("order", 0) or 0))
    assert len(nodes) == 4
    pasted = nodes[2:]
    assert pasted[0]["processor_id"] == "text_input"
    assert pasted[0]["args"] == {"text": "hello"}
    assert "status" not in pasted[0]
    assert pasted[1]["processor_id"] == "text_template"
    assert pasted[1]["args"] == {"template": "{input} world"}

    connections = dialog.canvas_widget.canvas["connections"]
    assert len(connections) == 2
    pasted_connection = connections[1]
    assert pasted_connection["source_node"] == pasted[0]["id"]
    assert pasted_connection["target_node"] == pasted[1]["id"]
    assert pasted_connection["source_port"] == "output"
    assert pasted_connection["target_port"] == "input"


def test_chain_canvas_auto_arrange_nodes(qapp):
    parent = _Parent([])
    dialog = ChainDialog(parent)
    dialog._add_processor_node("text_input")
    dialog._add_processor_node("text_template")
    for _ in range(8):
        dialog._add_processor_node("text_input")

    canvas_widget = dialog.canvas_widget
    nodes = canvas_widget.canvas["nodes"]
    for index, node in enumerate(nodes):
        node["x"] = 900.0 - index * 17.0
        node["y"] = 500.0 + index * 23.0
    first = nodes[0]
    second = nodes[1]
    canvas_widget.canvas["connections"] = [
        {
            "id": "auto-layout-connection",
            "source_node": first["id"],
            "source_port": "output",
            "target_node": second["id"],
            "target_port": "input",
        }
    ]
    canvas_widget._render()
    canvas_widget.select_node(first["id"])

    assert canvas_widget.auto_arrange_nodes() is True

    arranged = sorted(canvas_widget.canvas["nodes"], key=lambda n: int(n.get("order", 0) or 0))
    assert [(node["order"], node["x"], node["y"]) for node in arranged[:3]] == [
        (1, 40.0, 60.0),
        (2, 270.0, 60.0),
        (3, 500.0, 60.0),
    ]
    assert arranged[7]["x"] == 40.0 + 7 * 230.0
    assert arranged[7]["y"] == 60.0
    assert arranged[8]["x"] == 40.0
    assert arranged[8]["y"] == 210.0
    assert canvas_widget.node_items[first["id"]].isSelected() is True
    assert len(canvas_widget.connection_items) == 1
    assert canvas_widget.connection_items[0].path().isEmpty() is False

    canvas_widget._sync_order_from_positions()
    assert [(node["order"], node["x"], node["y"]) for node in arranged[:3]] == [
        (1, 40.0, 60.0),
        (2, 270.0, 60.0),
        (3, 500.0, 60.0),
    ]

    from qt_compat import Qt

    class FakeEvent:
        def key(self):
            return Qt.Key_R

        def modifiers(self):
            return Qt.ControlModifier

    assert canvas_widget.handle_key_press(FakeEvent()) is True


def test_chain_canvas_undo_redo_edit_history(qapp):
    parent = _Parent([])
    dialog = ChainDialog(parent)
    canvas_widget = dialog.canvas_widget

    assert canvas_widget.can_undo() is False
    dialog._add_processor_node("text_input")
    first = canvas_widget.canvas["nodes"][0]
    assert len(canvas_widget.canvas["nodes"]) == 1
    assert canvas_widget.can_undo() is True

    assert canvas_widget.undo() is True
    assert canvas_widget.canvas["nodes"] == []
    assert canvas_widget.can_redo() is True

    assert canvas_widget.redo() is True
    assert len(canvas_widget.canvas["nodes"]) == 1
    first = canvas_widget.canvas["nodes"][0]

    dialog._add_processor_node("text_template")
    second = canvas_widget.canvas["nodes"][1]
    canvas_widget._connect(first["id"], "output", second["id"], "input")
    assert len(canvas_widget.canvas["connections"]) == 1
    assert canvas_widget.undo() is True
    assert canvas_widget.canvas["connections"] == []
    assert canvas_widget.redo() is True
    assert len(canvas_widget.canvas["connections"]) == 1

    canvas_widget.node_items[first["id"]].setSelected(True)
    canvas_widget.node_items[second["id"]].setSelected(True)
    assert canvas_widget.copy_selected_nodes() is True
    assert canvas_widget.paste_copied_nodes() is True
    assert len(canvas_widget.canvas["nodes"]) == 4
    assert canvas_widget.undo() is True
    assert len(canvas_widget.canvas["nodes"]) == 2
    assert canvas_widget.redo() is True
    assert len(canvas_widget.canvas["nodes"]) == 4

    before_layout = [(node["x"], node["y"]) for node in canvas_widget.canvas["nodes"]]
    assert canvas_widget.auto_arrange_nodes() is True
    after_layout = [(node["x"], node["y"]) for node in canvas_widget.canvas["nodes"]]
    assert after_layout != before_layout
    assert canvas_widget.undo() is True
    assert [(node["x"], node["y"]) for node in canvas_widget.canvas["nodes"]] == before_layout

    from qt_compat import Qt

    class FakeEvent:
        def __init__(self, key):
            self._key = key

        def key(self):
            return self._key

        def modifiers(self):
            return Qt.ControlModifier

    assert canvas_widget.handle_key_press(FakeEvent(Qt.Key_Y)) is True
    assert [(node["x"], node["y"]) for node in canvas_widget.canvas["nodes"]] == after_layout
    assert canvas_widget.handle_key_press(FakeEvent(Qt.Key_Z)) is True
    assert [(node["x"], node["y"]) for node in canvas_widget.canvas["nodes"]] == before_layout

    canvas_widget.select_node(first["id"])
    canvas_widget.delete_selected_nodes()
    assert len(canvas_widget.canvas["nodes"]) == 3
    assert canvas_widget.undo() is True
    assert len(canvas_widget.canvas["nodes"]) == 4
