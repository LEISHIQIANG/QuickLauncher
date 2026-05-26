"""Config icon grid selection and batch action regressions."""

from types import SimpleNamespace

import ui.config_window.icon_grid as grid_mod
from core import ShortcutItem, ShortcutType
from qt_compat import QPoint, Qt
from ui.config_window.icon_grid import IconContainer, IconGrid, IconWidget


class _Widget:
    def __init__(self, shortcut_id):
        self.shortcut = SimpleNamespace(id=shortcut_id)
        self.selected = False
        self.visible = True

    def set_selected(self, selected):
        self.selected = bool(selected)

    def setVisible(self, visible):
        self.visible = bool(visible)


def _grid_with_widgets():
    grid = IconGrid.__new__(IconGrid)
    grid.icon_widgets = [_Widget("one"), _Widget("two"), _Widget("three")]
    grid.selected_shortcut_ids = set()
    grid._last_selected_index = -1
    return grid


def test_ctrl_and_shift_click_update_selection(monkeypatch):
    grid = _grid_with_widgets()

    monkeypatch.setattr(grid_mod.QApplication, "keyboardModifiers", lambda: 0)
    IconGrid._on_item_clicked(grid, grid.icon_widgets[0].shortcut)

    assert grid.selected_shortcut_ids == {"one"}
    assert grid.icon_widgets[0].selected

    monkeypatch.setattr(grid_mod.QApplication, "keyboardModifiers", lambda: grid_mod.QtCompat.ControlModifier)
    IconGrid._on_item_clicked(grid, grid.icon_widgets[2].shortcut)

    assert grid.selected_shortcut_ids == {"one", "three"}

    monkeypatch.setattr(grid_mod.QApplication, "keyboardModifiers", lambda: grid_mod.QtCompat.ShiftModifier)
    IconGrid._on_item_clicked(grid, grid.icon_widgets[1].shortcut)

    assert grid.selected_shortcut_ids == {"one", "two", "three"}
    assert all(widget.selected for widget in grid.icon_widgets)


def test_batch_actions_refresh_folder_and_emit_signal():
    grid = _grid_with_widgets()
    calls = []
    emits = []

    grid.current_folder_id = "source"
    grid._take_batch_snapshot = lambda: calls.append(("snapshot",))
    grid._confirm_batch = lambda title, count: True
    grid.load_folder = lambda folder_id: calls.append(("load", folder_id))
    grid.shortcut_added = SimpleNamespace(emit=lambda: emits.append(True))
    grid.data_manager = SimpleNamespace(
        set_shortcuts_enabled_batch=lambda ids, enabled: calls.append(("enabled", tuple(ids), enabled)),
        delete_shortcuts_batch=lambda ids: calls.append(("delete", tuple(ids))),
    )

    IconGrid._batch_set_enabled(grid, ["one", "two"], False)
    IconGrid._batch_delete(grid, ["one", "two"])

    assert ("enabled", ("one", "two"), False) in calls
    assert ("delete", ("one", "two")) in calls
    assert calls.count(("load", "source")) == 2
    assert emits == [True, True]


def test_drag_ids_follow_current_selection_order():
    grid = _grid_with_widgets()
    grid.selected_shortcut_ids = {"three", "one"}

    assert IconGrid.get_drag_shortcut_ids(grid, "one") == ["one", "three"]
    assert IconGrid.get_drag_shortcut_ids(grid, "two") == ["two"]


def test_multi_drag_group_moves_down_as_a_block():
    grid = _grid_with_widgets()

    moved = IconGrid._move_drag_group(grid, "one", "three", ["one", "two"])

    assert moved is True
    assert [widget.shortcut.id for widget in grid.icon_widgets] == ["three", "one", "two"]


def test_multi_drag_group_moves_up_as_a_block():
    grid = _grid_with_widgets()
    grid.icon_widgets = [_Widget("one"), _Widget("two"), _Widget("three"), _Widget("four")]

    moved = IconGrid._move_drag_group(grid, "three", "one", ["three", "four"])

    assert moved is True
    assert [widget.shortcut.id for widget in grid.icon_widgets] == ["three", "four", "one", "two"]


def test_multi_drag_over_selected_target_is_noop():
    grid = _grid_with_widgets()

    moved = IconGrid._move_drag_group(grid, "one", "two", ["one", "two"])

    assert moved is False
    assert [widget.shortcut.id for widget in grid.icon_widgets] == ["one", "two", "three"]


def test_drag_leave_removes_active_placeholder_and_restore_adds_it_back():
    grid = _grid_with_widgets()
    grid._initial_widgets = list(grid.icon_widgets)
    grid._active_drag_ids = ["one"]
    place_calls = []
    grid._place_icons = lambda animate=False: place_calls.append(animate)

    IconGrid._remove_active_drag_placeholders(grid, animate=True)

    assert [widget.shortcut.id for widget in grid.icon_widgets] == ["two", "three"]
    assert grid._initial_widgets[0].visible is False
    assert place_calls == [True]

    IconGrid._restore_drag_preview_order(grid, animate=False)

    assert [widget.shortcut.id for widget in grid.icon_widgets] == ["one", "two", "three"]
    assert grid._initial_widgets[0].visible is True
    assert place_calls == [True, False]


def test_realtime_swap_restores_placeholder_after_drag_returns():
    grid = _grid_with_widgets()
    grid._initial_widgets = list(grid.icon_widgets)
    grid._active_drag_ids = ["one"]
    grid.data_manager = SimpleNamespace(
        get_settings=lambda: SimpleNamespace(sort_mode="custom"),
    )
    place_calls = []
    grid._place_icons = lambda animate=False: place_calls.append(animate)

    IconGrid._remove_active_drag_placeholders(grid, animate=True)
    IconGrid.handle_realtime_swap(grid, "one", "three")

    assert [widget.shortcut.id for widget in grid.icon_widgets] == ["two", "three", "one"]
    assert grid._initial_widgets[0].visible is True
    assert place_calls == [True, False, True]


def test_realtime_swap_suppresses_boundary_jitter(monkeypatch):
    grid = _grid_with_widgets()
    grid.data_manager = SimpleNamespace(
        get_settings=lambda: SimpleNamespace(sort_mode="custom"),
    )
    grid._get_cell_size = lambda: 60
    place_calls = []
    grid._place_icons = lambda animate=False: place_calls.append(animate)
    times = [10.0, 10.05, 10.08, 10.10, 10.11]
    monkeypatch.setattr(grid_mod.time, "monotonic", lambda: times.pop(0))

    IconGrid.handle_realtime_swap(grid, "one", "three", pointer_pos=QPoint(100, 100))
    IconGrid.handle_realtime_swap(grid, "one", "two", pointer_pos=QPoint(104, 101))
    IconGrid.handle_realtime_swap(grid, "one", "two", pointer_pos=QPoint(122, 101))

    assert [widget.shortcut.id for widget in grid.icon_widgets] == ["two", "three", "one"]
    assert place_calls == [True]

    IconGrid.handle_realtime_swap(grid, "one", "two", pointer_pos=QPoint(136, 100))

    assert [widget.shortcut.id for widget in grid.icon_widgets] == ["one", "two", "three"]
    assert place_calls == [True, True]


def test_double_click_edit_emits_signal_directly(monkeypatch, qapp):
    """mouseDoubleClickEvent emits the double_clicked signal."""
    widget = IconWidget(ShortcutItem(id="one", name="One", type=ShortcutType.FILE))
    emitted = []
    widget.double_clicked.connect(lambda: emitted.append(True))
    try:
        from qt_compat import QtCompat
        class _FakeEvent:
            def button(self):
                return QtCompat.LeftButton
        widget.mouseDoubleClickEvent(_FakeEvent())
        assert emitted == [True]
    finally:
        widget.deleteLater()


def test_stale_icon_load_generation_is_ignored():
    grid = _grid_with_widgets()
    grid._icon_load_generation = 2

    IconGrid._on_icon_loaded(grid, 1, "one", None)

    assert grid._icon_load_generation == 2


def test_clear_icons_skips_deleted_wrappers():
    class DeletedWidget:
        def __getattribute__(self, name):
            if name in {"_pos_anim", "deleteLater"}:
                raise RuntimeError("wrapped C/C++ object has been deleted")
            return object.__getattribute__(self, name)

    grid = IconGrid.__new__(IconGrid)
    grid._icon_load_generation = 0
    grid.icon_widgets = [DeletedWidget()]
    grid._stop_icon_thread = lambda: None
    grid.hint_container = SimpleNamespace(show=lambda: None)

    IconGrid._clear_icons(grid)

    assert grid.icon_widgets == []
    assert grid._icon_load_generation == 1


def test_clear_icons_deletes_drag_widget_removed_from_layout():
    class ClearWidget:
        def __init__(self, shortcut_id):
            self.shortcut = SimpleNamespace(id=shortcut_id)
            self.deleted = False
            self._pos_anim = None

        def deleteLater(self):
            self.deleted = True

    dragged = ClearWidget("one")
    remaining = ClearWidget("two")
    grid = IconGrid.__new__(IconGrid)
    grid._icon_load_generation = 0
    grid.icon_widgets = [remaining]
    grid._initial_widgets = [dragged, remaining]
    grid._drag_visual_widgets = [dragged]
    grid._active_drag_ids = ["one"]
    grid._stop_icon_thread = lambda: None
    grid.hint_container = SimpleNamespace(show=lambda: None)

    IconGrid._clear_icons(grid)

    assert dragged.deleted is True
    assert remaining.deleted is True
    assert grid.icon_widgets == []
    assert grid._initial_widgets == []
    assert grid._drag_visual_widgets == []
    assert grid._active_drag_ids == []


def test_icon_widget_child_widgets_do_not_steal_mouse_events(qapp):
    widget = IconWidget(ShortcutItem(id="one", name="One", type=ShortcutType.FILE))
    try:
        assert widget.icon_frame.testAttribute(Qt.WA_TransparentForMouseEvents)
        assert widget.icon_label.testAttribute(Qt.WA_TransparentForMouseEvents)
        assert widget.name_label.testAttribute(Qt.WA_TransparentForMouseEvents)
    finally:
        widget.deleteLater()


def test_icon_drag_is_blocked_when_smart_sort_enabled(monkeypatch, qapp):
    parent = grid_mod.QWidget()
    parent.data_manager = SimpleNamespace(
        get_settings=lambda: SimpleNamespace(sort_mode="smart"),
    )
    widget = IconWidget(ShortcutItem(id="one", name="One", type=ShortcutType.FILE))
    widget.setParent(parent)
    exec_calls = []

    class FakeDrag:
        def __init__(self, source):
            self.source = source
            self.mime_data = None

        def setMimeData(self, mime_data):
            self.mime_data = mime_data

        def exec_(self, action):
            exec_calls.append(action)

    monkeypatch.setattr(grid_mod, "QDrag", FakeDrag)

    try:
        widget._start_drag()
        assert exec_calls == []
    finally:
        widget.deleteLater()
        parent.deleteLater()


def test_icon_drag_starts_normally_when_custom_sort(monkeypatch, qapp):
    parent = grid_mod.QWidget()
    parent.data_manager = SimpleNamespace(
        get_settings=lambda: SimpleNamespace(sort_mode="custom"),
    )
    parent.current_folder_id = "source"
    parent._drag_completed = False
    widget = IconWidget(ShortcutItem(id="one", name="One", type=ShortcutType.FILE))
    widget.setParent(parent)
    exec_calls = []
    drag_objects = []

    class FakeDrag:
        def __init__(self, source):
            self.source = source
            self.mime_data = None
            drag_objects.append(self)

        def setMimeData(self, mime_data):
            self.mime_data = mime_data

        def setPixmap(self, pixmap):
            self.pixmap = pixmap

        def setHotSpot(self, point):
            self.hot_spot = point

        def exec_(self, action):
            exec_calls.append(action)
            return action

    monkeypatch.setattr(grid_mod, "QDrag", FakeDrag)

    try:
        widget._start_drag()

        assert exec_calls == [grid_mod.QtCompat.MoveAction]
        assert parent._drag_completed is True
        assert drag_objects[0].mime_data.data("application/x-shortcut-id").data().decode() == "one"
        assert drag_objects[0].mime_data.data("application/x-source-folder-id").data().decode() == "source"
    finally:
        widget.deleteLater()
        parent.deleteLater()


def test_icon_drag_enter_accepts_shortcut_drop(qapp):
    """dragEnterEvent accepts proposed action for shortcut-id mime type."""
    widget = IconWidget(ShortcutItem(id="target", name="Target", type=ShortcutType.FILE))

    class FakeMime:
        def hasFormat(self, fmt):
            return fmt == "application/x-shortcut-id"
        def data(self, fmt):
            class _FakeBytes:
                def data(self):
                    return b"source"
            return _FakeBytes()

    class FakeEvent:
        def __init__(self):
            self.accepted = False
            self.ignored = False

        def mimeData(self):
            return FakeMime()

        def acceptProposedAction(self):
            self.accepted = True

        def ignore(self):
            self.ignored = True

    event = FakeEvent()
    try:
        widget.dragEnterEvent(event)
        assert event.accepted is True
        assert widget._is_drop_target is True
    finally:
        widget.deleteLater()


def test_icon_container_handles_blank_area_mouse_press(qapp):
    """IconContainer emits blank_clicked on left-click in empty area."""
    container = IconContainer()
    container.setGeometry(0, 0, 200, 200)
    emitted = []
    container.blank_clicked.connect(lambda: emitted.append(True))
    try:
        from qt_compat import QtCompat
        class _FakeEvent:
            def button(self):
                return QtCompat.LeftButton
            def pos(self):
                return QPoint(100, 100)
            def accept(self):
                pass
        container.mousePressEvent(_FakeEvent())
        assert emitted == [True]
    finally:
        container.deleteLater()


def test_drag_enter_triggers_realtime_swap(monkeypatch, qapp):
    """dragEnterEvent calls parent handle_realtime_swap when mime type matches."""
    parent = grid_mod.QWidget()
    swaps = []
    parent.handle_realtime_swap = lambda source_id, target_id, pointer_pos=None: swaps.append((source_id, target_id, pointer_pos))
    widget = IconWidget(ShortcutItem(id="target", name="Target", type=ShortcutType.FILE))
    widget.setParent(parent)

    class FakeMime:
        def hasFormat(self, fmt):
            return fmt == "application/x-shortcut-id"
        def data(self, fmt):
            class _FakeBytes:
                def data(self):
                    return b"source"
            return _FakeBytes()

    class FakeEvent:
        def mimeData(self):
            return FakeMime()
        def acceptProposedAction(self):
            pass

    try:
        widget.dragEnterEvent(FakeEvent())
        assert swaps == [("source", "target", None)]
    finally:
        widget.deleteLater()
        parent.deleteLater()


def test_drop_triggers_handle_final_reorder(monkeypatch, qapp):
    """dropEvent calls parent handle_final_reorder when mime type matches."""
    parent = grid_mod.QWidget()
    reorders = []
    parent.handle_final_reorder = lambda: reorders.append(True)
    widget = IconWidget(ShortcutItem(id="target", name="Target", type=ShortcutType.FILE))
    widget.setParent(parent)

    class FakeMime:
        def hasFormat(self, fmt):
            return fmt == "application/x-shortcut-id"

    class FakeEvent:
        def mimeData(self):
            return FakeMime()
        def acceptProposedAction(self):
            pass

    try:
        widget.dropEvent(FakeEvent())
        assert reorders == [True]
        assert widget._is_drop_target is False
    finally:
        widget.deleteLater()
        parent.deleteLater()


def test_create_drag_preview_pixmap_returns_valid_pixmap(qapp):
    """create_drag_preview_pixmap returns non-null pixmap with expected size."""
    widget = IconWidget(ShortcutItem(id="one", name="One", type=ShortcutType.FILE), icon_size=26, cell_size=56)

    try:
        pixmap = widget.create_drag_preview_pixmap()

        assert pixmap is not None
        assert pixmap.isNull() is False
        expected_size = widget.icon_size + 14
        assert pixmap.width() == expected_size
        assert pixmap.height() == expected_size
    finally:
        widget.deleteLater()


def test_drag_enter_highlights_target_widget(qapp):
    """dragEnterEvent sets _is_drop_target=True and _set_drop_target_style on the target."""
    widget = IconWidget(ShortcutItem(id="target", name="Target", type=ShortcutType.FILE))

    class FakeMime:
        def hasFormat(self, fmt):
            return fmt == "application/x-shortcut-id"
        def data(self, fmt):
            class _FakeBytes:
                def data(self):
                    return b"source"
            return _FakeBytes()

    class FakeEvent:
        def mimeData(self):
            return FakeMime()
        def acceptProposedAction(self):
            pass

    event = FakeEvent()
    try:
        assert widget._is_drop_target is False
        widget.dragEnterEvent(event)
        assert widget._is_drop_target is True
    finally:
        widget.deleteLater()
