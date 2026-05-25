"""Launcher popup search interaction regressions."""

from types import SimpleNamespace

from core.data_models import Folder, ShortcutItem, ShortcutType
from qt_compat import QPoint, QRect, Qt, QtCompat
from ui.launcher_popup.popup_window import LauncherPopup


class _FakeKeyEvent:
    def __init__(self, key, text="", modifiers=0):
        self._key = key
        self._text = text
        self._modifiers = modifiers
        self.accepted = False

    def key(self):
        return self._key

    def text(self):
        return self._text

    def modifiers(self):
        return self._modifiers

    def accept(self):
        self.accepted = True


class _FakeInputMethodEvent:
    def __init__(self, commit="", preedit=""):
        self._commit = commit
        self._preedit = preedit
        self.accepted = False

    def commitString(self):
        return self._commit

    def preeditString(self):
        return self._preedit

    def accept(self):
        self.accepted = True


class _FakeMouseEvent:
    def __init__(self, pos, button=QtCompat.LeftButton, modifiers=0):
        self._pos = pos
        self._button = button
        self._modifiers = modifiers
        self.accepted = False

    def pos(self):
        return self._pos

    def button(self):
        return self._button

    def modifiers(self):
        return self._modifiers

    def globalPos(self):
        return self._pos

    def accept(self):
        self.accepted = True


def _popup_with_items(items):
    popup = LauncherPopup.__new__(LauncherPopup)
    popup.search_query = ""
    popup.search_results = []
    popup.search_selected_index = -1
    popup.search_cursor_pos = 0
    popup.search_selection_anchor = None
    popup._search_preedit_text = ""
    popup._search_forced_active = False
    popup._search_drag_selecting = False
    popup.pages = [Folder(id="default", name="Default", items=items)]
    popup.dock_folder = None
    popup.dock_items = []
    popup.cols = 1
    popup.fixed_rows = 8
    popup.settings = SimpleNamespace(sort_mode="custom", dock_height_mode=1)
    popup.hover_index = -1
    popup.dock_hover_index = -1
    popup._page_render_cache = {}
    popup._start_search_reveal_animation = lambda active: None
    popup._body_y_offset = lambda: 0
    popup.update = lambda: None
    return popup


def test_typing_starts_search_escape_clears_and_arrows_select():
    popup = _popup_with_items([
        ShortcutItem(id="photoshop", name="Photoshop"),
        ShortcutItem(id="paint", name="Paint"),
    ])

    first = _FakeKeyEvent(0, "p")
    LauncherPopup.keyPressEvent(popup, first)

    assert first.accepted
    assert popup.search_query == "p"
    assert [r.shortcut.id for r in popup.search_results] == ["paint", "photoshop"]
    assert popup.search_selected_index == 0

    down = _FakeKeyEvent(Qt.Key_Down)
    LauncherPopup.keyPressEvent(popup, down)

    assert down.accepted
    assert popup.search_selected_index == 1

    escape = _FakeKeyEvent(QtCompat.Key_Escape)
    LauncherPopup.keyPressEvent(popup, escape)

    assert escape.accepted
    assert popup.search_query == ""
    assert popup.search_results == []
    assert popup.search_selected_index == -1


def test_first_space_opens_search_without_querying():
    popup = _popup_with_items([
        ShortcutItem(id="space-tool", name="Space Tool"),
    ])

    event = _FakeKeyEvent(Qt.Key_Space, " ")
    LauncherPopup.keyPressEvent(popup, event)

    assert event.accepted
    assert popup._is_search_active()
    assert popup.search_query == ""
    assert popup.search_results == []
    assert popup.search_cursor_pos == 0


def test_space_before_slash_enters_command_mode(monkeypatch):
    class FakeSettings:
        favorite_commands = ["config"]
        
    class FakeDataManager:
        @staticmethod
        def get_settings():
            return FakeSettings()
            
    import core
    monkeypatch.setattr(core, "data_manager", FakeDataManager)

    popup = _popup_with_items([])

    LauncherPopup.keyPressEvent(popup, _FakeKeyEvent(Qt.Key_Space, " "))
    slash = _FakeKeyEvent(0, "/")
    LauncherPopup.keyPressEvent(popup, slash)

    assert slash.accepted
    assert popup.search_query == "/"
    assert popup.search_results
    assert popup.search_results[0].shortcut.command_type == "builtin"


def test_enter_executes_selected_search_result():
    popup = _popup_with_items([ShortcutItem(id="paint", name="Paint")])
    executed = []
    popup._execute_item = lambda item, force_new=False: executed.append((item.id, force_new))

    LauncherPopup.keyPressEvent(popup, _FakeKeyEvent(0, "p"))
    enter = _FakeKeyEvent(Qt.Key_Return)
    LauncherPopup.keyPressEvent(popup, enter)

    assert enter.accepted
    assert executed == [("paint", False)]


def test_search_cursor_insert_and_backspace_edit_at_caret():
    popup = _popup_with_items([ShortcutItem(id="abc", name="abc")])

    for text in "abc":
        LauncherPopup.keyPressEvent(popup, _FakeKeyEvent(0, text))
    LauncherPopup.keyPressEvent(popup, _FakeKeyEvent(Qt.Key_Left))
    LauncherPopup.keyPressEvent(popup, _FakeKeyEvent(0, "X"))

    assert popup.search_query == "abXc"
    assert popup.search_cursor_pos == 3

    LauncherPopup.keyPressEvent(popup, _FakeKeyEvent(Qt.Key_Backspace))

    assert popup.search_query == "abc"
    assert popup.search_cursor_pos == 2


def test_search_selection_replaces_text():
    popup = _popup_with_items([ShortcutItem(id="abc", name="abc")])
    popup._set_search_query("abc", cursor_pos=3, selection_anchor=1)

    LauncherPopup.keyPressEvent(popup, _FakeKeyEvent(0, "Z"))

    assert popup.search_query == "aZ"
    assert popup.search_cursor_pos == 2
    assert popup.search_selection_anchor is None


def test_input_method_commit_adds_chinese_text():
    popup = _popup_with_items([ShortcutItem(id="paint", name="画图")])
    event = _FakeInputMethodEvent(commit="画")

    LauncherPopup.inputMethodEvent(popup, event)

    assert event.accepted
    assert popup.search_query == "画"
    assert popup.search_cursor_pos == 1


def test_input_method_preedit_is_exposed_for_chinese_ime():
    popup = _popup_with_items([ShortcutItem(id="paint", name="画图")])
    popup.padding = 8
    popup.width = lambda: 220
    popup._set_search_query("画", cursor_pos=1)

    event = _FakeInputMethodEvent(preedit="hua")
    LauncherPopup.inputMethodEvent(popup, event)

    assert event.accepted
    assert popup.search_query == "画"
    assert popup._search_preedit_text == "hua"
    assert LauncherPopup.inputMethodQuery(popup, Qt.ImSurroundingText) == "画"
    assert LauncherPopup.inputMethodQuery(popup, Qt.ImCursorPosition) == 1
    assert LauncherPopup.inputMethodQuery(popup, Qt.ImCursorRectangle).width() == 1


def test_shift_arrows_extend_search_selection_and_home_end_move_caret():
    popup = _popup_with_items([ShortcutItem(id="abc", name="abc")])
    popup._set_search_query("abcd", cursor_pos=2)

    LauncherPopup.keyPressEvent(popup, _FakeKeyEvent(Qt.Key_Right, modifiers=QtCompat.ShiftModifier))
    assert popup.search_cursor_pos == 3
    assert popup.search_selection_anchor == 2
    assert popup._selected_search_text() == "c"

    LauncherPopup.keyPressEvent(popup, _FakeKeyEvent(Qt.Key_Home))
    assert popup.search_cursor_pos == 0
    assert popup.search_selection_anchor is None

    LauncherPopup.keyPressEvent(popup, _FakeKeyEvent(Qt.Key_End))
    assert popup.search_cursor_pos == 4


def test_ctrl_a_selects_all_and_replaces_with_text():
    popup = _popup_with_items([ShortcutItem(id="abc", name="abc")])
    popup._set_search_query("abcd", cursor_pos=2)

    LauncherPopup.keyPressEvent(popup, _FakeKeyEvent(Qt.Key_A, modifiers=QtCompat.ControlModifier))
    assert popup._selected_search_text() == "abcd"

    LauncherPopup.keyPressEvent(popup, _FakeKeyEvent(0, "中"))
    assert popup.search_query == "中"
    assert popup.search_cursor_pos == 1


def test_mouse_drag_selects_search_text():
    popup = _popup_with_items([ShortcutItem(id="abc", name="abc")])
    popup.padding = 8
    popup.width = lambda: 220
    popup.height = lambda: 120
    popup._search_reveal_progress = 1.0
    popup._search_target_progress = 1.0
    popup._set_search_query("abcdef", cursor_pos=0)
    popup.setCursor = lambda cursor: None

    text_left = int(popup._search_text_rect().left() + popup._search_text_width(popup._search_text_prefix()))
    press = _FakeMouseEvent(QPoint(text_left, 12))
    move = _FakeMouseEvent(QPoint(text_left + popup._search_text_width("abc"), 12))
    release = _FakeMouseEvent(QPoint(text_left + popup._search_text_width("abc"), 12))

    LauncherPopup.mousePressEvent(popup, press)
    LauncherPopup.mouseMoveEvent(popup, move)
    LauncherPopup.mouseReleaseEvent(popup, release)

    assert press.accepted
    assert move.accepted
    assert release.accepted
    assert popup._selected_search_text() == "abc"


def test_blank_area_refresh_preserves_awakened_search_state():
    popup = LauncherPopup.__new__(LauncherPopup)
    calls = []
    popup._sync_all_folders = lambda: calls.append("sync")
    popup.refresh_data = lambda **kwargs: calls.append(("refresh", kwargs))
    popup._flash_icons = lambda: calls.append("flash")
    popup.tray_app = None

    LauncherPopup._refresh_after_folder_sync(popup)

    assert calls == [
        "sync",
        ("refresh", {
            "refresh_selection": False,
            "force": True,
            "reposition": False,
            "preserve_search_state": True,
        }),
        "flash",
    ]


def test_hide_reset_clears_stale_search_query_and_cursor_state():
    popup = _popup_with_items([ShortcutItem(id="abc", name="abc")])
    popup._set_search_query("abc", cursor_pos=1, selection_anchor=3)

    popup._reset_search_state()

    assert popup.search_query == ""
    assert popup.search_results == []
    assert popup.search_selected_index == -1
    assert popup.search_cursor_pos == 0
    assert popup.search_selection_anchor is None


def test_enter_executes_web_search_action_before_local_result():
    popup = _popup_with_items([ShortcutItem(id="google", name="Google")])
    executed = []
    popup._execute_item = lambda item, force_new=False: executed.append((item, force_new))

    popup.search_query = "g cats and dogs"
    popup._refresh_search_results()
    enter = _FakeKeyEvent(Qt.Key_Return)
    LauncherPopup.keyPressEvent(popup, enter)

    assert enter.accepted
    item, force_new = executed[0]
    assert item.type == ShortcutType.URL
    assert item.name == "google: cats and dogs"
    assert item.url == "https://www.google.com/search?q=cats%20and%20dogs"
    assert force_new is False


def test_search_includes_dock_in_result_grid_without_moving_dock_bar():
    normal = ShortcutItem(id="normal-tool", name="Tool")
    dock_item = ShortcutItem(id="dock-tool", name="Dock Tool")
    popup = _popup_with_items([normal])
    popup.dock_folder = Folder(id="dock", name="Dock", is_dock=True, items=[dock_item])
    popup.dock_items = [dock_item]
    popup.dock_height = 36

    popup._set_search_query("tool")

    assert {r.shortcut.id for r in popup.search_results} == {"dock-tool", "normal-tool"}


def test_dock_click_still_works_while_search_is_active():
    normal = ShortcutItem(id="normal", name="Normal")
    dock_item = ShortcutItem(id="dock-app", name="Dock App")
    popup = _popup_with_items([normal])
    popup.search_query = "dock"
    popup.dock_folder = Folder(id="dock", name="Dock", is_dock=True, items=[dock_item])
    popup.dock_items = [dock_item]
    popup.dock_height = 36
    popup.dock_y = 100
    popup.padding = 8
    popup.cell_size = 44
    popup.cell_h = 50
    popup.icon_size = 24
    popup.content_height = 90
    popup.width = lambda: 60

    assert popup._get_clicked_item_at(QPoint(30, 112)) is dock_item


def test_search_reveal_height_tracks_animation_progress():
    popup = LauncherPopup.__new__(LauncherPopup)
    popup.search_query = "p"
    popup._search_reveal_progress = 0.5
    popup._search_target_progress = 1.0
    popup._search_hide_geometry_pending = False

    assert LauncherPopup._search_visible_height(popup) == 17
    assert LauncherPopup._current_search_bar_height(popup) == 34
    assert LauncherPopup._body_y_offset(popup) == 17
    assert LauncherPopup._search_visible_top_inset(popup) == 17


def test_hidden_popup_height_does_not_depend_on_background_mode():
    heights = {}
    for bg_mode in ("theme", "image", "acrylic"):
        popup = LauncherPopup.__new__(LauncherPopup)
        popup.settings = SimpleNamespace(popup_max_rows=3, bg_mode=bg_mode)
        popup.padding = 8
        popup.cols = 4
        popup.cell_size = 48
        popup.icon_size = 32
        popup.dock_items = []
        popup.dock_height = 0
        popup.pages = [SimpleNamespace()]
        popup._search_reveal_progress = 0.0
        popup.setFixedSize = lambda width, height: None

        heights[bg_mode] = LauncherPopup._calculate_fixed_size(popup)[1]

    assert heights["theme"] == heights["image"] == heights["acrylic"]


def test_search_reveal_extends_height_upward_from_existing_body():
    popup = LauncherPopup.__new__(LauncherPopup)
    popup.settings = SimpleNamespace(popup_max_rows=3, bg_mode="theme")
    popup.padding = 8
    popup.cols = 4
    popup.cell_size = 48
    popup.icon_size = 32
    popup.dock_items = []
    popup.dock_height = 0
    popup.pages = [SimpleNamespace()]
    popup.setFixedSize = lambda width, height: None

    popup._search_reveal_progress = 0.0
    base_height = LauncherPopup._calculate_fixed_size(popup)[1]
    popup._search_reveal_progress = 1.0
    search_height = LauncherPopup._calculate_fixed_size(popup)[1]

    assert search_height - base_height == 34


def test_background_inset_only_applies_while_search_is_visible():
    popup = LauncherPopup.__new__(LauncherPopup)
    popup.search_query = ""
    popup._search_reveal_progress = 0.0
    popup._search_target_progress = 0.0
    popup._search_hide_geometry_pending = False

    assert LauncherPopup._background_top_inset(popup) == 0

    popup.search_query = "p"
    popup._search_reveal_progress = 0.5
    popup._search_target_progress = 1.0

    assert LauncherPopup._background_top_inset(popup) == 17


def test_search_start_shows_final_search_geometry_immediately():
    popup = LauncherPopup.__new__(LauncherPopup)
    popup._search_reveal_progress = 0.25
    popup._search_target_progress = 0.0
    popup._search_anim_from_progress = 0.0
    popup._search_hide_geometry_pending = False
    popup._remember_search_body_anchor = lambda: None
    popup._search_animation_update_rect = lambda: "search-rect"
    geometry_calls = []
    masks = []
    updates = []
    repaints = []

    class _Timer:
        def isActive(self):
            return False

        def start(self):
            pass

    popup._search_anim_timer = _Timer()
    popup._apply_search_geometry = lambda **kwargs: geometry_calls.append(kwargs)
    popup._apply_search_mask = lambda force=False: masks.append(force)
    popup.setUpdatesEnabled = lambda enabled: None
    popup.update = lambda rect=None: updates.append(rect)
    popup.repaint = lambda: repaints.append(True)

    LauncherPopup._start_search_reveal_animation(popup, True)

    assert geometry_calls == [{"repaint": False}]
    assert popup._search_reveal_progress == 1.0
    assert masks == [True]
    assert updates == ["search-rect"]
    assert repaints == [True]


def test_search_geometry_expands_only_from_top_edge():
    popup = LauncherPopup.__new__(LauncherPopup)
    popup.search_query = "p"
    popup._search_reveal_progress = 0.5
    popup._search_target_progress = 1.0
    popup._search_hide_geometry_pending = False
    popup._search_body_anchor_y = 200

    class _Geometry:
        def x(self):
            return 40

        def y(self):
            return 190

        def width(self):
            return 180

        def height(self):
            return 120

    applied = []

    def calculate_fixed_size(apply_size=False, y_offset_override=None):
        y_offset = LauncherPopup._body_y_offset(popup) if y_offset_override is None else int(y_offset_override)
        return 180, 120 + y_offset

    popup.geometry = lambda: _Geometry()
    popup._calculate_fixed_size = calculate_fixed_size
    popup._set_fixed_geometry_atomically = lambda left, top, width, height: applied.append((left, top, width, height))
    popup.setUpdatesEnabled = lambda enabled: None
    popup.repaint = lambda: None

    LauncherPopup._apply_search_geometry(popup)

    assert applied == [(40, 183, 180, 137)]


def test_search_animation_updates_only_top_region():
    popup = LauncherPopup.__new__(LauncherPopup)
    popup.settings = SimpleNamespace(corner_radius=10)
    popup.width = lambda: 240
    popup.height = lambda: 180

    rect = LauncherPopup._search_animation_update_rect(popup)

    assert rect.x() == 0
    assert rect.y() == 0
    assert rect.width() == 240
    assert rect.height() == 46


def test_finishing_search_hide_shrinks_after_visual_edge_is_hidden():
    popup = LauncherPopup.__new__(LauncherPopup)
    popup.search_query = ""
    popup._search_reveal_progress = 1.0
    popup._search_target_progress = 0.0
    popup._search_anim_from_progress = 1.0
    popup._search_anim_started_at = 1.0
    popup._search_anim_last_ts = 1.0
    popup._search_anim_duration_ms = 1
    popup._search_hide_geometry_pending = True
    popup.settings = SimpleNamespace(corner_radius=10)
    popup.width = lambda: 240
    popup.height = lambda: 180
    applied = []
    updates = []
    repaints = []

    class _Timer:
        def stop(self):
            pass

    popup._search_anim_timer = _Timer()
    popup._apply_search_geometry = lambda: applied.append(True)
    popup._apply_search_mask = lambda force=False: None
    popup.setUpdatesEnabled = lambda enabled: None
    popup.clearMask = lambda: None
    popup.update = lambda rect=None: updates.append(rect)
    popup.repaint = lambda: repaints.append(True)

    LauncherPopup._tick_search_reveal(popup)

    assert popup._search_reveal_progress == 0.0
    assert popup._search_hide_geometry_pending is False
    assert applied == [True]
    assert repaints == [True]


def test_search_hover_and_click_target_search_results():
    from core.fuzzy_search import FuzzyMatchResult
    popup = _popup_with_items([
        ShortcutItem(id="photoshop", name="Photoshop"),
    ])
    popup.current_page = 0

    popup.padding = 8
    popup.cell_size = 50
    popup.cell_h = 57
    popup.cols = 1
    popup.fixed_rows = 8
    popup.content_height = 500
    popup.dock_y = 600
    popup.height = lambda: 430

    photoshop_result = FuzzyMatchResult(
        shortcut=ShortcutItem(id="photoshop_search", name="Photoshop Search"),
        folder_id="default",
        folder_name="Default",
        score=100.0,
        original_index=0,
        matched_fields=["name"]
    )
    popup.search_results = [photoshop_result]
    popup.search_query = "p"

    class FakeMouseEvent:
        def __init__(self, pos):
            self._pos = pos
        def pos(self):
            return self._pos

    event = FakeMouseEvent(QPoint(10, 10))
    LauncherPopup.mouseMoveEvent(popup, event)
    assert popup.hover_index == 0

    clicked_item = LauncherPopup._get_clicked_item_at(popup, QPoint(10, 10))
    assert clicked_item is not None
    assert clicked_item.id == "photoshop_search"

    popup.search_query = ""
    popup.search_results = []

    clicked_item_normal = LauncherPopup._get_clicked_item_at(popup, QPoint(10, 10))
    assert clicked_item_normal is not None
    assert clicked_item_normal.id == "photoshop"


def test_slash_command_empty_query_sorting(monkeypatch):
    from core.slash_commands import SlashCommand
    
    # 1. Setup mock commands
    mock_cmds = [
        SlashCommand("quit", ["quit"], "退出", "system", "quit_app", "", "退出"),
        SlashCommand("restart", ["restart"], "重启", "system", "restart_app", "", "重启"),
        SlashCommand("config", ["config"], "配置", "system", "show_config_window", "", "配置"),
        SlashCommand("log", ["log"], "日志", "system", "show_log", "", "日志"),
    ]
    import ui.launcher_popup.popup_window as popup_window_mod
    monkeypatch.setattr(popup_window_mod, "find_matching_commands", lambda q: mock_cmds)
    
    # 2. Setup mock data_manager and settings with favorite commands: restart then config
    class FakeSettings:
        favorite_commands = ["restart", "config"]
        
    class FakeDataManager:
        @staticmethod
        def get_settings():
            return FakeSettings()
            
    import core
    monkeypatch.setattr(core, "data_manager", FakeDataManager)
    
    # 3. Create popup and trigger empty query / command search
    popup = _popup_with_items([])
    popup.search_query = "/"
    popup._refresh_search_results()
    
    # The expected output order:
    # Favorites first (in saved order): restart, config
    # Non-favorited commands are excluded when query is empty
    results = popup.search_results
    assert len(results) == 2
    
    # Check ids and folder names
    assert results[0].shortcut.id == "restart"
    assert results[0].folder_name == "收藏命令"
    
    assert results[1].shortcut.id == "config"
    assert results[1].folder_name == "收藏命令"


def test_plain_search_includes_command_results(monkeypatch):
    from core.slash_commands import SlashCommand
    import ui.launcher_popup.popup_window as popup_window_mod

    mock_cmds = [
        SlashCommand(
            "text_tools.count",
            ["count"],
            "Count text",
            "文本",
            "text_tools.count",
            "",
            "文本统计",
        ),
    ]
    monkeypatch.setattr(popup_window_mod, "find_matching_commands", lambda q: mock_cmds if q == "text" else [])

    popup = _popup_with_items([])
    popup.search_query = "text"
    popup._refresh_search_results()

    assert len(popup.search_results) == 1
    result = popup.search_results[0]
    assert result.shortcut.id == "text_tools.count"
    assert result.shortcut.type == ShortcutType.COMMAND
    assert result.shortcut.command == "text_tools.count"
    assert result.folder_name == "Commands"


def test_command_result_keys_and_autofill(monkeypatch):
    popup = _popup_with_items([])
    
    # 1. Test auto-fill command name on execution
    item = ShortcutItem(
        id="wifi",
        name="Wifi",
        type=ShortcutType.COMMAND,
        command="/wifi",
        command_type="builtin"
    )
    # Mock data manager
    class FakeSettings:
        pass
    class FakeDataManager:
        @staticmethod
        def get_settings():
            return FakeSettings()
    
    import core
    monkeypatch.setattr(core, "data_manager", FakeDataManager)
    
    popup._executing = False
    popup.search_query = ""
    
    # Run _execute_item (which fails safely or executes)
    try:
        popup._execute_item(item)
    except Exception:
        pass
        
    assert popup.search_query == "/wifi"
    
    # 2. Test keyboard events when command result is active
    class FakeCommandResult:
        display_type = "text"
        actions = []
        
    popup._command_result = FakeCommandResult()
    popup.clear_command_result_called = False
    def mock_clear_command_result():
        popup.clear_command_result_called = True
        popup._command_result = None
    popup.clear_command_result = mock_clear_command_result
    
    # Modifier alone (Ctrl)
    event_ctrl = _FakeKeyEvent(Qt.Key_Control, modifiers=Qt.ControlModifier)
    LauncherPopup.keyPressEvent(popup, event_ctrl)
    assert event_ctrl.accepted
    assert not popup.clear_command_result_called
    
    # Ctrl+C Copy shortcut
    event_ctrl_c = _FakeKeyEvent(Qt.Key_C, modifiers=Qt.ControlModifier)
    LauncherPopup.keyPressEvent(popup, event_ctrl_c)
    assert event_ctrl_c.accepted
    assert not popup.clear_command_result_called
    
    # Ctrl+A SelectAll shortcut
    event_ctrl_a = _FakeKeyEvent(Qt.Key_A, modifiers=Qt.ControlModifier)
    LauncherPopup.keyPressEvent(popup, event_ctrl_a)
    assert event_ctrl_a.accepted
    assert not popup.clear_command_result_called
    
    # Arrow key (Left)
    event_left = _FakeKeyEvent(Qt.Key_Left)
    LauncherPopup.keyPressEvent(popup, event_left)
    assert event_left.accepted
    assert not popup.clear_command_result_called
    
    # Arrow key (Up)
    event_up = _FakeKeyEvent(Qt.Key_Up)
    LauncherPopup.keyPressEvent(popup, event_up)
    assert event_up.accepted
    assert not popup.clear_command_result_called
    
    # Normal printable character (a) - should clear the command result and fall through
    event_char = _FakeKeyEvent(0, "a")
    popup._is_search_active = lambda: False
    popup._insert_or_replace_text = lambda t: None
    
    LauncherPopup.keyPressEvent(popup, event_char)
    assert event_char.accepted
    assert popup.clear_command_result_called


def test_command_result_ctrl_c_prefers_search_selection():
    popup = _popup_with_items([])
    popup._set_search_query("/wifi LEI", cursor_pos=5, selection_anchor=1)
    popup._command_id = "wifi"
    popup._command_result = SimpleNamespace(display_type="text", actions=[])
    popup._search_forced_active = True
    popup._text_shortcut_target = "search"

    copied = []
    popup._copy_search_selection = lambda: copied.append(popup._selected_search_text())

    class FakeTextEdit:
        def isVisible(self):
            return True

        def hasFocus(self):
            return True

        def copy(self):
            copied.append("panel")

    popup._result_text_edit = FakeTextEdit()

    event = _FakeKeyEvent(Qt.Key_C, modifiers=QtCompat.ControlModifier)
    LauncherPopup.keyPressEvent(popup, event)

    assert event.accepted
    assert copied == ["wifi"]


def test_command_result_ctrl_a_prefers_search_when_panel_is_not_focused():
    popup = _popup_with_items([])
    popup._set_search_query("/wifi LEI", cursor_pos=3)
    popup._command_id = "wifi"
    popup._command_result = SimpleNamespace(display_type="text", actions=[])
    popup._search_forced_active = True
    popup._text_shortcut_target = "search"

    selected_panel = []

    class FakeTextEdit:
        def isVisible(self):
            return True

        def hasFocus(self):
            return False

        def selectAll(self):
            selected_panel.append(True)

    popup._result_text_edit = FakeTextEdit()

    event = _FakeKeyEvent(Qt.Key_A, modifiers=QtCompat.ControlModifier)
    LauncherPopup.keyPressEvent(popup, event)

    assert event.accepted
    assert popup._selected_search_text() == "/wifi LEI"
    assert selected_panel == []


def test_command_result_ctrl_c_uses_focused_result_panel():
    popup = _popup_with_items([])
    popup._set_search_query("/wifi LEI", cursor_pos=5, selection_anchor=1)
    popup._command_id = "wifi"
    popup._command_result = SimpleNamespace(display_type="text", actions=[])
    popup._search_forced_active = True
    popup._text_shortcut_target = "result"

    copied = []

    class FakeCursor:
        def hasSelection(self):
            return True

    class FakeTextEdit:
        def isVisible(self):
            return True

        def hasFocus(self):
            return True

        def textCursor(self):
            return FakeCursor()

        def copy(self):
            copied.append("panel")

    popup._result_text_edit = FakeTextEdit()

    event = _FakeKeyEvent(Qt.Key_C, modifiers=QtCompat.ControlModifier)
    LauncherPopup.keyPressEvent(popup, event)

    assert event.accepted
    assert copied == ["panel"]


def test_command_result_ctrl_c_without_selection_does_not_copy_all():
    popup = _popup_with_items([])
    popup._set_search_query("/wifi LEI", cursor_pos=5)
    popup._command_id = "wifi"
    popup._command_result = SimpleNamespace(display_type="text", actions=[])
    popup._search_forced_active = True
    popup._text_shortcut_target = "result"

    copied = []

    class FakeCursor:
        def hasSelection(self):
            return False

    class FakeTextEdit:
        def isVisible(self):
            return True

        def hasFocus(self):
            return True

        def textCursor(self):
            return FakeCursor()

        def copy(self):
            copied.append("selection")

        def toPlainText(self):
            copied.append("all")
            return "panel text"

    popup._result_text_edit = FakeTextEdit()

    event = _FakeKeyEvent(Qt.Key_C, modifiers=QtCompat.ControlModifier)
    LauncherPopup.keyPressEvent(popup, event)

    assert event.accepted
    assert copied == []


def test_command_result_action_button_executes_on_release():
    popup = _popup_with_items([])
    action = SimpleNamespace(type="copy", value="abc")
    popup._command_result = SimpleNamespace(display_type="text", actions=[action])
    popup._command_id = ""
    popup._result_pressed_button = None
    popup._result_hover_button = None
    popup._is_click_on_result_panel = lambda pos: True
    popup._close_button_rect = lambda: QRect(80, 0, 20, 20)
    popup._action_button_rects = lambda: [(QRect(0, 0, 40, 20), 0)]
    popup.update = lambda: None
    executed = []
    popup._execute_action = lambda selected: executed.append(selected.value)

    press = _FakeMouseEvent(QPoint(10, 10), button=QtCompat.LeftButton)
    release = _FakeMouseEvent(QPoint(10, 10), button=QtCompat.LeftButton)

    LauncherPopup.mousePressEvent(popup, press)
    assert press.accepted
    assert popup._result_pressed_button == ("action", 0)
    assert executed == []

    LauncherPopup.mouseReleaseEvent(popup, release)
    assert release.accepted
    assert popup._result_pressed_button is None
    assert popup._result_hover_button == ("action", 0)
    assert executed == ["abc"]


def test_command_result_action_button_release_outside_cancels_click():
    popup = _popup_with_items([])
    action = SimpleNamespace(type="copy", value="abc")
    popup._command_result = SimpleNamespace(display_type="text", actions=[action])
    popup._command_id = ""
    popup._result_pressed_button = None
    popup._result_hover_button = None
    popup._is_click_on_result_panel = lambda pos: True
    popup._close_button_rect = lambda: QRect(80, 0, 20, 20)
    popup._action_button_rects = lambda: [(QRect(0, 0, 40, 20), 0)]
    popup.update = lambda: None
    executed = []
    popup._execute_action = lambda selected: executed.append(selected.value)

    press = _FakeMouseEvent(QPoint(10, 10), button=QtCompat.LeftButton)
    release = _FakeMouseEvent(QPoint(55, 10), button=QtCompat.LeftButton)

    LauncherPopup.mousePressEvent(popup, press)
    LauncherPopup.mouseReleaseEvent(popup, release)

    assert release.accepted
    assert popup._result_pressed_button is None
    assert popup._result_hover_button is None
    assert executed == []


def test_clicking_search_keeps_panel_when_query_is_full_command():
    popup = _popup_with_items([])
    popup.search_query = "/wifi LEI"
    popup.search_cursor_pos = len(popup.search_query)
    popup._command_id = "wifi"
    popup._command_result = SimpleNamespace(display_type="text", actions=[])
    popup._body_y_offset = lambda: 30
    popup.dock_y = 100
    popup._search_bar_contains = lambda pos: True
    popup._search_pos_from_point = lambda pos: len(popup.search_query)
    popup._restart_search_cursor_blink = lambda: None

    cleared = []
    popup.clear_command_result = lambda: cleared.append(True)

    event = _FakeMouseEvent(QPoint(10, 10), button=QtCompat.LeftButton)
    LauncherPopup.mousePressEvent(popup, event)

    assert event.accepted
    assert cleared == []
    assert popup._command_result is not None


def test_clicking_search_closes_panel_when_query_is_not_full_command():
    popup = _popup_with_items([])
    popup.search_query = "/wi"
    popup.search_cursor_pos = len(popup.search_query)
    popup._command_id = "wifi"
    popup._command_result = SimpleNamespace(display_type="text", actions=[])
    popup._body_y_offset = lambda: 30
    popup.dock_y = 100
    popup._search_bar_contains = lambda pos: True
    popup._search_pos_from_point = lambda pos: len(popup.search_query)
    popup._restart_search_cursor_blink = lambda: None

    cleared = []

    def clear_command_result():
        cleared.append(True)
        popup._command_result = None

    popup.clear_command_result = clear_command_result

    event = _FakeMouseEvent(QPoint(10, 10), button=QtCompat.LeftButton)
    LauncherPopup.mousePressEvent(popup, event)

    assert event.accepted
    assert cleared == [True]
    assert popup._command_result is None


def test_typing_args_after_full_command_keeps_result_panel():
    popup = _popup_with_items([])
    popup._set_search_query("/wifi ", cursor_pos=len("/wifi "))
    popup._command_id = "wifi"
    popup._command_result = SimpleNamespace(display_type="text", actions=[])
    popup._search_forced_active = True

    cleared = []
    popup.clear_command_result = lambda: cleared.append(True)

    event = _FakeKeyEvent(0, "L")
    LauncherPopup.keyPressEvent(popup, event)

    assert event.accepted
    assert popup.search_query == "/wifi L"
    assert cleared == []
    assert popup._command_result is not None


def test_pasting_args_after_full_command_keeps_result_panel():
    popup = _popup_with_items([])
    popup._set_search_query("/wifi ", cursor_pos=len("/wifi "))
    popup._command_id = "wifi"
    popup._command_result = SimpleNamespace(display_type="text", actions=[])
    popup._search_forced_active = True
    popup._read_clipboard_text = lambda: "LEI"

    cleared = []
    popup.clear_command_result = lambda: cleared.append(True)

    event = _FakeKeyEvent(Qt.Key_V, modifiers=QtCompat.ControlModifier)
    LauncherPopup.keyPressEvent(popup, event)

    assert event.accepted
    assert popup.search_query == "/wifi LEI"
    assert cleared == []
    assert popup._command_result is not None


def test_editing_full_command_token_closes_result_panel_after_change():
    popup = _popup_with_items([])
    popup._set_search_query("/wifi", cursor_pos=len("/wifi"))
    popup._command_id = "wifi"
    popup._command_result = SimpleNamespace(display_type="text", actions=[])
    popup._search_forced_active = True

    cleared = []

    def clear_command_result():
        cleared.append(True)
        popup._command_result = None

    popup.clear_command_result = clear_command_result

    event = _FakeKeyEvent(Qt.Key_Backspace)
    LauncherPopup.keyPressEvent(popup, event)

    assert event.accepted
    assert popup.search_query == "/wif"
    assert cleared == [True]
    assert popup._command_result is None


def test_keyboard_slash_panel_command_preserves_typed_args(monkeypatch):
    from core.command_registry import COMMAND_INTERACTION_PANEL, CommandDefinition, CommandResult

    popup = _popup_with_items([])
    popup._executing = False
    popup.is_pinned = False
    popup.search_query = "/wifi LEI"
    popup._read_clipboard_text = lambda: ""
    popup.show = lambda: None
    popup.raise_ = lambda: None
    popup.activateWindow = lambda: None
    popup._set_search_query = lambda query: setattr(popup, "search_query", query)

    captured = {}

    def handler(ctx):
        captured["raw_input"] = ctx.raw_input
        captured["args_text"] = ctx.args_text
        return CommandResult(success=True, message=f"password for {ctx.args_text}")

    cmd_def = CommandDefinition(
        id="wifi",
        title="Wi-Fi",
        aliases=["wifi"],
        description="Wi-Fi password",
        category="system",
        handler=handler,
        interaction_mode=COMMAND_INTERACTION_PANEL,
    )

    class FakeRegistry:
        def count(self):
            return 1

        def get_canonical(self, alias):
            return "wifi" if alias == "wifi" else ""

        def get(self, command_id):
            return cmd_def if command_id == "wifi" else None

    class FakeSettings:
        pass

    class FakeDataManager:
        @staticmethod
        def get_settings():
            return FakeSettings()

    import core
    monkeypatch.setattr(core, "registry", FakeRegistry())
    monkeypatch.setattr(core, "data_manager", FakeDataManager)

    shown = {}
    popup.show_command_result = lambda result, command_id="": shown.update(result=result, command_id=command_id)
    popup._search_execute_from_keyboard = True

    item = ShortcutItem(
        id="wifi",
        name="Wi-Fi",
        type=ShortcutType.COMMAND,
        command="/wifi",
        command_type="builtin",
    )

    popup._execute_item(item)

    assert captured["args_text"] == "LEI"
    assert captured["raw_input"] == "/wifi LEI"
    assert popup.search_query == "/wifi LEI"
    assert shown["command_id"] == "wifi"
    assert shown["result"].message == "password for LEI"


def test_plain_search_panel_command_preserves_typed_args(monkeypatch):
    from core.command_registry import COMMAND_INTERACTION_PANEL, CommandDefinition, CommandResult

    popup = _popup_with_items([])
    popup._executing = False
    popup.is_pinned = False
    popup.search_query = "proc python"
    popup._read_clipboard_text = lambda: ""
    popup.show = lambda: None
    popup.raise_ = lambda: None
    popup.activateWindow = lambda: None
    popup._set_search_query = lambda query: setattr(popup, "search_query", query)

    captured = {}

    def handler(ctx):
        captured["raw_input"] = ctx.raw_input
        captured["args_text"] = ctx.args_text
        return CommandResult(success=True, message=ctx.args_text)

    cmd_def = CommandDefinition(
        id="process_tools.find",
        title="查找进程",
        aliases=["proc"],
        description="Find process",
        category="排障",
        handler=handler,
        interaction_mode=COMMAND_INTERACTION_PANEL,
    )

    class FakeRegistry:
        def count(self):
            return 1

        def get_canonical(self, alias):
            return "process_tools.find" if alias == "proc" else ""

        def get(self, command_id):
            return cmd_def if command_id == "process_tools.find" else None

    class FakeSettings:
        pass

    class FakeDataManager:
        @staticmethod
        def get_settings():
            return FakeSettings()

    import core
    monkeypatch.setattr(core, "registry", FakeRegistry())
    monkeypatch.setattr(core, "data_manager", FakeDataManager)

    shown = {}
    popup.show_command_result = lambda result, command_id="": shown.update(result=result, command_id=command_id)
    popup._search_execute_from_keyboard = True

    item = ShortcutItem(
        id="process_tools.find",
        name="查找进程",
        type=ShortcutType.COMMAND,
        command="process_tools.find",
        command_type="builtin",
    )

    popup._execute_item(item)

    assert captured["args_text"] == "python"
    assert captured["raw_input"] == "/process_tools.find python"
    assert popup.search_query == "proc python"
    assert shown["command_id"] == "process_tools.find"
    assert shown["result"].message == "python"


def test_direct_slash_command_closes_even_when_pinned(monkeypatch):
    from core.command_registry import COMMAND_INTERACTION_DIRECT, CommandDefinition, CommandResult

    popup = _popup_with_items([])
    popup._executing = False
    popup.is_pinned = True
    popup.search_query = "/env"

    hidden = []
    popup.hide = lambda: hidden.append(True)

    cmd_def = CommandDefinition(
        id="env",
        title="Env",
        aliases=["env"],
        description="Open environment editor",
        category="system",
        handler=lambda ctx: CommandResult(success=True),
        interaction_mode=COMMAND_INTERACTION_DIRECT,
    )

    class FakeRegistry:
        def count(self):
            return 1

        def get_canonical(self, alias):
            return "env" if alias == "env" else ""

        def get(self, command_id):
            return cmd_def if command_id == "env" else None

    class FakeSettings:
        pass

    class FakeDataManager:
        @staticmethod
        def get_settings():
            return FakeSettings()

    calls = []

    class FakeExecutor:
        @staticmethod
        def execute(shortcut, force_new=False):
            calls.append((shortcut.command, force_new))
            return True, ""

    import core
    import ui.launcher_popup.popup_window as popup_window_mod

    monkeypatch.setattr(core, "registry", FakeRegistry())
    monkeypatch.setattr(core, "data_manager", FakeDataManager)
    monkeypatch.setattr(popup_window_mod, "HAS_EXECUTOR", True)
    monkeypatch.setattr(popup_window_mod, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(popup_window_mod.threading.Thread, "start", lambda self: self.run())

    item = ShortcutItem(
        id="env",
        name="Env",
        type=ShortcutType.COMMAND,
        command="/env",
        command_type="builtin",
    )

    popup._execute_item(item)

    assert hidden == [True]
    assert calls == [("env", False)]


def test_command_result_auto_pin_restores_previous_pin_state():
    from core.command_registry import CommandResult

    popup = LauncherPopup.__new__(LauncherPopup)
    popup._command_result = None
    popup._command_id = ""
    popup._result_auto_pin_previous_state = None
    popup._hide_timer = SimpleNamespace(isActive=lambda: False)
    popup._ensure_text_edit = lambda: None
    popup.update = lambda: None
    popup.setFocus = lambda: None

    popup.is_pinned = False
    popup.show_command_result(CommandResult(success=True, message="ok"), "uuid")
    assert popup.is_pinned is True
    popup.clear_command_result()
    assert popup.is_pinned is False

    popup.is_pinned = True
    popup.show_command_result(CommandResult(success=True, message="ok"), "uuid")
    assert popup.is_pinned is True
    popup.clear_command_result()
    assert popup.is_pinned is True


def test_command_result_right_click_toggles_post_close_pin_state():
    from core.command_registry import CommandResult

    popup = LauncherPopup.__new__(LauncherPopup)
    popup._command_result = None
    popup._command_id = ""
    popup._result_auto_pin_previous_state = None
    popup._hide_timer = SimpleNamespace(isActive=lambda: False)
    popup._ensure_text_edit = lambda: None
    popup.update = lambda: None
    popup.setFocus = lambda: None

    popup.is_pinned = False
    popup.show_command_result(CommandResult(success=True, message="ok"), "uuid")
    assert popup.is_pinned is True
    assert popup.toggle_result_panel_post_close_pin() is True
    assert popup.is_pinned is True
    popup.clear_command_result()
    assert popup.is_pinned is True

    popup.show_command_result(CommandResult(success=True, message="ok"), "uuid")
    assert popup.toggle_result_panel_post_close_pin() is True
    assert popup.is_pinned is True
    popup.clear_command_result()
    assert popup.is_pinned is False


def test_search_bar_right_click_shows_context_menu_without_toggling_pin(monkeypatch):
    import ui.launcher_popup.popup_window as popup_window_mod

    popup = _popup_with_items([])
    popup.is_pinned = False
    popup.search_query = "abc"
    popup.search_cursor_pos = 0
    popup.search_selection_anchor = None
    popup._search_scroll_x = 0
    popup._is_search_layout_visible = lambda: True
    popup._is_search_active = lambda: True
    popup._search_bar_contains = lambda pos: True
    popup._search_pos_from_point = lambda pos: 2
    popup._read_clipboard_text = lambda: "XYZ"
    popup._hide_timer = SimpleNamespace(isActive=lambda: False, stop=lambda: None)

    created = {}

    class FakeMenu:
        def __init__(self, theme="dark", parent=None):
            self.actions = []
            created["menu"] = self

        def add_action(self, text, callback, enabled=True):
            self.actions.append((text, callback, enabled))

        def add_separator(self):
            self.actions.append(("separator", None, True))

        def popup(self, pos):
            created["pos"] = pos

    monkeypatch.setattr(popup_window_mod, "CompactResultPopupMenu", FakeMenu)

    event = _FakeMouseEvent(QPoint(10, 10), button=QtCompat.RightButton)
    LauncherPopup.mouseReleaseEvent(popup, event)

    assert event.accepted
    assert popup.is_pinned is False
    assert popup.search_cursor_pos == 2
    assert [a[0] for a in created["menu"].actions] == ["粘贴", "separator", "复制", "剪切", "全选", "清空"]


def test_search_context_menu_paste_replaces_selection():
    popup = _popup_with_items([])
    popup.search_query = "abcdef"
    popup.search_cursor_pos = 4
    popup.search_selection_anchor = 2
    popup._read_clipboard_text = lambda: "X\nY"

    popup._paste_search_clipboard()

    assert popup.search_query == "abX Yef"
    assert popup.search_cursor_pos == 5
    assert popup.search_selection_anchor is None
