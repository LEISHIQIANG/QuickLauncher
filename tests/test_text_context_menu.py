from qt_compat import QLineEdit, QPlainTextEdit, QTextEdit


class _FakeContextMenuEvent:
    def __init__(self):
        self.accepted = False

    def globalPos(self):
        return None

    def accept(self):
        self.accepted = True


class _FakeMenu:
    instances = []

    def __init__(self, theme, radius, parent):
        self.theme = theme
        self.radius = radius
        self.parent = parent
        self.actions = []
        self.popup_pos = object()
        self.__class__.instances.append(self)

    def add_action(self, label, callback, enabled=True):
        self.actions.append((label, callback, enabled))

    def add_separator(self):
        self.actions.append(("separator", None, True))

    def popup(self, pos):
        self.popup_pos = pos


def _show_menu(monkeypatch, widget):
    import ui.styles.style as style_mod

    _FakeMenu.instances.clear()
    monkeypatch.setattr(style_mod, "PopupMenu", _FakeMenu)
    event = _FakeContextMenuEvent()
    widget.contextMenuEvent(event)
    return event, _FakeMenu.instances[-1]


def test_read_only_text_controls_use_log_style_context_menu(qapp, monkeypatch):
    for widget in (QPlainTextEdit("plain"), QTextEdit("rich")):
        widget.setReadOnly(True)
        widget.selectAll()

        event, menu = _show_menu(monkeypatch, widget)

        assert event.accepted
        assert menu.theme == "dark"
        assert menu.radius == 12
        assert [action[0] for action in menu.actions] == ["复制", "全选"]
        assert menu.actions[0][2] is True
        assert menu.actions[-1][2] is True


def test_editable_line_edit_uses_full_custom_context_menu(qapp, monkeypatch):
    widget = QLineEdit("command text")
    widget.selectAll()

    event, menu = _show_menu(monkeypatch, widget)

    assert event.accepted
    assert [action[0] for action in menu.actions] == [
        "撤销",
        "重做",
        "separator",
        "剪切",
        "复制",
        "粘贴",
        "删除",
        "separator",
        "全选",
    ]
    enabled = {label: state for label, _callback, state in menu.actions if label != "separator"}
    assert enabled["剪切"] is True
    assert enabled["复制"] is True
    assert enabled["删除"] is True
    assert enabled["全选"] is True


def test_password_line_edit_disables_copy_and_cut(qapp, monkeypatch):
    widget = QLineEdit("secret")
    widget.setEchoMode(QLineEdit.Password)
    widget.selectAll()

    _event, menu = _show_menu(monkeypatch, widget)

    enabled = {label: state for label, _callback, state in menu.actions if label != "separator"}
    assert enabled["剪切"] is False
    assert enabled["复制"] is False
    assert enabled["删除"] is True
