import threading

from core.command_registry import CommandResult
from core.data_models import Folder, ShortcutItem, ShortcutType
from core.shortcut_chain_exec import execute_shortcut_chain


class _Data:
    def __init__(self, items):
        self.data = type("AppData", (), {"folders": [Folder(id="f", name="F", items=items)]})()


def test_shortcut_item_serializes_chain_steps():
    item = ShortcutItem(type=ShortcutType.CHAIN, name="chain")
    item.chain_steps = [{"shortcut_id": "a", "enabled": False, "stop_on_error": False, "delay_ms": 5}]

    loaded = ShortcutItem.from_dict(item.to_dict())

    assert loaded.type == ShortcutType.CHAIN
    assert loaded.chain_steps[0]["shortcut_id"] == "a"
    assert loaded.chain_steps[0]["enabled"] is False
    assert loaded.chain_steps[0]["stop_on_error"] is False
    assert loaded.chain_steps[0]["delay_ms"] == 5


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
            seen.append((shortcut.id, getattr(shortcut, "_runtime_input_values", {}), getattr(shortcut, "_chain_values", {})))
            if shortcut.id == "first":
                return CommandResult(success=True, message="done", display_type="log", payload={"stdout": "hello"})
            return CommandResult(success=True, message="done", display_type="log", payload={"stdout": "ok"})

    monkeypatch.setattr("core.ShortcutExecutor", Executor)

    result = execute_shortcut_chain(chain, _Data([first, second]))

    assert result.success is True
    assert seen[1][1]["input"] == "hello"
    assert seen[1][2]["prev.stdout"] == "hello"


def test_chain_guards_nested_missing_max_and_cancel(monkeypatch):
    nested = ShortcutItem(id="nested", name="Nested", type=ShortcutType.CHAIN)
    chain = ShortcutItem(type=ShortcutType.CHAIN)
    chain.chain_steps = [{"shortcut_id": "nested"}]
    result = execute_shortcut_chain(chain, _Data([nested]))
    assert result.success is False
    assert "Nested" in result.payload["items"][0]["detail"]

    missing = ShortcutItem(type=ShortcutType.CHAIN, chain_steps=[{"shortcut_id": "missing"}])
    result = execute_shortcut_chain(missing, _Data([]))
    assert result.success is False
    assert "not found" in result.payload["items"][0]["detail"]

    too_many = ShortcutItem(type=ShortcutType.CHAIN)
    too_many.chain_steps = [{"shortcut_id": "missing", "stop_on_error": False} for _ in range(51)]
    result = execute_shortcut_chain(too_many, _Data([]), max_steps=50)
    assert result.success is False
    assert "more than 50" in result.payload["items"][0]["detail"]

    event = threading.Event()
    event.set()
    cancelled = ShortcutItem(type=ShortcutType.CHAIN, chain_steps=[{"shortcut_id": "missing"}])
    result = execute_shortcut_chain(cancelled, _Data([]), cancel_event=event)
    assert result.success is False
    assert result.error == "Cancelled"


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
        {"id": "s1", "shortcut_id": "aaa", "enabled": True, "stop_on_error": True, "delay_ms": 100},
        {"id": "s2", "shortcut_id": "bbb", "enabled": False, "stop_on_error": False, "delay_ms": 0},
        {"id": "s3", "shortcut_id": "ccc", "enabled": True, "stop_on_error": True, "delay_ms": 500},
    ]
    loaded = ShortcutItem.from_dict(item.to_dict())
    assert loaded.type == ShortcutType.CHAIN
    assert loaded.name == "Test Chain"
    assert len(loaded.chain_steps) == 3
    assert loaded.chain_steps[0]["shortcut_id"] == "aaa"
    assert loaded.chain_steps[0]["delay_ms"] == 100
    assert loaded.chain_steps[1]["enabled"] is False
    assert loaded.chain_steps[1]["stop_on_error"] is False
    assert loaded.chain_steps[2]["delay_ms"] == 500


def test_chain_from_dict_missing_chain_steps_backward_compat():
    """旧配置缺少 chain_steps 字段时应加载为空列表。"""
    data = {"id": "old", "name": "Old Chain", "type": "chain"}
    loaded = ShortcutItem.from_dict(data)
    assert loaded.type == ShortcutType.CHAIN
    assert loaded.chain_steps == []
