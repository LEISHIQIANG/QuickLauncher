from types import SimpleNamespace

from core.batch_launch_exec import execute_batch_launch
from core.data_models import Folder, ShortcutItem, ShortcutType


class _Data:
    def __init__(self, items):
        self.data = SimpleNamespace(folders=[Folder(id="f", name="Folder", items=list(items))])


def test_batch_launch_executes_steps_in_order(monkeypatch):
    calls = []
    one = ShortcutItem(id="one", name="One", type=ShortcutType.FILE)
    two = ShortcutItem(id="two", name="Two", type=ShortcutType.URL)
    batch = ShortcutItem(
        id="batch",
        name="Batch",
        type=ShortcutType.BATCH_LAUNCH,
        batch_launch_steps=[
            {"shortcut_id": "one"},
            {"shortcut_id": "two"},
        ],
    )

    from core import shortcut_executor

    monkeypatch.setattr(
        shortcut_executor.ShortcutExecutor,
        "execute",
        staticmethod(lambda shortcut, _force_new=False: (calls.append(shortcut.id) or True, "")),
    )

    result = execute_batch_launch(batch, _Data([one, two, batch]))

    assert result.success is True
    assert calls == ["one", "two"]
    assert result.payload["kind"] == "batch_launch"


def test_batch_launch_reports_missing_reference():
    batch = ShortcutItem(
        id="batch",
        name="Batch",
        type=ShortcutType.BATCH_LAUNCH,
        batch_launch_steps=[{"shortcut_id": "missing"}],
    )

    result = execute_batch_launch(batch, _Data([batch]))

    assert result.success is False
    assert result.error == "引用的快捷方式不存在。"
    assert result.payload["items"][0]["shortcut_id"] == "missing"


def test_batch_launch_rejects_nested_batch_or_chain():
    nested = ShortcutItem(id="nested", name="Nested", type=ShortcutType.BATCH_LAUNCH)
    chain = ShortcutItem(id="chain", name="Chain", type=ShortcutType.CHAIN)
    batch = ShortcutItem(
        id="batch",
        name="Batch",
        type=ShortcutType.BATCH_LAUNCH,
        batch_launch_steps=[
            {"shortcut_id": "nested", "stop_on_error": False},
            {"shortcut_id": "chain", "stop_on_error": False},
        ],
    )

    result = execute_batch_launch(batch, _Data([nested, chain, batch]))

    assert result.success is False
    assert [item["status"] for item in result.payload["items"]] == ["failed", "failed"]
    assert all("嵌套" in item["detail"] for item in result.payload["items"])
