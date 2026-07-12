"""Tests for the P1-06 Stage 3 :class:`IconGridViewModel`."""

from __future__ import annotations

import pytest

from ui.view_models.icon_grid_view_model import IconGridViewModel

pytestmark = pytest.mark.ui


def _icon(item_id: str, name: str = "", type_: str = "shortcut", order: int = 0) -> dict:
    return {
        "id": item_id,
        "name": name or item_id,
        "type": type_,
        "order": order,
        "command": "echo hi",
        "command_type": "cmd",
    }


def test_default_state_is_empty():
    vm = IconGridViewModel()
    assert vm.get_items() == []
    assert vm.get_selection() == []
    assert vm.get_drag_payload() == []
    assert vm.get_search_query() == ""


def test_set_items_emits_inserts_and_resets_selection():
    vm = IconGridViewModel()
    seen_inserts = []
    vm.item_inserted.connect(lambda i: seen_inserts.append(i))
    vm.set_items([_icon("a"), _icon("b")])
    assert seen_inserts == [0, 1]
    assert vm.get_selection() == []


def test_append_and_remove_item_keep_selection_consistent():
    vm = IconGridViewModel()
    vm.set_items([_icon("a"), _icon("b")])
    vm.set_selection(["a", "b"])
    assert vm.remove_item("a") is True
    assert vm.is_selected("a") is False
    assert vm.is_selected("b") is True
    assert vm.item_count() == 1


def test_update_item_emits_updated_signal():
    vm = IconGridViewModel()
    vm.set_items([_icon("a", "Alpha")])
    seen = []
    vm.item_updated.connect(lambda i: seen.append(i))
    assert vm.update_item("a", name="Beta") is True
    assert vm.find_item("a")["name"] == "Beta"
    assert seen == [0]


def test_find_item_returns_none_for_missing():
    vm = IconGridViewModel()
    assert vm.find_item("nope") is None


def test_set_selection_emits_signal_with_first_id():
    vm = IconGridViewModel()
    seen = []
    vm.selection_changed.connect(lambda sel: seen.append(sel))
    vm.set_selection(["a", "b"])
    assert seen == [["a", "b"]]
    # ``add_to_selection`` reuses the same payload format.
    vm.add_to_selection("c")
    assert seen[-1] == ["a", "b", "c"]


def test_clear_selection_only_emits_when_changed():
    vm = IconGridViewModel()
    seen = []
    vm.selection_changed.connect(lambda sel: seen.append(sel))
    vm.clear_selection()
    assert seen == []
    vm.set_selection(["a"])
    vm.clear_selection()
    assert seen == [["a"], []]


def test_drag_payload_round_trip():
    vm = IconGridViewModel()
    seen_started, seen_ended = [], []
    vm.drag_started.connect(lambda payload: seen_started.append(payload))
    vm.drag_ended.connect(lambda: seen_ended.append(True))
    vm.begin_drag(["a", "b"])
    assert vm.get_drag_payload() == ["a", "b"]
    assert seen_started == [["a", "b"]]
    vm.end_drag()
    assert vm.get_drag_payload() == []
    assert seen_ended == [True]


def test_end_drag_is_noop_when_payload_empty():
    vm = IconGridViewModel()
    seen_ended = []
    vm.drag_ended.connect(lambda: seen_ended.append(True))
    vm.end_drag()
    assert seen_ended == []


def test_move_items_reorders_in_place():
    vm = IconGridViewModel()
    vm.set_items([_icon("a"), _icon("b"), _icon("c"), _icon("d")])
    moved = vm.move_items(["a", "b"], target_index=3)
    assert moved == 2
    assert [item["id"] for item in vm.get_items()] == ["c", "d", "a", "b"]


def test_move_items_unknown_is_noop():
    vm = IconGridViewModel()
    vm.set_items([_icon("a")])
    moved = vm.move_items(["nope"], target_index=0)
    assert moved == 0
    assert [item["id"] for item in vm.get_items()] == ["a"]


def test_set_search_query_emits_state_changed():
    vm = IconGridViewModel()
    seen = []
    vm.state_changed.connect(lambda payload: seen.append(payload))
    vm.set_search_query("abc")
    vm.set_search_query("abc")  # idempotent
    assert seen == [{"search_query": "abc"}]
    assert vm.get_search_query() == "abc"


def test_filter_items_matches_name_id_and_type():
    vm = IconGridViewModel()
    vm.set_items(
        [
            _icon("a", "Alpha"),
            _icon("b", "Beta"),
            {"id": "f", "name": "Folder", "type": "folder"},
        ]
    )
    assert [item["id"] for item in vm.filter_items("alp")] == ["a"]
    assert [item["id"] for item in vm.filter_items("folder")] == ["f"]
    # An empty query returns every item.
    assert len(vm.filter_items("")) == 3


def test_sort_items_groups_folders_first():
    vm = IconGridViewModel()
    vm.set_items(
        [
            _icon("a", "Z-shortcut"),
            {"id": "f", "name": "Folder", "type": "folder"},
            _icon("b", "A-shortcut"),
        ]
    )
    vm.sort_items()
    items = vm.get_items()
    assert items[0]["id"] == "f"
    assert items[1]["name"] == "A-shortcut"
    assert items[2]["name"] == "Z-shortcut"


def test_shortcuts_in_skips_non_dict_items():
    vm = IconGridViewModel()
    vm.set_items(
        [
            _icon("a", "Alpha"),
            "garbage",
            None,
        ]
    )
    result = vm.shortcuts_in()
    assert len(result) == 1
    assert result[0].id == "a"
    assert result[0].name == "Alpha"


def test_shutdown_clears_state():
    vm = IconGridViewModel()
    vm.set_items([_icon("a")])
    vm.set_selection(["a"])
    vm.begin_drag(["a"])
    vm.shutdown()
    assert vm.get_items() == []
    assert vm.get_selection() == []
    assert vm.get_drag_payload() == []
