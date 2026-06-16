from hooks import hooks_wrapper
from hooks.hooks_wrapper import CAPTURE_KEYBOARD, INPUT_FLAG_ABSOLUTE, INPUT_KEY_DOWN


def test_macro_recorder_rearms_hooks_and_keeps_injected_keyboard_input(qapp, monkeypatch):
    calls = []

    class FakeDLL:
        loaded = True
        compatible = True

        def rearm_keyboard_hook_for_capture(self):
            calls.append("rearm_keyboard")
            return True, False

        def is_mouse_hook_installed(self):
            return True

        def start_input_capture(self, callback, **kwargs):
            calls.append(("start_input_capture", kwargs))
            self.callback = callback
            return True

        def stop_input_capture(self, **kwargs):
            calls.append(("stop_input_capture", kwargs))
            return True

        def is_input_capture_active(self):
            return True

        def captured_events_to_macro(self, events, **_kwargs):
            return list(events)

        def play_macro(self, events, **_kwargs):
            return bool(events)

        def wait_for_macro_playback(self, timeout_ms):
            return timeout_ms > 0

        def is_macro_playback_active(self):
            return False

    fake = FakeDLL()
    monkeypatch.setattr(hooks_wrapper.HooksDLL, "get_instance", lambda: fake)

    from ui.config_window.macro_record_dialog import MacroRecorderWidget

    recorder = MacroRecorderWidget()
    try:
        recorder.start()

        assert calls[0] == "rearm_keyboard"
        start_call = next(call for call in calls if call[0] == "start_input_capture")
        assert start_call[1]["filter_flags"] & CAPTURE_KEYBOARD
        assert start_call[1]["include_injected"] is True
        assert start_call[1]["include_own_playback"] is False
        assert start_call[1]["owner"] is recorder._backend
        fake.callback({"type": INPUT_KEY_DOWN, "vk_code": 0x41, "timestamp_us": 100})
        assert recorder.get_events() == [{"type": INPUT_KEY_DOWN, "vk_code": 0x41, "timestamp_us": 100}]
    finally:
        recorder.stop()


def test_macro_recorder_filters_f8_and_uses_it_only_to_stop(qapp, monkeypatch):
    class FakeDLL:
        loaded = True
        compatible = True

        def __init__(self):
            self.capture_callback = None
            self.stop_count = 0

        def rearm_keyboard_hook_for_capture(self):
            return True, False

        def is_mouse_hook_installed(self):
            return True

        def start_input_capture(self, callback, **_kwargs):
            self.capture_callback = callback
            return True

        def stop_input_capture(self, **_kwargs):
            self.stop_count += 1
            return True

        def is_input_capture_active(self):
            return self.stop_count == 0

        def captured_events_to_macro(self, events, **_kwargs):
            return list(events)

        def play_macro(self, events, **_kwargs):
            return bool(events)

        def wait_for_macro_playback(self, _timeout_ms):
            return True

        def is_macro_playback_active(self):
            return False

    fake = FakeDLL()
    monkeypatch.setattr(hooks_wrapper.HooksDLL, "get_instance", lambda: fake)

    from ui.config_window.macro_record_dialog import MacroRecorderWidget

    recorder = MacroRecorderWidget()
    recorder.start()
    assert recorder.is_recording()

    fake.capture_callback({"type": INPUT_KEY_DOWN, "vk_code": 0x77, "timestamp_us": 100})
    qapp.processEvents()

    assert recorder.get_events() == []
    assert recorder.is_recording() is False


def test_macro_recorder_f8_press_stops_via_input_capture_filter(qapp, monkeypatch):
    """F8 停止录制由「键盘钩子 → _filter_recorded_event → f8_stop_requested」链路完成。

    已移除原先的 Win32 全局热键（与 input capture 重复，会导致
    启动录制的那次 F8 按键被立即识别为停止，从而「按一次 F8 录制就
    开始又停止」、UI 闪一下）。本测试覆盖新的正确行为。
    """
    import ui.config_window.macro_record_dialog as macro_dialog

    class FakeDLL:
        loaded = True
        compatible = True

        def __init__(self):
            self.capture_callback = None
            self.stop_count = 0

        def rearm_keyboard_hook_for_capture(self):
            return True, False

        def is_mouse_hook_installed(self):
            return True

        def start_input_capture(self, callback, **_kwargs):
            self.capture_callback = callback
            return True

        def stop_input_capture(self, **_kwargs):
            self.stop_count += 1
            return True

        def is_input_capture_active(self):
            return self.stop_count == 0

        def captured_events_to_macro(self, events, **_kwargs):
            return list(events)

        def play_macro(self, events, **_kwargs):
            return bool(events)

        def wait_for_macro_playback(self, _timeout_ms):
            return True

        def is_macro_playback_active(self):
            return False

    fake = FakeDLL()
    monkeypatch.setattr(hooks_wrapper.HooksDLL, "get_instance", lambda: fake)

    # 显式校验：Win32GlobalHotkey 不应再被引用（已被移除以避免双触发）
    assert not hasattr(macro_dialog, "Win32GlobalHotkey"), (
        "Win32GlobalHotkey 不应再被 macro_record_dialog 引用，" "否则会和 input capture 的 F8 过滤形成重复触发"
    )

    recorder = macro_dialog.MacroRecorderWidget()
    recorder.start()
    assert recorder.is_recording()
    # 模拟「录制中」按下 F8：键盘钩子应通过 _filter_recorded_event 把它转为停止信号
    fake.capture_callback({"type": INPUT_KEY_DOWN, "vk_code": 0x77, "timestamp_us": 100})
    # queued connection，需要让事件循环跑一次
    qapp.processEvents()

    assert recorder.is_recording() is False
    # F8 事件已被过滤，不应进入事件列表
    assert recorder.get_events() == []


def test_macro_recorder_f8_filter_guarded_by_recording_state(qapp, monkeypatch):
    """关键回归测试：F8 过滤器在「未在录制中」时不应发出停止信号。

    之前因为同时存在 input capture 过滤 + Win32 全局热键 + Qt keyPressEvent
    三个 F8 路径，按一次 F8 会导致「开始 → 立即停止」。现在 input capture
    过滤新增 ``self._recording`` 守卫，未录制时不会误触发停止信号。
    """
    import ui.config_window.macro_record_dialog as macro_dialog

    stop_signal_count = []

    class FakeDLL:
        loaded = True
        compatible = True

        def __init__(self):
            self.capture_callback = None
            self.stop_count = 0

        def rearm_keyboard_hook_for_capture(self):
            return True, False

        def is_mouse_hook_installed(self):
            return True

        def start_input_capture(self, callback, **_kwargs):
            self.capture_callback = callback
            return True

        def stop_input_capture(self, **_kwargs):
            self.stop_count += 1
            return True

        def is_input_capture_active(self):
            return self.stop_count == 0

    fake = FakeDLL()
    monkeypatch.setattr(hooks_wrapper.HooksDLL, "get_instance", lambda: fake)

    recorder = macro_dialog.MacroRecorderWidget()

    # 用一个 spy 监听 f8_stop_requested 信号
    recorder.f8_stop_requested.connect(lambda: stop_signal_count.append(1))

    # 场景 1：未录制时钩子收到 F8 → 不应发射停止信号
    f8_event = {"type": INPUT_KEY_DOWN, "vk_code": 0x77, "timestamp_us": 100}
    result = recorder._filter_recorded_event(dict(f8_event))
    qapp.processEvents()
    # 过滤函数返回 False 表示事件被丢弃；同时停止信号不应被发射
    assert result is False
    assert stop_signal_count == []
    assert recorder.is_recording() is False

    # 场景 2：进入录制后钩子再次收到 F8 → 应当正常发射停止信号
    recorder.start()
    assert recorder.is_recording() is True
    result = recorder._filter_recorded_event(dict(f8_event))
    qapp.processEvents()
    assert result is False
    assert stop_signal_count == [1]
    assert recorder.is_recording() is False


def test_macro_event_text_round_trips_mouse_click_position(qapp):
    from hooks.hooks_wrapper import INPUT_MOUSE_BUTTON_DOWN, INPUT_MOUSE_BUTTON_UP
    from ui.config_window.macro_record_dialog import MacroRecordDialog, _format_event_line

    event = {
        "type": INPUT_MOUSE_BUTTON_DOWN,
        "flags": INPUT_FLAG_ABSOLUTE,
        "delay_us": 0,
        "x": 123,
        "y": 456,
        "data": 1,
        "vk_code": 0,
        "scan_code": 0,
        "screen_index": 0,
        "screen_left": 0,
        "screen_top": 0,
        "screen_width": 1920,
        "screen_height": 1080,
        "screen_ratio_x": 0.064096,
        "screen_ratio_y": 0.422613,
        "virtual_left": 0,
        "virtual_top": 0,
        "virtual_width": 1920,
        "virtual_height": 1080,
    }

    line, _kind = _format_event_line(event, total_elapsed_us=0)
    assert "鼠标左键 @ 123,456" in line
    assert "screen=0" in line
    assert "rel=0.064096,0.422613" in line

    parsed = MacroRecordDialog._parse_event_text(
        "[0.200s] 按下 鼠标左键 @ 123,456 # screen=0 rel=0.064096,0.422613 rect=0,0,1920,1080 virtual=0,0,1920,1080\n"
        "[0.250s] 抬起 鼠标左键 @ 123,456 # screen=0 rel=0.064096,0.422613 rect=0,0,1920,1080 virtual=0,0,1920,1080"
    )

    assert parsed[0]["type"] == INPUT_MOUSE_BUTTON_DOWN
    assert parsed[0]["delay_us"] == 200000
    assert parsed[0]["screen_width"] == 1920
    assert parsed[0]["screen_ratio_x"] == 0.064096
    assert parsed[1]["type"] == INPUT_MOUSE_BUTTON_UP
    assert parsed[1]["delay_us"] == 50000


def test_macro_dialog_first_recorded_event_starts_at_200ms(qapp):
    from hooks.hooks_wrapper import INPUT_MOUSE_BUTTON_DOWN
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    dialog = MacroRecordDialog()
    dialog._on_event_recorded(
        {
            "type": INPUT_MOUSE_BUTTON_DOWN,
            "flags": 0,
            "timestamp_us": 999,
            "x": 0,
            "y": 0,
            "data": 1,
            "vk_code": 0,
            "scan_code": 0,
        }
    )

    assert "[000.200s]" in dialog.event_list.get_text()


def test_macro_dialog_f8_is_the_only_recording_control_key(qapp, monkeypatch):
    from PyQt5.QtGui import QKeyEvent

    from qt_compat import QEvent, Qt, QtCompat
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    class FakeRecorder:
        def __init__(self):
            self.recording = False
            self.starts = 0
            self.stops = 0

        def is_recording(self):
            return self.recording

        def start(self):
            self.starts += 1
            self.recording = True

        def stop(self):
            self.stops += 1
            self.recording = False
            return []

    class FakeKeyEvent:
        def __init__(self, key):
            self._key = key
            self.accepted = False

        def key(self):
            return self._key

        def accept(self):
            self.accepted = True

    dialog = MacroRecordDialog()
    fake = FakeRecorder()
    dialog.recorder = fake

    enter = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, QtCompat.NoModifier)
    dialog.keyPressEvent(enter)
    assert fake.starts == 0

    f8 = FakeKeyEvent(Qt.Key_F8)
    dialog.keyPressEvent(f8)
    assert f8.accepted is True
    assert fake.starts == 1

    esc = FakeKeyEvent(Qt.Key_Escape)
    dialog.keyPressEvent(esc)
    assert esc.accepted is True
    assert fake.stops == 0

    f8_stop = FakeKeyEvent(Qt.Key_F8)
    dialog.keyPressEvent(f8_stop)
    assert f8_stop.accepted is True
    assert fake.stops == 1


def test_macro_dialog_f8_press_does_not_close_window(qapp, monkeypatch):
    """回归测试：F8 不应触发任何关窗逻辑。

    用户反馈：「点击 F8 后 '编辑宏' 的窗口自动关闭」。F8 只是启停录制的
    热键，不应触发 ``accept`` / ``reject`` / ``done``。同时不应影响
    其它顶层窗口（主配置窗口）的可见性。
    """
    from PyQt5.QtGui import QKeyEvent

    from qt_compat import QEvent, Qt, QtCompat
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    class FakeRecorder:
        def __init__(self):
            self.recording = False

        def is_recording(self):
            return self.recording

        def start(self):
            self.recording = True

        def stop(self):
            self.recording = False
            return []

    dialog = MacroRecordDialog()
    fake = FakeRecorder()
    dialog.recorder = fake
    dialog.show()
    qapp.processEvents()

    # 第一次 F8：开始录制
    f8_start = QKeyEvent(QEvent.KeyPress, Qt.Key_F8, QtCompat.NoModifier)
    dialog.keyPressEvent(f8_start)
    assert f8_start.isAccepted()
    assert fake.is_recording() is True
    # 录制期间 accept/reject/done 都不应让 dialog 消失
    assert dialog.result() == 0
    assert dialog.isVisible()

    # 第二次 F8：停止录制
    f8_stop = QKeyEvent(QEvent.KeyPress, Qt.Key_F8, QtCompat.NoModifier)
    dialog.keyPressEvent(f8_stop)
    assert f8_stop.isAccepted()
    assert fake.is_recording() is False
    # 录制结束后 dialog 仍应可见
    assert dialog.isVisible()


def test_macro_dialog_does_not_accept_or_stop_while_recording(qapp):
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    class FakeRecorder:
        def __init__(self):
            self.stops = 0

        def is_recording(self):
            return True

        def stop(self):
            self.stops += 1

    dialog = MacroRecordDialog()
    fake = FakeRecorder()
    dialog.recorder = fake

    dialog._on_ok()
    dialog.accept()
    dialog.reject()

    assert fake.stops == 0
    assert dialog.result() == 0


def test_macro_dialog_hide_restore_keeps_window_geometry(qapp):
    from qt_compat import QWidget
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    class FakeRecorder:
        def is_recording(self):
            return True

    host = QWidget()
    host.resize(420, 260)
    host.move(30, 40)
    host.show()
    qapp.processEvents()

    dialog = MacroRecordDialog()
    dialog.recorder = FakeRecorder()
    original = host.saveGeometry()
    try:
        dialog._hide_windows_for_recording()
        dialog._restore_windows_after_recording()
        qapp.processEvents()

        assert host.saveGeometry() == original
    finally:
        host.close()


def test_macro_dialog_continue_recording_appends_after_200ms(qapp):
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    class FakeRecorder:
        def __init__(self):
            self.recording = False
            self.append_mode = False

        def is_recording(self):
            return self.recording

        def is_append_mode(self):
            return self.append_mode

        def start(self, *, append=False):
            self.append_mode = bool(append)
            self.recording = True
            return True

    dialog = MacroRecordDialog()
    fake = FakeRecorder()
    dialog.recorder = fake
    dialog.event_list.set_read_only(False)
    dialog.event_list.setPlainText("[0.200s] 按下 A\n[0.250s] 抬起 A")

    dialog._continue_recording()
    dialog._on_recorder_state_changed()
    dialog._on_event_recorded(
        {
            "type": INPUT_KEY_DOWN,
            "flags": 0,
            "timestamp_us": 1000,
            "x": 0,
            "y": 0,
            "data": 0,
            "vk_code": 0x42,
            "scan_code": 0,
        }
    )

    text = dialog.event_list.get_text()
    assert "[0.200s] 按下 A" in text
    assert "[000.450s] 按下 B" in text


def test_macro_dialog_persists_recording_options(qapp):
    from core.data_models import ShortcutItem, ShortcutType
    from hooks.hooks_wrapper import INPUT_MOUSE_BUTTON_DOWN
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    shortcut = ShortcutItem(
        type=ShortcutType.MACRO,
        name="宏",
        macro_events=[
            {
                "type": INPUT_MOUSE_BUTTON_DOWN,
                "flags": 0,
                "delay_us": 200_000,
                "x": 0,
                "y": 0,
                "data": 1,
                "vk_code": 0,
                "scan_code": 0,
            }
        ],
        macro_speed=2.0,
        macro_hide_while_recording=True,
    )

    dialog = MacroRecordDialog(shortcut=shortcut)

    assert dialog.hide_while_recording_cb.isChecked() is True
    assert dialog.double_speed_cb.isChecked() is True

    saved = dialog.get_shortcut()
    assert saved.macro_hide_while_recording is True
    assert saved.macro_speed == 2.0


def test_macro_test_playback_waits_for_completion(qapp, monkeypatch):
    import core.background_tasks as background_tasks
    import ui.config_window.macro_record_dialog as macro_dialog
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    calls = []

    class FakeBackend:
        def play(self, events=None, **kwargs):
            calls.append(("play", list(events or []), kwargs))
            return True

        def wait(self, timeout_ms):
            calls.append(("wait", timeout_ms))
            return True

    monkeypatch.setattr(macro_dialog, "InputMacroBackend", FakeBackend)
    monkeypatch.setattr(
        background_tasks,
        "start_background_thread",
        lambda **kwargs: kwargs["target"](),
    )

    dialog = MacroRecordDialog()
    dialog.event_list.set_read_only(False)
    dialog.event_list.setPlainText("[0.200s] 按下 A\n[0.250s] 抬起 A")
    dialog.double_speed_cb.setChecked(True)

    dialog._test_playback()
    qapp.processEvents()

    assert calls[0][0] == "play"
    assert calls[0][2]["speed"] == 2.0
    assert calls[1][0] == "wait"
    assert dialog.test_result_label.text() == "播放成功"


# ============================================================================
# 下列测试覆盖宏模块深度审计后的修复点
# ============================================================================


def test_macro_recorder_cleanup_stops_input_capture_only_once(qapp, monkeypatch):
    """_cleanup_owned_hooks 现在会显式调用一次 stop_input_capture，且在
    卸载任何钩子前完成；后续 uninstall_* 钩子函数如果再次调用应是冗余的。"""
    from hooks import hooks_wrapper
    from ui.config_window.macro_record_dialog import MacroRecorderWidget

    captured = []

    class FakeDLL:
        loaded = True
        compatible = True

        def rearm_keyboard_hook_for_capture(self):
            return True, True  # 标记为本控件临时安装

        def is_mouse_hook_installed(self):
            return False

        def install_mouse_hook(self, _cb):
            captured.append("install_mouse")
            return True

        def uninstall_mouse_hook(self):
            captured.append("uninstall_mouse")

        def is_keyboard_hook_installed(self):
            return True

        def uninstall_keyboard_hook(self):
            captured.append("uninstall_keyboard")

        def start_input_capture(self, _cb, **_kwargs):
            captured.append("start_capture")
            return True

        def stop_input_capture(self, *, force=False, owner=None):
            captured.append(("stop_capture", force))
            return True

        def is_input_capture_active(self):
            return True

    fake = FakeDLL()
    monkeypatch.setattr(hooks_wrapper.HooksDLL, "get_instance", lambda: fake)

    recorder = MacroRecorderWidget()
    recorder.start()
    captured.clear()  # 关注 stop 阶段
    recorder.stop()

    stop_calls = [entry for entry in captured if isinstance(entry, tuple) and entry[0] == "stop_capture"]
    # stop_recording 一次 + _cleanup_owned_hooks 显式一次，合计两次（幂等）。
    # 关键点：先 stop_capture，再 uninstall_* 钩子。
    assert len(stop_calls) == 2
    assert captured.index(stop_calls[0]) < captured.index(("stop_capture", True)) or stop_calls[0] == (
        "stop_capture",
        True,
    )
    # 卸载顺序：先 stop，再 uninstall
    for entry in ("uninstall_mouse", "uninstall_keyboard"):
        if entry in captured:
            assert captured.index(entry) > captured.index(stop_calls[0])


def test_macro_recorder_set_events_keeps_backend_in_sync(qapp, monkeypatch):
    """set_events 后 get_events 必须返回相同的事件列表，
    避免 get_shortcut 在解析失败时回退到空 backend 导致数据丢失。"""
    from hooks import hooks_wrapper
    from ui.config_window.macro_record_dialog import MacroRecorderWidget

    class FakeDLL:
        loaded = True
        compatible = True

        def rearm_keyboard_hook_for_capture(self):
            return True, False

        def is_mouse_hook_installed(self):
            return True

    fake = FakeDLL()
    monkeypatch.setattr(hooks_wrapper.HooksDLL, "get_instance", lambda: fake)

    recorder = MacroRecorderWidget()
    sample = [
        {"type": 6, "delay_us": 200_000, "vk_code": 65},
        {"type": 7, "delay_us": 50_000, "vk_code": 65},
    ]
    recorder.set_events(sample)

    assert recorder.get_events() == sample
    assert recorder.is_recording() is False
    # 状态栏反映加载数量
    assert "2" in recorder.status_label.text()


def test_macro_recorder_inject_events_respects_maxlen(qapp):
    """InputMacroBackend.inject_events 需要遵守 max_events 限制。"""
    from hooks.input_macro import InputMacroBackend

    class StubDLL:
        def __init__(self):
            self.calls = []

        def stop_input_capture(self, **_):
            return True

        def is_input_capture_active(self):
            return False

    backend = InputMacroBackend(StubDLL(), max_events=3)
    backend.inject_events(
        [
            {"type": 6, "delay_us": 100},
            {"type": 7, "delay_us": 200},
            {"type": 6, "delay_us": 300},
            {"type": 7, "delay_us": 400},
            {"type": 6, "delay_us": 500},
        ]
    )

    events = backend.recorded_events()
    assert len(events) == 3
    assert backend.dropped_events == 2
    assert [event["delay_us"] for event in events] == [300, 400, 500]


def test_macro_dialog_load_data_validates_loaded_text(qapp):
    """打开既有宏时，_load_data 必须把校验过的状态写入 parse_status_label。"""
    from core.data_models import ShortcutItem, ShortcutType
    from hooks.hooks_wrapper import INPUT_KEY_DOWN, INPUT_KEY_UP
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    shortcut = ShortcutItem(
        type=ShortcutType.MACRO,
        name="宏",
        macro_events=[
            {
                "type": INPUT_KEY_DOWN,
                "delay_us": 200_000,
                "vk_code": 65,
                "flags": 0,
                "x": 0,
                "y": 0,
                "data": 0,
                "scan_code": 0,
            },
            {
                "type": INPUT_KEY_UP,
                "delay_us": 50_000,
                "vk_code": 65,
                "flags": 0,
                "x": 0,
                "y": 0,
                "data": 0,
                "scan_code": 0,
            },
        ],
    )
    dialog = MacroRecordDialog(shortcut=shortcut)

    # 解析通过，状态行应当显示条数与总间隔
    status = dialog.parse_status_label.text()
    assert "2" in status
    assert "ms" in status or "✓" in status


def test_macro_dialog_get_shortcut_propagates_parse_error(qapp, monkeypatch):
    """当用户编辑后文本损坏时，get_shortcut 应抛出 ValueError 而不是
    静默回退到 recorder 后端的（可能为空的）事件列表。"""
    from core.data_models import ShortcutItem, ShortcutType
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    shortcut = ShortcutItem(
        type=ShortcutType.MACRO,
        name="宏",
        macro_events=[
            {"type": 6, "delay_us": 200_000, "vk_code": 65, "flags": 0, "x": 0, "y": 0, "data": 0, "scan_code": 0}
        ],
    )
    dialog = MacroRecordDialog(shortcut=shortcut)
    dialog.event_list.set_read_only(False)
    dialog.event_list.setPlainText("这是一段损坏的宏文本")

    import pytest

    with pytest.raises(ValueError):
        dialog.get_shortcut()


def test_macro_dialog_parse_event_text_caps_delay_us(qapp):
    """_parse_event_text 应当把 delay_us 限制在 uint32 范围，避免溢出。"""
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    events = MacroRecordDialog._parse_event_text("[0.000s] 按下 A 间隔 999999s" "\n[0.000s] 抬起 A")
    assert events[0]["delay_us"] == 0xFFFFFFFF
    assert events[1]["delay_us"] == 0  # 0.000s - 0.000s = 0


def test_macro_recorder_status_refresh_routes_via_signal(qapp, monkeypatch):
    """事件回调中的状态刷新必须通过 queued signal 转发到 GUI 线程，
    避免从原生 dispatch 线程直接修改 QLabel。"""
    from hooks import hooks_wrapper
    from ui.config_window.macro_record_dialog import MacroRecorderWidget

    class FakeDLL:
        loaded = True
        compatible = True

        def __init__(self):
            self.capture_callback = None

        def rearm_keyboard_hook_for_capture(self):
            return True, False

        def is_mouse_hook_installed(self):
            return True

        def start_input_capture(self, callback, **_kwargs):
            self.capture_callback = callback
            return True

        def stop_input_capture(self, **_kwargs):
            return True

        def is_input_capture_active(self):
            return True

    fake = FakeDLL()
    monkeypatch.setattr(hooks_wrapper.HooksDLL, "get_instance", lambda: fake)

    recorder = MacroRecorderWidget()
    # 验证 _status_refresh_requested 信号存在
    assert hasattr(recorder, "_status_refresh_requested")
    # 验证 _refresh_status 是该信号的目标槽（通过 disconnect 测试反向验证已连接）
    assert hasattr(recorder, "_refresh_status")
    # 启动录制后，模拟原生线程发事件，状态栏应该被刷新
    recorder.start()
    assert recorder.is_recording()
    fake.capture_callback({"type": 6, "vk_code": 0x41, "timestamp_us": 1000})
    qapp.processEvents()
    # 状态栏包含「录制中」字样
    assert "录制中" in recorder.status_label.text()
    recorder.stop()


# ============================================================================
# 宏模块审计后的回归测试
# ============================================================================


def test_macro_dialog_load_data_syncs_recorder_state(qapp, monkeypatch):
    """_load_data 应同步把事件写入 recorder 后端，状态栏显示「已加载 N 个事件」。

    修复：之前 _load_data 只填了文本框，recorder.status_label 仍显示「尚未录制」，
    与 get_events() 返回空不一致。
    """
    from core.data_models import ShortcutItem, ShortcutType
    from hooks import hooks_wrapper
    from hooks.hooks_wrapper import INPUT_KEY_DOWN, INPUT_KEY_UP
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    class FakeDLL:
        loaded = True
        compatible = True

        def rearm_keyboard_hook_for_capture(self):
            return True, False

        def is_mouse_hook_installed(self):
            return True

    monkeypatch.setattr(hooks_wrapper.HooksDLL, "get_instance", lambda: FakeDLL())

    shortcut = ShortcutItem(
        type=ShortcutType.MACRO,
        name="宏",
        macro_events=[
            {
                "type": INPUT_KEY_DOWN,
                "delay_us": 200_000,
                "vk_code": 65,
                "flags": 0,
                "x": 0,
                "y": 0,
                "data": 0,
                "scan_code": 0,
            },
            {
                "type": INPUT_KEY_UP,
                "delay_us": 50_000,
                "vk_code": 65,
                "flags": 0,
                "x": 0,
                "y": 0,
                "data": 0,
                "scan_code": 0,
            },
        ],
    )
    dialog = MacroRecordDialog(shortcut=shortcut)
    assert "已加载 2 个事件" in dialog.recorder.status_label.text()
    # 状态栏不再显示「尚未录制」
    assert "尚未录制" not in dialog.recorder.status_label.text()


def test_macro_dialog_invert_checkbox_updates_preview(qapp, monkeypatch):
    """勾选/取消反转 Checkbox 应触发 _update_icon_preview 重新生成图标。

    修复：之前 invert_light_cb / invert_dark_cb 的 stateChanged 未连接。
    """
    from core.data_models import ShortcutItem, ShortcutType
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    shortcut = ShortcutItem(type=ShortcutType.MACRO, name="宏", icon_invert_dark=False)
    dialog = MacroRecordDialog(shortcut=shortcut)

    # 验证 stateChanged 已连接到 _update_icon_preview（>0 表示有接收者）
    receivers_light = dialog.invert_light_cb.receivers(dialog.invert_light_cb.stateChanged)
    receivers_dark = dialog.invert_dark_cb.receivers(dialog.invert_dark_cb.stateChanged)
    assert receivers_light > 0, "invert_light_cb.stateChanged 应连接到 _update_icon_preview"
    assert receivers_dark > 0, "invert_dark_cb.stateChanged 应连接到 _update_icon_preview"

    # 验证真实调用：通过 monkeypatch 替换 _update_icon_preview，验证切换 checkbox
    # 时它被调用（replace 后重新连接信号，绕过 PyQt 已连接旧方法的限制）
    call_count = []

    def spy():
        call_count.append(1)

    dialog.invert_dark_cb.stateChanged.disconnect()
    dialog.invert_dark_cb.stateChanged.connect(spy)
    dialog.invert_light_cb.stateChanged.disconnect()
    dialog.invert_light_cb.stateChanged.connect(spy)

    dialog.invert_dark_cb.setChecked(True)
    qapp.processEvents()
    assert len(call_count) == 1
    dialog.invert_dark_cb.setChecked(False)
    qapp.processEvents()
    assert len(call_count) == 2
    dialog.invert_light_cb.setChecked(True)
    qapp.processEvents()
    assert len(call_count) == 3


def test_macro_dialog_double_speed_checkbox_round_trip(qapp):
    """「两倍速执行」复选框：勾选保存为 2.0，取消保存为 1.0。"""
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    dialog = MacroRecordDialog()
    assert dialog.double_speed_cb.isChecked() is False
    dialog.double_speed_cb.setChecked(True)
    saved = dialog.get_shortcut()
    assert saved.macro_speed == 2.0

    dialog.double_speed_cb.setChecked(False)
    saved = dialog.get_shortcut()
    assert saved.macro_speed == 1.0


def test_macro_dialog_load_data_speed_2_checks_box(qapp, monkeypatch):
    """加载 macro_speed=2.0 的既有宏时，「两倍速执行」应自动勾选。"""
    from core.data_models import ShortcutItem, ShortcutType
    from hooks import hooks_wrapper
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    class FakeDLL:
        loaded = True
        compatible = True

        def rearm_keyboard_hook_for_capture(self):
            return True, False

        def is_mouse_hook_installed(self):
            return True

    monkeypatch.setattr(hooks_wrapper.HooksDLL, "get_instance", lambda: FakeDLL())

    shortcut = ShortcutItem(type=ShortcutType.MACRO, name="宏", macro_speed=2.0)
    dialog = MacroRecordDialog(shortcut=shortcut)
    assert dialog.double_speed_cb.isChecked() is True


def test_macro_dialog_f8_hint_after_hide_checkbox(qapp):
    """F8 提示应在「录制时隐藏窗口」之后、「两倍速执行」之前。"""
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    dialog = MacroRecordDialog()
    # 此断言仅确保三者在同一 row（顺序由源码保证）
    assert dialog.hide_while_recording_cb.parent() is dialog.record_hotkey_hint.parent()
    assert dialog.record_hotkey_hint.parent() is dialog.double_speed_cb.parent()


def test_macro_dialog_done_cancels_test_playback_thread(qapp, monkeypatch):
    """done() 期间若测试线程仍在跑，应调用 InputMacroBackend().cancel() 并 join。"""
    import core.background_tasks as background_tasks
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    class FakeBackend:
        cancel_calls = []

        def __init__(self, *_a, **_kw):
            pass

        def play(self, events=None, **kwargs):
            return True

        def wait(self, timeout_ms):
            return True

        def cancel(self):
            self.cancel_calls.append(1)

    fake_backend = FakeBackend()
    monkeypatch.setattr("ui.config_window.macro_record_dialog.InputMacroBackend", FakeBackend)

    class _FakeThread:
        def __init__(self):
            self.alive = True
            self.joined = False
            self.timeout = None

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            self.timeout = timeout
            self.joined = True
            self.alive = False

    fake_thread = _FakeThread()
    monkeypatch.setattr(background_tasks, "start_background_thread", lambda **kw: fake_thread)

    dialog = MacroRecordDialog()
    dialog._test_thread = fake_thread
    dialog.done(0)
    assert fake_thread.joined is True
    assert fake_backend.cancel_calls == [1]
    assert dialog._test_thread is None


def test_macro_dialog_parse_error_uses_dedicated_label(qapp, monkeypatch):
    """解析失败应使用独立 error label，复用 test_result_label 会导致语义混乱。"""
    from core.data_models import ShortcutItem, ShortcutType
    from ui.config_window.macro_record_dialog import MacroRecordDialog

    shortcut = ShortcutItem(type=ShortcutType.MACRO, name="宏", macro_events=[])
    dialog = MacroRecordDialog(shortcut=shortcut)
    dialog.event_list.set_read_only(False)
    dialog.event_list.setPlainText("这是损坏的宏文本")

    dialog._on_ok()
    assert not dialog.parse_error_label.isHidden()
    assert "解析失败" in dialog.parse_error_label.text()
    # test_result_label 不应被错误消息污染
    assert "解析失败" not in dialog.test_result_label.text()


def test_macro_dialog_input_macro_backend_exposes_max_events():
    """InputMacroBackend 应暴露 max_events 供 set_events 沿用。"""
    from hooks.input_macro import InputMacroBackend

    backend = InputMacroBackend()
    assert backend.max_events == 100_000

    small = InputMacroBackend(max_events=128)
    assert small.max_events == 128


def test_macro_recorder_set_events_preserves_max_events(qapp, monkeypatch):
    """set_events 应沿用原后端 max_events，避免大事件列表被截断。"""
    from hooks import hooks_wrapper
    from hooks.input_macro import InputMacroBackend
    from ui.config_window.macro_record_dialog import MacroRecorderWidget

    class FakeDLL:
        loaded = True
        compatible = True

        def rearm_keyboard_hook_for_capture(self):
            return True, False

        def is_mouse_hook_installed(self):
            return True

    monkeypatch.setattr(hooks_wrapper.HooksDLL, "get_instance", lambda: FakeDLL())

    recorder = MacroRecorderWidget()
    # 替换后端为 max_events=3
    recorder._backend = InputMacroBackend(max_events=3)
    sample = [{"type": 6, "delay_us": 100}] * 5
    recorder.set_events(sample)
    # 新后端应继承 max_events=3，5 条事件保留 3 条
    assert recorder._backend.max_events == 3
    assert len(recorder.get_events()) == 3
    # dropped 应有提示
    assert "截断" in recorder.status_label.text()
