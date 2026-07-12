"""Tests for the P1-06 Stage 1 observable collections."""

from __future__ import annotations

import pytest

from ui.view_models.observable import (
    ObservableDict,
    ObservableList,
    as_observable_dict,
    as_observable_list,
)

pytestmark = pytest.mark.ui


def test_observable_list_emits_on_append():
    items = ObservableList()
    seen = []
    items.changed.connect(lambda payload: seen.append(payload))
    items.append("a")
    items.append("b")
    assert [event["op"] for event in seen] == ["add", "add"]
    assert [event["index"] for event in seen] == [0, 1]


def test_observable_list_emits_on_pop_and_remove():
    items = ObservableList(["a", "b", "c"])
    seen = []
    items.changed.connect(lambda payload: seen.append(payload))
    items.pop(1)
    items.remove("a")
    assert [event["op"] for event in seen] == ["remove", "remove"]
    assert items == ["c"]


def test_observable_list_setitem_emits_update():
    items = ObservableList(["a", "b", "c"])
    seen = []
    items.changed.connect(lambda payload: seen.append(payload))
    items[0] = "x"
    items[5] = "y"  # out of range → treated as add
    assert [event["op"] for event in seen] == ["update", "add"]
    assert items == ["x", "b", "c", "y"]


def test_observable_list_clear_emits_reset():
    items = ObservableList([1, 2, 3])
    seen = []
    items.changed.connect(lambda payload: seen.append(payload))
    items.clear()
    # Second clear must not emit because the list is already empty.
    items.clear()
    assert [event["op"] for event in seen] == ["reset"]
    assert items == []


def test_observable_list_negative_index_overwrites():
    """Negative indices must overwrite like a real ``list``."""
    items = ObservableList(["a", "b", "c"])
    seen = []
    items.changed.connect(lambda payload: seen.append(payload))
    items[-1] = "z"
    assert list(items) == ["a", "b", "z"]
    assert seen[-1]["op"] == "update"


def test_observable_list_negative_index_out_of_range_raises():
    items = ObservableList(["a", "b"])
    with pytest.raises(IndexError):
        items[-5] = "z"


def test_observable_list_non_int_non_slice_index_raises():
    items = ObservableList()
    with pytest.raises(TypeError):
        items["foo"] = 1


def test_observable_list_extend_emits_per_item():
    items = ObservableList(["a"])
    seen = []
    items.changed.connect(lambda payload: seen.append(payload))
    items.extend(["b", "c"])
    adds = [event for event in seen if event["op"] == "add"]
    assert [event["value"] for event in adds] == ["b", "c"]
    assert [event["index"] for event in adds] == [1, 2]


def test_observable_list_slice_delete_emits_per_removed_item():
    items = ObservableList(["a", "b", "c", "d"])
    seen = []
    items.changed.connect(lambda payload: seen.append(payload))
    del items[1:3]
    removes = [event for event in seen if event["op"] == "remove"]
    assert len(removes) == 2
    assert list(items) == ["a", "d"]


def test_observable_list_slice_setitem_emits_per_replaced_item():
    items = ObservableList(["a", "b", "c", "d"])
    seen = []
    items.changed.connect(lambda payload: seen.append(payload))
    items[1:3] = ["x", "y", "z"]
    updates = [event for event in seen if event["op"] == "update"]
    assert len(updates) == 3
    assert list(items) == ["a", "x", "y", "z", "d"]


def test_observable_dict_pop_validates_arity():
    mapping = ObservableDict({"a": 1})
    with pytest.raises(TypeError):
        mapping.pop("missing", 1, 2, 3)


def test_observable_list_iteration_is_list_like():
    items = ObservableList(["a", "b", "c"])
    assert len(items) == 3
    assert items[1] == "b"
    assert list(items) == ["a", "b", "c"]
    assert "a" in items
    assert "z" not in items
    assert items.index("b") == 1
    assert items.count("a") == 1


def test_observable_dict_emits_on_setitem():
    mapping = ObservableDict()
    seen = []
    mapping.changed.connect(lambda payload: seen.append(payload))
    mapping["a"] = 1
    mapping["b"] = 2
    mapping["a"] = 3
    assert [event["op"] for event in seen] == ["add", "add", "update"]
    assert mapping["a"] == 3


def test_observable_dict_emits_on_pop_and_del():
    mapping = ObservableDict({"a": 1, "b": 2})
    seen = []
    mapping.changed.connect(lambda payload: seen.append(payload))
    del mapping["a"]
    mapping.pop("b")
    assert [event["op"] for event in seen] == ["remove", "remove"]
    assert dict(mapping) == {}


def test_observable_dict_clear_emits_reset_only_once():
    mapping = ObservableDict({"a": 1})
    seen = []
    mapping.changed.connect(lambda payload: seen.append(payload))
    mapping.clear()
    mapping.clear()
    assert [event["op"] for event in seen] == ["reset"]


def test_observable_dict_getitem_and_iteration():
    mapping = ObservableDict({"a": 1, "b": 2})
    assert len(mapping) == 2
    assert mapping["a"] == 1
    assert mapping.get("missing", 99) == 99
    assert set(mapping.keys()) == {"a", "b"}
    assert set(mapping.values()) == {1, 2}


def test_observable_dict_update_emits_per_key():
    mapping = ObservableDict({"a": 1})
    seen = []
    mapping.changed.connect(lambda payload: seen.append(payload))
    mapping.update({"b": 2, "c": 3})
    mapping.update(a=10)
    assert [event["op"] for event in seen] == ["add", "add", "update"]


def test_as_observable_helpers_return_fresh_collections():
    items = as_observable_list([1, 2])
    mapping = as_observable_dict({"a": 1})
    assert isinstance(items, ObservableList)
    assert isinstance(mapping, ObservableDict)
    assert items == [1, 2]
    assert dict(mapping) == {"a": 1}


def test_observable_collections_do_not_share_state():
    items1 = as_observable_list([1, 2])
    items2 = as_observable_list([1, 2])
    items1.append(3)
    assert items2 == [1, 2]
