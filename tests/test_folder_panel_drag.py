"""Folder panel drag/drop dispatch regressions."""

from types import SimpleNamespace

import pytest

from qt_compat import QListWidgetItem, QRectF, QSize, QtCompat, QVBoxLayout, QWidget
from ui.config_window.folder_panel import FolderItemWidget, FolderListWidget, FolderPanel

pytestmark = pytest.mark.ui


def test_folder_list_widget_delegates_drag_drop_events(qapp):
    calls = []

    class Owner:
        def _list_start_drag(self, event):
            calls.append(("start", event))

        def _list_drag_enter_event(self, event):
            calls.append(("enter", event))

        def _list_drag_move_event(self, event):
            calls.append(("move", event))

        def _list_drag_leave_event(self, event):
            calls.append(("leave", event))

        def _list_drop_event(self, event):
            calls.append(("drop", event))

    owner = Owner()
    widget = FolderListWidget(owner)
    try:
        widget.startDrag("actions")
        widget.dragEnterEvent("enter-event")
        widget.dragMoveEvent("move-event")
        widget.dragLeaveEvent("leave-event")
        widget.dropEvent("drop-event")

        assert calls == [
            ("start", "actions"),
            ("enter", "enter-event"),
            ("move", "move-event"),
            ("leave", "leave-event"),
            ("drop", "drop-event"),
        ]
    finally:
        widget.deleteLater()


def test_folder_list_selection_pill_tracks_scroll_position(qapp):
    owner = SimpleNamespace(_get_current_theme=lambda: "dark")
    host = QWidget()
    host.resize(140, 100)
    layout = QVBoxLayout(host)
    widget = FolderListWidget(owner)
    layout.addWidget(widget)
    for index in range(16):
        widget.addItem(QListWidgetItem(f"Folder {index}"))

    host.show()
    qapp.processEvents()
    widget.setCurrentRow(0)
    qapp.processEvents()
    widget.verticalScrollBar().setValue(widget.verticalScrollBar().maximum())
    qapp.processEvents()
    qapp.processEvents()

    expected = QRectF(widget.visualRect(widget.currentIndex())).adjusted(4, 1, -2, -1)
    assert widget.pill_rect == expected
    host.close()


def test_folder_item_uses_compact_dimensions_for_top_tabs(qapp):
    item_widget = FolderItemWidget("分类标签", None)
    sidebar_size = item_widget.sizeHint()
    item_widget.set_compact_tab_mode(True)
    tab_size = item_widget.sizeHint()

    assert tab_size.height() == 44
    assert tab_size.height() > sidebar_size.height()
    assert 96 <= tab_size.width() <= 182
    item_widget.resize(122, 40)
    capsule = item_widget._top_tab_capsule_rect()
    assert capsule.height() == 32
    assert capsule.top() == 4
    assert item_widget.height() - (capsule.top() + capsule.height()) == 4


def test_top_tab_selection_capsule_has_equal_vertical_safety_gaps(qapp):
    owner = SimpleNamespace(_get_current_theme=lambda: "dark", layout_mode="top_tabs")
    host = QWidget()
    host.resize(180, 40)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    widget = FolderListWidget(owner)
    layout.addWidget(widget)
    item = QListWidgetItem("Tab")
    item.setSizeHint(QSize(122, 42))
    widget.addItem(item)
    host.show()
    qapp.processEvents()
    widget.setCurrentItem(item)
    widget._sync_pill_to_scroll()
    widget.verticalScrollBar().setRange(0, 100)
    widget.verticalScrollBar().setValue(80)

    item_rect = widget.visualItemRect(item)
    pill = widget.pill_rect
    assert pill.top() - item_rect.top() == 5
    assert item_rect.y() + item_rect.height() - (pill.y() + pill.height()) == 5
    assert pill.bottom() < widget.viewport().height()
    assert widget.verticalScrollBar().value() == 0
    host.close()


class _MimePayload:
    def __init__(self, value):
        self._value = value

    def data(self):
        return self._value


class _ShortcutMime:
    def __init__(self, formats):
        self._formats = formats

    def hasFormat(self, fmt):
        return fmt in self._formats

    def data(self, fmt):
        return _MimePayload(self._formats.get(fmt, b""))

    def hasUrls(self):
        return False


def test_shortcut_ids_from_mime_prefers_batch_and_dedupes():
    mime = _ShortcutMime(
        {
            "application/x-shortcut-id": b"one",
            "application/x-shortcut-ids": b"one\ntwo\none\n",
        }
    )

    assert FolderPanel._shortcut_ids_from_mime(mime) == ["one", "two"]


def test_folder_drop_moves_batch_only_when_successful(qapp):
    calls = []
    emits = []

    class FakeItem:
        def __init__(self, folder_id, highlighted=False):
            self.folder_id = folder_id
            self.highlighted = highlighted

        def data(self, role):
            if role == QtCompat.UserRole:
                return self.folder_id
            if role == QtCompat.UserRole + 1:
                return self.highlighted
            return None

        def setData(self, role, value):
            if role == QtCompat.UserRole + 1:
                self.highlighted = value

    target_item = FakeItem("target", highlighted=True)
    current_item = FakeItem("source")

    class FakeList:
        def count(self):
            return 1

        def item(self, index):
            return target_item

        def itemAt(self, pos):
            return target_item

        def currentItem(self):
            return current_item

        def viewport(self):
            return SimpleNamespace(update=lambda: None)

    class FakeEvent:
        def __init__(self, success):
            self.accepted = False
            self.ignored = False
            self.success = success
            self._mime = _ShortcutMime(
                {
                    "application/x-shortcut-id": b"one",
                    "application/x-shortcut-ids": b"one\ntwo\n",
                    "application/x-source-folder-id": b"source",
                }
            )

        def mimeData(self):
            return self._mime

        def acceptProposedAction(self):
            self.accepted = True

        def ignore(self):
            self.ignored = True

    folders = {
        "source": SimpleNamespace(id="source", linked_path="", auto_sync=False),
        "target": SimpleNamespace(id="target", linked_path="", auto_sync=False),
    }

    panel = SimpleNamespace(
        folder_list=FakeList(),
        data_manager=SimpleNamespace(
            data=SimpleNamespace(get_folder_by_id=lambda folder_id: folders.get(folder_id)),
            move_shortcuts_batch=lambda ids, target: calls.append((tuple(ids), target)) or {"success": 2},
        ),
        folder_selected=SimpleNamespace(emit=lambda folder_id: emits.append(folder_id)),
        _decode_mime_text=FolderPanel._decode_mime_text,
        _shortcut_ids_from_mime=FolderPanel._shortcut_ids_from_mime,
    )

    event = FakeEvent(success=True)
    FolderPanel._list_drop_event(panel, event)

    assert calls == [(("one", "two"), "target")]
    assert emits == ["source"]
    assert event.accepted is True
    assert event.ignored is False


def test_folder_drop_ignores_when_batch_move_has_no_effect(qapp):
    calls = []
    target_item = SimpleNamespace(
        data=lambda role: "source" if role == QtCompat.UserRole else True,
        setData=lambda role, value: None,
    )

    class FakeList:
        def count(self):
            return 1

        def item(self, index):
            return target_item

        def itemAt(self, pos):
            return target_item

        def currentItem(self):
            return target_item

        def viewport(self):
            return SimpleNamespace(update=lambda: None)

    class FakeEvent:
        accepted = False
        ignored = False

        def __init__(self):
            self._mime = _ShortcutMime({"application/x-shortcut-id": b"one"})

        def mimeData(self):
            return self._mime

        def acceptProposedAction(self):
            self.accepted = True

        def ignore(self):
            self.ignored = True

    folders = {"source": SimpleNamespace(id="source", linked_path="", auto_sync=False)}
    panel = SimpleNamespace(
        folder_list=FakeList(),
        data_manager=SimpleNamespace(
            data=SimpleNamespace(get_folder_by_id=lambda folder_id: folders.get(folder_id)),
            move_shortcuts_batch=lambda ids, target: calls.append((tuple(ids), target)) or {"success": 0},
        ),
        folder_selected=SimpleNamespace(emit=lambda folder_id: None),
        _decode_mime_text=FolderPanel._decode_mime_text,
        _shortcut_ids_from_mime=FolderPanel._shortcut_ids_from_mime,
    )

    event = FakeEvent()
    FolderPanel._list_drop_event(panel, event)

    assert calls == [(("one",), "source")]
    assert event.accepted is False
    assert event.ignored is True
