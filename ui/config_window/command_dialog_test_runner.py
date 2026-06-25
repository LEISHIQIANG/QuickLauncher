"""Command-dialog test-runner mixin.

Extracted from :mod:`ui.config_window.command_dialog` as part of the
P1-06 file-split pass.  The :class:`CommandDialogTestRunnerMixin`
provides the ``_test_command`` / ``_show_test_result`` /
``_cleanup_command_test_thread`` plumbing and the ``done`` override
that triggers cleanup.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from .test_task_runner import DialogTestTask

logger = logging.getLogger(__name__)


class CommandDialogTestRunnerMixin:
    """Mixin that owns the dialog's command-test thread lifecycle.

    The host class is expected to expose:

    * :pyattr:`type_combo` — index 4 means "builtin", tests are skipped
    * :pyattr:`test_output` — ``QPlainTextEdit`` for status output
    * :pyattr:`_test_btn` — run-test button
    * :pyattr:`capture_timeout_spin` — ``QSpinBox`` with timeout in seconds
    * :pyattr:`_command_test_thread` — current ``DialogTestTask``
    * :pyattr:`_dialog_finished` — set by ``QDialog`` when finished
    * :pyattr:`shortcut` — configured ``ShortcutItem`` (used to kill
      any orphaned test subprocess)
    """

    def _test_command(self):
        host = cast(Any, self)
        if host.type_combo.currentIndex() == 4:
            return
        if host._command_test_thread is not None and host._command_test_thread.isRunning():
            return
        shortcut = host._build_preview_shortcut()
        host.test_output.setVisible(True)
        host.adjustSize()
        if not shortcut.command:
            host.test_output.setPlainText("命令内容为空。")
            return
        inputs = host._collect_runtime_inputs(shortcut.command) if shortcut.command_variables_enabled else {}
        if inputs is None:
            host.test_output.setPlainText("测试运行已取消。")
            return
        if inputs:
            from core.command_io import CommandInvocationSnapshot, prepare_runtime_shortcut

            shortcut = prepare_runtime_shortcut(
                shortcut,
                CommandInvocationSnapshot(
                    command_id=getattr(shortcut, "id", ""),
                    command_title=getattr(shortcut, "name", ""),
                    input_values=dict(inputs),
                ),
            )

        host._cleanup_command_test_thread()
        host._test_btn.setEnabled(False)
        host.test_output.setPlainText("正在测试...")
        timeout = float(host.capture_timeout_spin.value())

        def run_command_test(cancel_event):
            from core import ShortcutExecutor

            if not ShortcutExecutor:
                return {
                    "success": False,
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "",
                    "error": "执行器不可用，请检查运行环境依赖。",
                    "duration": 0.0,
                }
            return ShortcutExecutor.test_command(shortcut, timeout=timeout, cancel_event=cancel_event)

        host._command_test_thread = DialogTestTask(
            name="command-dialog-test",
            callback=run_command_test,
            owner=host,
        )
        host._command_test_thread.result_ready.connect(host._show_test_result)
        host._command_test_thread.start()

    def _show_test_result(self, result: dict):
        try:
            host = cast(Any, self)
            if host._dialog_finished or not hasattr(host, "test_output") or not hasattr(host, "_test_btn"):
                return
            lines = [
                f"状态: {'成功' if result.get('success') else '失败'}",
                f"退出码: {result.get('exit_code')}",
                f"耗时: {result.get('duration', 0):.2f}s",
            ]
            if result.get("resolved_command"):
                lines.extend(["", "最终命令:", str(result.get("resolved_command"))])
            if result.get("error"):
                lines.extend(["", "错误:", str(result.get("error"))])
            if result.get("stdout"):
                lines.extend(["", "stdout:", str(result.get("stdout"))])
            if result.get("stderr"):
                lines.extend(["", "stderr:", str(result.get("stderr"))])
            host.test_output.setPlainText("\n".join(lines))
            host._test_btn.setEnabled(host.type_combo.currentIndex() != 4)
            task = host._command_test_thread
            host._command_test_thread = None
            if task is not None:
                try:
                    task.deleteLater()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("删除命令测试任务失败: %s", exc, exc_info=True)
        except (RuntimeError, AttributeError, TypeError) as exc:  # noqa: BLE001
            logger.debug("命令测试结果回调命中已销毁 widget: %s", exc, exc_info=True)
            return

    def done(self, result):
        self._cleanup_command_test_thread()
        super().done(result)

    def _cleanup_command_test_thread(self):
        # 强制终止正在后台测试的挂起子进程（如果有），避免垃圾子进程泄露
        if hasattr(self, "shortcut") and self.shortcut:
            try:
                process = getattr(self.shortcut, "_active_test_process", None)
                if process and process.poll() is None:
                    process.kill()
                    try:
                        process.wait(timeout=1.0)
                        logger.info("测试后台挂起子进程已被成功强制终止清理")
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("子进程终止超时: %s", exc, exc_info=True)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"清理挂起子进程时发生异常: {e}")

        thread = getattr(self, "_command_test_thread", None)
        if thread is None:
            return
        try:
            thread.result_ready.disconnect(self._show_test_result)
        except Exception as exc:  # noqa: BLE001
            logger.debug("断开信号失败: %s", exc, exc_info=True)
        try:
            thread.suppress_result_signal()
            thread.cancel()
        except Exception as exc:  # noqa: BLE001
            logger.debug("取消测试线程失败: %s", exc, exc_info=True)
        if not thread.isRunning():
            try:
                thread.deleteLater()
            except Exception as exc:  # noqa: BLE001
                logger.debug("删除线程失败: %s", exc, exc_info=True)
        else:
            try:
                thread.delete_when_finished()
            except Exception as exc:  # noqa: BLE001
                logger.debug("注册命令测试任务异步删除失败: %s", exc, exc_info=True)
            logger.debug("命令测试任务已请求取消，将在后台自然结束后回收")
        self._command_test_thread = None


__all__ = ["CommandDialogTestRunnerMixin"]
