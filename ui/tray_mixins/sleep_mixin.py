"""
休眠/唤醒/内存管理相关方法。
"""

import logging

logger = logging.getLogger(__name__)


class SleepMixin:
    """休眠/唤醒/内存管理相关方法。"""

    def _mark_activity(self, source: str = ""):
        settings = None
        try:
            settings = self.data_manager.get_settings()
        except Exception:
            settings = None

        if not getattr(settings, "sleep_mode_enabled", True):
            try:
                if self._sleep_timer.isActive():
                    self._sleep_timer.stop()
            except Exception:
                pass
            return

        timeout_s = 10
        try:
            timeout_s = max(1, int(getattr(settings, "sleep_timeout_seconds", 10) or 10))
        except Exception:
            timeout_s = 10

        if self._sleeping:
            return

        for widget in self._iter_visible_blocking_widgets():
            try:
                if widget and widget.isVisible():
                    return
            except Exception:
                pass

        try:
            self._sleep_timer.start(timeout_s * 1000)
        except Exception:
            pass

    def _enter_light_sleep(self):
        if self._sleeping:
            return

        try:
            settings = self.data_manager.get_settings()
        except Exception:
            settings = None

        if not getattr(settings, "sleep_mode_enabled", True):
            return

        for widget in self._iter_visible_blocking_widgets():
            try:
                if widget and widget.isVisible():
                    timeout_s = 10
                    try:
                        timeout_s = max(1, int(getattr(settings, "sleep_timeout_seconds", 10) or 10))
                    except Exception:
                        timeout_s = 10
                    try:
                        self._sleep_timer.start(timeout_s * 1000)
                    except Exception:
                        pass
                    return
            except Exception:
                pass

        self._sleeping = True
        logger.info("进入轻睡眠模式")

        try:
            self._sleep_was_hw_accel = bool(getattr(settings, "hardware_acceleration", False))
            if self._sleep_was_hw_accel:
                self._apply_hardware_acceleration(False)
        except Exception:
            self._sleep_was_hw_accel = False

        if self._mouse_paused_state:
            logger.info("进入轻睡眠模式：中键已禁用，保留 Alt 双击恢复通道")

        for timer_name in (
            "_memory_check_timer",
            "_process_check_timer",
            "_deferred_startup_timer",
        ):
            self._stop_timer_if_active(timer_name)

        try:
            from core.folder_watcher import shutdown_watcher_manager

            shutdown_watcher_manager()
        except Exception:
            pass

    def _iter_visible_blocking_widgets(self):
        yield self.popup_window
        for popup in list(getattr(self, "_extra_popup_windows", []) or []):
            yield popup
        yield self.config_window
        yield self.log_window
        yield getattr(self, "command_panel_window", None)

        try:
            self.hotkey_manager.stop()
        except Exception:
            pass

        logger.info("进入轻睡眠模式：保留键盘 Hook 用于 Alt 双击切换中键")

        try:
            self._cleanup_icon_cache()
        except Exception:
            pass

        try:
            from core import IconExtractor

            if hasattr(IconExtractor, "clear_cache"):
                IconExtractor.clear_cache()
        except Exception:
            pass

        try:
            if self.popup_window:
                try:
                    self.popup_window._release_background_cache()
                except Exception:
                    pass
                try:
                    self.popup_window._icon_pixmap_cache.clear()
                    self.popup_window._icon_miss_cache.clear()
                    self.popup_window._default_icon_cache.clear()
                except Exception:
                    pass
                try:
                    type(self.popup_window)._global_bg_cache.clear()
                except Exception:
                    pass
            for popup in list(getattr(self, "_extra_popup_windows", []) or []):
                try:
                    popup._release_background_cache()
                except Exception:
                    pass
                try:
                    popup._icon_pixmap_cache.clear()
                    popup._icon_miss_cache.clear()
                    popup._default_icon_cache.clear()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            self.memory_guard.check_and_optimize()
        except Exception:
            pass

        try:
            import gc

            gc.collect()
        except Exception:
            pass

    def _wake_from_sleep(self, source: str = ""):
        if not self._sleeping:
            self._mark_activity(source)
            return False

        self._sleeping = False
        logger.info("退出轻睡眠模式: %s", source or "unknown")

        try:
            self._apply_pending_settings_changes()
        except Exception:
            pass

        try:
            if not self._memory_check_timer.isActive():
                self._memory_check_timer.start()
        except Exception:
            pass

        try:
            if self._sleep_was_hw_accel:
                self._apply_hardware_acceleration(True)
        except Exception:
            pass
        self._sleep_was_hw_accel = False

        try:
            if self.keyboard_hook is None:
                self._install_keyboard_hook_and_hotkey()
            else:
                self.hotkey_manager.start()
        except Exception:
            pass

        try:
            if self.mouse_hook and self._mouse_paused_state:
                self.mouse_hook.set_paused(True)
        except Exception:
            pass

        try:
            self._update_special_app_monitors(reset_state=True)
            if self.mouse_hook:
                if self.keyboard_hook:
                    try:
                        self.mouse_hook.set_keyboard_hook(self.keyboard_hook)
                    except Exception:
                        pass
                self._apply_mouse_hook_settings()
        except Exception:
            pass

        try:
            self._mark_activity(source)
        except Exception:
            pass
        return False

    def _check_memory(self):
        """定期检查内存并优化"""
        try:
            self.memory_guard.check_and_optimize()
        except Exception:
            pass

    def _cleanup_icon_cache(self):
        """清理图标缓存以释放内存"""
        try:
            from core import IconExtractor

            if hasattr(IconExtractor, "_cache"):
                cache_size = len(IconExtractor._cache)
                if cache_size > 50:
                    items = list(IconExtractor._cache.items())
                    IconExtractor._cache.clear()
                    for k, v in items[-50:]:
                        IconExtractor._cache[k] = v
                    logger.info(f"清理图标缓存: {cache_size} -> 50")
        except Exception as e:
            logger.debug(f"清理图标缓存失败: {e}")
