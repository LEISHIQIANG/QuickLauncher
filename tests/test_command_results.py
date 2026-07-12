from core.command_registry import CommandResult
from core.command_results import CommandResultStore


def test_command_result_store_keeps_latest_first_and_limits_capacity():
    store = CommandResultStore(max_items=2)

    first = store.add(CommandResult(message="one"), command_id="one")
    second = store.add(CommandResult(message="two"), command_id="two")
    third = store.add(CommandResult(message="three"), command_id="three")

    items = store.list()
    assert [item.id for item in items] == [third, second]
    assert store.get(first) is None
    assert store.latest().result.message == "three"


def test_command_result_store_preserves_metadata_and_clears():
    store = CommandResultStore(max_items=5)
    result_id = store.add(
        CommandResult(message="ok"),
        command_id="uuid",
        command_title="UUID",
        raw_input="/uuid",
        source="builtin",
        duration=0.25,
        created_at=123.0,
        args={"host": "example.com"},
        masked_args={"token": "******", "host": "example.com"},
        has_sensitive_args=True,
        context_meta={"selected_files": ["C:/a.txt"]},
        outputs={"host": "example.com"},
    )

    stored = store.get(result_id)
    assert stored.command_id == "uuid"
    assert stored.command_title == "UUID"
    assert stored.raw_input == "/uuid"
    assert stored.source == "builtin"
    assert stored.duration == 0.25
    assert stored.created_at == 123.0
    assert stored.args == {"host": "example.com"}
    assert stored.masked_args == {"token": "******", "host": "example.com"}
    assert stored.has_sensitive_args is True
    assert stored.context_meta == {"selected_files": ["C:/a.txt"]}
    assert stored.outputs == {"host": "example.com"}

    store.clear()
    assert store.list() == []


def test_command_result_store_defaults_to_five_recent_items():
    store = CommandResultStore()

    for idx in range(6):
        store.add(CommandResult(message=str(idx)), command_id=str(idx))

    items = store.list()
    assert len(items) == 5
    assert [item.result.message for item in items] == ["5", "4", "3", "2", "1"]
