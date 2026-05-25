import logging
import sys
import threading

from qt_compat import QMetaObject, QObject, Qt, QTimer, pyqtSignal

logger = logging.getLogger(__name__)


class HotkeyManager(QObject):
    """全局热键管理器"""

    activated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_hotkey = None
        self._is_running = False
        self._pending_activated = 0
        self._pending_lock = threading.Lock()
        self._dispatch_timer = QTimer(self)
        self._dispatch_timer.setSingleShot(True)
        self._dispatch_timer.setInterval(15)
        self._dispatch_timer.timeout.connect(self._drain_pending_activated)
        self._dll = None

    def _release_modifier_keys(self):
        """释放修饰键"""
        try:
            logger.info("正在释放修饰键...")
            if self._dll is None:
                from hooks.hooks_wrapper import HooksDLL
                self._dll = HooksDLL.get_instance()
            self._dll.release_all_modifier_keys()
            logger.info("修饰键已释放")
        except Exception as e:
            logger.debug(f"释放修饰键失败: {e}")

    def start(self):
        """启动监听"""
        if self._is_running:
            return True

        if self._current_hotkey:
            hotkey = self._current_hotkey
            try:
                return self.set_hotkey(hotkey)
            except Exception as e:
                logger.debug(f"Resume hotkey failed: {e}")

        self._is_running = True
        logger.info("HotkeyManager started")
        return True

    def stop(self):
        """停止监听"""
        if self._dll:
            try:
                self._dll.clear_hotkey()
            except Exception:
                pass
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
            if core in ("lctrl", "ctrl_l"):
                normalized_parts.append("<ctrl_l>")
                continue
            if core in ("rctrl", "ctrl_r"):
                normalized_parts.append("<ctrl_r>")
                continue
            if core in ("alt",):
                normalized_parts.append("<alt>")
                continue
            if core in ("lalt", "alt_l"):
                normalized_parts.append("<alt_l>")
                continue
            if core in ("ralt", "alt_r"):
                normalized_parts.append("<alt_r>")
                continue
            if core in ("shift",):
                normalized_parts.append("<shift>")
                continue
            if core in ("lshift", "shift_l"):
                normalized_parts.append("<shift_l>")
                continue
            if core in ("rshift", "shift_r"):
                normalized_parts.append("<shift_r>")
                continue
            if core in ("win", "windows", "meta", "cmd", "super"):
                normalized_parts.append("<cmd>")
                continue
            if core in ("lwin", "win_l", "cmd_l"):
                normalized_parts.append("<cmd_l>")
                continue
            if core in ("rwin", "win_r", "cmd_r"):
                normalized_parts.append("<cmd_r>")
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

        mods = {"<ctrl>", "<alt>", "<shift>", "<cmd>", "<ctrl_l>", "<ctrl_r>", "<alt_l>", "<alt_r>", "<shift_l>", "<shift_r>", "<cmd_l>", "<cmd_r>"}
        if all(p in mods for p in normalized_parts):
            return ""

        return "+".join(normalized_parts)

    def _has_side_specific_modifier(self, normalized: str) -> bool:
        return any(token in normalized for token in ("<ctrl_l>", "<ctrl_r>", "<alt_l>", "<alt_r>", "<shift_l>", "<shift_r>", "<cmd_l>", "<cmd_r>"))

    def set_hotkey(self, hotkey_str: str):
        """设置热键 (e.g. '<alt>+<space>')"""
        if not hotkey_str:
            self._current_hotkey = None
            self.stop()
            return False

        # Stop existing listener
        self.stop()

        normalized = self._normalize_hotkey(hotkey_str)
        if not normalized:
            self._current_hotkey = None
            return False

        self._current_hotkey = normalized

        # 拒绝带有左右区分的修饰键
        if self._has_side_specific_modifier(normalized):
            logger.warning("不支持区分左右的修饰键用于全局热键: %s", normalized)
            return False

        # 使用DLL钩子设置热键
        try:
            logger.info(f"尝试使用DLL钩子设置热键: {normalized}")
            if self._dll is None:
                # 获取全局键盘钩子实例
                if hasattr(sys.modules.get('__main__'), 'keyboard_hook'):
                    kb = sys.modules['__main__'].keyboard_hook
                    if hasattr(kb, '_dll'):
                        self._dll = kb._dll
                if self._dll is None:
                    from hooks.hooks_wrapper import HooksDLL
                    self._dll = HooksDLL.get_instance()
            logger.info(f"DLL实例: {self._dll}")
            if self._dll.set_hotkey(normalized, self._on_activated):
                self._is_running = True
                logger.info(f"Global hotkey set to (DLL hook): {normalized}")
                return True
            logger.error("DLL钩子设置热键失败: %s", normalized)
            try:
                self._dll.clear_hotkey()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"DLL hook failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

        return False

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
