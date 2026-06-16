"""
休眠/唤醒/内存管理相关方法。
"""

import logging

logger = logging.getLogger(__name__)
_SLEEP_MIXIN_ERRORS = (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError)


class SleepMixin:
    """休眠/唤醒/内存管理相关方法。"""

    def _mark_activity(self, source: str = ""):
        settings = None
        try:
            settings = self.data_manager.get_settings()  # type: ignore[attr-defined]
        except _SLEEP_MIXIN_ERRORS as e:
            logger.debug("获取设置失败 (_mark_activity): %s", e)
            settings = None

        if not getattr(settings, "sleep_mode_enabled", True):
            try:
                if self._sleep_timer.isActive():  # type: ignore[attr-defined]
                    self._sleep_timer.stop()  # type: ignore[attr-defined]
            except _SLEEP_MIXIN_ERRORS as e:
                logger.debug("停止 sleep_timer 失败: %s", e)
            return

        timeout_s = 10
        try:
            timeout_s = max(1, int(getattr(settings, "sleep_timeout_seconds", 10) or 10))
        except _SLEEP_MIXIN_ERRORS as e:
            logger.debug("读取 sleep_timeout_seconds 失败: %s", e)
            timeout_s = 10

        if self._sleeping:
            return

        for widget in self._iter_visible_blocking_widgets():
            try:
                if widget and widget.isVisible():
                    return
            except _SLEEP_MIXIN_ERRORS as exc:
                logger.debug("检查控件可见性: %s", exc, exc_info=True)

        try:
            self._sleep_timer.start(timeout_s * 1000)  # type: ignore[attr-defined]
        except _SLEEP_MIXIN_ERRORS as e:
            logger.debug("启动 sleep_timer 失败: %s", e)

    def _enter_light_sleep(self):
        if self._sleeping:
            return

        try:
            settings = self.data_manager.get_settings()
        except _SLEEP_MIXIN_ERRORS as e:
            logger.debug("获取设置失败 (_enter_light_sleep): %s", e)
            settings = None

        if not getattr(settings, "sleep_mode_enabled", True):
            return

        for widget in self._iter_visible_blocking_widgets():
            try:
                if widget and widget.isVisible():
                    timeout_s = 10
                    try:
                        timeout_s = max(1, int(getattr(settings, "sleep_timeout_seconds", 10) or 10))
                    except _SLEEP_MIXIN_ERRORS:
                        timeout_s = 10
                    try:
                        self._sleep_timer.start(timeout_s * 1000)
                    except _SLEEP_MIXIN_ERRORS as e:
                        logger.debug("重启 sleep_timer 失败: %s", e)
                    return
            except _SLEEP_MIXIN_ERRORS as exc:
                logger.debug("检查可见控件并重启休眠定时器失败: %s", exc, exc_info=True)

        self._sleeping = True
        logger.info("进入轻睡眠模式")

        try:
            self._sleep_was_hw_accel = bool(getattr(settings, "hardware_acceleration", False))
            if self._sleep_was_hw_accel:
                self._apply_hardware_acceleration(False)
        except _SLEEP_MIXIN_ERRORS:
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
        except _SLEEP_MIXIN_ERRORS as exc:
            logger.debug("关闭文件夹监听管理器: %s", exc, exc_info=True)

        self._perform_sleep_cleanup()

    def _iter_visible_blocking_widgets(self):
        yield self.popup_window
        yield from list(getattr(self, "_extra_popup_windows", []) or [])
        yield self.config_window
        yield self.log_window
        yield getattr(self, "command_panel_window", None)

    def _perform_sleep_cleanup(self):
        logger.info("进入轻睡眠模式：保留键盘 Hook 用于 Alt 双击切换中键")

        try:
            if self.popup_window:
                try:
                    self.popup_window._release_background_cache()
                except _SLEEP_MIXIN_ERRORS as exc:
                    logger.debug("释放背景缓存: %s", exc, exc_info=True)
                try:
                    type(self.popup_window)._global_bg_cache.clear()
                except _SLEEP_MIXIN_ERRORS as exc:
                    logger.debug("清理全局背景缓存: %s", exc, exc_info=True)
            for popup in list(getattr(self, "_extra_popup_windows", []) or []):
                try:
                    popup._release_background_cache()
                except _SLEEP_MIXIN_ERRORS as exc:
                    logger.debug("释放背景缓存: %s", exc, exc_info=True)
        except _SLEEP_MIXIN_ERRORS as exc:
            logger.debug("释放弹窗背景缓存: %s", exc, exc_info=True)

        try:
            self.memory_guard.check_and_optimize()
        except _SLEEP_MIXIN_ERRORS as exc:
            logger.debug("内存检查与优化: %s", exc, exc_info=True)

        try:
            import gc

            gc.collect()
        except _SLEEP_MIXIN_ERRORS as exc:
            logger.debug("执行垃圾回收: %s", exc, exc_info=True)

    def _wake_from_sleep(self, source: str = ""):
        if not self._sleeping:
            self._mark_activity(source)
            return False

        self._sleeping = False
        logger.info("退出轻睡眠模式: %s", source or "unknown")

        try:
            self._apply_pending_settings_changes()  # type: ignore[attr-defined]
        except _SLEEP_MIXIN_ERRORS as exc:
            logger.debug("应用待处理设置变更: %s", exc, exc_info=True)

        try:
            if not self._memory_check_timer.isActive():  # type: ignore[attr-defined]
                self._memory_check_timer.start()  # type: ignore[attr-defined]
        except _SLEEP_MIXIN_ERRORS as e:
            logger.debug("重启 memory_check_timer 失败: %s", e)

        try:
            if self._sleep_was_hw_accel:
                self._apply_hardware_acceleration(True)  # type: ignore[attr-defined]
        except _SLEEP_MIXIN_ERRORS as exc:
            logger.debug("恢复硬件加速: %s", exc, exc_info=True)
        self._sleep_was_hw_accel = False

        try:
            if self.keyboard_hook is None:  # type: ignore[attr-defined]
                self._install_keyboard_hook_and_hotkey()  # type: ignore[attr-defined]
        except _SLEEP_MIXIN_ERRORS as e:
            logger.debug("恢复键盘钩子失败: %s", e)

        try:
            if self.mouse_hook and self._mouse_paused_state:  # type: ignore[attr-defined]
                self.mouse_hook.set_paused(True)  # type: ignore[attr-defined]
        except _SLEEP_MIXIN_ERRORS as exc:
            logger.debug("设置鼠标钩子暂停状态: %s", exc, exc_info=True)

        try:
            self._update_special_app_monitors(reset_state=True)  # type: ignore[attr-defined]
            if self.mouse_hook:  # type: ignore[attr-defined]
                if self.keyboard_hook:  # type: ignore[attr-defined]
                    try:
                        self.mouse_hook.set_keyboard_hook(self.keyboard_hook)  # type: ignore[attr-defined]
                    except _SLEEP_MIXIN_ERRORS as exc:
                        logger.debug("关联键盘钩子到鼠标钩子: %s", exc, exc_info=True)
                self._apply_mouse_hook_settings()  # type: ignore[attr-defined]
        except _SLEEP_MIXIN_ERRORS as exc:
            logger.debug("关联键盘钩子到鼠标钩子: %s", exc, exc_info=True)

        try:
            self._mark_activity(source)
        except _SLEEP_MIXIN_ERRORS as exc:
            logger.debug("标记活动: %s", exc, exc_info=True)
        return False

    def _check_memory(self):
        """定期检查内存并优化"""
        try:
            self.memory_guard.check_and_optimize()
        except _SLEEP_MIXIN_ERRORS as exc:
            logger.debug("内存检查与优化: %s", exc, exc_info=True)

    def _cleanup_icon_cache(self, level: str = "manual"):
        """手动清理图标提取缓存；常规内存检查不再调用此方法。"""
        try:
            from core import IconExtractor

            if level == "critical":
                IconExtractor.clear_cache()
            elif level == "manual":
                cache_size = len(getattr(IconExtractor, "_cache", {}))
                IconExtractor.clear_cache()
                if cache_size:
                    logger.info("手动清理内存图标缓存: %s -> 0", cache_size)
        except _SLEEP_MIXIN_ERRORS as e:
            logger.debug(f"清理图标缓存失败: {e}")
