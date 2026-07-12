"""Macro recorder widget — extracted from macro_record_dialog."""

from __future__ import annotations

import logging
import threading
import time

from hooks.hooks_wrapper import INPUT_KEY_DOWN, enrich_pointer_context
from hooks.input_macro import InputMacroBackend
from qt_compat import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QtCompat,
    QTimer,
    QWidget,
    pyqtSignal,
)
from ui.utils.ui_scale import sp

logger = logging.getLogger(__name__)

_IDLE_STATUS_TEXT = "尚未录制"
_RECORD_INDICATOR_TEXT = "● 录制中"
F8_VK = 0x77


class MacroRecorderWidget(QWidget):
    """宏录制控件：开始 / 停止 / 清空 + 实时状态。

    仅包装 InputMacroBackend 的控制面，不直接持有任何 UI 样式。
    """

    event_recorded = pyqtSignal(dict)
    state_changed = pyqtSignal()
    f8_stop_requested = pyqtSignal()
    continue_requested = pyqtSignal()
    # 从原生 dispatch 线程发出，触发 GUI 线程刷新状态栏（避免跨线程直接 setText）
    _status_refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._backend = InputMacroBackend()
        self._recording = False
        self._lock = threading.Lock()
        self._started_at = 0.0
        self._dropped = 0
        self._count = 0
        # 原始事件列表（仅当用户希望查看 / 调试时使用，UI 文本框由调用方维护）
        self._raw_events: list[dict] = []
        self._append_mode = False
        # 标记本次录制是否由本控件主动安装了钩子（用于结束时清理）
        self._keyboard_hook_owned = False
        self._mouse_hook_owned = False
        self._dll_ref = None
        self.f8_stop_requested.connect(self.stop)
        # 跨线程安全：把原生 dispatch 线程的「刷新状态栏」请求转发到 GUI 线程
        self._status_refresh_requested.connect(self._refresh_status)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(sp(6))

        self.start_btn = QPushButton("开始录制")
        self.start_btn.setFixedWidth(sp(72))
        self.start_btn.setFixedHeight(sp(24))
        self.start_btn.clicked.connect(self._toggle_recording)
        layout.addWidget(self.start_btn)

        self.continue_btn = QPushButton("继续录制")
        self.continue_btn.setFixedWidth(sp(72))
        self.continue_btn.setFixedHeight(sp(24))
        self.continue_btn.clicked.connect(self._request_continue_recording)
        layout.addWidget(self.continue_btn)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setFixedHeight(sp(24))
        self.clear_btn.clicked.connect(self.clear)
        layout.addWidget(self.clear_btn)

        layout.addStretch(1)

        self.status_label = QLabel(_IDLE_STATUS_TEXT)
        self.status_label.setAlignment(QtCompat.AlignRight | QtCompat.AlignVCenter)
        layout.addWidget(self.status_label, 1)

        # 定时刷新录制时长（仅在录制中实际运行）
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(200)
        self._tick_timer.timeout.connect(self._refresh_status)

    def _toggle_recording(self):
        if self._recording:
            self.stop()
        else:
            self.start()

    def _request_continue_recording(self):
        if self._recording:
            return
        self.continue_requested.emit()

    def start(self, *, append: bool = False) -> bool:
        if self._recording:
            return False
        self._append_mode = bool(append)
        # 1. 先确保键盘 / 鼠标钩子已安装；StartInputCapture 不会自动安装。
        #    仿照 input_trigger_recorder.py 的 rearm + install 模式：
        #    - 键盘：rearm_keyboard_hook_for_capture 负责重建（如已存在则保留 callback）
        #    - 鼠标：仅在未安装时安装，并在结束时还原
        try:
            from hooks.hooks_wrapper import HooksDLL  # 懒加载避免循环
        except Exception as exc:
            logger.warning("宏录制启动失败：无法导入 HooksDLL: %s", exc)
            self.status_label.setText("启动失败：hooks 模块不可用")
            self.state_changed.emit()
            return False
        dll = HooksDLL.get_instance()
        self._dll_ref = dll
        if not dll.loaded or not dll.compatible:
            self.status_label.setText("启动失败：请确认 hooks.dll 已加载")
            self.state_changed.emit()
            return False

        # 键盘钩子：rearm 会处理「已存在 / 需重建」两种情况
        keyboard_ready, installed_temporarily = dll.rearm_keyboard_hook_for_capture()
        if not keyboard_ready:
            self.status_label.setText("启动失败：无法安装键盘钩子")
            self.state_changed.emit()
            return False
        self._keyboard_hook_owned = installed_temporarily

        # 鼠标钩子：仅在未安装时安装，并在结束时还原
        if not dll.is_mouse_hook_installed():
            self._mouse_hook_owned = dll.install_mouse_hook(lambda *_args: None)
            if not self._mouse_hook_owned:
                # 还原键盘钩子
                if self._keyboard_hook_owned:
                    dll.uninstall_keyboard_hook()
                self._keyboard_hook_owned = False
                self.status_label.setText("启动失败：无法安装鼠标钩子")
                self.state_changed.emit()
                return False

        # 2. 启动宏录制
        ok = self._backend.start_recording(
            mouse_move=False,
            mouse_buttons=True,
            mouse_wheel=True,
            keyboard=True,
            include_injected=True,
            include_own_playback=False,
            coalesce_mouse_moves=False,
            event_filter=self._filter_recorded_event,
            on_event=self._on_event,
        )
        if not ok:
            self._cleanup_owned_hooks()
            logger.warning("宏录制启动失败：底层钩子不可用")
            self.status_label.setText("启动失败，请确认 hooks.dll 已加载")
            self.state_changed.emit()
            return False
        with self._lock:
            self._recording = True
            self._started_at = time.monotonic()
            self._count = 0
            self._dropped = 0
            self._raw_events = []
        self._refresh_buttons()
        self._refresh_status()
        self._tick_timer.start()
        self.state_changed.emit()
        return True

    def _filter_recorded_event(self, event: dict) -> bool:
        if int(event.get("vk_code", 0)) != F8_VK:
            return True
        # 关键：只有在「真正录制中」时才把 F8 当作停止信号。
        # 原因：键盘钩子比 Qt keyPressEvent 更早收到 F8 按键；
        # 如果不在此加守卫，启动录制的那次 F8 按键会被错误识别为「停止」，
        # 导致「按一次 F8 录制就立即开始又停止」、UI 闪一下、按钮状态混乱。
        if not self._recording:
            return False
        event_type = int(event.get("type", 0))
        if event_type == INPUT_KEY_DOWN:
            self.f8_stop_requested.emit()
        return False

    def stop(self) -> list[dict]:
        if not self._recording:
            self._cleanup_owned_hooks()
            return list(self._backend.recorded_events())
        events: list[dict] = self._backend.stop_recording()
        with self._lock:
            self._recording = False
            # 重新从底层读取最终事件列表，确保与 UI 行数一致
            self._raw_events = list(self._backend.recorded_events())
            self._append_mode = False
        self._cleanup_owned_hooks()
        self._tick_timer.stop()
        self._refresh_buttons()
        self._refresh_status()
        self.state_changed.emit()
        return events

    def clear(self):
        if self._recording:
            self.stop()
        else:
            # 兜底：极端情况下 tick_timer 仍在运行（例如外部直接调用 clear）
            if self._tick_timer.isActive():
                self._tick_timer.stop()
        with self._lock:
            self._count = 0
            self._dropped = 0
            self._raw_events = []
        self.status_label.setText(_IDLE_STATUS_TEXT)
        self.state_changed.emit()

    def _cleanup_owned_hooks(self):
        """清理本控件主动安装的钩子（不影响应用本身已安装的钩子）。

        顺序：
            1) 停止 input_capture（必须在卸载钩子前完成，否则 DLL 会拒绝卸载）
            2) 仅卸载本控件主动安装的钩子（不会触碰应用本身已安装的钩子）
        """
        dll = self._dll_ref
        if dll is None:
            self._keyboard_hook_owned = False
            self._mouse_hook_owned = False
            return

        # 1) 停掉 input_capture（幂等，多个分支共享一次调用）
        try:
            dll.stop_input_capture(force=True)
        except (AttributeError, OSError) as exc:
            logger.debug("stop_input_capture failed: %s", exc)
        except Exception as exc:
            logger.debug("stop_input_capture unexpected error: %s", exc, exc_info=True)

        # 2) 仅卸载本控件主动安装的钩子
        if self._mouse_hook_owned:
            try:
                if dll.is_mouse_hook_installed():
                    dll.uninstall_mouse_hook()
            except Exception as exc:
                logger.debug("卸载鼠标钩子失败: %s", exc, exc_info=True)
            self._mouse_hook_owned = False

        if self._keyboard_hook_owned:
            try:
                if dll.is_keyboard_hook_installed():
                    dll.uninstall_keyboard_hook()
            except Exception as exc:
                logger.debug("卸载键盘钩子失败: %s", exc, exc_info=True)
            self._keyboard_hook_owned = False

        self._dll_ref = None

    def is_recording(self) -> bool:
        return bool(self._recording)

    def is_append_mode(self) -> bool:
        return bool(self._append_mode)

    def get_events(self) -> list[dict]:
        return list(self._backend.recorded_events())

    def set_events(self, events: list[dict] | None):
        """用于编辑既有宏时回填数据，UI 状态以回填的事件数为准。

        通过同步注入到后端的 deque，使 ``get_events()`` 与 ``_raw_events``
        保持一致，避免 ``get_shortcut`` 解析失败时回退到空列表。
        """
        if self._recording:
            self.stop()
        normalized = [dict(event) for event in (events or []) if isinstance(event, dict)]
        new_backend = InputMacroBackend(max_events=self._backend.max_events)
        new_backend.inject_events(normalized)
        self._backend = new_backend
        with self._lock:
            self._raw_events = list(normalized)
            self._count = len(self._raw_events)
            self._dropped = 0
        dropped = self._backend.dropped_events
        if dropped > 0:
            self.status_label.setText(f"已加载 {self._count} 个事件，已截断 {dropped} 条")
        else:
            self.status_label.setText(f"已加载 {self._count} 个事件")
        self.state_changed.emit()

    def _on_event(self, event: dict):
        # event 来自 hooks.dll，字段包括 type / flags / vk_code / scan_code / data / x / y / timestamp_us 等
        # 来自原生 dispatch 线程（非 Qt GUI 线程），只做最少的工作
        snapshot = enrich_pointer_context(event)
        with self._lock:
            self._count += 1
            self._dropped = int(self._backend.dropped_events)
            self._raw_events.append(snapshot)
        # 通过信号把状态更新与新事件投递交给 GUI 线程（queued connection）
        self.event_recorded.emit(snapshot)
        self._status_refresh_requested.emit()

    def _refresh_buttons(self):
        if self._recording:
            self.start_btn.setText("停止录制")
            self.continue_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)
        else:
            self.start_btn.setText("开始录制")
            self.continue_btn.setEnabled(True)
            self.clear_btn.setEnabled(True)

    def _refresh_status(self):
        with self._lock:
            if not self._recording:
                if self._count <= 0:
                    self.status_label.setText(_IDLE_STATUS_TEXT)
                else:
                    self.status_label.setText(f"已录制 {self._count} 个事件")
                return
            seconds = max(0.0, time.monotonic() - self._started_at)
            text = _RECORD_INDICATOR_TEXT.format(
                count=self._count,
                dropped=self._dropped,
                seconds=seconds,
            )
        self.status_label.setText(text)
