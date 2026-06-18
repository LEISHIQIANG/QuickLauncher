import threading
import time

from core.action_chain_host import DefaultActionChainHostAPI
from core.command_registry import CommandResult
from core.data_models import Folder, ShortcutItem, ShortcutType
from core.shortcut_chain_exec import (
    _execute_processor_with_timeout,
    _execute_shortcut_chain_runtime,
    execute_shortcut_chain,
)


class _Data:
    def __init__(self, items, *, confirm_dangerous=False):
        self._confirm_dangerous = confirm_dangerous
        self.data = type("AppData", (), {"folders": [Folder(id="f", name="F", items=items)]})()

    def request_action_chain_confirmation(self, request):
        return self._confirm_dangerous


def test_shortcut_item_serializes_chain_steps():
    item = ShortcutItem(type=ShortcutType.CHAIN, name="chain")
    item.chain_steps = [{"shortcut_id": "a", "enabled": False, "stop_on_error": False, "delay_ms": 5}]

    loaded = ShortcutItem.from_dict(item.to_dict())

    assert loaded.type == ShortcutType.CHAIN
    assert loaded.chain_steps[0]["shortcut_id"] == "a"
    assert loaded.chain_steps[0]["enabled"] is False
    assert loaded.chain_steps[0]["stop_on_error"] is False
    assert loaded.chain_steps[0]["delay_ms"] == 5


def test_runtime_executes_canvas_only_processor_chain_without_mutating_steps():
    chain = ShortcutItem(
        id="chain",
        type=ShortcutType.CHAIN,
        chain_steps=[],
        chain_canvas={
            "nodes": [
                {
                    "id": "input",
                    "node_type": "processor",
                    "processor_id": "text_input",
                    "args": {"text": "Hello"},
                    "order": 1,
                },
                {
                    "id": "panel",
                    "node_type": "processor",
                    "processor_id": "panel_node",
                    "order": 2,
                },
            ],
            "connections": [
                {
                    "id": "conn",
                    "source_node": "input",
                    "source_port": "output",
                    "target_node": "panel",
                    "target_port": "input",
                }
            ],
        },
    )

    result = _execute_shortcut_chain_runtime(chain, _Data([]), host_api=DefaultActionChainHostAPI(_Data([])))

    assert result.success is True
    assert result.payload["items"][-1]["node_id"] == "panel"
    assert result.payload["node_snapshots"]["panel"]["outputs"]["output"] == "Hello"
    assert chain.chain_steps == []


def test_processor_timeout_cancels_cooperative_sleep_node():
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {
                "node_type": "processor",
                "processor_id": "sleep_node",
                "args": {"ms": "2000"},
                "timeout_ms": 50,
            }
        ],
    )

    started = time.monotonic()
    result = execute_shortcut_chain(chain, _Data([]))
    elapsed = time.monotonic() - started

    assert result.success is False
    assert "超时" in result.payload["items"][0]["detail"]
    assert elapsed < 1.0


def test_non_cooperative_processor_timeouts_are_bounded(monkeypatch):
    release = threading.Event()

    def stuck_processor(*_args, **_kwargs):
        release.wait(2.0)
        return CommandResult(success=True, message="late")

    monkeypatch.setattr("core.chain_processors.execute_chain_processor", stuck_processor)
    step = {"processor_id": "stuck", "source": ""}
    workers = []
    results = []

    for _ in range(8):
        worker = threading.Thread(
            target=lambda: results.append(_execute_processor_with_timeout(step, {}, None, 10)),
            daemon=True,
        )
        worker.start()
        workers.append(worker)
    for worker in workers:
        worker.join(timeout=0.5)

    _result, error = _execute_processor_with_timeout(step, {}, None, 10)
    assert "仍在退出" in error
    assert len(results) == 8
    release.set()


def test_dangerous_processor_requires_confirmation(tmp_path):
    target = tmp_path / "blocked.txt"
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {
                "node_type": "processor",
                "processor_id": "file_write_text",
                "args": {"path": str(target), "text": "blocked"},
            }
        ],
    )

    result = execute_shortcut_chain(chain, _Data([], confirm_dangerous=False))

    assert result.success is False
    assert "未确认" in result.payload["items"][0]["detail"]
    assert not target.exists()


def test_dangerous_processor_executes_after_confirmation(tmp_path):
    target = tmp_path / "allowed.txt"
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {
                "node_type": "processor",
                "processor_id": "file_write_text",
                "args": {"path": str(target), "text": "allowed"},
            }
        ],
    )

    result = execute_shortcut_chain(chain, _Data([], confirm_dangerous=True))

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "allowed"


def test_chain_executes_steps_skips_disabled_and_stops_on_error(monkeypatch):
    ok = ShortcutItem(id="ok", name="OK", type=ShortcutType.FILE)
    fail = ShortcutItem(id="fail", name="Fail", type=ShortcutType.FILE)
    skipped = ShortcutItem(id="skip", name="Skip", type=ShortcutType.FILE)
    chain = ShortcutItem(type=ShortcutType.CHAIN, name="chain")
    chain.chain_steps = [
        {"shortcut_id": "ok", "enabled": True, "stop_on_error": True, "delay_ms": 0},
        {"shortcut_id": "skip", "enabled": False, "stop_on_error": True, "delay_ms": 0},
        {"shortcut_id": "fail", "enabled": True, "stop_on_error": True, "delay_ms": 0},
        {"shortcut_id": "ok", "enabled": True, "stop_on_error": True, "delay_ms": 0},
    ]
    calls = []

    class Executor:
        @staticmethod
        def execute(shortcut, force_new=False):
            calls.append(shortcut.id)
            return shortcut.id != "fail", "boom" if shortcut.id == "fail" else ""

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([ok, fail, skipped]))

    assert result.success is False
    assert calls == ["ok", "fail"]
    statuses = [item["status"] for item in result.payload["items"]]
    assert statuses == ["ok", "skipped", "failed"]


def test_chain_can_continue_after_failure(monkeypatch):
    fail = ShortcutItem(id="fail", name="Fail", type=ShortcutType.FILE)
    ok = ShortcutItem(id="ok", name="OK", type=ShortcutType.FILE)
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {"shortcut_id": "fail", "enabled": True, "stop_on_error": False, "delay_ms": 0},
            {"shortcut_id": "ok", "enabled": True, "stop_on_error": True, "delay_ms": 0},
        ],
    )
    calls = []

    class Executor:
        @staticmethod
        def execute(shortcut, force_new=False):
            calls.append(shortcut.id)
            return shortcut.id == "ok", "failed"

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([fail, ok]))

    assert result.success is False
    assert calls == ["fail", "ok"]
    assert [item["status"] for item in result.payload["items"]] == ["failed", "ok"]


def test_chain_uses_capture_for_captured_command(monkeypatch):
    cmd = ShortcutItem(
        id="cmd",
        name="Cmd",
        type=ShortcutType.COMMAND,
        command_type="cmd",
        capture_output=True,
        show_window=False,
        run_as_admin=False,
    )
    chain = ShortcutItem(type=ShortcutType.CHAIN, chain_steps=[{"shortcut_id": "cmd"}])

    class Executor:
        @staticmethod
        def run_command_capture(shortcut, cancel_event=None):
            return CommandResult(success=True, message="done", display_type="log", payload={"stdout": "hello"})

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([cmd]))

    assert result.success is True
    assert "hello" in result.payload["items"][0]["detail"]


def test_chain_uses_capture_for_captured_bash_command(monkeypatch):
    cmd = ShortcutItem(
        id="bash",
        name="Bash",
        type=ShortcutType.COMMAND,
        command_type="bash",
        capture_output=True,
        show_window=False,
        run_as_admin=False,
    )
    chain = ShortcutItem(type=ShortcutType.CHAIN, chain_steps=[{"shortcut_id": "bash"}])
    seen = []

    class Executor:
        @staticmethod
        def run_command_capture(shortcut, cancel_event=None):
            seen.append(shortcut.command_type)
            return CommandResult(success=True, message="done", display_type="log", payload={"stdout": "bash out"})

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([cmd]))

    assert result.success is True
    assert seen == ["bash"]
    assert "bash out" in result.payload["items"][0]["detail"]


def test_chain_passes_previous_output_to_later_step(monkeypatch):
    first = ShortcutItem(
        id="first",
        name="First",
        type=ShortcutType.COMMAND,
        command_type="cmd",
        capture_output=True,
    )
    second = ShortcutItem(
        id="second",
        name="Second",
        type=ShortcutType.COMMAND,
        command_type="cmd",
        capture_output=True,
    )
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {"shortcut_id": "first"},
            {"shortcut_id": "second", "use_previous_output": True},
        ],
    )
    seen = []

    class Executor:
        @staticmethod
        def run_command_capture(shortcut, cancel_event=None):
            seen.append(
                (shortcut.id, getattr(shortcut, "_runtime_input_values", {}), getattr(shortcut, "_chain_values", {}))
            )
            if shortcut.id == "first":
                return CommandResult(success=True, message="done", display_type="log", payload={"stdout": "hello"})
            return CommandResult(success=True, message="done", display_type="log", payload={"stdout": "ok"})

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([first, second]))

    assert result.success is True
    assert seen[1][1]["input"] == "hello"
    assert seen[1][2]["prev.stdout"] == "hello"


def test_chain_param_and_input_bindings_use_chain_values(monkeypatch):
    first = ShortcutItem(
        id="first",
        name="First",
        type=ShortcutType.COMMAND,
        command_type="cmd",
        capture_output=True,
    )
    second = ShortcutItem(
        id="second",
        name="Second",
        type=ShortcutType.COMMAND,
        command_type="cmd",
        capture_output=True,
    )
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {"shortcut_id": "first"},
            {
                "shortcut_id": "second",
                "args": {"port": "443"},
                "param_bindings": {"host": "prev.outputs.host"},
                "input_binding": "prev.stdout",
            },
        ],
    )
    seen = []

    class Executor:
        @staticmethod
        def run_command_capture(shortcut, cancel_event=None):
            seen.append(
                (
                    shortcut.id,
                    getattr(shortcut, "_runtime_param_values", {}),
                    getattr(shortcut, "_runtime_input_values", {}),
                )
            )
            if shortcut.id == "first":
                return CommandResult(
                    success=True,
                    message="done",
                    display_type="log",
                    payload={"stdout": "raw", "outputs": {"host": "example.com"}},
                )
            return CommandResult(success=True, message="ok", display_type="log", payload={"stdout": "ok"})

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([first, second]))

    assert result.success is True
    assert seen[1][1] == {"port": "443", "host": "example.com"}
    assert seen[1][2] == {"input": "raw"}


def test_chain_bound_params_are_validated_by_command_runtime(monkeypatch):
    import core.shortcut_command_exec as command_exec

    target = ShortcutItem(
        id="target",
        name="Target",
        type=ShortcutType.COMMAND,
        command="echo ok",
        command_type="cmd",
        capture_output=True,
        command_params=[{"name": "port", "validator": "port", "default": "443"}],
    )
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[{"shortcut_id": "target", "args": {"port": "0"}}],
    )

    class Executor:
        @staticmethod
        def run_command_capture(shortcut, cancel_event=None):
            return command_exec.CommandExecutionMixin.run_command_capture(shortcut, cancel_event=cancel_event)

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([target]))

    assert result.success is False
    assert "端口范围" in result.payload["items"][0]["detail"]


def test_chain_missing_binding_fails_step(monkeypatch):
    target = ShortcutItem(id="target", name="Target", type=ShortcutType.FILE)
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[{"shortcut_id": "target", "param_bindings": {"host": "prev.outputs.host"}}],
    )

    class Executor:
        @staticmethod
        def execute(shortcut, force_new=False):
            raise AssertionError("missing bindings must stop before executing the shortcut")

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([target]))

    assert result.success is False
    assert "绑定不存在" in result.payload["items"][0]["detail"]
    assert "目标端口" in result.payload["items"][0]["detail"]


def test_chain_rejects_future_step_binding(monkeypatch):
    first = ShortcutItem(id="first", name="First", type=ShortcutType.COMMAND, command_type="cmd", capture_output=True)
    second = ShortcutItem(
        id="second", name="Second", type=ShortcutType.COMMAND, command_type="cmd", capture_output=True
    )
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {"shortcut_id": "first", "input_binding": "2.stdout"},
            {"shortcut_id": "second"},
        ],
    )

    class Executor:
        @staticmethod
        def run_command_capture(shortcut, cancel_event=None):
            raise AssertionError("future bindings must stop before execution")

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([first, second]))

    assert result.success is False
    assert "更早的步骤" in result.payload["items"][0]["detail"]


def test_chain_processor_node_passes_output_to_later_step(monkeypatch):
    target = ShortcutItem(
        id="target", name="Target", type=ShortcutType.COMMAND, command_type="cmd", capture_output=True
    )
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {
                "node_type": "processor",
                "processor_id": "text_template",
                "args": {"template": "hello {a}", "a": "world"},
            },
            {"shortcut_id": "target", "input_binding": "1.stdout"},
        ],
    )
    seen = []

    class Executor:
        @staticmethod
        def run_command_capture(shortcut, cancel_event=None):
            seen.append(getattr(shortcut, "_runtime_input_values", {}))
            return CommandResult(success=True, message="ok", display_type="log", payload={"stdout": "done"})

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([target]))

    assert result.success is True
    assert seen == [{"input": "hello world"}]


def test_chain_runtime_records_node_snapshots(monkeypatch):
    target = ShortcutItem(
        id="target", name="Target", type=ShortcutType.COMMAND, command_type="cmd", capture_output=True
    )
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {
                "id": "node-template",
                "node_type": "processor",
                "processor_id": "text_template",
                "args": {"template": "hello {a}", "a": "world"},
            },
            {"id": "node-target", "shortcut_id": "target", "input_binding": "1.stdout"},
        ],
    )

    class Executor:
        @staticmethod
        def run_command_capture(shortcut, cancel_event=None):
            return CommandResult(success=True, message="ok", display_type="log", payload={"stdout": "done"})

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([target]))
    snapshots = result.payload["node_snapshots"]

    assert result.payload["items"][0]["node_id"] == "node-template"
    assert snapshots["node-template"]["status"] == "ok"
    assert snapshots["node-template"]["inputs"]["template"] == "hello {a}"
    assert snapshots["node-template"]["outputs"]["output"] == "hello world"
    assert snapshots["node-target"]["inputs"]["input"] == "hello world"
    assert snapshots["node-target"]["outputs"]["stdout"] == "done"
    assert snapshots["node-template"]["started_at"] > 0
    assert snapshots["node-template"]["typed_outputs"]["output"]["kind"] == "text"
    assert snapshots["node-target"]["typed_inputs"]["input"]["text"] == "hello world"


def test_chain_preserves_typed_list_between_processors():
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {
                "id": "split",
                "node_type": "processor",
                "processor_id": "text_split",
                "args": {"text": "甲,乙,丙", "delimiter": ","},
            },
            {
                "id": "join",
                "node_type": "processor",
                "processor_id": "list_join",
                "param_bindings": {"list": "1.output"},
                "args": {"delimiter": "|"},
            },
        ],
    )

    result = execute_shortcut_chain(chain, _Data([]))
    snapshots = result.payload["node_snapshots"]

    assert result.success is True
    assert snapshots["split"]["typed_outputs"]["output"]["kind"] == "list"
    assert snapshots["split"]["typed_outputs"]["output"]["value"] == ["甲", "乙", "丙"]
    assert snapshots["join"]["typed_inputs"]["list"]["kind"] == "list"
    assert snapshots["join"]["typed_inputs"]["list"]["value"] == ["甲", "乙", "丙"]
    assert snapshots["join"]["outputs"]["output"] == "甲|乙|丙"


def test_chain_preserves_loop_counter_list_output_between_processors():
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {
                "id": "counter",
                "node_type": "processor",
                "processor_id": "loop_counter",
                "args": {"start": "1", "end": "3", "step": "1"},
            },
            {
                "id": "join",
                "node_type": "processor",
                "processor_id": "list_join",
                "param_bindings": {"list": "1.output"},
                "args": {"delimiter": ","},
            },
        ],
    )

    result = execute_shortcut_chain(chain, _Data([]))
    snapshots = result.payload["node_snapshots"]

    assert result.success is True
    assert snapshots["counter"]["typed_outputs"]["output"]["kind"] == "list"
    assert snapshots["counter"]["typed_outputs"]["output"]["value"] == ["1", "2", "3"]
    assert snapshots["join"]["typed_inputs"]["list"]["value"] == ["1", "2", "3"]
    assert snapshots["join"]["outputs"]["output"] == "1,2,3"


def test_file_shortcut_input_opens_bound_files(monkeypatch):
    target = ShortcutItem(id="target", name="Target", type=ShortcutType.FILE, target_path="app.exe")
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {
                "node_type": "processor",
                "processor_id": "file_path_input",
                "args": {"path": "C:\\Logs\\a.txt\nC:\\Logs\\b.txt"},
            },
            {"shortcut_id": "target", "param_bindings": {"open_file": "1.outputs.path"}},
        ],
    )
    seen = []

    class Executor:
        @staticmethod
        def execute_with_files(shortcut, files):
            seen.append((shortcut.id, files))
            return True

        @staticmethod
        def execute(shortcut, force_new=False):
            raise AssertionError("file input should use execute_with_files")

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([target]))

    assert result.success is True
    assert seen == [("target", ["C:\\Logs\\a.txt", "C:\\Logs\\b.txt"])]
    assert "输入文件打开" in result.payload["items"][1]["detail"]


def test_chain_processor_assert_failure_respects_stop_on_error(monkeypatch):
    target = ShortcutItem(id="target", name="Target", type=ShortcutType.FILE)
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {"node_type": "processor", "processor_id": "assert_not_empty", "args": {"text": ""}},
            {"shortcut_id": "target"},
        ],
    )

    class Executor:
        @staticmethod
        def execute(shortcut, force_new=False):
            raise AssertionError("stop_on_error should prevent target execution")

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([target]))

    assert result.success is False
    assert len(result.payload["items"]) == 1


def test_python_processor_custom_output_and_multi_input_bindings():
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {
                "node_type": "processor",
                "processor_id": "python_cell",
                "source": 'INPUTS=[]\nOUTPUTS=["foo"]\ndef process(inputs):\n    return {"foo": "A"}\n',
            },
            {
                "node_type": "processor",
                "processor_id": "python_cell",
                "source": 'INPUTS=[]\nOUTPUTS=["bar"]\ndef process(inputs):\n    return {"bar": "B"}\n',
            },
            {
                "node_type": "processor",
                "processor_id": "python_cell",
                "input_binding": ["1.outputs.foo", "2.outputs.bar"],
                "source": (
                    'INPUTS=["input"]\nOUTPUTS=["joined"]\n'
                    "def process(inputs):\n"
                    '    return {"joined": ",".join(inputs["input"])}\n'
                ),
            },
        ],
    )

    result = execute_shortcut_chain(chain, _Data([], confirm_dangerous=True))

    assert result.success is True
    assert "A,B" in result.payload["items"][2]["detail"]


def test_dangerous_processor_requires_runtime_confirmation():
    chain = ShortcutItem(
        type=ShortcutType.CHAIN,
        chain_steps=[
            {
                "node_type": "processor",
                "processor_id": "python_cell",
                "source": 'INPUTS=[]\nOUTPUTS=["foo"]\ndef process(inputs):\n    return {"foo": "A"}\n',
            }
        ],
    )

    result = execute_shortcut_chain(chain, _Data([]))

    assert result.success is False
    assert "未确认" in result.payload["items"][0]["detail"]


def test_chain_guards_nested_missing_max_and_cancel(monkeypatch):
    nested = ShortcutItem(id="nested", name="Nested", type=ShortcutType.CHAIN)
    chain = ShortcutItem(type=ShortcutType.CHAIN)
    chain.chain_steps = [{"shortcut_id": "nested"}]
    result = execute_shortcut_chain(chain, _Data([nested]))
    assert result.success is False
    assert "嵌套" in result.payload["items"][0]["detail"]

    missing = ShortcutItem(type=ShortcutType.CHAIN, chain_steps=[{"shortcut_id": "missing"}])
    result = execute_shortcut_chain(missing, _Data([]))
    assert result.success is False
    assert "不存在" in result.payload["items"][0]["detail"]

    too_many = ShortcutItem(type=ShortcutType.CHAIN)
    too_many.chain_steps = [{"shortcut_id": "missing", "stop_on_error": False} for _ in range(51)]
    result = execute_shortcut_chain(too_many, _Data([]), max_steps=50)
    assert result.success is False
    assert "超过 50" in result.payload["items"][0]["detail"]

    event = threading.Event()
    event.set()
    cancelled = ShortcutItem(type=ShortcutType.CHAIN, chain_steps=[{"shortcut_id": "missing"}])
    result = execute_shortcut_chain(cancelled, _Data([]), cancel_event=event)
    assert result.success is False
    assert result.error == "已取消"


def test_empty_chain_returns_failure():
    """空步骤链应返回失败。"""
    chain = ShortcutItem(type=ShortcutType.CHAIN, chain_steps=[])
    result = execute_shortcut_chain(chain, _Data([]))
    assert result.success is False
    assert "no steps" in result.message.lower() or "没有" in result.message


def test_normalize_clamps_delay_ms_upper_bound():
    """delay_ms 超过 60000 应被钳位。"""
    steps = [{"shortcut_id": "a", "delay_ms": 99999}]
    normalized = ShortcutItem._normalize_chain_steps(steps)
    assert normalized[0]["delay_ms"] == 60000


def test_normalize_truncates_over_max_steps():
    """超过 MAX_CHAIN_STEPS 的步骤应被截断。"""
    steps = [{"shortcut_id": f"s{i}"} for i in range(150)]
    normalized = ShortcutItem._normalize_chain_steps(steps)
    assert len(normalized) == ShortcutItem.MAX_CHAIN_STEPS


def test_normalize_filters_empty_shortcut_id():
    """空 shortcut_id 的步骤应被过滤。"""
    steps = [
        {"shortcut_id": "valid"},
        {"shortcut_id": ""},
        {"shortcut_id": "  "},
        {"shortcut_id": "also_valid"},
    ]
    normalized = ShortcutItem._normalize_chain_steps(steps)
    assert len(normalized) == 2
    assert normalized[0]["shortcut_id"] == "valid"
    assert normalized[1]["shortcut_id"] == "also_valid"


def test_chain_to_dict_from_dict_roundtrip():
    """复杂动作链的序列化往返应保持一致。"""
    item = ShortcutItem(type=ShortcutType.CHAIN, name="Test Chain")
    item.chain_steps = [
        {
            "id": "s1",
            "shortcut_id": "aaa",
            "enabled": True,
            "stop_on_error": True,
            "delay_ms": 100,
            "input_binding": "prev.output",
            "param_bindings": {"host": "prev.outputs.host"},
            "args": {"port": "443"},
        },
        {"id": "s2", "shortcut_id": "bbb", "enabled": False, "stop_on_error": False, "delay_ms": 0},
        {"id": "s3", "shortcut_id": "ccc", "enabled": True, "stop_on_error": True, "delay_ms": 500},
    ]
    loaded = ShortcutItem.from_dict(item.to_dict())
    assert loaded.type == ShortcutType.CHAIN
    assert loaded.name == "Test Chain"
    assert len(loaded.chain_steps) == 3
    assert loaded.chain_steps[0]["shortcut_id"] == "aaa"
    assert loaded.chain_steps[0]["delay_ms"] == 100
    assert loaded.chain_steps[0]["input_binding"] == "prev.output"
    assert loaded.chain_steps[0]["param_bindings"] == {"host": "prev.outputs.host"}
    assert loaded.chain_steps[0]["args"] == {"port": "443"}
    assert loaded.chain_steps[1]["enabled"] is False
    assert loaded.chain_steps[1]["stop_on_error"] is False
    assert loaded.chain_steps[2]["delay_ms"] == 500


def test_chain_from_dict_missing_chain_steps_backward_compat():
    """旧配置缺少 chain_steps 字段时应加载为空列表。"""
    data = {"id": "old", "name": "Old Chain", "type": "chain"}
    loaded = ShortcutItem.from_dict(data)
    assert loaded.type == ShortcutType.CHAIN
    assert loaded.chain_steps == []
