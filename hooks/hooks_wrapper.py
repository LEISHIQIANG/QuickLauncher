"""
C++ DLL钩子的Python封装
使用ctypes调用hooks.dll
"""

import ctypes
import hashlib
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime

from runtime_paths import app_root

# 回调函数类型
MOUSE_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int)
KEYBOARD_CALLBACK = ctypes.CFUNCTYPE(None)
HOTKEY_CAPTURE_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int, ctypes.c_int)
PROTECTED_CHORD_CAPTURE_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int, ctypes.c_int)
logger = logging.getLogger(__name__)

INPUT_MOUSE_MOVE = 1
INPUT_MOUSE_BUTTON_DOWN = 2
INPUT_MOUSE_BUTTON_UP = 3
INPUT_MOUSE_WHEEL = 4
INPUT_MOUSE_HWHEEL = 5
INPUT_KEY_DOWN = 6
INPUT_KEY_UP = 7
INPUT_UNICODE_DOWN = 8
INPUT_UNICODE_UP = 9

INPUT_FLAG_EXTENDED = 0x0001
INPUT_FLAG_INJECTED = 0x0002
INPUT_FLAG_LOWER_IL_INJECTED = 0x0004
INPUT_FLAG_OWN_PLAYBACK = 0x0008
INPUT_FLAG_SYSTEM_KEY = 0x0010
INPUT_FLAG_REPEAT = 0x0020
INPUT_FLAG_ABSOLUTE = 0x0040

CAPTURE_MOUSE_MOVE = 0x0001
CAPTURE_MOUSE_BUTTON = 0x0002
CAPTURE_MOUSE_WHEEL = 0x0004
CAPTURE_KEYBOARD = 0x0008
CAPTURE_ALL_PHYSICAL = 0x000F
CAPTURE_INCLUDE_INJECTED = 0x0100
CAPTURE_INCLUDE_OWN_PLAYBACK = 0x0200
CAPTURE_COALESCE_MOUSE_MOVE = 0x0400

CHORD_CAPTURE_KEYBOARD = 0x0001
CHORD_CAPTURE_MOUSE_BUTTON = 0x0002
CHORD_CAPTURE_INCLUDE_INJECTED = 0x0100

PLAYBACK_NO_TIMING = 0x0001
PLAYBACK_KEEP_PRESSED_ON_CANCEL = 0x0002
_POINTER_CONTEXT_KEYS = (
    "screen_index",
    "screen_left",
    "screen_top",
    "screen_width",
    "screen_height",
    "screen_ratio_x",
    "screen_ratio_y",
    "virtual_left",
    "virtual_top",
    "virtual_width",
    "virtual_height",
)


class HooksRuntimeStats(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("version", ctypes.c_uint),
        ("health_flags", ctypes.c_uint),
        ("callback_queue_depth", ctypes.c_uint),
        ("low_level_mouse_events", ctypes.c_uint64),
        ("raw_mouse_events", ctypes.c_uint64),
        ("raw_fallback_triggers", ctypes.c_uint64),
        ("injected_mouse_events_ignored", ctypes.c_uint64),
        ("low_level_keyboard_events", ctypes.c_uint64),
        ("raw_keyboard_events", ctypes.c_uint64),
        ("injected_keyboard_events_ignored", ctypes.c_uint64),
        ("callback_queue_dropped", ctypes.c_uint64),
        ("callback_exceptions", ctypes.c_uint64),
        ("mouse_last_event_tick", ctypes.c_uint64),
        ("keyboard_last_event_tick", ctypes.c_uint64),
    ]


class HookInputEvent(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("type", ctypes.c_uint),
        ("flags", ctypes.c_uint),
        ("reserved", ctypes.c_uint),
        ("timestamp_us", ctypes.c_uint64),
        ("sequence", ctypes.c_uint64),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("data", ctypes.c_int),
        ("vk_code", ctypes.c_uint),
        ("scan_code", ctypes.c_uint),
        ("extra_info", ctypes.c_uint64),
    ]


class HookMacroEvent(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("type", ctypes.c_uint),
        ("flags", ctypes.c_uint),
        ("delay_us", ctypes.c_uint),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("data", ctypes.c_int),
        ("vk_code", ctypes.c_uint),
        ("scan_code", ctypes.c_uint),
    ]


class HookMacroStatus(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("active", ctypes.c_uint),
        ("cancel_requested", ctypes.c_uint),
        ("last_error", ctypes.c_uint),
        ("total_events", ctypes.c_uint64),
        ("completed_events", ctypes.c_uint64),
        ("captured_events", ctypes.c_uint64),
        ("capture_dropped", ctypes.c_uint64),
        ("playback_started_tick", ctypes.c_uint64),
        ("playback_finished_tick", ctypes.c_uint64),
    ]


INPUT_EVENT_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.POINTER(HookInputEvent))


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def _virtual_screen_rect() -> dict:
    if os.name != "nt":
        return {"left": 0, "top": 0, "width": 0, "height": 0}
    user32 = ctypes.windll.user32
    return {
        "left": int(user32.GetSystemMetrics(76)),  # SM_XVIRTUALSCREEN
        "top": int(user32.GetSystemMetrics(77)),  # SM_YVIRTUALSCREEN
        "width": max(1, int(user32.GetSystemMetrics(78))),  # SM_CXVIRTUALSCREEN
        "height": max(1, int(user32.GetSystemMetrics(79))),  # SM_CYVIRTUALSCREEN
    }


def _monitor_rects() -> list[dict]:
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    rects: list[dict] = []
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(_RECT),
        ctypes.c_void_p,
    )
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONITORINFO)]
    user32.GetMonitorInfoW.restype = ctypes.c_bool
    user32.EnumDisplayMonitors.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        callback_type,
        ctypes.c_void_p,
    ]
    user32.EnumDisplayMonitors.restype = ctypes.c_bool

    def _enum_proc(hmonitor, _hdc, _rect, _lparam):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            rect = info.rcMonitor
            rects.append(
                {
                    "left": int(rect.left),
                    "top": int(rect.top),
                    "width": max(1, int(rect.right - rect.left)),
                    "height": max(1, int(rect.bottom - rect.top)),
                    "primary": bool(info.dwFlags & 1),
                }
            )
        return True

    enum_proc = callback_type(_enum_proc)
    user32.EnumDisplayMonitors(None, None, enum_proc, 0)
    return sorted(rects, key=lambda item: (not item.get("primary", False), item["left"], item["top"]))


def _monitor_for_point(x: int, y: int, rects: list[dict]) -> tuple[int, dict] | tuple[None, None]:
    for index, rect in enumerate(rects):
        if rect["left"] <= x < rect["left"] + rect["width"] and rect["top"] <= y < rect["top"] + rect["height"]:
            return index, rect
    return (0, rects[0]) if rects else (None, None)


def enrich_pointer_context(event: dict) -> dict:
    """Attach monitor-relative coordinates for resolution/DPI-resilient playback."""
    event = dict(event)
    if int(event.get("flags", 0)) & INPUT_FLAG_ABSOLUTE == 0:
        return event
    event_type = int(event.get("type", 0))
    if event_type not in (
        INPUT_MOUSE_MOVE,
        INPUT_MOUSE_BUTTON_DOWN,
        INPUT_MOUSE_BUTTON_UP,
        INPUT_MOUSE_WHEEL,
        INPUT_MOUSE_HWHEEL,
    ):
        return event

    x = int(event.get("x", 0))
    y = int(event.get("y", 0))
    rects = _monitor_rects()
    screen_index, screen = _monitor_for_point(x, y, rects)
    if screen is None:
        return event

    virtual = _virtual_screen_rect()
    width = max(1, int(screen["width"]))
    height = max(1, int(screen["height"]))
    event.update(
        {
            "screen_index": int(screen_index or 0),
            "screen_left": int(screen["left"]),
            "screen_top": int(screen["top"]),
            "screen_width": width,
            "screen_height": height,
            "screen_ratio_x": max(0.0, min(1.0, (x - int(screen["left"])) / max(1, width - 1))),
            "screen_ratio_y": max(0.0, min(1.0, (y - int(screen["top"])) / max(1, height - 1))),
            "virtual_left": int(virtual["left"]),
            "virtual_top": int(virtual["top"]),
            "virtual_width": int(virtual["width"]),
            "virtual_height": int(virtual["height"]),
        }
    )
    return event


def _remap_pointer_context(event: dict) -> dict:
    if int(event.get("flags", 0)) & INPUT_FLAG_ABSOLUTE == 0:
        return event
    if "screen_ratio_x" not in event or "screen_ratio_y" not in event:
        return event
    rects = _monitor_rects()
    if not rects:
        return event
    try:
        index = int(event.get("screen_index", 0))
    except (TypeError, ValueError):
        index = 0
    if not 0 <= index < len(rects):
        index = 0
    screen = rects[index]
    ratio_x = max(0.0, min(1.0, float(event.get("screen_ratio_x", 0.0))))
    ratio_y = max(0.0, min(1.0, float(event.get("screen_ratio_y", 0.0))))
    event = dict(event)
    event["x"] = int(round(screen["left"] + ratio_x * max(0, screen["width"] - 1)))
    event["y"] = int(round(screen["top"] + ratio_y * max(0, screen["height"] - 1)))
    return event


class HooksDLL:
    EXPECTED_VERSION = 15
    EXPECTED_DLL_SHA256 = "45babb9f58f180a01cfa21e3c8e59d29d887e61bc3c179b5c3fe1ddec240f72c"
    REQUIRED_EXPORTS = (
        "InstallMouseHook",
        "UninstallMouseHook",
        "SetMousePaused",
        "IsMousePaused",
        "SetAltDoubleClickCallback",
        "InstallKeyboardHook",
        "UninstallKeyboardHook",
        "IsAltHeld",
        "IsCtrlHeld",
        "SetGlobalHotkey",
        "ClearGlobalHotkey",
        "StartHotkeyCapture",
        "StopHotkeyCapture",
        "IsHotkeyCaptureActive",
        "StartProtectedChordCapture",
        "StopProtectedChordCapture",
        "IsProtectedChordCaptureActive",
        "ReleaseAllModifierKeys",
        "AreHooksQuiescent",
    )
    _last_probe = {}  # type: ignore[var-annotated]
    _instance = None
    _instance_lock = threading.Lock()
    _load_attempted = False

    @classmethod
    def reset(cls) -> None:
        """清除加载状态，允许下次 get_instance() 重新尝试加载 DLL。

        适用于 DLL 文件从不可用变为可用的场景（如安装过程中 DLL 部署延迟）。
        """
        with cls._instance_lock:
            if cls._instance is not None:
                try:
                    if not cls._instance.shutdown_hooks():
                        logger.error("hooks.dll reset aborted because native callbacks are still active")
                        return
                except Exception as exc:
                    logger.warning("hooks.dll reset 卸载钩子失败: %s", exc, exc_info=True)
                    return
            cls._instance = None
            cls._load_attempted = False

    @classmethod
    def get_instance(cls, dll_path: str = None) -> "HooksDLL":  # type: ignore[assignment]
        """获取单例实例，避免多次加载DLL导致GC回调问题

        P0 FIX: If a previous load attempt produced a broken instance (dll is None,
        e.g. due to a hardcoded SHA-256 mismatch), create a fresh instance instead
        of returning the broken one forever.  Retiring the old callback refs before
        replacement prevents late native callbacks from jumping into freed memory.
        """
        if cls._instance is not None and cls._instance.dll is not None:
            return cls._instance
        with cls._instance_lock:
            if cls._instance is not None and cls._instance.dll is not None:
                return cls._instance
            if cls._load_attempted and cls._instance is not None:
                if cls._instance.dll is None:
                    # Produce a fresh instance rather than returning a permanently
                    # broken one.  The old instance's callbacks are safe to discard
                    # because its DLL was never loaded (self.dll is None).
                    logger.warning(
                        "hooks.dll previous load attempt produced a broken instance "
                        "(error=%s); creating fresh instance",
                        getattr(cls._instance, "load_error", "unknown"),
                    )
                    cls._instance = cls(dll_path)
                    return cls._instance
                return cls._instance
            cls._load_attempted = True
            cls._instance = cls(dll_path)
            return cls._instance

    def __init__(
        self,
        dll_path: str = None,  # type: ignore[assignment]
        *,
        expected_sha256: str | None = None,
        verify_integrity: bool = False,
    ):
        # P0 FIX: QL_ENFORCE_DLL_INTEGRITY env var allows developers to opt back
        # into strict SHA-256 enforcement for testing DLL integrity.
        if os.environ.get("QL_ENFORCE_DLL_INTEGRITY"):
            verify_integrity = True
        if dll_path is None:
            dll_path = self._default_dll_path()
        dll_path = os.path.abspath(dll_path)
        self.dll_path = dll_path
        self._expected_sha256 = (
            str(expected_sha256).strip().lower()
            if expected_sha256 is not None
            else str(self.EXPECTED_DLL_SHA256 or "").strip().lower()
        )
        self._verify_integrity = bool(verify_integrity)
        self.dll = None
        self.loaded = False
        self.compatible = False
        self.load_error = ""
        self.missing_exports = []  # type: ignore[var-annotated]
        self.version = None
        self.capabilities = 0
        self._has_special_apps = False
        self._has_last_error = False
        self._has_hook_health = False
        self._has_raw_input_status = False
        self._has_hotkey_capture = False
        self._has_protected_chord_capture = False
        self._has_runtime_stats = False
        self._has_input_capture = False
        self._has_macro_playback = False
        self._lifecycle_lock = threading.RLock()
        integrity_error = self._validate_integrity()
        if integrity_error:
            if self._verify_integrity:
                # P0 FIX: SHA-256 mismatch no longer blocks DLL loading by default.
                # The hardcoded hash would break the hook system after every DLL rebuild,
                # silently disabling mouse gestures, keyboard triggers, and global hotkeys.
                # Version + export-based compatibility checks below are sufficient for
                # production use.  SHA-256 verification is an opt-in developer feature
                # (set verify_integrity=True or QL_ENFORCE_DLL_INTEGRITY=1).
                self.load_error = integrity_error
                HooksDLL._last_probe = self.get_diagnostics()
                logger.error("hooks.dll integrity check failed: %s", integrity_error)
                self._init_callback_refs()
                return
            else:
                logger.warning(
                    "hooks.dll SHA-256 mismatch (expected=%s actual=%s); "
                    "continuing with version-based compatibility check only. "
                    "Set QL_ENFORCE_DLL_INTEGRITY=1 to enforce.",
                    self._expected_sha256,
                    _dll_file_info(self.dll_path).get("sha256", "?"),
                )
        try:
            self.dll = ctypes.CDLL(dll_path)
            self.loaded = True
        except Exception as e:
            self.load_error = str(e)
            HooksDLL._last_probe = self.get_diagnostics()
            logger.error("hooks.dll load failed: %s", e)
            self._init_callback_refs()
            return

        self._bind_required_exports()
        self._bind_optional_exports()
        self.compatible = bool(
            self.loaded and not self.missing_exports and (self.version is None or self.version >= self.EXPECTED_VERSION)
        )

        # 保持回调引用防止GC
        self._init_callback_refs()
        HooksDLL._last_probe = self.get_diagnostics()

    def _init_callback_refs(self):
        if not hasattr(self, "_retired_callback_refs"):
            self._retired_callback_refs = deque(maxlen=64)  # type: ignore[var-annotated]
        self._mouse_callback_ref = None
        self._alt_dclick_callback_ref = None
        self._taskbar_dclick_callback_ref = None
        self._keyboard_callback_ref = None
        self._hotkey_callback_ref = None
        self._hotkey_capture_callback_ref = None
        self._hotkey_capture_owner = None
        self._protected_chord_capture_callback_ref = None
        self._protected_chord_capture_owner = None
        self._protected_chord_capture_flags = 0
        self._retire_callback_ref(getattr(self, "_input_event_callback_ref", None))
        self._input_event_callback_ref = None
        self._input_capture_filter_flags = 0
        self._input_capture_owner = None

    def _retire_callback_ref(self, callback_ref) -> None:
        """Keep native callback thunks alive after replacement or timeout.

        Native shutdown has bounded waits so a misbehaving Python callback
        cannot freeze application exit. Retaining old thunks prevents a late
        native return from jumping into freed ctypes memory.
        """
        if callback_ref is not None:
            if not hasattr(self, "_retired_callback_refs"):
                self._retired_callback_refs = deque(maxlen=64)
            self._retired_callback_refs.append(callback_ref)

    def _clear_inactive_capture_owners_locked(self) -> None:
        """Drop stale Python owners after native timeout or auto-completion."""
        if not self._ready():
            return
        captures = (
            (
                "_hotkey_capture_owner",
                "_hotkey_capture_callback_ref",
                "_has_hotkey_capture",
                "IsHotkeyCaptureActive",
            ),
            (
                "_protected_chord_capture_owner",
                "_protected_chord_capture_callback_ref",
                "_has_protected_chord_capture",
                "IsProtectedChordCaptureActive",
            ),
            (
                "_input_capture_owner",
                "_input_event_callback_ref",
                "_has_input_capture",
                "IsInputCaptureActive",
            ),
        )
        for owner_attr, callback_attr, capability_attr, active_func_name in captures:
            if getattr(self, owner_attr, None) is None or not getattr(self, capability_attr, False):
                continue
            try:
                active = bool(getattr(self.dll, active_func_name)())
            except Exception:
                continue
            if active:
                continue
            self._retire_callback_ref(getattr(self, callback_attr, None))
            setattr(self, callback_attr, None)
            setattr(self, owner_attr, None)
            if owner_attr == "_protected_chord_capture_owner":
                self._protected_chord_capture_flags = 0
            elif owner_attr == "_input_capture_owner":
                self._input_capture_filter_flags = 0

    @classmethod
    def _default_dll_path(cls) -> str:
        return str(app_root() / "hooks" / "hooks.dll")

    def _validate_integrity(self) -> str:
        if not self._verify_integrity:
            return ""
        expected = self._expected_sha256
        if not expected:
            return "hooks.dll integrity verification enabled without an expected SHA-256"
        file_info = _dll_file_info(self.dll_path)
        if not file_info["exists"]:
            return ""
        actual = str(file_info["sha256"] or "").strip().lower()
        if actual != expected:
            return f"hooks.dll SHA-256 mismatch: expected {expected}, actual {actual}"
        return ""

    @property
    def expected_sha256(self) -> str:
        return self._expected_sha256

    def verify_integrity(self) -> bool:
        """Recompute and compare the configured hooks.dll SHA-256."""
        if not self._verify_integrity or not self._expected_sha256:
            return False
        file_info = _dll_file_info(self.dll_path)
        return bool(file_info["exists"] and str(file_info["sha256"] or "").strip().lower() == self._expected_sha256)

    def _bind_required_exports(self):
        for name in self.REQUIRED_EXPORTS:
            if not hasattr(self.dll, name):
                self.missing_exports.append(name)

        if self.missing_exports:
            logger.warning("hooks.dll missing exports: %s", self.missing_exports)
            return

        self.dll.InstallMouseHook.argtypes = [MOUSE_CALLBACK]  # type: ignore[union-attr]
        self.dll.InstallMouseHook.restype = ctypes.c_bool  # type: ignore[union-attr]
        self.dll.UninstallMouseHook.argtypes = []  # type: ignore[union-attr]
        self.dll.UninstallMouseHook.restype = None  # type: ignore[union-attr]
        self.dll.SetMousePaused.argtypes = [ctypes.c_bool]  # type: ignore[union-attr]
        self.dll.SetMousePaused.restype = None  # type: ignore[union-attr]
        self.dll.IsMousePaused.argtypes = []  # type: ignore[union-attr]
        self.dll.IsMousePaused.restype = ctypes.c_bool  # type: ignore[union-attr]
        self.dll.SetAltDoubleClickCallback.argtypes = [MOUSE_CALLBACK]  # type: ignore[union-attr]
        self.dll.SetAltDoubleClickCallback.restype = None  # type: ignore[union-attr]

        self.dll.InstallKeyboardHook.argtypes = [KEYBOARD_CALLBACK]  # type: ignore[union-attr]
        self.dll.InstallKeyboardHook.restype = ctypes.c_bool  # type: ignore[union-attr]
        self.dll.UninstallKeyboardHook.argtypes = []  # type: ignore[union-attr]
        self.dll.UninstallKeyboardHook.restype = None  # type: ignore[union-attr]
        self.dll.IsAltHeld.argtypes = []  # type: ignore[union-attr]
        self.dll.IsAltHeld.restype = ctypes.c_bool  # type: ignore[union-attr]
        self.dll.IsCtrlHeld.argtypes = []  # type: ignore[union-attr]
        self.dll.IsCtrlHeld.restype = ctypes.c_bool  # type: ignore[union-attr]
        self.dll.SetGlobalHotkey.argtypes = [ctypes.c_char_p, KEYBOARD_CALLBACK]  # type: ignore[union-attr]
        self.dll.SetGlobalHotkey.restype = ctypes.c_bool  # type: ignore[union-attr]
        self.dll.ClearGlobalHotkey.argtypes = []  # type: ignore[union-attr]
        self.dll.ClearGlobalHotkey.restype = None  # type: ignore[union-attr]
        self.dll.ReleaseAllModifierKeys.argtypes = []  # type: ignore[union-attr]
        self.dll.ReleaseAllModifierKeys.restype = None  # type: ignore[union-attr]
        self.dll.AreHooksQuiescent.argtypes = []  # type: ignore[union-attr]
        self.dll.AreHooksQuiescent.restype = ctypes.c_bool  # type: ignore[union-attr]

    def _bind_optional_exports(self):
        # 特殊应用支持（可选，兼容旧DLL）
        try:
            self.dll.SetSpecialApps.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_int]  # type: ignore[union-attr]
            self.dll.SetSpecialApps.restype = None  # type: ignore[union-attr]
            self.dll.ClearSpecialApps.argtypes = []  # type: ignore[union-attr]
            self.dll.ClearSpecialApps.restype = None  # type: ignore[union-attr]
            self._has_special_apps = True
        except AttributeError:
            self._has_special_apps = False

        try:
            self.dll.GetHooksVersion.argtypes = []  # type: ignore[union-attr]
            self.dll.GetHooksVersion.restype = ctypes.c_int  # type: ignore[union-attr]
            self.version = int(self.dll.GetHooksVersion())  # type: ignore[union-attr]
        except AttributeError:
            self.version = None

        try:
            self.dll.GetHooksCapabilities.argtypes = []  # type: ignore[union-attr]
            self.dll.GetHooksCapabilities.restype = ctypes.c_uint  # type: ignore[union-attr]
            self.capabilities = int(self.dll.GetHooksCapabilities())  # type: ignore[union-attr]
        except AttributeError:
            self.capabilities = 0

        try:
            self.dll.GetLastHookError.argtypes = []  # type: ignore[union-attr]
            self.dll.GetLastHookError.restype = ctypes.c_ulong  # type: ignore[union-attr]
            self._has_last_error = True
        except AttributeError:
            self._has_last_error = False

        try:
            self.dll.IsMouseHookInstalled.argtypes = []  # type: ignore[union-attr]
            self.dll.IsMouseHookInstalled.restype = ctypes.c_bool  # type: ignore[union-attr]
            self.dll.IsKeyboardHookInstalled.argtypes = []  # type: ignore[union-attr]
            self.dll.IsKeyboardHookInstalled.restype = ctypes.c_bool  # type: ignore[union-attr]
            self._has_hook_health = True
        except AttributeError:
            self._has_hook_health = False

        try:
            self.dll.IsRawInputFallbackActive.argtypes = []  # type: ignore[union-attr]
            self.dll.IsRawInputFallbackActive.restype = ctypes.c_bool  # type: ignore[union-attr]
            self._has_raw_input_status = True
        except AttributeError:
            self._has_raw_input_status = False

        try:
            self.dll.StartHotkeyCapture.argtypes = [HOTKEY_CAPTURE_CALLBACK, ctypes.c_int]  # type: ignore[union-attr]
            self.dll.StartHotkeyCapture.restype = ctypes.c_bool  # type: ignore[union-attr]
            self.dll.StopHotkeyCapture.argtypes = []  # type: ignore[union-attr]
            self.dll.StopHotkeyCapture.restype = None  # type: ignore[union-attr]
            self.dll.IsHotkeyCaptureActive.argtypes = []  # type: ignore[union-attr]
            self.dll.IsHotkeyCaptureActive.restype = ctypes.c_bool  # type: ignore[union-attr]
            self._has_hotkey_capture = True
        except AttributeError:
            self._has_hotkey_capture = False

        try:
            self.dll.StartProtectedChordCapture.argtypes = [  # type: ignore[union-attr]
                PROTECTED_CHORD_CAPTURE_CALLBACK,
                ctypes.c_uint,
                ctypes.c_int,
            ]
            self.dll.StartProtectedChordCapture.restype = ctypes.c_bool  # type: ignore[union-attr]
            self.dll.StopProtectedChordCapture.argtypes = []  # type: ignore[union-attr]
            self.dll.StopProtectedChordCapture.restype = None  # type: ignore[union-attr]
            self.dll.IsProtectedChordCaptureActive.argtypes = []  # type: ignore[union-attr]
            self.dll.IsProtectedChordCaptureActive.restype = ctypes.c_bool  # type: ignore[union-attr]
            self._has_protected_chord_capture = True
        except AttributeError:
            self._has_protected_chord_capture = False

        try:
            self.dll.GetHooksRuntimeStats.argtypes = [ctypes.POINTER(HooksRuntimeStats), ctypes.c_uint]  # type: ignore[union-attr]
            self.dll.GetHooksRuntimeStats.restype = ctypes.c_bool  # type: ignore[union-attr]
            self.dll.ResetHooksRuntimeStats.argtypes = []  # type: ignore[union-attr]
            self.dll.ResetHooksRuntimeStats.restype = None  # type: ignore[union-attr]
            self._has_runtime_stats = True
        except AttributeError:
            self._has_runtime_stats = False

        try:
            self.dll.StartInputCapture.argtypes = [INPUT_EVENT_CALLBACK, ctypes.c_uint]  # type: ignore[union-attr]
            self.dll.StartInputCapture.restype = ctypes.c_bool  # type: ignore[union-attr]
            self.dll.StopInputCapture.argtypes = []  # type: ignore[union-attr]
            self.dll.StopInputCapture.restype = None  # type: ignore[union-attr]
            self.dll.IsInputCaptureActive.argtypes = []  # type: ignore[union-attr]
            self.dll.IsInputCaptureActive.restype = ctypes.c_bool  # type: ignore[union-attr]
            self._has_input_capture = True
        except AttributeError:
            self._has_input_capture = False

        try:
            self.dll.PlayMacroEvents.argtypes = [ctypes.POINTER(HookMacroEvent), ctypes.c_uint, ctypes.c_uint]  # type: ignore[union-attr]
            self.dll.PlayMacroEvents.restype = ctypes.c_bool  # type: ignore[union-attr]
            self.dll.CancelMacroPlayback.argtypes = []  # type: ignore[union-attr]
            self.dll.CancelMacroPlayback.restype = None  # type: ignore[union-attr]
            self.dll.IsMacroPlaybackActive.argtypes = []  # type: ignore[union-attr]
            self.dll.IsMacroPlaybackActive.restype = ctypes.c_bool  # type: ignore[union-attr]
            self.dll.WaitForMacroPlayback.argtypes = [ctypes.c_uint]  # type: ignore[union-attr]
            self.dll.WaitForMacroPlayback.restype = ctypes.c_bool  # type: ignore[union-attr]
            self.dll.GetMacroStatus.argtypes = [ctypes.POINTER(HookMacroStatus), ctypes.c_uint]  # type: ignore[union-attr]
            self.dll.GetMacroStatus.restype = ctypes.c_bool  # type: ignore[union-attr]
            self.dll.ReleaseMacroPressedInputs.argtypes = []  # type: ignore[union-attr]
            self.dll.ReleaseMacroPressedInputs.restype = None  # type: ignore[union-attr]
            self._has_macro_playback = True
        except AttributeError:
            self._has_macro_playback = False

        # 触发配置支持（可选）
        try:
            self.dll.SetTriggerConfig.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]  # type: ignore[union-attr]
            self.dll.SetTriggerConfig.restype = None  # type: ignore[union-attr]
            self._has_trigger_config = True
        except AttributeError:
            self._has_trigger_config = False

        # 扩展触发配置支持（可选）
        try:
            self.dll.SetTriggerConfigEx.argtypes = [  # type: ignore[union-attr]
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
            ]
            self.dll.SetTriggerConfigEx.restype = None  # type: ignore[union-attr]
            self._has_trigger_config_ex = True
        except AttributeError:
            self._has_trigger_config_ex = False

        # 触发热键注册状态查询（可选）
        try:
            self.dll.IsNormalTriggerHotkeyRegistered.argtypes = []  # type: ignore[union-attr]
            self.dll.IsNormalTriggerHotkeyRegistered.restype = ctypes.c_bool  # type: ignore[union-attr]
            self.dll.IsSpecialTriggerHotkeyRegistered.argtypes = []  # type: ignore[union-attr]
            self.dll.IsSpecialTriggerHotkeyRegistered.restype = ctypes.c_bool  # type: ignore[union-attr]
            self._has_trigger_hotkey_status = True
        except AttributeError:
            self._has_trigger_hotkey_status = False

        # 任务栏触发支持（可选）
        try:
            self.dll.SetTaskbarDoubleClickCallback.argtypes = [MOUSE_CALLBACK]  # type: ignore[union-attr]
            self.dll.SetTaskbarDoubleClickCallback.restype = None  # type: ignore[union-attr]
            self.dll.SetTaskbarTriggerEnabled.argtypes = [ctypes.c_bool, ctypes.c_bool]  # type: ignore[union-attr]
            self.dll.SetTaskbarTriggerEnabled.restype = None  # type: ignore[union-attr]
            try:
                self.dll.SetTaskbarTriggerConfig.argtypes = [ctypes.c_bool, ctypes.c_bool, ctypes.c_int]  # type: ignore[union-attr]
                self.dll.SetTaskbarTriggerConfig.restype = None  # type: ignore[union-attr]
                self._has_taskbar_trigger_config = True
            except AttributeError:
                self._has_taskbar_trigger_config = False
            self.dll.IsTaskbarTriggerAvailable.argtypes = []  # type: ignore[union-attr]
            self.dll.IsTaskbarTriggerAvailable.restype = ctypes.c_bool  # type: ignore[union-attr]
            self._has_taskbar_trigger = True
        except AttributeError:
            self._has_taskbar_trigger = False
            self._has_taskbar_trigger_config = False

    def get_last_hook_error(self) -> int:
        if self.dll is None or not getattr(self, "_has_last_error", False):
            return 0
        try:
            return int(self.dll.GetLastHookError())
        except Exception:
            return 0

    def is_mouse_hook_installed(self) -> bool:
        if self.dll is None or not getattr(self, "_has_hook_health", False):
            return False
        try:
            return bool(self.dll.IsMouseHookInstalled())
        except Exception as exc:
            logger.debug("hooks.dll IsMouseHookInstalled failed: %s", exc, exc_info=True)
            return False

    def is_keyboard_hook_installed(self) -> bool:
        if self.dll is None or not getattr(self, "_has_hook_health", False):
            return False
        try:
            return bool(self.dll.IsKeyboardHookInstalled())
        except Exception as exc:
            logger.debug("hooks.dll IsKeyboardHookInstalled failed: %s", exc, exc_info=True)
            return False

    def is_raw_input_fallback_active(self) -> bool:
        if self.dll is None or not getattr(self, "_has_raw_input_status", False):
            return False
        try:
            return bool(self.dll.IsRawInputFallbackActive())
        except Exception as exc:
            logger.debug("hooks.dll IsRawInputFallbackActive failed: %s", exc, exc_info=True)
            return False

    def get_runtime_stats(self) -> dict:
        if self.dll is None or not getattr(self, "_has_runtime_stats", False):
            return {}
        try:
            stats = HooksRuntimeStats()
            stats.size = ctypes.sizeof(HooksRuntimeStats)
            if not self.dll.GetHooksRuntimeStats(ctypes.byref(stats), stats.size):
                return {}
            return {name: int(getattr(stats, name)) for name, _ctype in HooksRuntimeStats._fields_}  # type: ignore[misc]
        except Exception as exc:
            logger.debug("hooks.dll GetHooksRuntimeStats failed: %s", exc, exc_info=True)
            return {}

    def reset_runtime_stats(self) -> None:
        if self.dll is not None and getattr(self, "_has_runtime_stats", False):
            try:
                self.dll.ResetHooksRuntimeStats()
            except Exception as exc:
                logger.debug("hooks.dll ResetHooksRuntimeStats failed: %s", exc, exc_info=True)

    def get_diagnostics(self) -> dict:
        compatible = bool(self.loaded and not self.missing_exports)
        version_ok = self.version is None or self.version >= self.EXPECTED_VERSION
        summary = "hooks.dll 可用" if compatible and version_ok else "hooks.dll 需要更新或不可用"
        file_info = _dll_file_info(self.dll_path)
        return {
            "path": self.dll_path,
            "path_resolved": file_info["path_resolved"],
            "exists": file_info["exists"],
            "size_bytes": file_info["size_bytes"],
            "mtime": file_info["mtime"],
            "sha256": file_info["sha256"],
            "loaded": self.loaded,
            "compatible": compatible and version_ok,
            "version": self.version,
            "expected_version": self.EXPECTED_VERSION,
            "capabilities": self.capabilities,
            "has_hook_health": bool(getattr(self, "_has_hook_health", False)),
            "has_raw_input_status": bool(getattr(self, "_has_raw_input_status", False)),
            "has_hotkey_capture": bool(getattr(self, "_has_hotkey_capture", False)),
            "has_protected_chord_capture": bool(getattr(self, "_has_protected_chord_capture", False)),
            "has_runtime_stats": bool(getattr(self, "_has_runtime_stats", False)),
            "has_input_capture": bool(getattr(self, "_has_input_capture", False)),
            "has_macro_playback": bool(getattr(self, "_has_macro_playback", False)),
            "mouse_hook_installed": self.is_mouse_hook_installed(),
            "raw_input_fallback_active": self.is_raw_input_fallback_active(),
            "keyboard_hook_installed": self.is_keyboard_hook_installed(),
            "runtime_stats": self.get_runtime_stats(),
            "missing_exports": list(self.missing_exports),
            "load_error": self.load_error,
            "last_hook_error": self.get_last_hook_error(),
            "summary": summary,
        }

    @classmethod
    def probe_default(cls) -> dict:
        """Quick diagnostic probe that always disables SHA integrity enforcement."""
        try:
            return cls(verify_integrity=False).get_diagnostics()
        except Exception as e:
            return {"loaded": False, "compatible": False, "summary": "hooks.dll 检测失败", "load_error": str(e)}

    def _ready(self) -> bool:
        return bool(self.loaded and self.compatible and self.dll is not None)

    def is_ready(self) -> bool:
        """Return whether the native DLL is loaded and API-compatible."""
        with self._lifecycle_lock:
            return self._ready()

    def are_hooks_quiescent(self) -> bool:
        with self._lifecycle_lock:
            if self.dll is None:
                return True
            try:
                return bool(self.dll.AreHooksQuiescent())
            except Exception as exc:
                logger.debug("hooks.dll AreHooksQuiescent failed: %s", exc, exc_info=True)
                return False

    def shutdown_hooks(self) -> bool:
        """Uninstall native hooks before dropping the DLL reference."""
        lifecycle_lock = getattr(self, "_lifecycle_lock", None)
        if lifecycle_lock is None:
            lifecycle_lock = threading.RLock()
            self._lifecycle_lock = lifecycle_lock
        with lifecycle_lock:
            dll = self.dll
            if dll is None:
                return True

            try:
                self.stop_input_capture(force=True)
            except Exception as exc:
                logger.debug("hooks.dll StopInputCapture failed during shutdown: %s", exc, exc_info=True)

            for func_name in ("CancelMacroPlayback",):
                try:
                    func = getattr(dll, func_name, None)
                    if func is not None:
                        func()
                except Exception as exc:
                    logger.debug("hooks.dll %s failed during shutdown: %s", func_name, exc, exc_info=True)

            try:
                wait_for_playback = getattr(dll, "WaitForMacroPlayback", None)
                if wait_for_playback is not None:
                    wait_for_playback(2000)
            except Exception as exc:
                logger.debug("hooks.dll WaitForMacroPlayback failed during shutdown: %s", exc, exc_info=True)

            for func_name in (
                "ReleaseMacroPressedInputs",
                "StopProtectedChordCapture",
                "StopHotkeyCapture",
                "UninstallMouseHook",
                "UninstallKeyboardHook",
                "ClearGlobalHotkey",
            ):
                try:
                    func = getattr(dll, func_name, None)
                    if func is not None:
                        func()
                except Exception as exc:
                    logger.debug("hooks.dll %s failed during shutdown: %s", func_name, exc, exc_info=True)

            deadline = time.monotonic() + 2.5
            while time.monotonic() < deadline:
                try:
                    if bool(dll.AreHooksQuiescent()):
                        break
                except Exception:
                    break
                time.sleep(0.02)
            try:
                quiescent = bool(dll.AreHooksQuiescent())
            except Exception:
                quiescent = False
            if not quiescent:
                logger.error(
                    "hooks.dll shutdown timed out; retaining DLL and callback references to prevent a native crash"
                )
                return False

            for attr_name in (
                "_mouse_callback_ref",
                "_alt_dclick_callback_ref",
                "_taskbar_dclick_callback_ref",
                "_keyboard_callback_ref",
                "_hotkey_callback_ref",
                "_hotkey_capture_callback_ref",
                "_protected_chord_capture_callback_ref",
                "_input_event_callback_ref",
            ):
                self._retire_callback_ref(getattr(self, attr_name, None))
                setattr(self, attr_name, None)
            self.dll = None
            self.loaded = False
            self.compatible = False
            self._init_callback_refs()
            return True

    def install_mouse_hook(self, callback: Callable[[int, int], None]) -> bool:
        """安装鼠标钩子"""
        with self._lifecycle_lock:
            if not self._ready():
                return False
            callback_ref = MOUSE_CALLBACK(callback)
            previous_ref = self._mouse_callback_ref
            ok = bool(self.dll.InstallMouseHook(callback_ref))  # type: ignore[union-attr]
            if ok:
                self._retire_callback_ref(previous_ref)
                self._mouse_callback_ref = callback_ref
            if not ok:
                logger.warning("InstallMouseHook failed, last_error=%s", self.get_last_hook_error())
            return ok

    def uninstall_mouse_hook(self):
        """卸载鼠标钩子"""
        mouse_filters = CAPTURE_MOUSE_MOVE | CAPTURE_MOUSE_BUTTON | CAPTURE_MOUSE_WHEEL
        if getattr(self, "_input_capture_filter_flags", 0) & mouse_filters:
            self.stop_input_capture(force=True)
        with self._lifecycle_lock:
            if self._ready():
                self.dll.UninstallMouseHook()  # type: ignore[union-attr]
            self._retire_callback_ref(self._mouse_callback_ref)
            self._retire_callback_ref(self._alt_dclick_callback_ref)
            self._retire_callback_ref(self._taskbar_dclick_callback_ref)
            self._mouse_callback_ref = None
            self._alt_dclick_callback_ref = None
            self._taskbar_dclick_callback_ref = None

    def set_mouse_paused(self, paused: bool):
        """设置鼠标钩子暂停状态"""
        with self._lifecycle_lock:
            if self._ready():
                self.dll.SetMousePaused(paused)  # type: ignore[union-attr]

    def is_mouse_paused(self) -> bool:
        """获取鼠标钩子暂停状态"""
        if not self._ready():
            return False
        return self.dll.IsMousePaused()  # type: ignore[no-any-return, union-attr]

    def set_alt_double_click_callback(self, callback: Callable[[int, int], None] | None):
        """设置Alt+左键双击回调"""
        with self._lifecycle_lock:
            previous_ref = self._alt_dclick_callback_ref
            if callback:
                callback_ref = MOUSE_CALLBACK(callback)
                if self._ready():
                    self.dll.SetAltDoubleClickCallback(callback_ref)  # type: ignore[union-attr]
                self._alt_dclick_callback_ref = callback_ref
            else:
                if self._ready():
                    self.dll.SetAltDoubleClickCallback(None)  # type: ignore[union-attr]
                self._alt_dclick_callback_ref = None
            self._retire_callback_ref(previous_ref)

    def install_keyboard_hook(self, alt_double_tap_callback: Callable[[], None] | None = None) -> bool:
        """安装键盘钩子"""
        with self._lifecycle_lock:
            if alt_double_tap_callback:
                callback_ref = KEYBOARD_CALLBACK(alt_double_tap_callback)
            else:
                callback_ref = KEYBOARD_CALLBACK(lambda: None)
            if not self._ready():
                return False
            previous_ref = self._keyboard_callback_ref
            ok = bool(self.dll.InstallKeyboardHook(callback_ref))  # type: ignore[union-attr]
            if ok:
                self._retire_callback_ref(previous_ref)
                self._keyboard_callback_ref = callback_ref
            if not ok:
                logger.warning("InstallKeyboardHook failed, last_error=%s", self.get_last_hook_error())
            return ok

    def rearm_keyboard_hook_for_capture(self) -> tuple[bool, bool]:
        """Reinstall the low-level keyboard hook before protected recording.

        Windows may silently detach a low-level hook while its thread and
        handle still appear active. Reinstalling here gives both recorder
        widgets the same known-good keyboard input path.

        Returns ``(success, installed_temporarily)``.
        """
        with self._lifecycle_lock:
            if not self._ready():
                logger.debug("键盘捕获重装被拒绝: hooks.dll 未就绪")
                return False, False

            previous_ref = self._keyboard_callback_ref
            installed_temporarily = previous_ref is None
            callback_ref = previous_ref or KEYBOARD_CALLBACK(lambda: None)
            logger.debug(
                "键盘捕获重装开始: installed=%s temporary=%s callback_ref=%s",
                self.is_keyboard_hook_installed(),
                installed_temporarily,
                hex(id(callback_ref)),
            )

            try:
                self.dll.UninstallKeyboardHook()  # type: ignore[union-attr]
                ok = bool(self.dll.InstallKeyboardHook(callback_ref))  # type: ignore[union-attr]
            except Exception as exc:
                logger.warning("重新装载录制键盘钩子失败: %s", exc, exc_info=True)
                return False, installed_temporarily

            if not ok:
                logger.warning("重新装载录制键盘钩子失败, last_error=%s", self.get_last_hook_error())
                return False, installed_temporarily

            if installed_temporarily:
                self._keyboard_callback_ref = callback_ref
            logger.debug(
                "键盘捕获重装完成: ok=%s installed=%s last_error=%s",
                ok,
                self.is_keyboard_hook_installed(),
                self.get_last_hook_error(),
            )
            return True, installed_temporarily

    def uninstall_keyboard_hook(self):
        """卸载键盘钩子"""
        if getattr(self, "_input_capture_filter_flags", 0) & CAPTURE_KEYBOARD:
            self.stop_input_capture(force=True)
        with self._lifecycle_lock:
            if self._ready():
                self.dll.UninstallKeyboardHook()  # type: ignore[union-attr]
            self._retire_callback_ref(self._keyboard_callback_ref)
            self._keyboard_callback_ref = None

    def is_alt_held(self) -> bool:
        """获取Alt键按住状态"""
        if not self._ready():
            return False
        return self.dll.IsAltHeld()  # type: ignore[no-any-return, union-attr]

    def is_ctrl_held(self) -> bool:
        """获取Ctrl键按住状态"""
        if not self._ready():
            return False
        return self.dll.IsCtrlHeld()  # type: ignore[no-any-return, union-attr]

    def set_hotkey(self, hotkey_str: str, callback: Callable[[], None]):
        """设置全局热键"""
        with self._lifecycle_lock:
            if not self._ready():
                return False
            callback_ref = KEYBOARD_CALLBACK(callback)
            ok = bool(self.dll.SetGlobalHotkey(hotkey_str.encode("utf-8"), callback_ref))  # type: ignore[union-attr]
            if ok:
                self._retire_callback_ref(self._hotkey_callback_ref)
                self._hotkey_callback_ref = callback_ref
            return ok

    def clear_hotkey(self):
        """清除全局热键"""
        with self._lifecycle_lock:
            if self._ready():
                self.dll.ClearGlobalHotkey()  # type: ignore[union-attr]
            self._retire_callback_ref(self._hotkey_callback_ref)
            self._hotkey_callback_ref = None

    def start_hotkey_capture(
        self,
        callback: Callable[[int, int, int], None],
        timeout_ms: int = 10000,
        *,
        owner=None,
    ) -> bool:
        """启动受保护快捷键录制，录制期间 DLL 会吞掉所有键盘事件。"""
        with self._lifecycle_lock:
            if not self._ready() or not getattr(self, "_has_hotkey_capture", False) or not callback:  # type: ignore[truthy-function]
                return False
            self._clear_inactive_capture_owners_locked()
            capture_owner = owner if owner is not None else self
            if (
                self._hotkey_capture_owner is not None
                or self._protected_chord_capture_owner is not None
                or self._input_capture_owner is not None
            ):
                logger.warning("StartHotkeyCapture rejected because another owner is recording")
                return False
            callback_ref = HOTKEY_CAPTURE_CALLBACK(callback)
            ok = bool(self.dll.StartHotkeyCapture(callback_ref, int(timeout_ms)))  # type: ignore[union-attr]
            if ok:
                self._retire_callback_ref(self._hotkey_capture_callback_ref)
                self._hotkey_capture_callback_ref = callback_ref
                self._hotkey_capture_owner = capture_owner
            return ok

    def stop_hotkey_capture(self, *, owner=None, force: bool = False) -> bool:
        """停止受保护快捷键录制。"""
        with self._lifecycle_lock:
            requested_owner = owner if owner is not None else self
            if (
                not force
                and self._hotkey_capture_owner is not None
                and self._hotkey_capture_owner is not requested_owner
            ):
                logger.warning("StopHotkeyCapture rejected for non-owner")
                return False
            if self._ready() and getattr(self, "_has_hotkey_capture", False):
                self.dll.StopHotkeyCapture()  # type: ignore[union-attr]
            self._retire_callback_ref(self._hotkey_capture_callback_ref)
            self._hotkey_capture_callback_ref = None
            self._hotkey_capture_owner = None
            return True

    def hotkey_capture_owned_by(self, owner) -> bool:
        with self._lifecycle_lock:
            return self._hotkey_capture_owner is owner

    def is_hotkey_capture_active(self) -> bool:
        """返回 DLL 当前是否处于快捷键录制模式。"""
        with self._lifecycle_lock:
            if not self._ready() or not getattr(self, "_has_hotkey_capture", False):
                return False
            try:
                active = bool(self.dll.IsHotkeyCaptureActive())  # type: ignore[union-attr]
            except Exception:
                return False
            if not active:
                self._clear_inactive_capture_owners_locked()
            return active

    def start_protected_chord_capture(
        self,
        callback: Callable[[int, int, int], None],
        *,
        keyboard: bool = True,
        mouse_buttons: bool = False,
        include_injected: bool = False,
        timeout_ms: int = 10000,
        owner=None,
    ) -> bool:
        """Capture a physical chord while swallowing its keyboard/mouse events."""
        with self._lifecycle_lock:
            if not self._ready() or not self._has_protected_chord_capture or not callback:  # type: ignore[truthy-function]
                return False
            self._clear_inactive_capture_owners_locked()
            if (
                self._protected_chord_capture_owner is not None
                or self._hotkey_capture_owner is not None
                or self._input_capture_owner is not None
            ):
                logger.warning("StartProtectedChordCapture rejected because another owner is recording")
                return False
            flags = 0
            if keyboard:
                flags |= CHORD_CAPTURE_KEYBOARD
            if mouse_buttons:
                flags |= CHORD_CAPTURE_MOUSE_BUTTON
            if include_injected:
                flags |= CHORD_CAPTURE_INCLUDE_INJECTED
            if not flags:
                return False
            callback_ref = PROTECTED_CHORD_CAPTURE_CALLBACK(callback)
            capture_owner = owner if owner is not None else self
            logger.debug(
                "受保护组合捕获开始: owner=%s flags=%s keyboard_installed=%s mouse_installed=%s",
                hex(id(capture_owner)),
                flags,
                self.is_keyboard_hook_installed(),
                self.is_mouse_hook_installed(),
            )
            ok = bool(self.dll.StartProtectedChordCapture(callback_ref, flags, int(timeout_ms)))  # type: ignore[union-attr]
            if ok:
                self._retire_callback_ref(self._protected_chord_capture_callback_ref)
                self._protected_chord_capture_callback_ref = callback_ref
                self._protected_chord_capture_owner = capture_owner
                self._protected_chord_capture_flags = flags
            logger.debug(
                "受保护组合捕获结果: owner=%s ok=%s active=%s last_error=%s",
                hex(id(capture_owner)),
                ok,
                self.is_protected_chord_capture_active(),
                self.get_last_hook_error(),
            )
            return ok

    def stop_protected_chord_capture(self, *, owner=None, force: bool = False) -> bool:
        with self._lifecycle_lock:
            requested_owner = owner if owner is not None else self
            logger.debug(
                "受保护组合捕获停止: requested_owner=%s current_owner=%s force=%s active=%s",
                hex(id(requested_owner)),
                hex(id(self._protected_chord_capture_owner)) if self._protected_chord_capture_owner is not None else "",
                force,
                self.is_protected_chord_capture_active(),
            )
            if (
                not force
                and self._protected_chord_capture_owner is not None
                and self._protected_chord_capture_owner is not requested_owner
            ):
                logger.warning("StopProtectedChordCapture rejected for non-owner")
                return False
            if self._ready() and self._has_protected_chord_capture:
                self.dll.StopProtectedChordCapture()  # type: ignore[union-attr]
            self._retire_callback_ref(self._protected_chord_capture_callback_ref)
            self._protected_chord_capture_callback_ref = None
            self._protected_chord_capture_owner = None
            self._protected_chord_capture_flags = 0
            logger.debug("受保护组合捕获已停止并清除所有者")
            return True

    def protected_chord_capture_owned_by(self, owner) -> bool:
        with self._lifecycle_lock:
            return self._protected_chord_capture_owner is owner

    def is_protected_chord_capture_active(self) -> bool:
        with self._lifecycle_lock:
            if not self._ready() or not self._has_protected_chord_capture:
                return False
            try:
                active = bool(self.dll.IsProtectedChordCaptureActive())  # type: ignore[union-attr]
            except Exception:
                return False
            if not active:
                self._clear_inactive_capture_owners_locked()
            return active

    @staticmethod
    def _input_event_to_dict(event: HookInputEvent) -> dict:
        return {name: int(getattr(event, name)) for name, _ctype in HookInputEvent._fields_}  # type: ignore[misc]

    def start_input_capture(
        self,
        callback: Callable[[dict], None],
        *,
        filter_flags: int = CAPTURE_ALL_PHYSICAL,
        include_injected: bool = False,
        include_own_playback: bool = False,
        coalesce_mouse_moves: bool = False,
        owner=None,
    ) -> bool:
        """Start non-blocking keyboard/mouse macro capture.

        The callback runs on a native capture-dispatch thread and must return
        quickly. Event dictionaries are detached copies and may be retained.
        """
        with self._lifecycle_lock:
            if not self._ready() or not self._has_input_capture or not callback:  # type: ignore[truthy-function]
                return False
            self._clear_inactive_capture_owners_locked()
            flags = int(filter_flags)
            if include_injected:
                flags |= CAPTURE_INCLUDE_INJECTED
            if include_own_playback:
                flags |= CAPTURE_INCLUDE_OWN_PLAYBACK
            if coalesce_mouse_moves:
                flags |= CAPTURE_COALESCE_MOUSE_MOVE

            def _dispatch(event_ptr):
                if not event_ptr:
                    return
                try:
                    callback(self._input_event_to_dict(event_ptr.contents))
                except Exception:
                    logger.exception("input capture callback failed")

            callback_ref = INPUT_EVENT_CALLBACK(_dispatch)
            capture_owner = owner if owner is not None else self
            if (
                self._input_capture_owner is not None
                or self._hotkey_capture_owner is not None
                or self._protected_chord_capture_owner is not None
            ):
                logger.warning("StartInputCapture rejected because another owner is recording")
                return False
            previous_ref = self._input_event_callback_ref
            ok = bool(self.dll.StartInputCapture(callback_ref, flags))  # type: ignore[union-attr]
            if not ok:
                logger.warning("StartInputCapture failed, last_error=%s", self.get_last_hook_error())
            else:
                self._retire_callback_ref(previous_ref)
                self._input_event_callback_ref = callback_ref
                self._input_capture_filter_flags = flags
                self._input_capture_owner = capture_owner
            return ok

    def stop_input_capture(self, *, owner=None, force: bool = False) -> bool:
        with self._lifecycle_lock:
            requested_owner = owner if owner is not None else self
            if not force and self._input_capture_owner is not None and self._input_capture_owner is not requested_owner:
                logger.warning("StopInputCapture rejected for non-owner")
                return False
            if self._ready() and self._has_input_capture:
                self.dll.StopInputCapture()  # type: ignore[union-attr]
            self._retire_callback_ref(self._input_event_callback_ref)
            self._input_event_callback_ref = None
            self._input_capture_filter_flags = 0
            self._input_capture_owner = None
            return True

    def is_input_capture_active(self) -> bool:
        with self._lifecycle_lock:
            if not self._ready() or not self._has_input_capture:
                return False
            active = bool(self.dll.IsInputCaptureActive())  # type: ignore[union-attr]
            if not active:
                self._clear_inactive_capture_owners_locked()
            return active

    @staticmethod
    def captured_events_to_macro(
        events: list[dict],
        *,
        speed: float = 1.0,
        preserve_initial_delay: bool = False,
    ) -> list[dict]:
        """Convert timestamped capture events into delayed playback events."""
        if speed <= 0:
            raise ValueError("speed must be greater than zero")
        result = []
        previous_timestamp = 0
        first_timestamp = None
        for raw in events:
            timestamp = max(0, int(raw.get("timestamp_us", 0)))
            if first_timestamp is None:
                first_timestamp = timestamp
                delay = timestamp if preserve_initial_delay else 0
            else:
                delay = max(0, timestamp - previous_timestamp)
            previous_timestamp = timestamp
            item = {
                "type": int(raw.get("type", 0)),
                "flags": int(raw.get("flags", 0)) & (INPUT_FLAG_EXTENDED | INPUT_FLAG_ABSOLUTE),
                "delay_us": min(0xFFFFFFFF, round(delay / speed)),
                "x": int(raw.get("x", 0)),
                "y": int(raw.get("y", 0)),
                "data": int(raw.get("data", 0)),
                "vk_code": int(raw.get("vk_code", 0)),
                "scan_code": int(raw.get("scan_code", 0)),
            }
            for key in _POINTER_CONTEXT_KEYS:
                if key in raw:
                    item[key] = raw[key]
            result.append(item)
        return result

    @staticmethod
    def _build_macro_event(raw: dict | HookMacroEvent) -> HookMacroEvent:
        if isinstance(raw, HookMacroEvent):
            event = raw
            if not event.size:
                event.size = ctypes.sizeof(HookMacroEvent)
            return event
        raw = _remap_pointer_context(raw)
        event = HookMacroEvent()
        event.size = ctypes.sizeof(HookMacroEvent)
        event.type = int(raw.get("type", 0))
        event.flags = int(raw.get("flags", 0))
        event.delay_us = max(0, min(0xFFFFFFFF, int(raw.get("delay_us", 0))))
        event.x = int(raw.get("x", 0))
        event.y = int(raw.get("y", 0))
        event.data = int(raw.get("data", 0))
        event.vk_code = int(raw.get("vk_code", 0))
        event.scan_code = int(raw.get("scan_code", 0))
        return event

    def play_macro(
        self,
        events: list[dict | HookMacroEvent],
        *,
        no_timing: bool = False,
        keep_pressed_on_cancel: bool = False,
    ) -> bool:
        """Copy a macro sequence into the DLL and play it asynchronously."""
        with self._lifecycle_lock:
            if not self._ready() or not self._has_macro_playback or not events:
                return False
            native_events = [self._build_macro_event(event) for event in events]
            array = (HookMacroEvent * len(native_events))(*native_events)
            options = 0
            if no_timing:
                options |= PLAYBACK_NO_TIMING
            if keep_pressed_on_cancel:
                options |= PLAYBACK_KEEP_PRESSED_ON_CANCEL
            ok = bool(self.dll.PlayMacroEvents(array, len(native_events), options))  # type: ignore[union-attr]
            if not ok:
                logger.warning("PlayMacroEvents failed, last_error=%s", self.get_last_hook_error())
            return ok

    def cancel_macro_playback(self) -> None:
        with self._lifecycle_lock:
            if self._ready() and self._has_macro_playback:
                self.dll.CancelMacroPlayback()  # type: ignore[union-attr]

    def wait_for_macro_playback(self, timeout_ms: int = 0xFFFFFFFF) -> bool:
        if not self._ready() or not self._has_macro_playback:
            return False
        return bool(self.dll.WaitForMacroPlayback(max(0, min(0xFFFFFFFF, int(timeout_ms)))))  # type: ignore[union-attr]

    def is_macro_playback_active(self) -> bool:
        if not self._ready() or not self._has_macro_playback:
            return False
        return bool(self.dll.IsMacroPlaybackActive())  # type: ignore[union-attr]

    def get_macro_status(self) -> dict:
        if not self._ready() or not self._has_macro_playback:
            return {}
        status = HookMacroStatus()
        status.size = ctypes.sizeof(HookMacroStatus)
        if not self.dll.GetMacroStatus(ctypes.byref(status), status.size):  # type: ignore[union-attr]
            return {}
        return {name: int(getattr(status, name)) for name, _ctype in HookMacroStatus._fields_}  # type: ignore[misc]

    def release_macro_pressed_inputs(self) -> None:
        with self._lifecycle_lock:
            if self._ready() and self._has_macro_playback:
                self.dll.ReleaseMacroPressedInputs()  # type: ignore[union-attr]

    def release_all_modifier_keys(self):
        """释放所有修饰键"""
        if self._ready():
            self.dll.ReleaseAllModifierKeys()  # type: ignore[union-attr]

    def set_special_apps(self, apps: list):
        """设置特殊应用列表"""
        if not self._ready() or not self._has_special_apps:
            return

        if not apps:
            self.dll.ClearSpecialApps()  # type: ignore[union-attr]
            return

        # 转换为 C 字符串数组
        c_apps = (ctypes.c_char_p * len(apps))()
        for i, app in enumerate(apps):
            c_apps[i] = app.encode("utf-8")

        self.dll.SetSpecialApps(c_apps, len(apps))  # type: ignore[union-attr]

    def clear_special_apps(self):
        """清除特殊应用列表"""
        if self._ready() and self._has_special_apps:
            self.dll.ClearSpecialApps()  # type: ignore[union-attr]

    def set_trigger_config(
        self, normal_button: str, normal_modifiers: list[str], special_button: str, special_modifiers: list[str]
    ) -> bool:
        """设置触发按键配置"""
        if not self._ready() or not self._has_trigger_config:
            logger.warning("hooks.dll 不支持基础触发配置或尚未就绪")
            return False

        from core.trigger_config import normalize_trigger_config

        normal_disabled = self._is_disabled_mouse_trigger("mouse", [], normal_button, normal_modifiers)
        special_disabled = self._is_disabled_mouse_trigger("mouse", [], special_button, special_modifiers)
        normal = (
            normalize_trigger_config("mouse", [], normal_button, normal_modifiers, fill_defaults=True)
            if not normal_disabled
            else None
        )
        special = (
            normalize_trigger_config(
                "mouse", [], special_button, special_modifiers, fill_defaults=True, default_modifiers=["ctrl"]
            )
            if not special_disabled
            else None
        )
        btn_map = {"left": 1, "right": 2, "middle": 4, "x1": 8, "x2": 16}
        mod_map = {"alt": 1, "ctrl": 2, "shift": 4, "win": 8}

        normal_btn = 0 if normal is None else btn_map.get(normal.button, 4)
        normal_mod = 0 if normal is None else sum(mod_map.get(m, 0) for m in normal.modifiers)
        special_btn = 0 if special is None else btn_map.get(special.button, 4)
        special_mod = 0 if special is None else sum(mod_map.get(m, 0) for m in special.modifiers)

        self.dll.SetTriggerConfig(normal_btn, normal_mod, special_btn, special_mod)  # type: ignore[union-attr]
        return True

    def set_trigger_config_ex(
        self,
        normal_mode: str,
        normal_button: str,
        normal_keys: list[str],
        normal_modifiers: list[str],
        special_mode: str,
        special_button: str,
        special_keys: list[str],
        special_modifiers: list[str],
    ) -> bool:
        """设置扩展触发按键配置（支持keyboard/mouse/hybrid模式）"""
        if not self._ready() or not self._has_trigger_config_ex:
            logger.warning("hooks.dll 不支持扩展触发配置或尚未就绪")
            return False

        from core.trigger_config import normalize_trigger_config

        normal_disabled = self._is_disabled_mouse_trigger(normal_mode, normal_keys, normal_button, normal_modifiers)
        special_disabled = self._is_disabled_mouse_trigger(
            special_mode, special_keys, special_button, special_modifiers
        )
        normal = (
            normalize_trigger_config(normal_mode, normal_keys, normal_button, normal_modifiers, fill_defaults=True)
            if not normal_disabled
            else None
        )
        special = (
            normalize_trigger_config(
                special_mode,
                special_keys,
                special_button,
                special_modifiers,
                fill_defaults=True,
                default_modifiers=["ctrl"],
            )
            if not special_disabled
            else None
        )
        mode_map = {"keyboard": 1, "mouse": 0, "hybrid": 2}
        btn_map = {"left": 1, "right": 2, "middle": 4, "x1": 8, "x2": 16}
        mod_map = {"alt": 1, "ctrl": 2, "shift": 4, "win": 8}

        normal_mode_int = 0 if normal is None else mode_map.get(normal.mode, 0)
        normal_btn = 0 if normal is None else btn_map.get(normal.button, 0)
        normal_vks = [] if normal is None else [self._key_to_vk(k) for k in normal.keys]
        normal_keys_vk = ",".join(str(vk) for vk in normal_vks if vk)
        normal_mod = 0 if normal is None else sum(mod_map.get(m, 0) for m in normal.modifiers)

        special_mode_int = 0 if special is None else mode_map.get(special.mode, 0)
        special_btn = 0 if special is None else btn_map.get(special.button, 0)
        special_vks = [] if special is None else [self._key_to_vk(k) for k in special.keys]
        special_keys_vk = ",".join(str(vk) for vk in special_vks if vk)
        special_mod = 0 if special is None else sum(mod_map.get(m, 0) for m in special.modifiers)

        self.dll.SetTriggerConfigEx(  # type: ignore[union-attr]
            normal_mode_int,
            normal_btn,
            normal_keys_vk.encode("utf-8"),
            normal_mod,
            special_mode_int,
            special_btn,
            special_keys_vk.encode("utf-8"),
            special_mod,
        )
        return True

    @staticmethod
    def _key_to_vk(key: str) -> int:
        """将按键字符串转换为VK码"""
        from hooks.key_map import key_to_vk

        return key_to_vk(key)

    @staticmethod
    def _is_disabled_mouse_trigger(mode: str, keys: list[str], button: str, modifiers: list[str]) -> bool:
        return (
            str(mode or "mouse").strip().lower() == "mouse"
            and not list(keys or [])
            and not str(button or "").strip()
            and not list(modifiers or [])
        )

    def is_normal_trigger_hotkey_registered(self) -> bool:
        """查询普通触发热键是否通过 RegisterHotKey 成功注册."""
        if not self._ready() or not self._has_trigger_hotkey_status:
            return False
        try:
            return bool(self.dll.IsNormalTriggerHotkeyRegistered())  # type: ignore[union-attr]
        except Exception as exc:
            logger.debug("查询普通触发热键状态失败: %s", exc)
            return False

    def is_special_trigger_hotkey_registered(self) -> bool:
        """查询特殊触发热键是否通过 RegisterHotKey 成功注册."""
        if not self._ready() or not self._has_trigger_hotkey_status:
            return False
        try:
            return bool(self.dll.IsSpecialTriggerHotkeyRegistered())  # type: ignore[union-attr]
        except Exception as exc:
            logger.debug("查询特殊触发热键状态失败: %s", exc)
            return False

    # === 任务栏触发相关方法 ===

    def set_taskbar_trigger_enabled(self, enabled: bool, require_ctrl: bool = False, interval_ms: int = 400):
        """启用/禁用任务栏双击触发（需要 DLL 支持 SetTaskbarTriggerEnabled 导出函数）"""
        if not hasattr(self.dll, "SetTaskbarTriggerEnabled"):
            logger.debug("当前 hooks.dll 不支持任务栏触发")
            return False
        if not self._ready():
            logger.warning("hooks.dll 尚未就绪，无法设置任务栏触发")
            return False
        try:
            if getattr(self, "_has_taskbar_trigger_config", False):
                self.dll.SetTaskbarTriggerConfig(bool(enabled), bool(require_ctrl), int(interval_ms))  # type: ignore[union-attr]
            else:
                self.dll.SetTaskbarTriggerEnabled(bool(enabled), bool(require_ctrl))  # type: ignore[union-attr]
            logger.info(
                "任务栏触发: %s (ctrl=%s interval_ms=%s)",
                "已启用" if enabled else "已禁用",
                require_ctrl,
                interval_ms,
            )
            return True
        except Exception as exc:
            logger.error("设置任务栏触发失败: %s", exc, exc_info=True)
            return False

    def set_taskbar_double_click_callback(self, callback):
        """设置任务栏双击回调（需要 DLL 支持 SetTaskbarDoubleClickCallback 导出函数）"""
        if not hasattr(self.dll, "SetTaskbarDoubleClickCallback"):
            logger.debug("当前 hooks.dll 不支持任务栏双击回调")
            return False
        with self._lifecycle_lock:
            if not self._ready():
                logger.warning("hooks.dll 尚未就绪，无法设置回调")
                return False
            previous_ref = self._taskbar_dclick_callback_ref
            if callback:
                callback_ref = MOUSE_CALLBACK(callback)
                self.dll.SetTaskbarDoubleClickCallback(callback_ref)  # type: ignore[union-attr]
                self._taskbar_dclick_callback_ref = callback_ref
            else:
                self.dll.SetTaskbarDoubleClickCallback(None)  # type: ignore[union-attr]
                self._taskbar_dclick_callback_ref = None
            self._retire_callback_ref(previous_ref)
            logger.info("任务栏双击回调已设置")
            return True

    def is_taskbar_trigger_available(self) -> bool:
        """检测当前系统是否支持任务栏触发"""
        if not hasattr(self.dll, "IsTaskbarTriggerAvailable"):
            return False
        if not self._ready():
            return False
        try:
            return bool(self.dll.IsTaskbarTriggerAvailable())  # type: ignore[union-attr]
        except Exception as exc:
            logger.debug("检测任务栏触发可用性失败: %s", exc)
            return False


def _dll_file_info(path: str) -> dict:
    info = {
        "path_resolved": "",
        "exists": False,
        "size_bytes": 0,
        "mtime": "",
        "sha256": "",
    }
    try:
        resolved = os.path.abspath(path or "")
        info["path_resolved"] = resolved
        if not os.path.isfile(resolved):
            return info
        stat = os.stat(resolved)
        info["exists"] = True
        info["size_bytes"] = int(stat.st_size)
        info["mtime"] = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
        digest = hashlib.sha256()
        with open(resolved, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        info["sha256"] = digest.hexdigest()
    except Exception as exc:
        logger.debug("hooks.dll file diagnostics failed: %s", exc)
    return info
