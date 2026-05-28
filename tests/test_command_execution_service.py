import threading
import time

from core.command_execution_service import CommandExecutionRequest, CommandExecutionService
from core.command_registry import CommandDefinition, CommandResult
from core.command_results import CommandResultStore
from core.data_models import ShortcutItem, ShortcutType


def _cmd(command_id, handler):
    return CommandDefinition(
        id=command_id,
        title="Test Command",
        aliases=[],
        description="",
        category="",
        handler=handler,
        source="test",
    )


def test_registry_command_success_update_and_store(monkeypatch):
    updates = []
    finished = []
    done = threading.Event()
    store = CommandResultStore()

    def handler(ctx):
        assert ctx.args == {"name": "LEI"}
        ctx.update_callback(CommandResult(message="working", progress=0.5))
        return CommandResult(message=f"done {ctx.args_text}")

    cmd = _cmd("test.echo", handler)
    service = CommandExecutionService(store)
    service.run_registry_command(
        CommandExecutionRequest(
            command_id="test.echo",
            args_text="hello",
            raw_input="/test.echo hello",
            args={"name": "LEI"},
            command_def=cmd,
        ),
        on_update=lambda token, result, command_def: updates.append((token, result.message, command_def.id)),
        on_finished=lambda token, result, command_def, duration, result_id: (finished.append(result_id), done.set()),
    )

    assert done.wait(2)
    assert updates and updates[0][1:] == ("working", "test.echo")
    stored = store.get(finished[0])
    assert stored.command_id == "test.echo"
    assert stored.raw_input == "/test.echo hello"
    assert stored.result.message == "done hello"


def test_registry_command_exception_and_bad_return_are_results():
    store = CommandResultStore()
    done = threading.Event()
    results = []
    service = CommandExecutionService(store)

    service.run_registry_command(
        CommandExecutionRequest(command_id="bad", command_def=_cmd("bad", lambda ctx: "nope")),
        on_finished=lambda token, result, command_def, duration, result_id: (results.append(result), done.set()),
    )
    assert done.wait(2)
    assert results[0].success is False
    assert "类型错误" in results[0].error

    done.clear()
    results.clear()

    def boom(ctx):
        raise RuntimeError("broken")

    service.run_registry_command(
        CommandExecutionRequest(command_id="boom", command_def=_cmd("boom", boom)),
        on_finished=lambda token, result, command_def, duration, result_id: (results.append(result), done.set()),
    )
    assert done.wait(2)
    assert results[0].success is False
    assert "broken" in results[0].error


def test_cancelled_registry_command_does_not_finish():
    started = threading.Event()
    finished = []
    service = CommandExecutionService(CommandResultStore())

    def handler(ctx):
        started.set()
        time.sleep(0.15)
        return CommandResult(message="late")

    handle = service.run_registry_command(
        CommandExecutionRequest(command_id="slow", command_def=_cmd("slow", handler)),
        on_finished=lambda *args: finished.append(args),
    )
    assert started.wait(1)
    handle.cancel()
    time.sleep(0.25)
    assert finished == []


def test_shortcut_capture_cancel_kills_process(monkeypatch):
    import core

    killed = []

    class FakeExecutor:
        @staticmethod
        def run_command_capture(shortcut, timeout=None, cancel_event=None):
            assert cancel_event is not None
            cancel_event.wait(1)
            killed.append(True)
            return CommandResult(success=False, message="cancelled", display_type="log", error="已取消")

    monkeypatch.setattr(core, "ShortcutExecutor", FakeExecutor)

    done = threading.Event()
    results = []
    service = CommandExecutionService(CommandResultStore())
    item = ShortcutItem(id="cap", name="Capture", type=ShortcutType.COMMAND, command="slow", command_type="cmd")
    handle = service.run_shortcut_capture(
        CommandExecutionRequest(command_id="cap", raw_input="slow", source="shortcut", shortcut=item),
        on_finished=lambda token, result, command_def, duration, result_id: (results.append(result), done.set()),
    )
    handle.cancel()

    assert done.wait(2)
    assert killed == [True]
    assert results[0].error == "已取消"


def test_shortcut_command_forwards_stream_updates(monkeypatch):
    import core

    updates = []

    class FakeExecutor:
        @staticmethod
        def run_command_capture(shortcut, timeout=None, cancel_event=None, on_update=None):
            assert on_update is not None
            on_update(CommandResult(success=True, message="partial", display_type="log"))
            return CommandResult(success=True, message="done", display_type="log")

    monkeypatch.setattr(core, "ShortcutExecutor", FakeExecutor)

    done = threading.Event()
    results = []
    service = CommandExecutionService(CommandResultStore())
    item = ShortcutItem(id="cap", name="Capture", type=ShortcutType.COMMAND, command="slow", command_type="cmd")
    service.run_shortcut_command(
        CommandExecutionRequest(command_id="cap", raw_input="slow", source="shortcut", shortcut=item),
        on_update=lambda token, result, command_def: updates.append((token, result.message, command_def)),
        on_finished=lambda token, result, command_def, duration, result_id: (results.append(result), done.set()),
    )

    assert done.wait(2)
    assert updates and updates[0][1:] == ("partial", None)
    assert results[0].message == "done"


def test_shortcut_command_routes_bash_capture_to_capture_runner(monkeypatch):
    import core

    seen = []

    class FakeExecutor:
        @staticmethod
        def run_command_capture(shortcut, timeout=None, cancel_event=None, on_update=None):
            seen.append((shortcut.command_type, on_update is not None))
            return CommandResult(success=True, message="bash done", display_type="log")

    monkeypatch.setattr(core, "ShortcutExecutor", FakeExecutor)

    done = threading.Event()
    results = []
    service = CommandExecutionService(CommandResultStore())
    item = ShortcutItem(id="bash", name="Bash", type=ShortcutType.COMMAND, command="echo ok", command_type="bash")
    service.run_shortcut_command(
        CommandExecutionRequest(command_id="bash", raw_input="echo ok", source="shortcut", shortcut=item),
        on_update=lambda token, result, command_def: None,
        on_finished=lambda token, result, command_def, duration, result_id: (results.append(result), done.set()),
    )

    assert done.wait(2)
    assert seen == [("bash", True)]
    assert results[0].message == "bash done"
