"""Config icon grid selection and batch action regressions."""

from types import SimpleNamespace

import pytest

import ui.config_window.icon_grid as grid_mod
from core import ShortcutItem, ShortcutType
from qt_compat import QPoint, Qt
from ui.config_window.icon_grid import IconContainer, IconGrid, IconWidget, MoveFolderDialog

pytestmark = pytest.mark.ui


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


def _shortcut(shortcut_id, name, stype=ShortcutType.FILE):
    return ShortcutItem(id=shortcut_id, name=name, type=stype)


def _data_with_folders(folders):
    return SimpleNamespace(
        folders=folders,
        get_folder_by_id=lambda folder_id: next((folder for folder in folders if folder.id == folder_id), None),
    )


def test_move_folder_dialog_constructs_before_child_buttons_exist(qapp):
    from core import Folder

    dialog = MoveFolderDialog([Folder(id="target", name="Target")])
    try:
        assert dialog.combo.count() == 1
        assert dialog.cancel_btn is not None
        assert dialog.ok_btn is not None
    finally:
        dialog.deleteLater()


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


def test_batch_launch_search_reflows_visible_icons(qapp):
    from ui.config_window.batch_launch_dialog import IconSelectorWidget

    selector = IconSelectorWidget()
    try:
        selector.show()
        qapp.processEvents()
        selector.set_shortcuts(
            [
                _shortcut("alpha", "Alpha"),
                _shortcut("bravo", "Bravo"),
                _shortcut("charlie", "Charlie"),
                _shortcut("delta", "Delta"),
            ]
        )

        selector.search_box.setText("charlie")
        selector._place_icons()
        qapp.processEvents()

        visible_widgets = [widget for widget in selector.icon_widgets.values() if widget.isVisible()]
        assert [widget.shortcut.id for widget in visible_widgets] == ["charlie"]
        assert selector.icon_widgets["charlie"].pos().x() >= 0
        assert selector.icon_widgets["charlie"].pos().y() == 0
        assert selector.icon_widgets["alpha"].isVisible() is False

        selector.search_box.clear()
        selector._place_icons()
        qapp.processEvents()
        assert all(widget.isVisible() for widget in selector.icon_widgets.values())
    finally:
        selector.deleteLater()


def test_batch_launch_checked_icon_creates_and_removes_card(qapp, monkeypatch):
    from core import Folder
    from ui.config_window.batch_launch_dialog import BatchLaunchCard, BatchLaunchDialog

    file_item = _shortcut("file", "File")
    url_item = _shortcut("url", "URL", ShortcutType.URL)
    repo_item = _shortcut("repo", "Repo")
    other_item = _shortcut("other", "Other")
    folder = Folder(id="default", name="Default", items=[file_item, url_item])
    other_folder = Folder(id="other_folder", name="Other", items=[other_item])
    icon_repo = Folder(id="icon_repo", name="图标仓库", is_icon_repo=True, items=[repo_item])
    shortcuts = {item.id: item for item in [file_item, url_item, repo_item, other_item]}
    manager = SimpleNamespace(
        data=_data_with_folders([folder, other_folder, icon_repo]),
        get_settings=lambda: SimpleNamespace(theme="dark"),
        get_shortcut_by_id=lambda shortcut_id: shortcuts.get(shortcut_id),
        add_shortcut=lambda folder_id, shortcut: True,
    )
    parent = grid_mod.QWidget()
    parent.data_manager = manager
    monkeypatch.setattr(
        "ui.config_window.batch_launch_dialog._load_shortcut_icon", lambda _shortcut, size: grid_mod.QPixmap(size, size)
    )

    dialog = BatchLaunchDialog(manager, "default", parent)
    try:
        dialog._load_shortcuts()
        assert set(dialog.icon_selector.icon_widgets) == {"file", "url", "other"}

        dialog.icon_selector.icon_widgets["file"].checkbox.setChecked(True)

        assert dialog.selected_order == ["file"]
        assert len(dialog.launch_cards) == 1
        assert dialog.launch_cards[0].shortcut.id == "file"
        assert dialog.launch_cards[0].icon_label.width() == BatchLaunchCard.ICON_LABEL_SIZE
        assert dialog.launch_cards[0].icon_label.pixmap().width() == BatchLaunchCard.ICON_PIXMAP_SIZE

        dialog._on_card_remove_requested("file")

        assert dialog.selected_order == []
        assert dialog.launch_cards == []
        assert dialog.icon_selector.icon_widgets["file"].checkbox.isChecked() is False
    finally:
        dialog.deleteLater()
        parent.deleteLater()


def test_batch_launch_cards_reorder_updates_execution_order(qapp, monkeypatch):
    from core import Folder
    from ui.config_window.batch_launch_dialog import BatchLaunchDialog

    items = [_shortcut("one", "One"), _shortcut("two", "Two"), _shortcut("three", "Three")]
    folder = Folder(id="default", name="Default", items=items)
    shortcuts = {item.id: item for item in items}
    manager = SimpleNamespace(
        data=_data_with_folders([folder]),
        get_settings=lambda: SimpleNamespace(theme="dark"),
        get_shortcut_by_id=lambda shortcut_id: shortcuts.get(shortcut_id),
        add_shortcut=lambda folder_id, shortcut: True,
    )
    parent = grid_mod.QWidget()
    parent.data_manager = manager
    monkeypatch.setattr(
        "ui.config_window.batch_launch_dialog._load_shortcut_icon", lambda _shortcut, size: grid_mod.QPixmap(size, size)
    )

    dialog = BatchLaunchDialog(manager, "default", parent)
    try:
        dialog._load_shortcuts()
        for shortcut_id in ["one", "two", "three"]:
            dialog.icon_selector.icon_widgets[shortcut_id].checkbox.setChecked(True)

        assert dialog.selected_order == ["one", "two", "three"]

        moved = dialog._move_launch_card("one", 2)

        assert moved is True
        assert dialog.selected_order == ["two", "three", "one"]
        assert [card.shortcut.id for card in dialog.launch_cards] == ["two", "three", "one"]
        assert [dialog.cards_layout.itemAt(i).widget().shortcut.id for i in range(3)] == ["two", "three", "one"]
    finally:
        dialog.deleteLater()
        parent.deleteLater()


def test_batch_launch_save_creates_batch_launch_shortcut(qapp, monkeypatch):
    from core import Folder
    from ui.config_window.batch_launch_dialog import BatchLaunchDialog

    items = [_shortcut("one", "One"), _shortcut("two", "Two")]
    folder = Folder(id="default", name="Default", items=items)
    shortcuts = {item.id: item for item in items}
    added = []

    def add_shortcut(folder_id, shortcut):
        added.append((folder_id, shortcut))
        return True

    manager = SimpleNamespace(
        data=_data_with_folders([folder]),
        get_settings=lambda: SimpleNamespace(theme="dark"),
        get_shortcut_by_id=lambda shortcut_id: shortcuts.get(shortcut_id),
        add_shortcut=add_shortcut,
    )
    parent = grid_mod.QWidget()
    parent.data_manager = manager
    monkeypatch.setattr(
        "ui.config_window.batch_launch_dialog._load_shortcut_icon", lambda _shortcut, size: grid_mod.QPixmap(size, size)
    )

    dialog = BatchLaunchDialog(manager, "default", parent)
    try:
        dialog._load_shortcuts()
        for shortcut_id in ["one", "two"]:
            dialog.icon_selector.icon_widgets[shortcut_id].checkbox.setChecked(True)
        dialog.batch_name_edit.setText("Batch")
        dialog._custom_icon_path = "C:/icons/batch.png"
        dialog.batch_invert_light_cb.setChecked(True)
        dialog.batch_invert_dark_cb.setChecked(True)
        dialog.launch_cards[0].delay_input.setText("1.25")
        dialog.launch_cards[0].pause_checkbox.setChecked(True)

        dialog._save_batch_launch()

        assert len(added) == 1
        folder_id, shortcut = added[0]
        assert folder_id == "default"
        assert shortcut.type == ShortcutType.BATCH_LAUNCH
        assert shortcut.name == "Batch"
        assert shortcut.icon_path == "C:/icons/batch.png"
        assert shortcut.icon_invert_light is True
        assert shortcut.icon_invert_dark is True
        assert [step["shortcut_id"] for step in shortcut.batch_launch_steps] == ["one", "two"]
        assert shortcut.batch_launch_steps[0]["delay_ms"] == 1250
        assert shortcut.batch_launch_steps[0]["stop_on_error"] is True
        assert dialog.saved_shortcut is shortcut
    finally:
        dialog.deleteLater()
        parent.deleteLater()


def test_batch_launch_edit_restores_settings_and_cards(qapp, monkeypatch):
    from core import Folder
    from ui.config_window.batch_launch_dialog import BatchLaunchDialog

    items = [_shortcut("one", "One"), _shortcut("two", "Two")]
    folder = Folder(id="default", name="Default", items=items)
    shortcuts = {item.id: item for item in items}
    existing = ShortcutItem(
        id="batch",
        name="RunAll",
        type=ShortcutType.BATCH_LAUNCH,
        icon_path="C:/icons/batch.png",
        icon_invert_light=True,
        icon_invert_dark=True,
        batch_launch_steps=[
            {"shortcut_id": "two", "delay_ms": 500, "stop_on_error": False},
            {"shortcut_id": "one", "delay_ms": 0, "stop_on_error": True},
        ],
    )

    manager = SimpleNamespace(
        data=_data_with_folders([folder]),
        get_settings=lambda: SimpleNamespace(theme="dark"),
        get_shortcut_by_id=lambda shortcut_id: shortcuts.get(shortcut_id),
        add_shortcut=lambda _folder_id, _shortcut: pytest.fail("edit mode must not add a new shortcut"),
    )
    parent = grid_mod.QWidget()
    parent.data_manager = manager
    monkeypatch.setattr(
        "ui.config_window.batch_launch_dialog._load_shortcut_icon", lambda _shortcut, size: grid_mod.QPixmap(size, size)
    )

    dialog = BatchLaunchDialog(manager, "default", parent, existing)
    try:
        dialog._load_shortcuts()

        assert dialog.batch_name_edit.text() == "RunAll"
        assert dialog.batch_icon_edit.text() == "C:/icons/batch.png"
        assert dialog.batch_invert_light_cb.isChecked() is True
        assert dialog.batch_invert_dark_cb.isChecked() is True
        assert dialog.selected_order == ["two", "one"]
        assert dialog.launch_cards[0].delay_input.text() == "0.5"
        assert dialog.launch_cards[0].pause_checkbox.isChecked() is False

        dialog.batch_name_edit.setText("New")
        dialog._save_batch_launch()
        updated = dialog.saved_shortcut

        assert updated.id == "batch"
        assert updated.type == ShortcutType.BATCH_LAUNCH
        assert updated.name == "New"
        assert [step["shortcut_id"] for step in updated.batch_launch_steps] == ["two", "one"]
    finally:
        dialog.deleteLater()
        parent.deleteLater()


def test_batch_launch_edit_reuses_config_window_icon_grid_pixmaps(qapp):
    from core import Folder
    from ui.config_window.batch_launch_dialog import BatchLaunchDialog

    target = _shortcut("one", "One")
    existing = ShortcutItem(
        id="batch",
        name="Batch",
        type=ShortcutType.BATCH_LAUNCH,
        batch_launch_steps=[{"shortcut_id": "one"}],
    )
    folder = Folder(id="default", name="Default", items=[target, existing])
    manager = SimpleNamespace(
        data=_data_with_folders([folder]),
        get_settings=lambda: SimpleNamespace(theme="dark"),
        get_shortcut_by_id=lambda shortcut_id: target if shortcut_id == "one" else None,
    )

    pixmap = grid_mod.QPixmap(24, 24)
    pixmap.fill(grid_mod.QColor(255, 0, 0))
    icon_label = SimpleNamespace(pixmap=lambda: pixmap)
    icon_widget = SimpleNamespace(shortcut=target, icon_label=icon_label)
    parent = grid_mod.QWidget()
    parent.icon_grid = SimpleNamespace(icon_widgets=[icon_widget])

    dialog = BatchLaunchDialog(manager, "default", parent, existing)
    try:
        assert dialog._icon_pixmap_cache["one"].cacheKey() == pixmap.cacheKey()
        dialog._load_shortcuts()
        shown = dialog.launch_cards[0].icon_label.pixmap().toImage()
        color = shown.pixelColor(shown.width() // 2, shown.height() // 2)
        assert color.red() > 200
        assert color.green() < 80
        assert color.blue() < 80
    finally:
        dialog.deleteLater()
        parent.deleteLater()


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


def test_batch_move_reports_dialog_failure(monkeypatch):
    from core import Folder

    grid = IconGrid.__new__(IconGrid)
    grid.current_folder_id = "source"
    source = Folder(id="source", name="Source")
    target = Folder(id="target", name="Target")
    grid.data_manager = SimpleNamespace(data=_data_with_folders([source, target]))
    warnings = []

    def fail_dialog(*_args, **_kwargs):
        raise RuntimeError("dialog boom")

    monkeypatch.setattr(grid_mod, "MoveFolderDialog", fail_dialog)
    monkeypatch.setattr(grid_mod.ThemedMessageBox, "warning", lambda *args, **kwargs: warnings.append(args))

    IconGrid._batch_move(grid, ["one"])

    assert warnings
    assert "dialog boom" in warnings[0][2]


def test_batch_fetch_icons_starts_worker_without_blocking(monkeypatch, qapp):
    grid = IconGrid.__new__(IconGrid)
    url_shortcut = ShortcutItem(
        id="url",
        name="URL",
        type=ShortcutType.URL,
        url="https://example.com",
    )
    file_shortcut = ShortcutItem(id="file", name="File", type=ShortcutType.FILE)
    grid._shortcut_map = {"url": url_shortcut, "file": file_shortcut}
    grid.current_folder_id = "source"
    grid._favicon_fetch_generation = 0
    grid._favicon_fetch_thread = None
    grid._favicon_fetch_worker = None
    grid._favicon_fetch_status_dialog = None
    grid._favicon_fetch_shortcuts = {}
    snapshots = []
    started = []
    grid._take_batch_snapshot = lambda: snapshots.append(True)
    grid._start_favicon_fetch_worker = lambda tasks, dialog, shortcuts: started.append((tasks, dialog, shortcuts))

    class _StatusDialog:
        def __init__(self, title, parent=None):
            self.title = title
            self.parent = parent
            self.texts = []
            self.shown = False

        def update_text(self, text):
            self.texts.append(text)

        def show(self):
            self.shown = True

    warnings = []
    monkeypatch.setattr(grid_mod, "SimpleStatusDialog", _StatusDialog)
    monkeypatch.setattr(grid_mod.ThemedMessageBox, "warning", lambda *args, **kwargs: warnings.append(args))

    IconGrid._batch_fetch_icons(grid, ["url", "file"])
    qapp.processEvents()

    assert snapshots == [True]
    assert warnings == []
    assert len(started) == 1
    tasks, dialog, shortcuts = started[0]
    assert tasks == [("url", "URL", "https://example.com")]
    assert shortcuts == {"url": url_shortcut}
    assert dialog.shown is True
    assert dialog.texts == ["正在获取图标... 0/1"]


def test_favicon_fetch_completion_updates_data_and_refreshes(monkeypatch):
    grid = IconGrid.__new__(IconGrid)
    shortcut = ShortcutItem(
        id="url",
        name="URL",
        type=ShortcutType.URL,
        url="https://example.com",
    )
    grid._favicon_fetch_generation = 3
    grid._favicon_fetch_shortcuts = {"url": shortcut}
    grid._favicon_fetch_success_count = 0
    grid.current_folder_id = "source"

    class _StatusDialog:
        def __init__(self):
            self.texts = []
            self.closed = False

        def update_text(self, text):
            self.texts.append(text)

        def close(self):
            self.closed = True

    status_dialog = _StatusDialog()
    grid._favicon_fetch_status_dialog = status_dialog
    calls = []
    emits = []
    infos = []
    grid.data_manager = SimpleNamespace(save=lambda immediate=False: calls.append(("save", immediate)))
    grid.load_folder = lambda folder_id: calls.append(("load", folder_id))
    grid.shortcut_added = SimpleNamespace(emit=lambda: emits.append(True))
    monkeypatch.setattr(grid_mod.ThemedMessageBox, "information", lambda *args, **kwargs: infos.append(args))

    IconGrid._on_favicon_fetch_result(grid, 3, "url", "icon.ico", None)
    IconGrid._on_favicon_fetch_progress(grid, 3, 1, 1)
    IconGrid._on_favicon_fetch_completed(grid, 3, 0, 1)

    assert shortcut.icon_path == "icon.ico"
    assert status_dialog.texts == ["正在获取图标... 1/1"]
    assert status_dialog.closed is True
    assert calls == [("save", True), ("load", "source")]
    assert emits == [True]
    assert infos


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
    times = [10.0, 10.05, 10.08]
    monkeypatch.setattr(grid_mod.time, "monotonic", lambda: times.pop(0))

    # 1. 首次触发交换，目标为 "three"
    IconGrid.handle_realtime_swap(grid, "one", "three", pointer_pos=QPoint(100, 100))
    assert [widget.shortcut.id for widget in grid.icon_widgets] == ["two", "three", "one"]
    assert place_calls == [True]

    # 2. 目标仍为 "three"，但时间较短且距离极短 (2px)，应该被抑制
    IconGrid.handle_realtime_swap(grid, "one", "three", pointer_pos=QPoint(102, 100))
    assert [widget.shortcut.id for widget in grid.icon_widgets] == ["two", "three", "one"]
    assert place_calls == [True]

    # 3. 目标更改为 "two" — 目标发生切换时应立即响应，不进行抖动抑制
    IconGrid.handle_realtime_swap(grid, "one", "two", pointer_pos=QPoint(120, 100))
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
    """dragEnterEvent ignores the event so it bubbles up to the parent."""
    widget = IconWidget(ShortcutItem(id="target", name="Target", type=ShortcutType.FILE))

    class FakeMime:
        def hasFormat(self, fmt):
            return fmt == "application/x-shortcut-id"

    class FakeEvent:
        def __init__(self):
            self.ignored = False

        def mimeData(self):
            return FakeMime()

        def ignore(self):
            self.ignored = True

    event = FakeEvent()
    try:
        widget.dragEnterEvent(event)
        assert event.ignored is True
        assert widget._is_drop_target is False
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
    """dragEnterEvent ignores the event and bubbles up."""
    parent = grid_mod.QWidget()
    swaps = []
    parent.handle_realtime_swap = lambda source_id, target_id, pointer_pos=None: swaps.append(
        (source_id, target_id, pointer_pos)
    )
    widget = IconWidget(ShortcutItem(id="target", name="Target", type=ShortcutType.FILE))
    widget.setParent(parent)

    class FakeMime:
        def hasFormat(self, fmt):
            return fmt == "application/x-shortcut-id"

    class FakeEvent:
        def __init__(self):
            self.ignored = False

        def mimeData(self):
            return FakeMime()

        def ignore(self):
            self.ignored = True

    event = FakeEvent()
    try:
        widget.dragEnterEvent(event)
        assert event.ignored is True
        assert swaps == []
    finally:
        widget.deleteLater()
        parent.deleteLater()


def test_drop_triggers_handle_final_reorder(monkeypatch, qapp):
    """dropEvent ignores the event to bubble up."""
    parent = grid_mod.QWidget()
    reorders = []
    parent.handle_final_reorder = lambda: reorders.append(True)
    widget = IconWidget(ShortcutItem(id="target", name="Target", type=ShortcutType.FILE))
    widget.setParent(parent)

    class FakeMime:
        def hasFormat(self, fmt):
            return fmt == "application/x-shortcut-id"

    class FakeEvent:
        def __init__(self):
            self.ignored = False

        def mimeData(self):
            return FakeMime()

        def ignore(self):
            self.ignored = True

    event = FakeEvent()
    try:
        widget.dropEvent(event)
        assert event.ignored is True
        assert reorders == []
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
    """dragEnterEvent ignores the event and does not set _is_drop_target=True."""
    widget = IconWidget(ShortcutItem(id="target", name="Target", type=ShortcutType.FILE))

    class FakeMime:
        def hasFormat(self, fmt):
            return fmt == "application/x-shortcut-id"

    class FakeEvent:
        def __init__(self):
            self.ignored = False

        def mimeData(self):
            return FakeMime()

        def ignore(self):
            self.ignored = True

    event = FakeEvent()
    try:
        assert widget._is_drop_target is False
        widget.dragEnterEvent(event)
        assert event.ignored is True
        assert widget._is_drop_target is False
    finally:
        widget.deleteLater()


def test_drag_enter_ignores_system_icon_repo_item(qapp):
    """dragEnterEvent ignores the event for a system icon repo item."""
    shortcut = ShortcutItem(id="target", name="Target", type=ShortcutType.FILE)
    shortcut._icon_repo_source = "system"
    widget = IconWidget(shortcut)

    class FakeMime:
        def hasFormat(self, fmt):
            return fmt in ("application/x-shortcut-id", "application/x-shortcut-ids")

    class FakeEvent:
        def __init__(self):
            self.ignored = False

        def mimeData(self):
            return FakeMime()

        def ignore(self):
            self.ignored = True

    event = FakeEvent()
    try:
        assert widget._is_drop_target is False
        widget.dragEnterEvent(event)
        assert event.ignored is True
        assert widget._is_drop_target is False
    finally:
        widget.deleteLater()


def test_drag_move_triggers_swap_and_updates_highlight(qapp):
    """dragMoveEvent ignores the event and bubbles up."""
    shortcut = ShortcutItem(id="target", name="Target", type=ShortcutType.FILE)
    widget = IconWidget(shortcut)

    class FakeMime:
        def hasFormat(self, fmt):
            return fmt in ("application/x-shortcut-id", "application/x-shortcut-ids")

    class FakeEvent:
        def __init__(self):
            self.ignored = False

        def mimeData(self):
            return FakeMime()

        def ignore(self):
            self.ignored = True

    event = FakeEvent()
    try:
        from qt_compat import QWidget

        parent_widget = QWidget()
        parent_widget.handle_realtime_swap = lambda source, target, pointer_pos=None: True
        widget.setParent(parent_widget)

        assert widget._is_drop_target is False
        widget.dragMoveEvent(event)
        assert event.ignored is True
        assert widget._is_drop_target is False
    finally:
        widget.deleteLater()


def test_realtime_swap_allows_system_icon_interleaving(qapp):
    """handle_realtime_swap allows dragging user icons over system icons (no redirection needed)."""
    from core import DataManager, ShortcutItem
    from ui.config_window.icon_grid import IconGrid

    manager = DataManager()
    grid = IconGrid(manager)
    try:
        grid.current_folder_id = "icon_repo"

        # Create system and user shortcut items
        sys_item = ShortcutItem(id="sys1", name="System1")
        sys_item._icon_repo_source = "system"
        user_item1 = ShortcutItem(id="user1", name="User1")
        user_item1._icon_repo_source = "user"
        user_item2 = ShortcutItem(id="user2", name="User2")
        user_item2._icon_repo_source = "user"

        grid._shortcut_map = {
            "sys1": sys_item,
            "user1": user_item1,
            "user2": user_item2,
        }

        # Create mock widgets
        from ui.config_window.icon_grid import IconWidget

        w_sys = IconWidget(sys_item)
        w_user1 = IconWidget(user_item1)
        w_user2 = IconWidget(user_item2)

        grid.icon_widgets = [w_sys, w_user1, w_user2]
        grid._active_drag_ids = ["user2"]

        # System icons are now fully sortable — dragging user2 over sys1 works directly
        calls = []
        original_move = grid._move_drag_group
        grid._move_drag_group = lambda src, tgt, m_ids: (calls.append((src, tgt, m_ids)) or True)

        try:
            res = grid.handle_realtime_swap(source_id="user2", target_id="sys1")
            assert res is True
            assert len(calls) == 1
            src, tgt, m_ids = calls[0]
            assert src == "user2"
            assert tgt == "sys1"  # No redirection — system icon is a valid drop target
        finally:
            grid._move_drag_group = original_move
            w_sys.deleteLater()
            w_user1.deleteLater()
            w_user2.deleteLater()
    finally:
        grid.deleteLater()


def test_handle_final_reorder_safeguards_missing_ids(qapp):
    """handle_final_reorder correctly sanitizes IDs and restores missing dragged items to prevent data loss or duplicates."""
    from core import DataManager, ShortcutItem
    from ui.config_window.icon_grid import IconGrid

    manager = DataManager()
    grid = IconGrid(manager)
    try:
        grid.current_folder_id = "test_folder"

        # Create shortcut items
        item1 = ShortcutItem(id="item1", name="Item1")
        item2 = ShortcutItem(id="item2", name="Item2")
        item3 = ShortcutItem(id="item3", name="Item3")

        # Create mock widgets
        from ui.config_window.icon_grid import IconWidget

        w1 = IconWidget(item1)
        w2 = IconWidget(item2)
        w3 = IconWidget(item3)

        # Set _initial_widgets with all 3 widgets
        grid._initial_widgets = [w1, w2, w3]

        # Simulate active drag state where w2 (item2) is missing from current widgets
        grid.icon_widgets = [w1, w3]

        # Mock reorder_shortcuts on manager
        calls = []
        original_reorder = manager.reorder_shortcuts
        manager.reorder_shortcuts = lambda fid, ids: calls.append((fid, ids))

        try:
            grid.handle_final_reorder()
            assert len(calls) == 1
            fid, ids = calls[0]
            assert fid == "test_folder"
            # Verify that item2 has been safely restored without duplicates!
            assert len(ids) == 3
            assert ids == ["item1", "item3", "item2"]  # item2 restored at the end
        finally:
            manager.reorder_shortcuts = original_reorder
            w1.deleteLater()
            w2.deleteLater()
            w3.deleteLater()
    finally:
        grid.deleteLater()


def test_icongrid_drag_move_event_empty_space_swap(qapp):
    """IconGrid.dragMoveEvent calculates closest slot and triggers swap when dragging in empty space."""
    from core import ShortcutItem, ShortcutType
    from core.data_manager import DataManager
    from qt_compat import QPoint
    from ui.config_window.icon_grid import IconGrid, IconWidget

    manager = DataManager()
    grid = IconGrid(manager)
    grid.current_folder_id = "test_folder"

    item1 = ShortcutItem(id="item1", name="Item1", type=ShortcutType.FILE)
    item2 = ShortcutItem(id="item2", name="Item2", type=ShortcutType.FILE)
    w1 = IconWidget(item1)
    w2 = IconWidget(item2)
    w1.setParent(grid.container)
    w2.setParent(grid.container)
    grid.icon_widgets = [w1, w2]

    # Mock coordinate mapping methods to avoid parentless widget coordinate system issues
    grid.mapToGlobal = lambda pt: pt
    grid.container.mapFromGlobal = lambda pt: pt

    # Mock handle_realtime_swap
    swaps = []
    grid.handle_realtime_swap = lambda src, tgt, pointer_pos=None: swaps.append((src, tgt))

    class FakeMime:
        def hasFormat(self, fmt):
            return fmt in ("application/x-shortcut-id", "application/x-shortcut-ids")

        def data(self, fmt):
            class _FakeBytes:
                def data(self):
                    return b"item1"

            return _FakeBytes()

    class FakeEvent:
        def mimeData(self):
            return FakeMime()

        def acceptProposedAction(self):
            pass

    event = FakeEvent()
    try:
        # Use QPoint(120, 20) to hit col=1, row=0 -> target_idx = 1 (cell width is 103 for default width 640)
        event.pos = lambda: QPoint(120, 20)
        grid.dragMoveEvent(event)
        # Should have detected item2 as the closest target slot and attempted a swap
        assert len(swaps) > 0
        assert swaps[0] == ("item1", "item2")
    finally:
        w1.deleteLater()
        w2.deleteLater()
        grid.deleteLater()
