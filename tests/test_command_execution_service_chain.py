import core
from core.command_execution_service import CommandExecutionRequest, CommandExecutionService
from core.command_results import CommandResultStore
from core.data_models import Folder, ShortcutItem, ShortcutType


def _make_data_manager(step, chain):
    return type("DM", (), {"data": type("Data", (), {"folders": [Folder(id="f", name="F", items=[step, chain])]})()})()


def test_shortcut_chain_runs_and_stores_result(monkeypatch):
    class FakeExecutor:
        @staticmethod
        def execute(shortcut, force_new=False):
            return True, ""

    monkeypatch.setattr(core, "ShortcutExecutor", FakeExecutor)
    step = ShortcutItem(id="step", name="Step", type=ShortcutType.FILE)
    chain = ShortcutItem(id="chain", name="Chain", type=ShortcutType.CHAIN, chain_steps=[{"shortcut_id": "step"}])
    data_manager = _make_data_manager(step, chain)
    store = CommandResultStore()
    service = CommandExecutionService(store)

    result, duration, result_id = service.execute_shortcut_chain_sync(
        CommandExecutionRequest(
            command_id="chain",
            raw_input="Chain",
            source="shortcut_chain",
            shortcut=chain,
            context_meta={"data_manager": data_manager},
        )
    )

    assert result.success is True
    assert result.display_type == "list"
    assert duration >= 0
    stored = store.get(result_id)
    assert stored.command_id == "chain"
    assert stored.command_title == "Chain"


def test_chain_with_missing_step_reports_failure(monkeypatch):
    class FakeExecutor:
        @staticmethod
        def execute(shortcut, force_new=False):
            return True, ""

    monkeypatch.setattr(core, "ShortcutExecutor", FakeExecutor)
    step = ShortcutItem(id="step", name="Step", type=ShortcutType.FILE)
    chain = ShortcutItem(
        id="chain",
        name="Chain",
        type=ShortcutType.CHAIN,
        chain_steps=[{"shortcut_id": "nonexistent"}],
    )
    data_manager = _make_data_manager(step, chain)
    store = CommandResultStore()
    service = CommandExecutionService(store)

    result, duration, result_id = service.execute_shortcut_chain_sync(
        CommandExecutionRequest(
            command_id="chain",
            raw_input="Chain",
            source="shortcut_chain",
            shortcut=chain,
            context_meta={"data_manager": data_manager},
        )
    )

    assert result.success is False
    assert "不存在" in result.message or "not found" in result.message.lower() or "nonexistent" in result.message


def test_chain_with_multiple_steps(monkeypatch):
    executed = []

    class FakeExecutor:
        @staticmethod
        def execute(shortcut, force_new=False):
            executed.append(shortcut.id)
            return True, ""

    monkeypatch.setattr(core, "ShortcutExecutor", FakeExecutor)
    step1 = ShortcutItem(id="step1", name="Step1", type=ShortcutType.FILE)
    step2 = ShortcutItem(id="step2", name="Step2", type=ShortcutType.FILE)
    chain = ShortcutItem(
        id="chain",
        name="MultiChain",
        type=ShortcutType.CHAIN,
        chain_steps=[{"shortcut_id": "step1"}, {"shortcut_id": "step2"}],
    )
    dm = type(
        "DM",
        (),
        {
            "data": type(
                "Data",
                (),
                {"folders": [Folder(id="f", name="F", items=[step1, step2, chain])]},
            )()
        },
    )()
    store = CommandResultStore()
    service = CommandExecutionService(store)

    result, duration, result_id = service.execute_shortcut_chain_sync(
        CommandExecutionRequest(
            command_id="chain",
            raw_input="MultiChain",
            source="shortcut_chain",
            shortcut=chain,
            context_meta={"data_manager": dm},
        )
    )

    assert result.success is True
    assert "step1" in executed
    assert "step2" in executed
    assert len(executed) == 2
