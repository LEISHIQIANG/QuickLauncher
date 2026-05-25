"""Folder panel drag/drop dispatch regressions."""

from ui.config_window.folder_panel import FolderListWidget


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
