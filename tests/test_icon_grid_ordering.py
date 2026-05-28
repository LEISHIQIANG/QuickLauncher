from ui.config_window.icon_grid_ordering import move_drag_group_order


def test_move_drag_group_order_moves_down_as_block():
    assert move_drag_group_order(["one", "two", "three"], "one", "three", ["one", "two"]) == [
        "three",
        "one",
        "two",
    ]


def test_move_drag_group_order_moves_up_as_block():
    assert move_drag_group_order(["one", "two", "three", "four"], "three", "one", ["three", "four"]) == [
        "three",
        "four",
        "one",
        "two",
    ]


def test_move_drag_group_order_preserves_non_shortcut_slots():
    assert move_drag_group_order(["one", None, "two", "three"], "one", "three", ["one"]) == [
        None,
        "two",
        "three",
        "one",
    ]


def test_move_drag_group_order_rejects_target_inside_drag_group():
    assert move_drag_group_order(["one", "two", "three"], "one", "two", ["one", "two"]) is None


def test_move_drag_group_order_rejects_missing_target_or_drag_group():
    assert move_drag_group_order(["one", "two"], "one", "missing", ["one"]) is None
    assert move_drag_group_order(["one", "two"], "missing", "two", ["missing"]) is None
