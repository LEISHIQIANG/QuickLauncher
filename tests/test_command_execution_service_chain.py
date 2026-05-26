import core
from core.command_execution_service import CommandExecutionRequest, CommandExecutionService
from core.command_results import CommandResultStore
from core.data_models import Folder, ShortcutItem, ShortcutType


def test_shortcut_chain_runs_and_stores_result(monkeypatch):
    class FakeExecutor:
        @staticmethod
        def execute(shortcut, force_new=False):
            return True, ""

    monkeypatch.setattr(core, "ShortcutExecutor", FakeExecutor)
    step = ShortcutItem(id="step", name="Step", type=ShortcutType.FILE)
    chain = ShortcutItem(id="chain", name="Chain", type=ShortcutType.CHAIN, chain_steps=[{"shortcut_id": "step"}])
    data_manager = type(
        "DM", (), {"data": type("Data", (), {"folders": [Folder(id="f", name="F", items=[step, chain])]})()}
    )()
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
