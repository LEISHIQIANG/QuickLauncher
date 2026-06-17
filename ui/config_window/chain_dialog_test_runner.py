"""Chain-dialog test-runner mixin.

Extracted from :mod:`ui.config_window.chain_dialog` as part of the
P1-06 file-split pass.  The :class:`ChainDialogTestRunnerMixin`
provides the ``_run_test`` / ``_on_test_result`` / ``_cleanup_chain_test_thread``
plumbing without dragging the rest of the dialog with it.
"""

from __future__ import annotations

import logging

from core.command_registry import CommandResult  # noqa: F401 - re-exported for tests
from core.i18n import tr

from .test_task_runner import DialogTestTask

logger = logging.getLogger(__name__)


class ChainDialogTestRunnerMixin:
    """Mixin that owns the dialog's chain-test thread lifecycle.

    The host class is expected to expose:

    * :pyattr:`result_view` — ``QPlainTextEdit`` for status output
    * :pyattr:`test_btn` / :pyattr:`clear_run_btn` — control buttons
    * :pyattr:`canvas_widget` — ``ChainCanvasWidget`` for run-status rendering
    * :pyattr:`_last_test_result` — cached ``CommandResult`` slot
    * :pyattr:`_test_thread` — current ``DialogTestTask`` slot
    * :pyattr:`parent` — must expose ``data_manager``
    * :meth:`get_shortcut` — returns the configured ``ShortcutItem``
    """

    def _run_test(self):
        self._cleanup_chain_test_thread()
        chain = self.get_shortcut()
        parent = self.parent()
        data_manager = getattr(parent, "data_manager", None)
        if data_manager is None:
            self.result_view.setPlainText(tr("错误: 无法获取数据管理器"))
            return
        self.test_btn.setEnabled(False)
        self.result_view.setPlainText(tr("正在执行..."))
        if hasattr(self, "canvas_widget"):
            self.canvas_widget.set_run_status([])
        self._test_thread = DialogTestTask(
            name="chain-dialog-test",
            callback=lambda cancel_event: self._execute_chain_test(chain, data_manager, cancel_event),
            owner=self,
        )
        self._test_thread.result_ready.connect(self._on_test_result)
        self._test_thread.start()

    def _execute_chain_test(self, chain, data_manager, cancel_event):
        try:
            from core.shortcut_chain_exec import execute_shortcut_chain

            return execute_shortcut_chain(chain, data_manager, cancel_event=cancel_event)
        except Exception as e:  # noqa: BLE001
            logger.exception("动作链测试运行失败")
            return CommandResult(success=False, message=str(e), error=str(e))

    def _on_test_result(self, result):
        self.test_btn.setEnabled(True)
        self._last_test_result = result
        lines = []
        success = getattr(result, "success", False)
        lines.append(("✓ " if success else "✗ ") + (getattr(result, "message", "") or ""))
        lines.append("")
        payload = getattr(result, "payload", None) or {}
        items = payload.get("items", [])
        if hasattr(self, "canvas_widget"):
            self.canvas_widget.set_run_status(items, payload.get("node_snapshots", {}))
        for item in items:
            status = item.get("status", "")
            icon = {"ok": "✓", "failed": "✗", "skipped": "○"}.get(status, "?")
            title = item.get("title", "")
            detail = item.get("detail", "")
            dur = item.get("duration", 0.0)
            line = f"  {icon} {title}"
            if dur > 0:
                line += f"  ({dur:.2f}s)"
            lines.append(line)
            if detail and status == "failed":
                for dl in str(detail).splitlines():
                    lines.append(f"      {dl}")
        duration = payload.get("duration", 0.0)
        if duration > 0:
            lines.append("")
            lines.append(tr("总耗时: {t:.2f}s", t=duration))
        error = getattr(result, "error", "")
        if error:
            lines.append(tr("错误: {e}", e=error))
        self.result_view.setPlainText("\n".join(lines))
        task = self._test_thread
        self._test_thread = None
        if task is not None:
            try:
                task.deleteLater()
            except Exception as exc:  # noqa: BLE001
                logger.debug("删除动作链测试任务失败: %s", exc, exc_info=True)

    def _clear_run_results(self):
        self._last_test_result = None
        if hasattr(self, "canvas_widget"):
            self.canvas_widget.set_run_status([])
        self._refresh_properties()
        self._refresh_risk_analysis()

    # ── 测试线程生命周期管理 ─────────────────────────────────────

    def _cleanup_chain_test_thread(self):
        """Comprehensive cleanup of the chain test thread, matching CommandDialog's pattern."""
        thread = getattr(self, "_test_thread", None)
        if thread is None:
            return
        try:
            thread.result_ready.disconnect(self._on_test_result)
        except Exception as exc:  # noqa: BLE001
            logger.debug("断开动作链测试信号失败: %s", exc, exc_info=True)
        try:
            thread.suppress_result_signal()
        except Exception as exc:  # noqa: BLE001
            logger.debug("抑制动作链测试结果信号失败: %s", exc, exc_info=True)
        try:
            thread.cancel()
        except Exception as exc:  # noqa: BLE001
            logger.debug("取消动作链测试线程失败: %s", exc, exc_info=True)
        if not thread.isRunning():
            try:
                thread.deleteLater()
            except Exception as exc:  # noqa: BLE001
                logger.debug("删除动作链测试线程失败: %s", exc, exc_info=True)
        else:
            try:
                thread.delete_when_finished()
            except Exception as exc:  # noqa: BLE001
                logger.debug("注册动作链测试任务异步删除失败: %s", exc, exc_info=True)
            logger.debug("动作链测试任务已请求取消，将在后台自然结束后回收")
        self._test_thread = None


__all__ = ["ChainDialogTestRunnerMixin", "CommandResult"]
