"""Shutdown / icon-cache helpers for :class:`TrayApp`.

Extracted from :mod:`ui.tray_app` as part of the P1-06 file-split
pass.  Owns ``_shutdown_runtime_components`` (stops background
timers + cache-clean threads) and the
``_clean_icon_cache_now`` / ``_on_icon_cache_clean_finished``
manual maintenance helpers.
"""

from __future__ import annotations

import logging

from core.i18n import tr
from ui.utils.qt_thread_cleanup import drain_deferred_qthreads, stop_qthread_nonblocking

logger = logging.getLogger(__name__)


class TrayAppShutdownMixin:
    """Lifecycle teardown + icon-cache maintenance plumbing.

    The host class is expected to expose:

    * :pyattr:`_icon_cache_clean_thread` — current
      :class:`IconCacheCleanThread` instance
    * :pyattr:`_settings_sync_timer` / :pyattr:`_sleep_timer` /
      :pyattr:`_deferred_startup_timer` / :pyattr:`_plugin_startup_timer` /
      :pyattr:`_memory_check_timer` / :pyattr:`_process_check_timer` /
      :pyattr:`_hook_health_timer` — ``QTimer`` instances
    * :pyattr:`_process_check_cancel_event` /
      :pyattr:`_process_check_future` — process check bookkeeping
    * :pyattr:`popup_window` — primary ``LauncherPopup``
    * :pyattr:`_extra_popup_windows` — pinned-popup list
    * :pyattr:`_show_toast` / :pyattr:`_wake_from_sleep` /
      :pyattr:`data_manager` / :pyattr:`_cleanup_icon_cache`
    """

    def stop(self) -> None:
        """Public shutdown entry point used by :class:`LifecycleManager`.

        The composition root registers ``tray_app.stop`` as the lifecycle
        handler for the tray app, so this method must exist and stay
        idempotent.  Delegates to the private teardown helper which is
        already guarded by ``_runtime_shutdown_started``.
        """
        self._shutdown_runtime_components()

    def _stop_timer_if_active(self, attr_name):
        try:
            timer = getattr(self, attr_name, None)
        except RuntimeError as exc:
            logger.debug("读取定时器失败: %s", exc, exc_info=True)
            return
        if timer is None:
            return
        try:
            if timer.isActive():
                timer.stop()
        except Exception:
            try:
                timer.stop()
            except Exception as exc:
                logger.debug("停止定时器失败: %s", exc, exc_info=True)

    def _close_widget_if_present(self, attr_name):
        widget = getattr(self, attr_name, None)
        if widget is None:
            return
        try:
            widget.close()
        except Exception as exc:
            logger.debug("关闭窗口组件: %s", exc, exc_info=True)
        try:
            setattr(self, attr_name, None)
        except Exception as exc:
            logger.debug("清除窗口引用失败: %s", exc, exc_info=True)

    def _close_extra_popup_windows(self):
        for popup in list(getattr(self, "_extra_popup_windows", []) or []):
            try:
                popup.close()
            except Exception as exc:
                logger.debug("关闭弹窗: %s", exc, exc_info=True)
        self._extra_popup_windows = []

    def _shutdown_runtime_components(self):
        if bool(self.__dict__.get("_runtime_shutdown_started", False)):
            return
        self._runtime_shutdown_started = True

        # Drain any late-finishing QThreads deferred by stop_qthread_nonblocking
        try:
            drain_deferred_qthreads(timeout=2.0)
        except Exception as exc:
            logger.debug("延迟线程 drain 失败: %s", exc, exc_info=True)

        # 停止后台线程
        try:
            _thread = self._icon_cache_clean_thread
        except Exception:
            _thread = None
        if _thread is not None:
            stopped = stop_qthread_nonblocking(
                _thread,
                owner="TrayApp.icon_cache_clean",
                wait_ms=0,
                disconnect_thread_signals=("finished", "finished_signal"),
            )
            if stopped:
                self._icon_cache_clean_thread = None

        for timer_name in (
            "_settings_sync_timer",
            "_sleep_timer",
            "_deferred_startup_timer",
            "_plugin_startup_timer",
            "_memory_check_timer",
            "_process_check_timer",
            "_hook_health_timer",
        ):
            self._stop_timer_if_active(timer_name)

        try:
            cancel_event = getattr(self, "_process_check_cancel_event", None)
            if cancel_event is not None:
                cancel_event.set()
            future = getattr(self, "_process_check_future", None)
            if future is not None and future.done():
                self._process_check_cancel_event = None
            self._process_check_future = None
        except Exception as exc:
            logger.debug("取消进程应用检查失败: %s", exc, exc_info=True)

        try:
            if self._update_checker:
                self._update_checker.stop()
        except Exception as e:
            logger.debug(f"stop update checker failed: {e}")

        # 清理 Win32 全局快捷键
        try:
            self._win32_hotkey.unregister_all()
            self._win32_hotkey.remove_filter()
        except Exception as exc:
            logger.debug("清理 Win32 全局快捷键失败: %s", exc, exc_info=True)

        try:
            from core.folder_watcher import shutdown_watcher_manager

            shutdown_watcher_manager()
        except Exception as e:
            logger.debug(f"stop folder watcher failed: {e}")

        try:
            plugin_manager = getattr(self, "plugin_manager", None)
            if plugin_manager is not None:
                plugin_manager.shutdown()
        except Exception as exc:
            logger.debug("关闭插件管理器失败: %s", exc, exc_info=True)

        mouse_hook = self.mouse_hook
        self.mouse_hook = None
        if mouse_hook:
            try:
                mouse_hook.uninstall()
            except Exception as exc:
                logger.debug("卸载鼠标钩子: %s", exc, exc_info=True)

        keyboard_hook = self.keyboard_hook
        self.keyboard_hook = None
        if keyboard_hook:
            try:
                keyboard_hook.uninstall()
            except Exception as exc:
                logger.debug("卸载键盘钩子: %s", exc, exc_info=True)

        try:
            self.tray_icon.hide()
        except Exception as exc:
            logger.debug("隐藏托盘图标: %s", exc, exc_info=True)

        for attr_name in (
            "config_window",
            "popup_window",
            "log_window",
            "diagnostics_window",
            "shortcut_health_window",
            "config_history_window",
            "slash_help_window",
            "command_panel_window",
            "_toast",
        ):
            self._close_widget_if_present(attr_name)
        self._close_extra_popup_windows()
        try:
            self.data_manager.shutdown()
        except Exception as exc:
            logger.error("退出时刷新配置失败: %s", exc, exc_info=True)

        try:
            from core.executor_manager import shutdown_all_executors

            pending = shutdown_all_executors(timeout=5.0)
            if pending:
                logger.warning("退出时仍有线程池任务未完成: %s", pending)
        except Exception as exc:
            logger.error("关闭应用线程池失败: %s", exc, exc_info=True)

        try:
            from core.shortcut_command_exec import shutdown_main_thread_invoker

            shutdown_main_thread_invoker()
        except Exception as exc:
            logger.debug("关闭 MainThreadInvoker 失败: %s", exc, exc_info=True)

    def _clean_icon_cache_now(self):
        """立即执行图标缓存维护。"""
        self._wake_from_sleep("clean_icon_cache")
        try:
            if self._icon_cache_clean_thread and self._icon_cache_clean_thread.isRunning():
                self._show_toast(tr("图标缓存正在清理中"), self.data_manager.get_settings().theme)
                return True

            self._cleanup_icon_cache()

            if self.popup_window:
                try:
                    self.popup_window._icon_pixmap_cache.clear()
                    self.popup_window._icon_miss_cache.clear()
                    self.popup_window._default_icon_cache.clear()
                except Exception:
                    logger.debug("清理弹窗图标缓存失败", exc_info=True)
            for popup in list(getattr(self, "_extra_popup_windows", []) or []):
                try:
                    popup._icon_pixmap_cache.clear()
                    popup._icon_miss_cache.clear()
                    popup._default_icon_cache.clear()
                except Exception:
                    logger.debug("清理固定多开弹窗图标缓存失败", exc_info=True)

            theme = self.data_manager.get_settings().theme
            self._show_toast(tr("正在清理图标缓存..."), theme)
            from ui.tray_app import IconCacheCleanThread

            self._icon_cache_clean_thread = IconCacheCleanThread(self.data_manager)
            self._icon_cache_clean_thread.finished_signal.connect(self._on_icon_cache_clean_finished)
            # 不要把 QThread 自身的 deleteLater 挂到自己的 finished 信号上 —
            # 跟 icon_grid 同源问题，详见 test_icon_grid_file_shortcut_delete.py。
            # 线程本身由 stop_qthread_nonblocking / 进程退出统一回收。
            self._icon_cache_clean_thread.finished.connect(
                lambda thread=self._icon_cache_clean_thread: (
                    setattr(self, "_icon_cache_clean_thread", None)
                    if getattr(self, "_icon_cache_clean_thread", None) is thread
                    else None
                )
            )
            self._icon_cache_clean_thread.start()
            return True
        except Exception as e:
            logger.error("手动图标缓存清理失败: %s", e, exc_info=True)
            return False

    def _on_icon_cache_clean_finished(self, stats: dict, error: str):
        try:
            theme = self.data_manager.get_settings().theme  # type: ignore[attr-defined]
            if error:
                logger.error("手动图标缓存清理失败: %s", error)
                self._show_toast(tr("图标缓存清理失败，请查看日志"), theme)  # type: ignore[attr-defined]
                return
            removed = int(stats.get("total_removed", 0) or 0)
            freed = float(stats.get("total_size_freed_mb", 0) or 0)
            logger.info("手动图标缓存清理完成: removed=%s freed=%.2fMB", removed, freed)
            self._show_toast(  # type: ignore[attr-defined]
                tr("图标缓存已清理：{removed} 个文件，释放 {freed:.1f} MB", removed=removed, freed=freed), theme
            )
        except (RuntimeError, AttributeError, TypeError) as exc:
            logger.debug("图标缓存清理回调命中已销毁 widget: %s", exc, exc_info=True)
            return


__all__ = ["TrayAppShutdownMixin"]
