"""Stress regressions for rapidly interrupted UI animations."""

from __future__ import annotations

from types import SimpleNamespace

from qt_compat import QPoint
from ui.config_window.main_window import ConfigWindow
from ui.launcher_popup.popup_window import LauncherPopup


class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self):
        for callback in list(self.callbacks):
            callback()


class _FakeAnimation:
    def __init__(self, *args, **kwargs):
        self.duration = None
        self.start_value = None
        self.end_value = None
        self.easing = None

    def setDuration(self, duration):
        self.duration = duration

    def setStartValue(self, value):
        self.start_value = value

    def setEndValue(self, value):
        self.end_value = value

    def setEasingCurve(self, easing):
        self.easing = easing


class _FakeAnimationGroup:
    instances = []

    def __init__(self, *args, **kwargs):
        self.finished = _Signal()
        self.animations = []
        self.running = False
        _FakeAnimationGroup.instances.append(self)

    def addAnimation(self, animation):
        self.animations.append(animation)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def state(self):
        return 2 if self.running else 0

    def finish(self):
        self.running = False
        self.finished.emit()


class _FakeTimer:
    instances = []
    single_shots = []

    def __init__(self, *args, **kwargs):
        self.timeout = _Signal()
        self.active = False
        self.interval = None
        _FakeTimer.instances.append(self)

    def setInterval(self, interval):
        self.interval = interval

    def setTimerType(self, timer_type):
        self.timer_type = timer_type

    def start(self, *args):
        self.active = True

    def stop(self):
        self.active = False

    def isActive(self):
        return self.active

    @staticmethod
    def singleShot(delay, callback):
        _FakeTimer.single_shots.append((delay, callback))


def _popup_animation_shell():
    popup = SimpleNamespace()
    popup._visibility_animation_generation = 0
    popup._reveal_progress = 0.0
    popup._is_hiding = False
    popup._opacity = 0.0
    popup.windowOpacity = lambda: popup._opacity
    popup.setWindowOpacity = lambda value: setattr(popup, "_opacity", float(value))
    popup.update = lambda: None
    popup._next_visibility_animation_generation = lambda: LauncherPopup._next_visibility_animation_generation(popup)
    popup._is_visibility_animation_current = lambda generation: LauncherPopup._is_visibility_animation_current(
        popup, generation
    )
    popup._finish_show_animation = lambda generation=None: LauncherPopup._finish_show_animation(popup, generation)
    popup._on_hide_finished = lambda generation=None: LauncherPopup._on_hide_finished(popup, generation)
    popup.hide = lambda: setattr(popup, "_hidden", True)
    return popup


def test_popup_show_hide_show_triple_interrupt_ignores_stale_finish(monkeypatch):
    import ui.launcher_popup.popup_window as popup_window_mod

    _FakeAnimationGroup.instances = []
    monkeypatch.setattr(popup_window_mod.QtCompat, "QPropertyAnimation", _FakeAnimation)
    monkeypatch.setattr(popup_window_mod.QtCompat, "QParallelAnimationGroup", _FakeAnimationGroup)

    popup = _popup_animation_shell()

    LauncherPopup._start_show_animation(popup)
    first_show = _FakeAnimationGroup.instances[-1]
    popup._is_hiding = True
    LauncherPopup._start_hide_animation(popup)
    first_hide = _FakeAnimationGroup.instances[-1]
    popup._is_hiding = False
    LauncherPopup._start_show_animation(popup)
    final_show = _FakeAnimationGroup.instances[-1]

    first_show.finish()
    first_hide.finish()

    assert popup._reveal_progress == 0.0
    assert popup._opacity == 0.0
    assert popup._is_hiding is False

    final_show.finish()

    assert popup._reveal_progress == 1.0
    assert popup._opacity == 1.0


def _config_window_animation_shell():
    window = SimpleNamespace()
    window._window_animation_generation = 0
    window._centered_show_animation = False
    window._opacity = 1.0
    window._pos = QPoint(20, 30)
    window.pos = lambda: QPoint(window._pos)
    window.move = lambda pos_or_x, y=None: setattr(
        window,
        "_pos",
        QPoint(pos_or_x, y) if y is not None else QPoint(pos_or_x),
    )
    window.setWindowOpacity = lambda value: setattr(window, "_opacity", float(value))
    window.windowOpacity = lambda: window._opacity
    window.close = lambda: None
    window._next_window_animation_generation = lambda: ConfigWindow._next_window_animation_generation(window)
    window._is_window_animation_current = lambda generation: ConfigWindow._is_window_animation_current(
        window, generation
    )
    window._stop_window_animation_timer = lambda name: ConfigWindow._stop_window_animation_timer(window, name)
    window._run_window_animation_callback = lambda generation, callback: ConfigWindow._run_window_animation_callback(
        window, generation, callback
    )
    return window


def test_config_window_close_open_close_callbacks_are_latest_only(monkeypatch):
    import ui.config_window.main_window as main_window_mod

    _FakeTimer.instances = []
    _FakeTimer.single_shots = []
    monkeypatch.setattr(main_window_mod, "QTimer", _FakeTimer)

    window = _config_window_animation_shell()
    calls = []

    ConfigWindow._start_show_animation(window)
    ConfigWindow.animate_close_then(window, callback=lambda: calls.append("stale"), callback_delay_ms=1)
    ConfigWindow._start_show_animation(window)

    for _delay, callback in list(_FakeTimer.single_shots):
        callback()

    assert calls == []

    _FakeTimer.single_shots = []
    ConfigWindow.animate_close_then(window, callback=lambda: calls.append("current"), callback_delay_ms=1)

    for _delay, callback in list(_FakeTimer.single_shots):
        callback()

    assert calls == ["current"]
