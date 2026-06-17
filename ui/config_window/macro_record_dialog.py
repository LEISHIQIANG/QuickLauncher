"""宏录制编辑对话框

布局与 HotkeyDialog 保持一致（基本信息 / 录制区 / 实时事件列表 / 触发模式 / 测试 / 图标 / 按钮），
所有样式均复用既有主题助手（Glassmorphism / flat / radio / checkbox），不新增任何 QSS。

实时事件列表为可编辑纯文本框：
- 录制中：只读追加事件
- 录制结束后：用户可增删改行
- 保存时：解析文本回到 events 列表
"""

import logging
import os
import re
import threading
import time

from core import ShortcutItem, ShortcutType
from core.i18n import tr
from hooks.hooks_wrapper import (
    INPUT_FLAG_ABSOLUTE,
    INPUT_KEY_DOWN,
    INPUT_KEY_UP,
    INPUT_MOUSE_BUTTON_DOWN,
    INPUT_MOUSE_BUTTON_UP,
    INPUT_MOUSE_HWHEEL,
    INPUT_MOUSE_MOVE,
    INPUT_MOUSE_WHEEL,
    enrich_pointer_context,
)
from hooks.input_macro import InputMacroBackend
from hooks.key_map import key_display_name, key_to_vk, vk_to_key
from qt_compat import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColor,
    QFont,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QPainter,
    QPixmap,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QRectF,
    Qt,
    QtCompat,
    QTextCharFormat,
    QTextCursor,
    QTimer,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from ui.styles.style import Glassmorphism
from ui.utils.ui_scale import font_px, scale_qss, sp

from .base_dialog import BaseDialog
from .icon_browse_helper import choose_custom_icon
from .theme_helper import (
    get_compact_checkbox_stylesheet,
    get_radio_stylesheet,
)

logger = logging.getLogger(__name__)

INITIAL_EVENT_DELAY_US = 200_000
F8_VK = 0x77

# ============ 文本格式常量 ============
# 展示格式：`[<time>s] <action> <key> [# 注释]`
#   动作支持（仅文字形式，不再兼容旧箭头写法）：
#     按下     键/鼠标按键 按下
#     抬起     键/鼠标按键 抬起
#     滚轮     滚轮事件
#     滚轮-横  横向滚轮
#   录制时不显示「间隔」字段（间隔由相邻事件的时间戳差自动推导）
#   编辑模式下可以手动追加「间隔 Xs」字段覆盖默认值
# 使用非 VERBOSE 模式以避免 # 在字符类中被当作注释起始
_LINE_PATTERN = re.compile(
    r"^\s*"
    r"(?:\[\s*(?P<time>[\d.]+)\s*s\]\s*)?"
    r"(?P<action>按下|抬起|滚轮|滚轮-横)\s+"
    r"(?P<key>.+?)"
    r"(?:\s+间隔\s*(?P<delay>[\d.]+)\s*s)?"
    r"\s*(?:\#.*)?$"
)
_ACTION_KEY_DOWN_TEXT = "按下"
_ACTION_KEY_UP_TEXT = "抬起"
_ACTION_WHEEL = "滚轮"
_ACTION_HWHEEL = "滚轮-横"


# 颜色方案（按当前主题区分按下 / 抬起 / 滚轮），不引入新 QSS，仅作为 QTextCharFormat 前景色使用
def _press_color(theme: str) -> QColor:
    # 深色：淡绿；浅色：深绿
    return QColor(120, 220, 150) if theme == "dark" else QColor(20, 130, 60)


def _release_color(theme: str) -> QColor:
    # 深色：偏粉的橙；浅色：深红
    return QColor(255, 145, 120) if theme == "dark" else QColor(170, 40, 40)


def _wheel_color(theme: str) -> QColor:
    # 深色：淡蓝；浅色：深蓝
    return QColor(120, 180, 240) if theme == "dark" else QColor(40, 90, 200)


_MOUSE_BUTTON_NAMES = {
    0x0001: "鼠标左键",
    0x0002: "鼠标右键",
    0x0004: "鼠标中键",
    0x0008: "侧键后",
    0x0010: "侧键前",
}
_MOUSE_BUTTON_VALUES = {v: k for k, v in _MOUSE_BUTTON_NAMES.items()}

_RECORD_INDICATOR_TEXT = "⏺ 录制中…  事件: {count}    丢弃: {dropped}    耗时: {seconds:.1f}s"
_IDLE_STATUS_TEXT = "尚未录制"


def _mouse_button_display(data: int) -> str:
    return _MOUSE_BUTTON_NAMES.get(int(data) & 0xFFFF, f"鼠标按键 0x{int(data) & 0xFFFF:04X}")


def _mouse_button_parse(name: str) -> int | None:
    name = (name or "").strip()
    if name in _MOUSE_BUTTON_VALUES:
        return _MOUSE_BUTTON_VALUES[name]
    return None


def _split_pointer_position(text: str) -> tuple[str, int | None, int | None]:
    """Split a display name like ``鼠标左键 @ 120,240`` into name and coordinates."""
    value = (text or "").strip()
    match = re.match(r"^(?P<name>.+?)\s*@\s*\(?\s*(?P<x>-?\d+)\s*,\s*(?P<y>-?\d+)\s*\)?$", value)
    if not match:
        return value, None, None
    return (
        match.group("name").strip(),
        int(match.group("x")),
        int(match.group("y")),
    )


def _pointer_context_comment(event: dict) -> str:
    if int(event.get("flags", 0)) & INPUT_FLAG_ABSOLUTE == 0:
        return ""
    if "screen_ratio_x" not in event or "screen_ratio_y" not in event:
        return ""
    return (
        " # screen={screen} rel={rx:.6f},{ry:.6f} rect={left},{top},{width},{height}"
        " virtual={vleft},{vtop},{vwidth},{vheight}"
    ).format(
        screen=int(event.get("screen_index", 0)),
        rx=float(event.get("screen_ratio_x", 0.0)),
        ry=float(event.get("screen_ratio_y", 0.0)),
        left=int(event.get("screen_left", 0)),
        top=int(event.get("screen_top", 0)),
        width=int(event.get("screen_width", 0)),
        height=int(event.get("screen_height", 0)),
        vleft=int(event.get("virtual_left", 0)),
        vtop=int(event.get("virtual_top", 0)),
        vwidth=int(event.get("virtual_width", 0)),
        vheight=int(event.get("virtual_height", 0)),
    )


def _parse_pointer_context_comment(line: str) -> dict:
    context: dict = {}
    comment_index = line.find("#")
    if comment_index < 0:
        return context
    comment = line[comment_index + 1 :]
    screen_match = re.search(r"\bscreen=(?P<screen>-?\d+)", comment)
    rel_match = re.search(r"\brel=(?P<x>-?\d+(?:\.\d+)?),(?P<y>-?\d+(?:\.\d+)?)", comment)
    rect_match = re.search(r"\brect=(?P<left>-?\d+),(?P<top>-?\d+),(?P<width>\d+),(?P<height>\d+)", comment)
    virtual_match = re.search(
        r"\bvirtual=(?P<left>-?\d+),(?P<top>-?\d+),(?P<width>\d+),(?P<height>\d+)",
        comment,
    )
    if screen_match:
        context["screen_index"] = int(screen_match.group("screen"))
    if rel_match:
        context["screen_ratio_x"] = float(rel_match.group("x"))
        context["screen_ratio_y"] = float(rel_match.group("y"))
    if rect_match:
        context["screen_left"] = int(rect_match.group("left"))
        context["screen_top"] = int(rect_match.group("top"))
        context["screen_width"] = int(rect_match.group("width"))
        context["screen_height"] = int(rect_match.group("height"))
    if virtual_match:
        context["virtual_left"] = int(virtual_match.group("left"))
        context["virtual_top"] = int(virtual_match.group("top"))
        context["virtual_width"] = int(virtual_match.group("width"))
        context["virtual_height"] = int(virtual_match.group("height"))
    return context


def _format_event_line(event: dict, *, total_elapsed_us: int) -> tuple[str, int]:
    """把单条事件格式化成可读文本行 + 着色类别。

    返回 (line, line_kind)
        - line_kind: 0 = 未知/默认, 1 = 按下（绿色）, 2 = 抬起（橙红色）, 3 = 滚轮（蓝色）
    """
    type_id = int(event.get("type", 0))
    total_s = max(0, int(total_elapsed_us)) / 1_000_000.0

    if type_id in (INPUT_KEY_DOWN, INPUT_KEY_UP):
        vk = int(event.get("vk_code", 0))
        key_name = vk_to_key(vk)
        if not key_name:
            key_name = f"vk_{vk:02x}"
        display = key_display_name(key_name) or key_name.upper()
        if type_id == INPUT_KEY_DOWN:
            action = _ACTION_KEY_DOWN_TEXT
            kind = 1
        else:
            action = _ACTION_KEY_UP_TEXT
            kind = 2
    elif type_id in (INPUT_MOUSE_BUTTON_DOWN, INPUT_MOUSE_BUTTON_UP):
        display = _mouse_button_display(int(event.get("data", 0)))
        if int(event.get("flags", 0)) & INPUT_FLAG_ABSOLUTE:
            display = f"{display} @ {int(event.get('x', 0))},{int(event.get('y', 0))}"
        if type_id == INPUT_MOUSE_BUTTON_DOWN:
            action = _ACTION_KEY_DOWN_TEXT
            kind = 1
        else:
            action = _ACTION_KEY_UP_TEXT
            kind = 2
    elif type_id == INPUT_MOUSE_WHEEL:
        delta = int(event.get("data", 0))
        display = f"Delta {delta}"
        action = _ACTION_WHEEL
        kind = 3
    elif type_id == INPUT_MOUSE_HWHEEL:
        delta = int(event.get("data", 0))
        display = f"Delta {delta}"
        action = _ACTION_HWHEEL
        kind = 3
    else:
        display = f"Type {type_id}"
        action = "?"
        kind = 0

    return f"[{total_s:07.3f}s] {action} {display}{_pointer_context_comment(event)}", kind


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
        self.start_btn.setFixedHeight(sp(26))
        self.start_btn.clicked.connect(self._toggle_recording)
        layout.addWidget(self.start_btn)

        self.continue_btn = QPushButton("继续录制")
        self.continue_btn.setFixedWidth(sp(72))
        self.continue_btn.setFixedHeight(sp(26))
        self.continue_btn.clicked.connect(self._request_continue_recording)
        layout.addWidget(self.continue_btn)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setFixedHeight(sp(26))
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


class _MacroEventListWidget(QPlainTextEdit):
    """实时事件列表 + 编辑面板。

    录制中：只读 + 自动追加新行（按下/抬起整行上色区分）
    停止后：用户可直接编辑（增删改行）；保存时调用方负责解析
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        # 使用 UI 默认 sans-serif 字体以保持视觉一致（不强制等宽）
        font = QFont()
        font.setPixelSize(font_px(12))
        self.setFont(font)
        try:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        except AttributeError:
            self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setPlaceholderText("事件列表将在录制时自动填充；停止后可编辑。")
        # 主题由父对话框在 _apply_theme 中注入；默认深色
        self._theme = "dark"

    def set_theme(self, theme: str):
        self._theme = "dark" if theme != "light" else "light"

    def _color_for_kind(self, kind: int) -> QColor | None:
        if kind == 1:
            return _press_color(self._theme)
        if kind == 2:
            return _release_color(self._theme)
        if kind == 3:
            return _wheel_color(self._theme)
        return None

    def append_line(self, line: str, kind: int = 0):
        """追加一行；按 kind 给整行上色（按下=绿，抬起=橙红，滚轮=蓝）。"""
        if not line:
            return
        color = self._color_for_kind(int(kind))
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self.toPlainText():
            cursor.insertText("\n", QTextCharFormat())
        char_format = QTextCharFormat()
        if color is not None:
            char_format.setForeground(color)
        cursor.insertText(line, char_format)
        # 移动可见光标到末尾
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        viewport = self.viewport()
        if viewport is not None:
            viewport.update()

    def finish_recording(self):
        self.setReadOnly(False)

    def reset_to_idle(self):
        self.setReadOnly(True)
        self.clear()

    def set_read_only(self, value: bool):
        self.setReadOnly(bool(value))

    def get_text(self) -> str:
        return self.toPlainText()


class MacroRecordDialog(BaseDialog):
    """宏录制编辑对话框

    整体布局与 HotkeyDialog 对齐：
        标题 / 基本信息 / 录制区 / 事件列表 / 触发模式 / 测试 / 图标 / 取消 + 确定
    """

    test_done_requested = pyqtSignal(str)

    def __init__(self, parent=None, shortcut: ShortcutItem = None):  # type: ignore[assignment]
        super().__init__(parent)
        self.shortcut = shortcut or ShortcutItem(type=ShortcutType.MACRO)
        self._custom_icon_path = self.shortcut.icon_path or ""
        self._test_thread = None
        # 录制中：累计时间（ms），用于在文本框中显示 [时间] 列
        self._cumulative_delay_us = 0
        self._hidden_record_windows: list[tuple[QWidget, object, bool, bool]] = []

        self.setWindowTitle(tr("编辑宏") if shortcut else tr("添加宏录制"))
        self.setMinimumWidth(sp(480))
        self.resize(sp(560), sp(640))

        self._setup_window_icon()
        self._setup_ui()
        self.test_done_requested.connect(self._on_test_done)
        self._load_data()
        self._apply_theme()

    def _setup_window_icon(self):
        if BaseDialog._is_compiled():
            return
        try:
            pixmap = QPixmap(64, 64)
            pixmap.fill(QtCompat.transparent)
            painter = QPainter(pixmap)
            try:
                painter.setRenderHint(QtCompat.Antialiasing)
                painter.setRenderHint(QtCompat.HighQualityAntialiasing)
                font = QFont("Segoe UI Symbol", font_px(38))
                font.setStyleHint(QFont.StyleHint.SansSerif)
                painter.setFont(font)
                painter.setPen(QColor(192, 132, 252))
                painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⏺")
            finally:
                painter.end()
            self.setWindowIcon(QIcon(pixmap))
        except Exception as exc:
            logger.debug("设置窗口图标失败: %s", exc, exc_info=True)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(sp(6))
        layout.setContentsMargins(sp(10), sp(10), sp(10), sp(10))

        title_label = QLabel("编辑宏" if self.shortcut.name else "添加宏录制")
        title_label.setStyleSheet(scale_qss("font-size: 12px; font-weight: 400; color: gray;"))
        layout.addWidget(title_label)

        # ===== 基本信息 =====
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(sp(6))
        basic_layout.setContentsMargins(sp(8), 0, sp(8), sp(8))
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(6)
        self.name_edit.setPlaceholderText("最多6个字符")
        basic_layout.addRow(tr("名称:"), self.name_edit)
        layout.addWidget(basic_group)

        # ===== 录制区 =====
        record_group = QGroupBox("宏录制")
        record_layout = QVBoxLayout(record_group)
        record_layout.setSpacing(sp(6))
        record_layout.setContentsMargins(sp(8), 0, sp(8), sp(8))
        self.recorder = MacroRecorderWidget()
        self.recorder.event_recorded.connect(self._on_event_recorded)
        self.recorder.state_changed.connect(self._on_recorder_state_changed)
        self.recorder.continue_requested.connect(self._continue_recording)
        record_layout.addWidget(self.recorder)
        record_options_row = QHBoxLayout()
        record_options_row.setSpacing(sp(8))
        self.hide_while_recording_cb = QCheckBox("录制时隐藏窗口")
        self.hide_while_recording_cb.setToolTip("勾选后开始录制会最小化本项目所有窗口，按 F8 结束后恢复显示。")
        record_options_row.addWidget(self.hide_while_recording_cb)
        self.record_hotkey_hint = QLabel("F8 开始 / 结束")
        self.record_hotkey_hint.setStyleSheet(scale_qss("color: rgba(128,128,128,0.74); font-size: 10px;"))
        record_options_row.addWidget(self.record_hotkey_hint)
        self.double_speed_cb = QCheckBox("两倍速执行")
        self.double_speed_cb.setToolTip("勾选后测试播放和每次触发都会按录制间隔的两倍速度执行。")
        record_options_row.addWidget(self.double_speed_cb)
        record_options_row.addStretch(1)
        record_layout.addLayout(record_options_row)
        layout.addWidget(record_group)

        # ===== 事件列表（实时显示 + 可编辑） =====
        events_group = QGroupBox("事件列表")
        events_layout = QVBoxLayout(events_group)
        events_layout.setSpacing(sp(6))
        events_layout.setContentsMargins(sp(8), 0, sp(8), sp(8))
        self.event_list = _MacroEventListWidget()
        self.event_list.setMinimumHeight(sp(180))
        events_layout.addWidget(self.event_list, 1)
        # 编辑工具条
        tools_row = QHBoxLayout()
        tools_row.setSpacing(sp(6))
        self.reparse_btn = QPushButton("重新解析")
        self.reparse_btn.setFixedHeight(sp(26))
        self.reparse_btn.clicked.connect(self._validate_edited_text)
        tools_row.addWidget(self.reparse_btn)
        self.parse_status_label = QLabel("事件格式：[时间s] 动作 键    间隔时间s")
        self.parse_status_label.setStyleSheet(scale_qss("color: rgba(128,128,128,0.8); font-size: 11px;"))
        tools_row.addWidget(self.parse_status_label, 1)
        events_layout.addLayout(tools_row)
        # 错误提示 label：仅在解析失败时显示，复位与样式独立于 test_result_label
        self.parse_error_label = QLabel("")
        self.parse_error_label.setWordWrap(True)
        self.parse_error_label.setVisible(False)
        events_layout.addWidget(self.parse_error_label)
        layout.addWidget(events_group, 1)

        # ===== 触发模式（复用 HotkeyDialog 模式） =====
        trigger_group = QGroupBox("触发模式")
        trigger_layout = QHBoxLayout(trigger_group)
        trigger_layout.setSpacing(sp(12))
        trigger_layout.setContentsMargins(sp(8), 0, sp(8), sp(8))
        self.trigger_immediate_rb = QRadioButton("无延迟运行")
        self.trigger_after_close_rb = QRadioButton("窗口淡出后运行")
        trigger_layout.addWidget(self.trigger_immediate_rb)
        trigger_layout.addWidget(self.trigger_after_close_rb)
        trigger_layout.addStretch()
        self.trigger_group_btn = QButtonGroup(self)
        self.trigger_group_btn.addButton(self.trigger_immediate_rb)
        self.trigger_group_btn.addButton(self.trigger_after_close_rb)
        layout.addWidget(trigger_group)

        # ===== 测试行 =====
        test_row = QHBoxLayout()
        test_row.setSpacing(sp(6))
        self._test_btn = QPushButton("测试播放")
        self._test_btn.clicked.connect(self._test_playback)
        test_row.addWidget(self._test_btn)
        self.test_result_label = QLabel("")
        test_row.addWidget(self.test_result_label, 1)
        layout.addLayout(test_row)

        # ===== 图标设置 =====
        icon_group = QGroupBox("图标")
        icon_layout = QHBoxLayout(icon_group)
        icon_layout.setSpacing(sp(6))
        icon_layout.setContentsMargins(sp(6), 0, sp(6), sp(6))
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(sp(32), sp(32))
        self.icon_preview.setAlignment(QtCompat.AlignCenter)
        icon_layout.addWidget(self.icon_preview)

        icon_right_layout = QVBoxLayout()
        icon_right_layout.setSpacing(sp(6))
        self.icon_path_edit = QLineEdit()
        self.icon_path_edit.setPlaceholderText("可选，自定义图标路径")
        self.icon_path_edit.setReadOnly(True)
        icon_right_layout.addWidget(self.icon_path_edit)

        icon_btn_layout = QHBoxLayout()
        icon_btn_layout.setSpacing(sp(6))
        self._browse_icon_btn = QPushButton("选择图标...")
        self._browse_icon_btn.clicked.connect(self._browse_icon)
        icon_btn_layout.addWidget(self._browse_icon_btn)
        self._clear_icon_btn = QPushButton("清除")
        self._clear_icon_btn.clicked.connect(self._clear_icon)
        icon_btn_layout.addWidget(self._clear_icon_btn)
        icon_btn_layout.addStretch()
        self.invert_light_cb = QCheckBox("浅色反转")
        self.invert_dark_cb = QCheckBox("深色反转")
        self.invert_light_cb.stateChanged.connect(self._update_icon_preview)
        self.invert_dark_cb.stateChanged.connect(self._update_icon_preview)
        icon_btn_layout.addWidget(self.invert_light_cb)
        icon_btn_layout.addWidget(self.invert_dark_cb)
        icon_right_layout.addLayout(icon_btn_layout)
        icon_layout.addLayout(icon_right_layout, 1)
        layout.addWidget(icon_group)

        # ===== 按钮 =====
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(sp(8))
        btn_layout.addStretch()
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setFixedSize(sp(80), sp(32))
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)
        self._ok_btn = QPushButton("确定")
        self._ok_btn.setFixedSize(sp(80), sp(32))
        self._ok_btn.setDefault(True)
        self._ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(self._ok_btn)
        layout.addLayout(btn_layout)

    def _apply_theme(self):
        self._apply_theme_colors()
        theme = self.theme
        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        border_color = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(0, 0, 0, 0.04)"
        title_color = "rgba(255, 255, 255, 0.6)" if theme == "dark" else "rgba(0, 0, 0, 0.5)"
        self.setStyleSheet(
            base_style
            + scale_qss(
                f"""
            QDialog {{ background: transparent; border: none; }}
            QGroupBox {{
                border: 1px solid {border_color};
                border-radius: 6px;
                margin-top: 16px;
                padding-top: 8px;
                font-weight: 400;
                font-size: 13px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: -9px;
                top: -3px;
                color: {title_color};
                font-size: 13px;
            }}
        """
            )
        )

        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme)
        for btn in [
            self.recorder.start_btn,
            self.recorder.continue_btn,
            self.recorder.clear_btn,
            self.reparse_btn,
            self._test_btn,
            self._browse_icon_btn,
            self._clear_icon_btn,
            self._cancel_btn,
            self._ok_btn,
        ]:
            btn.setStyleSheet(flat_btn_style)

        radio_style = get_radio_stylesheet(theme)
        self.trigger_immediate_rb.setStyleSheet(radio_style)
        self.trigger_after_close_rb.setStyleSheet(radio_style)

        invert_cb_style = get_compact_checkbox_stylesheet(theme)
        self.hide_while_recording_cb.setStyleSheet(invert_cb_style)
        self.double_speed_cb.setStyleSheet(invert_cb_style)
        self.invert_light_cb.setStyleSheet(invert_cb_style)
        self.invert_dark_cb.setStyleSheet(invert_cb_style)

        # 文本框样式 — 复用既有 QPlainTextEdit 风格（不新增 QSS，仅做颜色调整）
        if theme == "dark":
            self.event_list.setStyleSheet(
                scale_qss(
                    "QPlainTextEdit {"
                    "  background-color: rgba(0, 0, 0, 0.28);"
                    "  border: 1px solid rgba(255, 255, 255, 0.08);"
                    "  border-radius: 6px;"
                    "  padding: 4px 8px;"
                    "  color: rgba(255, 255, 255, 0.92);"
                    "  selection-background-color: rgba(10, 132, 255, 0.30);"
                    "  selection-color: rgba(255, 255, 255, 0.95);"
                    "}"
                )
            )
            self.icon_preview.setStyleSheet(
                scale_qss(
                    "QLabel { background-color: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.10); border-radius: 10px; }"
                )
            )
            self.test_result_label.setStyleSheet(scale_qss("color: rgba(255,255,255,0.62); font-size: 11px;"))
        else:
            self.event_list.setStyleSheet(
                scale_qss(
                    "QPlainTextEdit {"
                    "  background-color: rgba(255, 255, 255, 0.65);"
                    "  border: 1px solid rgba(0, 0, 0, 0.08);"
                    "  border-radius: 6px;"
                    "  padding: 4px 8px;"
                    "  color: rgba(28, 28, 30, 0.92);"
                    "  selection-background-color: rgba(0, 122, 255, 0.20);"
                    "  selection-color: rgba(28, 28, 30, 0.96);"
                    "}"
                )
            )
            self.icon_preview.setStyleSheet(
                scale_qss(
                    "QLabel { background-color: rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.05); border-radius: 10px; }"
                )
            )
            self.test_result_label.setStyleSheet(scale_qss("color: rgba(0,0,0,0.55); font-size: 11px;"))
        # 同步事件列表的主题（用于决定按下/抬起/滚轮的上色）
        self.event_list.set_theme(theme)

    def _load_data(self):
        self.name_edit.setText(self.shortcut.name or "")
        if getattr(self.shortcut, "trigger_mode", "immediate") == "after_close":
            self.trigger_after_close_rb.setChecked(True)
        else:
            self.trigger_immediate_rb.setChecked(True)
        if self._custom_icon_path:
            self.icon_path_edit.setText(self._custom_icon_path)
        self.hide_while_recording_cb.setChecked(bool(getattr(self.shortcut, "macro_hide_while_recording", False)))
        try:
            self.double_speed_cb.setChecked(float(getattr(self.shortcut, "macro_speed", 1.0) or 1.0) >= 2.0)
        except (TypeError, ValueError):
            self.double_speed_cb.setChecked(False)
        self.invert_light_cb.setChecked(self.shortcut.icon_invert_light)
        self.invert_dark_cb.setChecked(self.shortcut.icon_invert_dark)
        existing_events = list(self.shortcut.macro_events or [])
        if existing_events:
            self.recorder.set_events(existing_events)
            self._populate_event_list(existing_events)
            self.event_list.finish_recording()
            # 立即校验并刷新状态行，避免解析状态在编辑前就过时
            self._validate_edited_text()
        self._update_icon_preview()

    def _populate_event_list(self, events: list[dict]):
        """把已有事件格式化后填回文本框。"""
        self.event_list.reset_to_idle()
        cumulative = 0
        for event in events:
            cumulative += int(event.get("delay_us", 0))
            line, kind = _format_event_line(event, total_elapsed_us=cumulative)
            self.event_list.append_line(line, kind=kind)
        self._cumulative_delay_us = cumulative

    def _on_event_recorded(self, event: dict):
        """从 recorder 收到实时事件：格式化后追加到文本框。

        该槽由 ``event_recorded`` 信号触发；由于 recorder 端使用 queued
        connection，实际执行一定在 GUI 线程，因此可以安全地操作 QPlainTextEdit。
        """
        type_id = int(event.get("type", 0))
        if type_id == INPUT_MOUSE_MOVE:  # 忽略鼠标移动
            return
        # 第一次事件保留 200ms 起始延迟，避免播放时第一下过早执行。
        first_ts = getattr(self, "_raw_first_timestamp_us", None)
        if first_ts is not None:
            ts_now = int(event.get("timestamp_us", 0))
            # 距首事件的累计 delta（不是相邻事件 delay）
            delta_us = max(0, ts_now - first_ts)
            self._raw_first_timestamp_us = ts_now
            self._cumulative_delay_us += delta_us
        else:
            self._raw_first_timestamp_us = int(event.get("timestamp_us", 0))
            self._cumulative_delay_us += INITIAL_EVENT_DELAY_US

        line, kind = _format_event_line(event, total_elapsed_us=self._cumulative_delay_us)
        self.event_list.append_line(line, kind=kind)

    def _continue_recording(self):
        if self.recorder.is_recording():
            return
        try:
            events = self._parse_event_text(self.event_list.get_text())
        except ValueError as exc:
            self._set_parse_error(str(exc))
            self.event_list.setFocus()
            return
        self._clear_parse_error()
        self._cumulative_delay_us = sum(int(event.get("delay_us", 0)) for event in events)
        if hasattr(self, "_raw_first_timestamp_us"):
            del self._raw_first_timestamp_us
        self.recorder.start(append=True)

    def _on_recorder_state_changed(self):
        if self.recorder.is_recording():
            # 开始新一轮录制：普通开始会清空；继续录制保留现有内容并接在末尾。
            if self.recorder.is_append_mode():
                try:
                    events = self._parse_event_text(self.event_list.get_text())
                except ValueError:
                    events = []
                self._cumulative_delay_us = sum(int(event.get("delay_us", 0)) for event in events)
                self.event_list.set_read_only(True)
            else:
                self.event_list.reset_to_idle()
                self._cumulative_delay_us = 0
            if hasattr(self, "_raw_first_timestamp_us"):
                del self._raw_first_timestamp_us
            self._clear_parse_error()
            self.parse_status_label.setText("录制中…")
            self._cancel_btn.setEnabled(False)
            self._ok_btn.setEnabled(False)
            self._test_btn.setEnabled(False)
            self.reparse_btn.setEnabled(False)
            if self.hide_while_recording_cb.isChecked():
                QTimer.singleShot(0, self._hide_windows_for_recording)
        else:
            # 录制结束：解锁文本框以便编辑
            self._restore_windows_after_recording()
            self._cancel_btn.setEnabled(True)
            self._ok_btn.setEnabled(True)
            self._test_btn.setEnabled(True)
            self.reparse_btn.setEnabled(True)
            self.event_list.finish_recording()
            self._validate_edited_text()

    def _hide_windows_for_recording(self):
        if not self.recorder.is_recording():
            return
        self._hidden_record_windows = []
        for widget in QApplication.topLevelWidgets():
            if not isinstance(widget, QWidget) or not widget.isVisible():
                continue
            self._hidden_record_windows.append(
                (
                    widget,
                    widget.saveGeometry(),
                    bool(widget.isMaximized()),
                    bool(widget.isFullScreen()),
                )
            )
        for widget, _geometry, _was_maximized, _was_fullscreen in self._hidden_record_windows:
            widget.showMinimized()

    def _restore_windows_after_recording(self):
        windows = list(self._hidden_record_windows)
        self._hidden_record_windows = []
        for widget, geometry, was_maximized, was_fullscreen in windows:
            try:
                if was_fullscreen:
                    widget.showFullScreen()
                elif was_maximized:
                    widget.showMaximized()
                else:
                    widget.showNormal()
                    widget.restoreGeometry(geometry)
                widget.raise_()
                widget.activateWindow()
            except RuntimeError:
                continue

    def _validate_edited_text(self):
        """对文本框内容做一次试解析，给出顶部状态提示。"""
        try:
            events = self._parse_event_text(self.event_list.get_text())
        except ValueError as exc:
            self._set_parse_error(str(exc))
            return
        self._clear_parse_error()
        if not events:
            self.parse_status_label.setText("事件列表为空")
        else:
            total_ms = sum(int(ev.get("delay_us", 0)) for ev in events) / 1000.0
            self.parse_status_label.setText(f"✓ {len(events)} 条事件，总间隔 {total_ms:.0f} ms")

    def _set_parse_error(self, message: str):
        if not hasattr(self, "parse_error_label"):
            return
        self.parse_error_label.setText(f"⚠ {message}")
        self.parse_error_label.setStyleSheet(scale_qss("color: rgba(255, 96, 96, 0.92); font-size: 11px;"))
        self.parse_error_label.setVisible(True)

    def _clear_parse_error(self):
        if not hasattr(self, "parse_error_label"):
            return
        self.parse_error_label.clear()
        self.parse_error_label.setStyleSheet("")
        self.parse_error_label.setVisible(False)

    def _update_icon_preview(self):
        pixmap = None
        if self._custom_icon_path and os.path.exists(self._custom_icon_path):
            try:
                from core.icon_extractor import IconExtractor

                pixmap = IconExtractor.from_file(self._custom_icon_path, 40)
            except Exception as exc:
                logger.debug("加载自定义图标失败: %s", exc, exc_info=True)
        if not pixmap or pixmap.isNull():
            pixmap = self._create_macro_icon(40)
        _current_theme = getattr(self, "theme", "dark")
        _need_invert = (
            self.invert_light_cb.isChecked() if _current_theme == "light" else self.invert_dark_cb.isChecked()
        )
        if _need_invert and pixmap and not pixmap.isNull():
            from core.icon_extractor import IconExtractor

            pixmap = IconExtractor.invert_pixmap(pixmap)
        if pixmap and not pixmap.isNull():
            pixmap = pixmap.scaled(sp(32), sp(32), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
        self.icon_preview.setPixmap(pixmap)

    def _create_macro_icon(self, size: int) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)
            painter.setBrush(QColor(192, 132, 252))
            painter.setPen(QtCompat.NoPen)
            margin = size // 8
            painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), 6, 6)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Segoe UI Symbol", size // 3))
            painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⏺")
        finally:
            painter.end()
        return pixmap

    def _browse_icon(self):
        file_path = choose_custom_icon(self, "选择图标")
        if file_path:
            self._custom_icon_path = file_path
            self.icon_path_edit.setText(file_path)
            self._update_icon_preview()

    def _clear_icon(self):
        self._custom_icon_path = ""
        self.icon_path_edit.clear()
        self._update_icon_preview()

    def _test_playback(self):
        if self.recorder.is_recording():
            self.test_result_label.setText(tr("请先停止录制"))
            return
        try:
            events = self._parse_event_text(self.event_list.get_text())
        except ValueError as exc:
            self.test_result_label.setText(f"解析失败: {exc}")
            return
        if not events:
            self.test_result_label.setText(tr("尚无录制内容"))
            return
        self._test_btn.setEnabled(False)
        self.test_result_label.setText(tr("播放中..."))
        speed = 2.0 if self.double_speed_cb.isChecked() else 1.0

        def _do():
            try:
                backend = InputMacroBackend()
                ok = backend.play(events=events, speed=speed)
                if ok:
                    total_delay_us = sum(int(ev.get("delay_us", 0)) for ev in events)
                    timeout_ms = min(0xFFFFFFFF, max(1000, round(total_delay_us / speed / 1000) + 5000))
                    ok = backend.wait(timeout_ms)
                text = "播放成功" if ok else "播放失败"
            except Exception as exc:
                text = f"播放失败: {exc}"
            self.test_done_requested.emit(text)

        from core.background_tasks import start_background_thread

        self._test_thread = start_background_thread(
            name="MacroRecordDialogTest",
            target=_do,
            owner=self,
        )

    def _on_test_done(self, text: str):
        if self._dialog_finished:
            return
        self.test_result_label.setText(text)
        self._test_btn.setEnabled(True)

    def keyPressEvent(self, event):  # noqa: N802 - Qt override
        if event.key() == Qt.Key_F8:
            if self.recorder.is_recording():
                self.recorder.stop()
            else:
                self.recorder.start()
            event.accept()
            return
        if self.recorder.is_recording():
            event.accept()
            return
        super().keyPressEvent(event)

    def reject(self):
        if hasattr(self, "recorder") and self.recorder.is_recording():
            return
        super().reject()

    def _on_ok(self):
        if self.recorder.is_recording():
            return
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        try:
            events = self._parse_event_text(self.event_list.get_text())
        except ValueError as exc:
            self._set_parse_error(f"解析失败: {exc}")
            self.event_list.setFocus()
            return
        self._clear_parse_error()
        if not events:
            self._set_parse_error(tr("请先录制宏"))
            return
        self.accept()

    def accept(self):
        if hasattr(self, "recorder") and self.recorder.is_recording():
            return
        super().accept()

    def done(self, result):
        if hasattr(self, "recorder") and self.recorder.is_recording():
            self.recorder.stop()
        if getattr(self, "_test_thread", None) is not None and self._test_thread.is_alive():
            try:
                InputMacroBackend().cancel()
            except Exception as exc:
                logger.debug("取消测试播放失败: %s", exc, exc_info=True)
            self._test_thread.join(timeout=1.0)
        self._test_thread = None
        super().done(result)

    # ===== 文本解析器 =====

    @staticmethod
    def _parse_event_text(text: str) -> list[dict]:
        """解析文本框内容，回填到 events 列表。

        解析规则（每行）：
            [时间s] 动作 键    [间隔 Xs] [# 注释]
        - 动作：按下 / 抬起 / 滚轮 / 滚轮-横（仅文字形式）
        - 键：字母 / 名称（Ctrl、A、Enter、鼠标左键、Delta xxx 等）
        - 间隔：可省略；缺省时按相邻行时间戳差自动推导
        - 行尾可以加 # 注释
        """
        if not text or not text.strip():
            return []

        # 先收集每行的 (timestamp, action, key, override_delay_s_or_none)
        parsed: list[dict] = []
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue
            pointer_context = _parse_pointer_context_comment(line)
            match = _LINE_PATTERN.match(line)
            if not match:
                raise ValueError(f"无法解析行：{line.strip()[:60]}")
            action = (match.group("action") or "").strip()
            key = (match.group("key") or "").strip()
            time_str = (match.group("time") or "").strip()
            delay_str = (match.group("delay") or "").strip()

            timestamp_s: float | None
            if time_str:
                try:
                    timestamp_s = max(0.0, float(time_str))
                except ValueError as exc:
                    raise ValueError(f"时间戳非法：{time_str}") from exc
            else:
                timestamp_s = None

            override_delay_s: float | None = None
            if delay_str:
                try:
                    override_delay_s = max(0.0, float(delay_str))
                except ValueError as exc:
                    raise ValueError(f"间隔时间非法：{delay_str}") from exc

            parsed.append(
                {
                    "action": action,
                    "key": key,
                    "timestamp_s": timestamp_s,
                    "override_delay_s": override_delay_s,
                    "pointer_context": pointer_context,
                }
            )

        # 计算每行的 timestamp（如未填，按上一行 timestamp + 0 推导为 0；后续按行序递推）
        last_ts = 0.0
        for item in parsed:
            if item["timestamp_s"] is None:
                item["timestamp_s"] = last_ts
            else:
                last_ts = item["timestamp_s"]

        events: list[dict] = []
        previous_timestamp_s = 0.0
        for item in parsed:
            timestamp_s = float(item["timestamp_s"] or 0.0)
            if item["override_delay_s"] is not None:
                delay_s = item["override_delay_s"]
            else:
                delay_s = max(0.0, timestamp_s - previous_timestamp_s)
            # 与底层 ctypes ``HookMacroEvent.delay_us`` 字段一致，使用 uint32 上限
            delay_us = max(0, min(0xFFFFFFFF, int(round(delay_s * 1_000_000))))
            event = MacroRecordDialog._build_event_from_action(
                item["action"], item["key"], delay_us, item.get("pointer_context") or None
            )
            if event is None:
                raise ValueError(f"未知动作/键：{item['action']} {item['key']!r}（请检查格式）")
            events.append(event)
            previous_timestamp_s = timestamp_s
        return events

    @staticmethod
    def _build_event_from_action(
        action: str,
        key: str,
        delay_us: int,
        pointer_context: dict | None = None,
    ) -> dict | None:
        """根据 action + key 构造一个事件 dict。"""
        delay_us = max(0, min(0xFFFFFFFF, int(delay_us)))
        if action in (_ACTION_KEY_DOWN_TEXT, _ACTION_KEY_UP_TEXT):
            type_id = INPUT_KEY_DOWN if action == _ACTION_KEY_DOWN_TEXT else INPUT_KEY_UP
            vk = key_to_vk(key)
            if vk <= 0:
                # 尝试匹配鼠标按键
                button_name, x, y = _split_pointer_position(key)
                btn = _mouse_button_parse(button_name)
                if btn is not None:
                    type_id = INPUT_MOUSE_BUTTON_DOWN if action == _ACTION_KEY_DOWN_TEXT else INPUT_MOUSE_BUTTON_UP
                    has_position = x is not None and y is not None
                    event = {
                        "type": int(type_id),
                        "flags": INPUT_FLAG_ABSOLUTE if has_position else 0,
                        "delay_us": int(delay_us),
                        "x": int(x or 0),
                        "y": int(y or 0),
                        "data": int(btn),
                        "vk_code": 0,
                        "scan_code": 0,
                    }
                    if has_position and pointer_context:
                        event.update(pointer_context)
                    return event
                return None
            return {
                "type": int(type_id),
                "flags": 0,
                "delay_us": int(delay_us),
                "x": 0,
                "y": 0,
                "data": 0,
                "vk_code": int(vk),
                "scan_code": 0,
            }
        if action == _ACTION_WHEEL or action == _ACTION_HWHEEL:
            type_id = INPUT_MOUSE_HWHEEL if action == _ACTION_HWHEEL else INPUT_MOUSE_WHEEL
            # key 形如 "Delta 120" 或 "120"
            stripped = key.strip()
            m = re.match(r"(?:Delta\s*)?(-?\d+)", stripped, re.IGNORECASE)
            if not m:
                return None
            try:
                delta = int(m.group(1))
            except ValueError:
                return None
            return {
                "type": int(type_id),
                "flags": 0,
                "delay_us": int(delay_us),
                "x": 0,
                "y": 0,
                "data": int(delta),
                "vk_code": 0,
                "scan_code": 0,
            }
        return None

    def get_shortcut(self) -> ShortcutItem:
        if hasattr(self, "recorder"):
            if self.recorder.is_recording():
                self.recorder.stop()
            # 解析失败时直接把错误抛给上层（_on_ok），由调用方决定如何提示用户。
            # 之前静默回退到 recorder.get_events() 会让“编辑既有宏”场景在文本
            # 损坏时被清空，因为此时 backend 是空的新建实例。
            events = self._parse_event_text(self.event_list.get_text())
        self.shortcut.macro_events = events
        self.shortcut.macro_speed = 2.0 if self.double_speed_cb.isChecked() else 1.0
        self.shortcut.macro_hide_while_recording = bool(self.hide_while_recording_cb.isChecked())
        self.shortcut.name = self.name_edit.text().strip()[:6]
        self.shortcut.type = ShortcutType.MACRO
        self.shortcut.trigger_mode = "after_close" if self.trigger_after_close_rb.isChecked() else "immediate"
        self.shortcut.icon_path = self._custom_icon_path
        self.shortcut.icon_invert_light = self.invert_light_cb.isChecked()
        self.shortcut.icon_invert_dark = self.invert_dark_cb.isChecked()
        return self.shortcut
