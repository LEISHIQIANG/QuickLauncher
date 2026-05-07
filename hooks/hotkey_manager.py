import threading
import logging
import os
import sys
import ctypes
from ctypes import wintypes
from qt_compat import QObject, pyqtSignal, QTimer, Qt, QMetaObject

try:
    from pynput import keyboard
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

logger = logging.getLogger(__name__)


def _choose_backend() -> str:
    forced = (os.environ.get("QL_HOTKEY_BACKEND") or "").strip().lower()
    if forced in ("win32", "registerhotkey", "winhotkey"):
        return "win32"
    if forced in ("pynput",):
        return "pynput"
    if sys.platform == "win32":
        return "win32"
    return "pynput"


def _parse_win_hotkey(normalized: str):
    if not normalized:
        return None

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000

    mods = 0
    vk = None

    parts = [p for p in (normalized or "").split("+") if p]
    for raw in parts:
        t = (raw or "").strip().lower()
        if not t:
            continue

        if t in ("<alt>", "alt"):
            mods |= MOD_ALT
            continue
        if t in ("<ctrl>", "<control>", "ctrl", "control"):
            mods |= MOD_CONTROL
            continue
        if t in ("<shift>", "shift"):
            mods |= MOD_SHIFT
            continue
        if t in ("<cmd>", "<win>", "win", "windows", "meta", "cmd", "super"):
            mods |= MOD_WIN
            continue

        if t.startswith("<") and t.endswith(">") and len(t) > 2:
            t = t[1:-1]

        if len(t) == 1:
            ch = t.upper()
            vk = ord(ch)
            continue

        if t in ("space",):
            vk = 0x20
            continue
        if t in ("tab",):
            vk = 0x09
            continue
        if t in ("enter", "return"):
            vk = 0x0D
            continue
        if t in ("esc", "escape"):
            vk = 0x1B
            continue

        if t.startswith("f") and t[1:].isdigit():
            n = int(t[1:])
            if 1 <= n <= 24:
                vk = 0x70 + (n - 1)
                continue
            return None

        return None

    if vk is None:
        return None
    return (mods | MOD_NOREPEAT, vk)


class _WinHotkeyThread(threading.Thread):
    def __init__(self, modifiers: int, vk: int, on_activate):
        super().__init__(daemon=True)
        self._modifiers = int(modifiers)
        self._vk = int(vk)
        self._on_activate = on_activate
        self._stop_event = threading.Event()
        self._thread_id = None
        self._hwnd = None
        self._hotkey_id = 0xA0B1
        self._registered = False
        self._registered_event = threading.Event()

    def wait_registered(self, timeout: float = 0.25) -> bool:
        try:
            self._registered_event.wait(timeout=max(0.0, float(timeout)))
        except Exception:
            return False
        return bool(self._registered)

    def stop(self):
        self._stop_event.set()
        try:
            if self._thread_id:
                ctypes.windll.user32.PostThreadMessageW(int(self._thread_id), 0x0012, 0, 0)
        except Exception:
            pass
        try:
            self.join(timeout=0.8)
        except Exception:
            pass

    def run(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._thread_id = kernel32.GetCurrentThreadId()

        HWND = getattr(wintypes, "HWND", ctypes.c_void_p)
        UINT = getattr(wintypes, "UINT", ctypes.c_uint)
        WPARAM = getattr(wintypes, "WPARAM", ctypes.c_size_t)
        LPARAM = getattr(wintypes, "LPARAM", ctypes.c_ssize_t)
        LRESULT = getattr(wintypes, "LRESULT", ctypes.c_ssize_t)
        try:
            user32.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
            user32.DefWindowProcW.restype = LRESULT
        except Exception:
            pass

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", UINT),
                ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        WNDPROCTYPE = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)

        def _wndproc(hwnd, msg, wparam, lparam):
            try:
                return user32.DefWindowProcW(hwnd, msg, WPARAM(wparam), LPARAM(lparam))
            except Exception:
                return 0

        wndproc = WNDPROCTYPE(_wndproc)

        try:
            kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        except Exception:
            pass
        hinstance = kernel32.GetModuleHandleW(None)
        try:
            hinstance = wintypes.HINSTANCE(hinstance)
        except Exception:
            pass

        try:
            HMENU = getattr(wintypes, "HMENU", wintypes.HANDLE)
            user32.CreateWindowExW.argtypes = [
                wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                HWND, HMENU, wintypes.HINSTANCE, ctypes.c_void_p
            ]
            user32.CreateWindowExW.restype = HWND
        except Exception:
            pass

        class_name = "QuickLauncherHotkeyWindow"
        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = ctypes.cast(wndproc, ctypes.c_void_p)
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinstance
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = class_name

        try:
            user32.RegisterClassW(ctypes.byref(wc))
        except Exception:
            pass

        try:
            HWND_MESSAGE = HWND(-3)
        except Exception:
            HWND_MESSAGE = ctypes.c_void_p(-3)
        hwnd = user32.CreateWindowExW(
            0,
            class_name,
            class_name,
            0,
            0, 0, 0, 0,
            HWND_MESSAGE,
            None,
            hinstance,
            None,
        )
        self._hwnd = hwnd

        registered = False
        try:
            registered = bool(user32.RegisterHotKey(hwnd, int(self._hotkey_id), int(self._modifiers), int(self._vk)))
        except Exception:
            registered = False
        try:
            self._registered = bool(registered)
            self._registered_event.set()
        except Exception:
            pass

        if not registered:
            try:
                user32.DestroyWindow(hwnd)
            except Exception:
                pass
            return

        msg = wintypes.MSG()
        try:
            while not self._stop_event.is_set():
                r = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
                if r == 0 or r == -1:
                    break
                if msg.message == 0x0312 and int(msg.wParam) == int(self._hotkey_id):
                    try:
                        self._on_activate()
                    except Exception:
                        pass
        finally:
            try:
                user32.UnregisterHotKey(hwnd, int(self._hotkey_id))
            except Exception:
                pass
            try:
                user32.DestroyWindow(hwnd)
            except Exception:
                pass


class _WinHotkeyListener:
    def __init__(self, modifiers: int, vk: int, on_activate):
        self._thread = _WinHotkeyThread(modifiers=modifiers, vk=vk, on_activate=on_activate)

    def start(self) -> bool:
        self._thread.start()
        return self._thread.wait_registered(timeout=0.25)

    def stop(self):
        self._thread.stop()


class HotkeyManager(QObject):
    """全局热键管理器"""
    
    activated = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener = None
        self._current_hotkey = None
        self._is_running = False
        self._pending_activated = 0
        self._pending_lock = threading.Lock()
        self._dispatch_timer = QTimer(self)
        self._dispatch_timer.setSingleShot(True)
        self._dispatch_timer.setInterval(15)
        self._dispatch_timer.timeout.connect(self._drain_pending_activated)
        self._dll = None
        self._use_hook = True  # 使用钩子而不是RegisterHotKey

    def _release_modifier_keys(self):
        """释放修饰键"""
        try:
            logger.info("正在释放修饰键...")
            if self._dll is None:
                from hooks.hooks_wrapper import HooksDLL
                self._dll = HooksDLL()
            self._dll.release_all_modifier_keys()
            logger.info("修饰键已释放")
        except Exception as e:
            logger.debug(f"释放修饰键失败: {e}")
        
    def start(self):
        """启动监听"""
        if self._is_running:
            return
            
        self._is_running = True
        logger.info("HotkeyManager started")
        
    def stop(self):
        """停止监听"""
        if self._dll:
            try:
                self._dll.clear_hotkey()
            except Exception:
                pass
        if self._listener:
            try:
                self._listener.stop()
                self._listener = None
            except Exception as e:
                logger.error(f"Stop listener failed: {e}")
        self._is_running = False
        
    def _normalize_hotkey(self, hotkey_str: str) -> str:
        s = (hotkey_str or "").strip()
        if not s:
            return ""
        s = s.replace(" ", "")

        parts = [p for p in s.split("+") if p]
        normalized_parts = []

        for raw in parts:
            t = (raw or "").strip().lower()
            if not t:
                continue

            if t.startswith("<") and t.endswith(">") and len(t) > 2:
                core = t[1:-1]
            else:
                core = t

            if core in ("ctrl", "control"):
                normalized_parts.append("<ctrl>")
                continue
            if core in ("alt",):
                normalized_parts.append("<alt>")
                continue
            if core in ("shift",):
                normalized_parts.append("<shift>")
                continue
            if core in ("win", "windows", "meta", "cmd", "super"):
                normalized_parts.append("<cmd>")
                continue

            if core in ("space",):
                normalized_parts.append("<space>")
                continue
            if core in ("tab",):
                normalized_parts.append("<tab>")
                continue
            if core in ("enter", "return"):
                normalized_parts.append("<enter>")
                continue
            if core in ("esc", "escape"):
                normalized_parts.append("<esc>")
                continue

            if len(core) == 1:
                normalized_parts.append(core)
                continue

            if core.startswith("f") and core[1:].isdigit():
                normalized_parts.append(f"<{core}>")
                continue

            normalized_parts.append(f"<{core}>")

        if not normalized_parts:
            return ""

        mods = {"<ctrl>", "<alt>", "<shift>", "<cmd>"}
        if all(p in mods for p in normalized_parts):
            return ""

        return "+".join(normalized_parts)

    def set_hotkey(self, hotkey_str: str):
        """设置热键 (e.g. '<alt>+<space>')"""
        if not hotkey_str:
            self.stop()
            return

        # Stop existing listener
        self.stop()

        normalized = self._normalize_hotkey(hotkey_str)
        if not normalized:
            self._current_hotkey = None
            return

        self._current_hotkey = normalized

        # 优先使用DLL钩子，避免RegisterHotKey的Alt卡住问题
        if self._use_hook:
            try:
                logger.info(f"尝试使用DLL钩子设置热键: {normalized}")
                if self._dll is None:
                    from hooks.keyboard_hook_dll import KeyboardHook
                    # 获取全局键盘钩子实例
                    import sys
                    if hasattr(sys.modules.get('__main__'), 'keyboard_hook'):
                        kb = sys.modules['__main__'].keyboard_hook
                        if hasattr(kb, '_dll'):
                            self._dll = kb._dll
                    if self._dll is None:
                        from hooks.hooks_wrapper import HooksDLL
                        self._dll = HooksDLL()
                logger.info(f"DLL实例: {self._dll}")
                self._dll.set_hotkey(normalized, self._on_activated)
                self._is_running = True
                logger.info(f"Global hotkey set to (DLL hook): {normalized}")
                return
            except Exception as e:
                logger.error(f"DLL hook failed: {e}, fallback to RegisterHotKey")
                import traceback
                logger.error(traceback.format_exc())

        try:
            backend = _choose_backend()
            if backend == "win32" and sys.platform == "win32":
                parsed = _parse_win_hotkey(normalized)
                if not parsed:
                    logger.error(f"Unsupported hotkey for win32 backend: {normalized}")
                    return
                modifiers, vk = parsed
                self._listener = _WinHotkeyListener(modifiers=modifiers, vk=vk, on_activate=self._on_activated)
                ok = False
                try:
                    ok = bool(self._listener.start())
                except Exception:
                    ok = False
                if ok:
                    self._is_running = True
                    logger.info(f"Global hotkey set to (win32): {normalized}")
                    return
                try:
                    self._listener.stop()
                except Exception:
                    pass
                self._listener = None
                if not HAS_PYNPUT:
                    logger.warning("pynput not installed, hotkey disabled")
                    return
                self._listener = keyboard.GlobalHotKeys({normalized: self._on_activated})
                self._listener.start()
                self._is_running = True
                logger.info(f"Global hotkey set to (pynput): {normalized}")
            else:
                if not HAS_PYNPUT:
                    logger.warning("pynput not installed, hotkey disabled")
                    return
                self._listener = keyboard.GlobalHotKeys({normalized: self._on_activated})
                self._listener.start()
                self._is_running = True
                logger.info(f"Global hotkey set to (pynput): {normalized}")
        except Exception as e:
            logger.error(f"Failed to set hotkey '{normalized}': {e}")
            
    def _on_activated(self):
        """Callback from hotkey thread — must NOT touch QTimer directly"""
        logger.debug("Global hotkey activated")
        try:
            with self._pending_lock:
                self._pending_activated += 1
            # 安全地在主线程启动定时器（避免跨线程操作 QTimer）
            if QMetaObject is not None:
                try:
                    QMetaObject.invokeMethod(
                        self._dispatch_timer, "start",
                        Qt.ConnectionType.QueuedConnection
                    )
                except Exception:
                    # PyQt5 枚举风格不同
                    try:
                        QMetaObject.invokeMethod(
                            self._dispatch_timer, "start",
                            Qt.QueuedConnection
                        )
                    except Exception:
                        pass
            else:
                # 最后兜底：直接调用（仍可能触发警告，但不会崩溃）
                self._dispatch_timer.start()
        except Exception:
            return

    def _drain_pending_activated(self):
        n = 0
        try:
            with self._pending_lock:
                n = int(self._pending_activated)
                self._pending_activated = 0
        except Exception:
            n = 0

        if n <= 0:
            return

        try:
            self.activated.emit()
            # 不自动释放修饰键，避免干扰
        except Exception:
            pass
