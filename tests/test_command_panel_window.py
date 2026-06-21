from types import SimpleNamespace

import pytest

from core.command_registry import CommandAction, CommandDefinition, CommandMetadata, CommandParam, CommandResult
from core.command_results import CommandResultStore
from core.data_models import ShortcutItem, ShortcutType
from qt_compat import QDialog, QEvent, QPixmap, QPlainTextEdit, Qt, QTextOption, QTimer
from ui.command_panel_window import COMMAND_PANEL_SIZE_PRESETS, CommandPanelWindow
from ui.tray_mixins.windows_mixin import WindowsMixin
from ui.utils.ui_scale import sp

pytestmark = pytest.mark.ui


class FakeSettings:
    theme = "dark"


class FakeDataManager:
    def get_settings(self):
        return FakeSettings()


def _window(qapp):
    return CommandPanelWindow(FakeDataManager(), CommandResultStore())


def test_command_panel_applies_frameless_chrome_before_native_opacity(monkeypatch, qapp):
    import ui.themed_tool_window as themed_tool_window

    calls = []
    original_set_opacity = themed_tool_window.ThemedToolWindow.setWindowOpacity

    def record_chrome(widget, **_kwargs):
        calls.append("chrome")

    def record_opacity(widget, opacity):
        calls.append("opacity")
        return original_set_opacity(widget, opacity)

    monkeypatch.setattr(themed_tool_window, "apply_custom_window_chrome", record_chrome)
    monkeypatch.setattr(themed_tool_window.ThemedToolWindow, "setWindowOpacity", record_opacity)

    window = _window(qapp)
    try:
        assert calls.index("chrome") < calls.index("opacity")
        assert isinstance(window, QDialog)
    finally:
        window.close()


def test_command_panel_native_hwnd_never_has_a_windows_caption(qapp):
    from ctypes import c_int, windll

    window = _window(qapp)
    try:
        hwnd = int(window.winId())
        style = int(windll.user32.GetWindowLongW(hwnd, c_int(-16)))
        ws_caption = 0x00C00000

        assert window.windowFlags() & Qt.FramelessWindowHint
        assert style & ws_caption == 0
    finally:
        window.close()


def test_first_running_command_panel_shows_prepared_running_shell_immediately(monkeypatch):
    import ui.command_panel_window as panel_mod
    import ui.utils.window_effect as window_effect

    class FakePanel:
        def __init__(self, _data_manager, _result_store):
            self._running = False
            self.show_calls = 0
            self.calls = []

        def prepare_content_loading(self, **_kwargs):
            self.calls.append("prepare")

        def load_content_after_window_animation(self, callback):
            self.calls.append("schedule")
            callbacks.append(callback)

        def run_command(self, **_kwargs):
            self._running = True
            self.calls.append("run")

        def show(self):
            self.show_calls += 1
            self.calls.append("show")

        def raise_(self):
            return None

        def activateWindow(self):
            return None

        def winId(self):
            return 123

    class Tray(WindowsMixin):
        def __init__(self):
            self.data_manager = FakeDataManager()
            self.command_result_store = None
            self.command_panel_window = None

        def _wake_from_sleep(self, _source):
            return None

    monkeypatch.setattr(panel_mod, "CommandPanelWindow", FakePanel)
    callbacks = []
    monkeypatch.setattr(window_effect, "force_activate_window", lambda _hwnd: None)

    tray = Tray()
    assert tray.show_command_panel(command_id="test") is True
    assert tray.command_panel_window.show_calls == 1
    assert tray.command_panel_window.calls == ["prepare", "show", "schedule"]
    assert len(callbacks) == 1

    callbacks[0]()

    assert tray.command_panel_window.calls == ["prepare", "show", "schedule", "run"]
    assert tray._command_panel_hwnd == 123


def test_command_panel_uses_shared_tool_window_show_animation(qapp):
    win = _window(qapp)
    try:
        assert win.windowOpacity() == 0.0

        win.show()
        qapp.processEvents()

        assert hasattr(win, "opacity_anim")
        assert hasattr(win, "pos_anim")
        assert win.opacity_anim.duration() == 200
        assert win.pos_anim.duration() == 200
    finally:
        win.close()


def test_command_panel_shell_uses_shortcut_size_before_dynamic_content(qapp):
    win = _window(qapp)
    shortcut = ShortcutItem(type=ShortcutType.COMMAND, command_panel_size="small")
    try:
        win.prepare_content_loading(shortcut=shortcut)

        width, height = COMMAND_PANEL_SIZE_PRESETS["small"]
        assert win.width() == sp(width)
        assert win.height() == sp(height)
        assert win.text.toPlainText() == "正在加载..."
    finally:
        win.close()


def test_command_panel_renders_text_and_log(qapp):
    win = _window(qapp)

    win.show_transient_result(CommandResult(message="hello", display_type="text"))
    assert win.text.toPlainText() == "hello"

    win.show_transient_result(CommandResult(message="line 1\nline 2", display_type="log"))
    assert win.text.toPlainText() == "line 1\nline 2"


def test_command_panel_subtitle_includes_command_metadata(qapp):
    win = _window(qapp)
    command = CommandDefinition(
        id="hosts",
        title="Hosts",
        aliases=["hosts"],
        description="",
        category="system",
        handler=lambda ctx: CommandResult(success=True),
        metadata=CommandMetadata(
            category="system",
            risk_level="medium",
            requires_admin=True,
            uses_network=False,
            modifies_system=True,
        ),
    )
    win._current_definition = command
    win._current_command_title = command.title

    win._update_subtitle("等待输入")

    subtitle = win.subtitle_label.text()
    assert "中风险" in subtitle
    assert "管理员" in subtitle
    assert "修改系统" in subtitle


def test_live_log_update_preserves_manual_scroll_position(qapp):
    win = _window(qapp)
    win.resize(433, 300)
    win.show()
    qapp.processEvents()

    win.show_transient_result(
        CommandResult(message="\n".join(f"line {i}" for i in range(120)), display_type="log", payload={"running": True})
    )
    qapp.processEvents()
    scrollbar = win.text.verticalScrollBar()
    scrollbar.setValue(max(1, scrollbar.maximum() // 3))
    old_value = scrollbar.value()

    win._running = True
    win._render_text_like(
        CommandResult(
            message="\n".join(f"line {i}" for i in range(140)),
            display_type="log",
            payload={"running": True},
        ),
        "\n".join(f"line {i}" for i in range(140)),
        "log",
    )
    qapp.processEvents()

    assert scrollbar.value() == old_value


def test_live_log_update_follows_when_already_at_bottom(qapp):
    win = _window(qapp)
    win.resize(433, 300)
    win.show()
    qapp.processEvents()

    win.show_transient_result(
        CommandResult(message="\n".join(f"line {i}" for i in range(80)), display_type="log", payload={"running": True})
    )
    qapp.processEvents()
    scrollbar = win.text.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())

    win._running = True
    win._render_text_like(
        CommandResult(
            message="\n".join(f"line {i}" for i in range(120)),
            display_type="log",
            payload={"running": True},
        ),
        "\n".join(f"line {i}" for i in range(120)),
        "log",
    )
    qapp.processEvents()

    assert scrollbar.value() == scrollbar.maximum()


def test_command_panel_forces_long_result_wrapping(qapp):
    win = _window(qapp)

    win.show_transient_result(
        CommandResult(
            message="https://example.com/" + ("very-long-segment" * 20),
            display_type="log",
            payload={"wrap": False},
        )
    )

    assert win.text.lineWrapMode() == QPlainTextEdit.WidgetWidth
    assert win.text.wordWrapMode() == QTextOption.WrapAnywhere
    assert win.text.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff


def test_command_panel_only_exposes_titlebar_close_and_blocks_dialog_keys(qapp):
    win = _window(qapp)
    accepted = []

    class FakeKeyEvent:
        def __init__(self, key):
            self._key = key
            self.accepted = False

        def key(self):
            return self._key

        def accept(self):
            self.accepted = True

    win.accept()
    win.reject()
    assert accepted == []
    assert win.close_btn is None
    assert win.cancel_btn is None
    assert not win.run_btn.autoDefault()
    assert not win.run_btn.isDefault()
    assert not win.close_btn_top.autoDefault()

    event = FakeKeyEvent(Qt.Key_Escape)
    win.keyPressEvent(event)
    assert event.accepted


def test_command_panel_close_event_shuts_down_execution_service(qapp, monkeypatch):
    """P0-03: closing the command panel must shut down its execution service."""

    win = _window(qapp)
    shutdown_calls = []
    monkeypatch.setattr(
        win.execution_service,
        "shutdown",
        lambda timeout=0.0, **kwargs: shutdown_calls.append(timeout),
    )

    win.close()

    assert shutdown_calls, "closeEvent must call execution_service.shutdown"
    assert win._closing_panel is True


def test_command_input_focus_and_caret_are_prepared(qapp):
    win = _window(qapp)
    win.command_input.setText("/cmd value")

    win.show()
    qapp.processEvents()
    win._focus_command_input()
    qapp.processEvents()

    assert win.command_input.hasFocus()
    assert win.command_input.isEnabled()
    assert not win.command_input.isReadOnly()
    assert win.command_input.cursor().shape() == Qt.IBeamCursor
    assert win.command_input.cursorPosition() == len("/cmd value")


def test_command_input_mouse_focus_keeps_clicked_caret_position(qapp):
    win = _window(qapp)
    win.command_input.setText("/cmd value")

    win.show()
    qapp.processEvents()
    win._focus_command_input()
    win.command_input.setCursorPosition(3)
    qapp.processEvents()

    win.eventFilter(win.command_input, QEvent(QEvent.MouseButtonPress))
    qapp.processEvents()

    assert win.command_input.hasFocus()
    assert win.command_input.cursorPosition() == 3


def test_command_panel_does_not_auto_focus_input_on_show(qapp):
    win = _window(qapp)
    win.command_input.setText("/cmd value")

    win.show()
    qapp.processEvents()

    assert not win.command_input.hasFocus()
    assert not win._command_suggestions_visible()


def test_command_panel_shows_distinct_status_and_renames_history(qapp):
    store = CommandResultStore()
    store.add(CommandResult(message="old"), command_id="old", command_title="Old", raw_input="/old")
    win = CommandPanelWindow(FakeDataManager(), store)

    expected = {
        "执行中": ("运行中", "running"),
        "完成": ("完成", "success"),
        "失败": ("失败", "failure"),
    }
    styles = set()
    for state, (label, kind) in expected.items():
        win._update_subtitle(state)
        assert not win.status_badge.isHidden()
        assert win.status_label.text() == label
        assert win.status_label.property("status_kind") == kind
        assert win.status_indicator.is_ripple_active() is (kind == "running")
        styles.add(win.status_badge.styleSheet())

    win._refresh_history()

    assert len(styles) == 3
    assert win.history_toggle_btn.text() == ""
    assert win.history_toggle_btn.toolTip() == "最近命令"


def test_showing_failed_stored_result_keeps_failure_status(qapp):
    store = CommandResultStore()
    result_id = store.add(
        CommandResult(success=False, message="failed", error="boom"),
        command_id="broken",
        command_title="Broken",
        raw_input="/broken",
    )
    win = CommandPanelWindow(FakeDataManager(), store)

    win.show_result(result_id)

    assert win.status_label.text() == "失败"
    assert win.status_label.property("status_kind") == "failure"


def test_payload_window_size_overrides_definition_default(qapp):
    win = _window(qapp)
    cmd = CommandDefinition(
        id="test.cmd",
        title="Test",
        aliases=[],
        description="",
        category="",
        handler=lambda ctx: CommandResult(),
        result_window_size="large",
    )

    win.show_transient_result(CommandResult(message="ok", payload={"window_size": "small"}), cmd)

    assert win.size().width() == COMMAND_PANEL_SIZE_PRESETS["small"][0]
    assert win.size().height() == COMMAND_PANEL_SIZE_PRESETS["small"][1]


def test_fixed_presets_are_not_resizable(qapp):
    win = _window(qapp)

    for key in ("small", "medium", "large"):
        win._apply_size_preset(key)
        width, height = COMMAND_PANEL_SIZE_PRESETS[key]
        assert win.minimumWidth() == width
        assert win.maximumWidth() == width
        assert win.minimumHeight() == height
        assert win.maximumHeight() == height


def test_auto_preset_has_bounds_and_can_resize(qapp):
    win = _window(qapp)
    win.text.setPlainText("\n".join(["x" * 120 for _ in range(30)]))

    win._apply_size_preset("auto")

    assert win.minimumWidth() == COMMAND_PANEL_SIZE_PRESETS["small"][0]
    assert win.minimumHeight() == COMMAND_PANEL_SIZE_PRESETS["small"][1]
    assert win.maximumWidth() > win.minimumWidth()
    assert win.maximumHeight() > win.minimumHeight()


def test_copy_and_copy_action(qapp):
    win = _window(qapp)
    win.show_transient_result(
        CommandResult(
            message="panel text",
            actions=[CommandAction(type="copy", label="复制值", value="action text")],
        )
    )

    win.copy_result()
    assert qapp.clipboard().text() == "panel text"

    win._execute_action(win._current_result.actions[0])
    assert qapp.clipboard().text() == "action text"


def test_shortcut_destructive_confirmation_is_scoped_to_next_invocation(qapp, monkeypatch):
    win = _window(qapp)
    shortcut = ShortcutItem(id="s1", name="Danger", type=ShortcutType.COMMAND, command="del file.txt")
    captured = {}

    class FakeService:
        def run_shortcut_command(self, request, **_kwargs):
            captured["context_meta"] = dict(request.context_meta)
            return SimpleNamespace(request_id="run-1")

    win.execution_service = FakeService()
    win._current_shortcut = shortcut
    win._current_command_id = shortcut.id
    win._current_command_title = shortcut.name
    win._current_raw_input = shortcut.command
    win._current_context_meta = {"destructive_confirmed": True}
    monkeypatch.setattr(win, "_confirm_destructive_shortcut", lambda _shortcut: True)

    win._execute_current_shortcut_request()

    assert captured["context_meta"]["destructive_confirmed"] is True
    assert "destructive_confirmed" not in win._current_context_meta


def test_confirm_render_keeps_action_states(qapp):
    win = _window(qapp)

    win.show_transient_result(
        CommandResult(
            message="Delete item?",
            display_type="confirm",
            payload={"detail": "This cannot be undone."},
            actions=[
                CommandAction(type="copy", label="Delete", value="yes", danger=True, primary=True),
                CommandAction(type="copy", label="Disabled", value="no", enabled=False),
            ],
        )
    )

    assert "Delete item?" in win.text.toPlainText()
    assert "This cannot be undone." in win.text.toPlainText()
    assert win.action_buttons[0].text() == "Delete"
    assert win.action_buttons[0].isEnabled()
    assert win.action_buttons[1].text() == "Disabled"
    assert not win.action_buttons[1].isEnabled()


def test_live_result_update_does_not_render_or_relayout_actions(qapp, monkeypatch):
    import ui.command_panel_renderers as renderers

    win = _window(qapp)
    action_renders = []
    monkeypatch.setattr(renderers, "render_actions", lambda panel, result: action_renders.append((panel, result)))

    win.show_transient_result(
        CommandResult(
            message="running output",
            display_type="log",
            payload={"running": True, "window_size": "small"},
            actions=[CommandAction(type="copy", label="Copy", value="running output")],
        )
    )

    assert win.text.toPlainText() == "running output"
    assert action_renders == []

    win.show_transient_result(CommandResult(message="done", display_type="log"))

    assert len(action_renders) == 1


def test_footer_buttons_are_never_unparented_top_level_windows(qapp):
    win = _window(qapp)
    footer_buttons = [win.copy_btn, win.save_btn, win.rerun_btn, *win.action_buttons, win.more_btn]

    assert all(button.parentWidget() is win.footer_button_container for button in footer_buttons)
    assert all(not button.isWindow() for button in footer_buttons)

    win.show_transient_result(
        CommandResult(
            message="done",
            display_type="log",
            actions=[CommandAction(type="copy", label="Copy", value="done")],
        )
    )

    assert win.action_buttons[0].parentWidget() is win.footer_button_container
    assert not win.action_buttons[0].isWindow()


def test_command_panel_renders_structured_types(qapp, tmp_path):
    win = _window(qapp)

    win.show_transient_result(
        CommandResult(
            display_type="table",
            payload={"columns": ["name", "value"], "rows": [{"name": "a", "value": 1}]},
        )
    )
    assert not win.table.isHidden()
    assert win.table.rowCount() == 1
    assert win.table.columnCount() == 2
    assert win.table.item(0, 1).text() == "1"
    win.copy_result()
    assert "name\tvalue" in qapp.clipboard().text()

    win.show_transient_result(CommandResult(display_type="kv", payload={"items": [["host", "localhost"]]}))
    assert not win.table.isHidden()
    assert win.table.item(0, 0).text() == "host"
    assert win.table.item(0, 1).text() == "localhost"

    win.show_transient_result(
        CommandResult(
            display_type="list",
            payload={"items": [{"title": "step", "status": "ok", "detail": "done", "duration": 0.5}]},
        )
    )
    assert not win.list_widget.isHidden()
    assert "step" in win.list_widget.item(0).text()
    assert "done" in win.list_widget.item(0).text()

    win.show_transient_result(
        CommandResult(display_type="progress", message="Running", progress=0.25, payload={"detail": "phase 1"})
    )
    assert not win.progress_bar.isHidden()
    assert win.progress_bar.value() == 250
    assert win.progress_title.text() == "Running"

    image_path = tmp_path / "qr.png"
    pixmap = QPixmap(8, 8)
    pixmap.save(str(image_path))
    win.show_transient_result(
        CommandResult(display_type="qr", message="QR text", payload={"image_path": str(image_path)})
    )
    assert not win.qr_label.isHidden()
    assert win.qr_label.pixmap() is not None


def test_auto_size_recomputes_after_long_content(qapp):
    win = _window(qapp)
    win.show_transient_result(
        CommandResult(
            message="\n".join(["x" * 120 for _ in range(30)]),
            payload={"window_size": "auto"},
        )
    )

    assert win.width() > COMMAND_PANEL_SIZE_PRESETS["small"][0]
    assert win.height() > COMMAND_PANEL_SIZE_PRESETS["small"][1]


def test_stale_token_result_does_not_replace_current(qapp):
    win = _window(qapp)
    win._run_token = "new"
    win.show_transient_result(CommandResult(message="current"))

    win._on_result_ready("old", CommandResult(message="stale"), None, 0.1)

    assert win._current_result.message == "current"
    assert win.text.toPlainText() == "current"


def test_many_actions_use_more_menu(qapp, monkeypatch):
    import ui.command_panel_window as panel_mod

    win = _window(qapp)
    calls = []
    callbacks = []

    class FakeMenu:
        def __init__(self, *args, **kwargs):
            pass

        def add_action(self, label, callback, enabled=True):
            callbacks.append((label, callback, enabled))

        def setFixedWidth(self, width):
            pass

        def popup(self, pos):
            callbacks[0][1]()

    monkeypatch.setattr(panel_mod, "PopupMenu", FakeMenu)
    actions = [CommandAction(type="copy", label=f"A{i}", value=str(i)) for i in range(5)]
    win.show_transient_result(CommandResult(message="actions", actions=actions))

    assert not win.action_buttons[0].isHidden()
    assert not win.more_btn.isHidden()
    win._execute_action = lambda action: calls.append(action.label)
    win._show_more_actions()
    assert callbacks[0][0] == "A3"
    assert calls == ["A3"]


def test_save_text_action_writes_file(qapp, tmp_path, monkeypatch):
    import ui.command_panel_window as panel_mod

    win = _window(qapp)
    target = tmp_path / "out.txt"
    monkeypatch.setattr(panel_mod, "get_save_file_name", lambda *args, **kwargs: (str(target), ""))

    win._execute_action(CommandAction(type="save_text", value="saved text"))

    assert target.read_text(encoding="utf-8") == "saved text"


def test_param_inputs_required_validation_and_execution(qapp):
    win = _window(qapp)
    captured = {}

    class FakeService:
        def run_registry_command(self, request, on_update=None, on_finished=None):
            captured["request"] = request
            return SimpleNamespace(request_id="token", cancel=lambda: None, cancelled=False)

    win.execution_service = FakeService()
    cmd = CommandDefinition(
        id="tools.param",
        title="Params",
        aliases=[],
        description="",
        category="",
        handler=lambda ctx: CommandResult(),
        params=[
            CommandParam(name="text", type="text", required=True),
            CommandParam(name="mode", type="choice", choices=["a", "b"], default="b"),
            CommandParam(name="flag", type="bool", default="true"),
            CommandParam(name="secret", type="text", sensitive=True),
        ],
    )
    win._current_command_id = cmd.id
    win._current_definition = cmd
    win._current_raw_input = "/tools.param"
    win._render_params(cmd)

    win._execute_current_request()
    assert "必填参数" in win.text.toPlainText()
    assert captured == {}

    text_widget = win._param_widgets["text"][1]
    text_widget.setText("hello")
    win._execute_current_request()

    assert captured["request"].args["text"] == "hello"
    assert captured["request"].args["mode"] == "b"
    assert captured["request"].args["flag"] == "true"
    assert win._run_token == "token"


def test_param_line_edits_match_command_input_style(qapp):
    win = _window(qapp)
    cmd = CommandDefinition(
        id="tls",
        title="TLS",
        aliases=[],
        description="",
        category="",
        handler=lambda ctx: CommandResult(),
        params=[
            CommandParam(name="host", type="text", label="域名"),
            CommandParam(name="port", type="number", label="端口", default="443"),
        ],
    )

    win._render_params(cmd)

    for name in ("host", "port"):
        style = win._param_widgets[name][1].styleSheet()
        assert "min-height: 28px" in style
        assert "padding: 0 10px" in style
        assert "border-radius: 8px" in style
        assert "rgba(10, 132, 255, 0.82)" in style
        assert "rgba(255, 255, 255, 0.13)" in style


def test_shortcut_params_execute_through_panel(qapp):
    win = _window(qapp)
    captured = {}

    class FakeService:
        def run_shortcut_command(self, request, on_finished=None):
            captured["request"] = request
            return SimpleNamespace(request_id="shortcut-token", cancel=lambda: None)

    shortcut = ShortcutItem(
        id="cmd1",
        name="Cmd",
        type=ShortcutType.COMMAND,
        command="echo {{param:host:q}}",
        command_type="cmd",
        command_params=[{"name": "host", "type": "text", "required": True}],
    )
    win.execution_service = FakeService()
    win.run_shortcut(shortcut)
    win._param_widgets["host"][1].setText("example.com")
    win._execute_current_request()

    assert captured["request"].shortcut is shortcut
    assert captured["request"].args["host"] == "example.com"
    assert win._run_token == "shortcut-token"


def test_escape_cancels_running_command(qapp):
    win = _window(qapp)
    cancelled = []
    win._running = True
    win._current_handle = SimpleNamespace(cancel=lambda: cancelled.append(True))

    class Event:
        def key(self):
            return Qt.Key_Escape

        def accept(self):
            pass

    win.keyPressEvent(Event())

    assert cancelled == [True]
    assert "取消" in win.text.toPlainText()


def test_cancel_and_rerun_use_handle_and_request(qapp):
    win = _window(qapp)
    cancelled = []
    calls = []

    class FakeService:
        def run_registry_command(self, request, on_update=None, on_finished=None):
            calls.append(request.raw_input)
            return SimpleNamespace(request_id=f"token-{len(calls)}", cancel=lambda: cancelled.append(True))

    cmd = CommandDefinition(
        id="tools.rerun",
        title="Rerun",
        aliases=[],
        description="",
        category="",
        handler=lambda ctx: CommandResult(),
    )
    win.execution_service = FakeService()
    win._current_command_id = cmd.id
    win._current_definition = cmd
    win._current_raw_input = "/tools.rerun now"
    win._current_args_text = "now"
    win._execute_current_request()

    win.cancel_current()
    assert cancelled == [True]
    assert win.text.toPlainText() == "命令执行已取消。"

    win.rerun_current()
    assert calls == ["/tools.rerun now", "/tools.rerun now"]


def test_history_latest_first_and_click_shows_result(qapp):
    store = CommandResultStore()
    old_id = store.add(CommandResult(message="old"), command_id="old", command_title="Old", raw_input="/old")
    new_id = store.add(CommandResult(message="new"), command_id="new", command_title="New", raw_input="/new")
    win = CommandPanelWindow(FakeDataManager(), store)

    win._refresh_history()
    assert win.history_list.item(0).data(0x0100) == new_id  # Qt.UserRole
    assert win.history_list.item(1).data(0x0100) == old_id

    win._on_history_item_clicked(win.history_list.item(1))
    assert win.text.toPlainText() == "old"


def test_rendering_history_result_does_not_mutate_store(qapp):
    store = CommandResultStore()
    result = CommandResult(message="stored text")
    result_id = store.add(result, command_id="cmd", command_title="Cmd", raw_input="/cmd")
    win = CommandPanelWindow(FakeDataManager(), store)

    win.show_result(result_id)

    assert store.get(result_id).result.actions == []
    assert any(action.label == "复制全部" for action in win._current_result.actions)


def test_history_dropdown_uses_input_width_and_shows_recent_commands(qapp, monkeypatch):
    import ui.command_panel_history as history_mod

    store = CommandResultStore()
    store.add(CommandResult(message="old"), command_id="old", command_title="Old", raw_input="/old")
    store.add(CommandResult(message="new"), command_id="new", command_title="New", raw_input="/new")
    win = CommandPanelWindow(FakeDataManager(), store)
    win.command_input_group.resize(360, 28)
    labels = []
    widths = []
    popups = []

    class FakeMenu:
        def __init__(self, *args, **kwargs):
            self._width = 0
            self._layout = SimpleNamespace(setContentsMargins=lambda *args: None, setSpacing=lambda *args: None)
            self._btn_style_dark = ""
            self._btn_style_light = ""

        def setMinimumWidth(self, width):
            widths.append(("min", width))

        def setMaximumWidth(self, width):
            widths.append(("max", width))

        def setFixedWidth(self, width):
            self._width = width
            widths.append(("fixed", width))

        def add_action(self, label, callback, enabled=True):
            labels.append((label, callback, enabled))

        def popup(self, pos):
            popups.append(pos)

    monkeypatch.setattr(history_mod, "PopupMenu", FakeMenu)

    win._show_history_menu()

    assert labels[0][0] == "/new"
    assert labels[1][0] == "/old"
    assert ("fixed", 360) in widths
    assert popups
    labels[1][1]()
    assert win.text.toPlainText() == "old"


def test_command_input_realtime_suggestions_match_full_command_ids(qapp, monkeypatch):
    import core

    store = CommandResultStore()
    win = CommandPanelWindow(FakeDataManager(), store)
    cmd_a = CommandDefinition(
        id="tools.alpha",
        title="Alpha",
        aliases=["alpha"],
        description="",
        category="",
        handler=lambda ctx: CommandResult(),
    )
    cmd_b = CommandDefinition(
        id="tools.beta",
        title="Beta",
        aliases=["beta"],
        description="",
        category="",
        handler=lambda ctx: CommandResult(),
    )

    class FakeRegistry:
        def find(self, query):
            return [cmd for cmd in (cmd_a, cmd_b) if query in cmd.id or query in cmd.aliases]

    monkeypatch.setattr(core, "registry", FakeRegistry())
    win.show()
    qapp.processEvents()
    win._focus_command_input()

    win.command_input.setText("alp")
    qapp.processEvents()

    assert win.command_suggestion_popup.isVisible()
    assert win._command_suggestion_ids == ["tools.alpha"]
    assert win._accept_current_command_suggestion() is False
    assert win.command_input.hasFocus()

    win._apply_command_suggestion("tools.alpha")
    assert win.command_input.text() == "/tools.alpha "
    assert win.command_suggestion_popup is None or not win.command_suggestion_popup.isVisible()


def test_command_input_suggestions_hide_when_input_loses_focus(qapp, monkeypatch):
    import core

    store = CommandResultStore()
    win = CommandPanelWindow(FakeDataManager(), store)
    cmd = CommandDefinition(
        id="tools.alpha",
        title="Alpha",
        aliases=["alpha"],
        description="",
        category="",
        handler=lambda ctx: CommandResult(),
    )

    class FakeRegistry:
        def find(self, query):
            return [cmd] if query in cmd.id else []

    monkeypatch.setattr(core, "registry", FakeRegistry())
    win.show()
    qapp.processEvents()
    win._focus_command_input()
    win.command_input.setText("alp")
    qapp.processEvents()

    assert win.command_suggestion_popup.isVisible()

    win.text.setFocus()
    qapp.processEvents()
    QTimer.singleShot(0, lambda: None)
    qapp.processEvents()

    assert win.command_suggestion_popup is None or not win.command_suggestion_popup.isVisible()

    win._focus_command_input()
    qapp.processEvents()

    assert win.command_suggestion_popup.isVisible()


def test_command_input_suggestions_follow_window_move(qapp, monkeypatch):
    import core

    store = CommandResultStore()
    win = CommandPanelWindow(FakeDataManager(), store)
    cmd = CommandDefinition(
        id="tools.alpha",
        title="Alpha",
        aliases=["alpha"],
        description="",
        category="",
        handler=lambda ctx: CommandResult(),
    )

    class FakeRegistry:
        def find(self, query):
            return [cmd] if query in cmd.id else []

    monkeypatch.setattr(core, "registry", FakeRegistry())
    win.show()
    qapp.processEvents()
    win._focus_command_input()
    win.command_input.setText("alp")
    qapp.processEvents()

    popup = win.command_suggestion_popup
    assert popup.isVisible()
    original_pos = popup.pos()

    win.move(win.x() + 30, win.y() + 20)
    qapp.processEvents()

    assert popup.isVisible()
    assert popup.pos() != original_pos


def test_top_close_hides_panel_without_reopening_suggestions(qapp, monkeypatch):
    import core

    store = CommandResultStore()
    win = CommandPanelWindow(FakeDataManager(), store)
    cmd = CommandDefinition(
        id="tools.alpha",
        title="Alpha",
        aliases=["alpha"],
        description="",
        category="",
        handler=lambda ctx: CommandResult(),
    )

    class FakeRegistry:
        def find(self, query):
            return [cmd] if query in cmd.id else []

    monkeypatch.setattr(core, "registry", FakeRegistry())
    win.show()
    qapp.processEvents()
    win._focus_command_input()
    win.command_input.setText("alp")
    qapp.processEvents()

    assert win.command_suggestion_popup.isVisible()

    win.close_btn_top.click()
    qapp.processEvents()
    QTimer.singleShot(0, lambda: None)
    qapp.processEvents()

    assert not win.isVisible()
    assert win.command_suggestion_popup is None or not win.command_suggestion_popup.isVisible()
