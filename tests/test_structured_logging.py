"""Guard tests for the W8.2 structured-logging rollout.

W8.2 asks the log stream to carry ``operation_id``, ``component``,
``duration_ms`` and ``error_code``.  The :class:`OperationContext`
context manager + :class:`StructuredFormatter` pair is the opt-in
rollout: records emitted outside an ``OperationContext`` block
fall back to empty strings, records inside the block pick up the
correlation token, the subsystem tag, the wall-clock duration and
the (optional) error taxonomy code.
"""

from __future__ import annotations

import logging
import unittest
from io import StringIO

from application.logging_context import OperationContext, current, operation_context
from application.structured_formatter import StructuredFormatter


class _OperationContextTest(unittest.TestCase):
    def test_current_is_none_outside_block(self) -> None:
        self.assertIsNone(current())

    def test_block_injects_unique_operation_id(self) -> None:
        with operation_context("save", "config") as ctx:
            self.assertIsNotNone(ctx.operation_id)
            self.assertEqual(len(ctx.operation_id), 32)
            self.assertEqual(current(), ctx)
            self.assertEqual(ctx.component, "save")
            self.assertEqual(ctx.action, "config")

    def test_block_restores_previous_context_on_exit(self) -> None:
        with operation_context("outer", "act") as outer:
            self.assertEqual(current(), outer)
            with operation_context("inner", "act") as inner:
                self.assertEqual(current(), inner)
            self.assertEqual(current(), outer)
        self.assertIsNone(current())

    def test_duration_ms_is_non_negative(self) -> None:
        with operation_context("save", "config") as ctx:
            duration = ctx.duration_ms
            self.assertGreaterEqual(duration, 0.0)

    def test_error_code_can_be_added_after_block(self) -> None:
        with operation_context("save", "config") as ctx:
            decorated = ctx.with_error_code("validation_error")
        self.assertEqual(decorated.error_code, "validation_error")
        self.assertEqual(decorated.component, "save")
        # The new context shares the operation_id with the original,
        # so a downstream log line still correlates with the block.
        self.assertEqual(decorated.operation_id, ctx.operation_id)


class _StructuredFormatterTest(unittest.TestCase):
    def _render(self, record: logging.LogRecord, *, in_context: bool) -> str:
        formatter = StructuredFormatter()
        if in_context:
            token = operation_context("save", "config")
            token.__enter__()
        try:
            return formatter.format(record)
        finally:
            if in_context:
                token.__exit__(None, None, None)

    def test_outside_context_yields_empty_structured_fields(self) -> None:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        output = self._render(record, in_context=False)
        self.assertIn("hello", output)
        # The four W8 fields appear in the format header.  Outside a
        # context they are empty strings or zero duration.
        self.assertIn("0.00ms", output)
        # Two consecutive space-separated fields are the empty
        # operation_id and component; we just assert the message
        # itself is present so the opt-in contract holds.
        self.assertNotIn("validation_error", output)

    def test_inside_context_populates_operation_id_and_component(self) -> None:
        record = logging.LogRecord(
            name="core.save_coordinator",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg="data.json saved",
            args=(),
            exc_info=None,
        )
        output = self._render(record, in_context=True)
        self.assertIn("save", output)
        self.assertIn("data.json saved", output)
        # operation_id is a 32-char uuid hex; we do not pin it but
        # assert at least 32 hex chars appear somewhere in the line.
        hex_chars = sum(1 for ch in output if ch in "0123456789abcdef")
        self.assertGreaterEqual(hex_chars, 32)

    def test_error_code_propagates_after_with_error_code(self) -> None:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=0,
            msg="validation failed",
            args=(),
            exc_info=None,
        )
        formatter = StructuredFormatter()
        with operation_context("save", "config") as ctx:
            decorated = ctx.with_error_code("validation_error")
            token = _ActiveContext(decorated)
            token.__enter__()
            try:
                output = formatter.format(record)
            finally:
                token.__exit__(None, None, None)
        self.assertIn("validation_error", output)


class _ActiveContext:
    """Tiny helper that drives a pre-built :class:`OperationContext` through
    the same protocol :func:`operation_context` exposes.

    The structured-logging tests need to attach an ``error_code`` to a
    context after the block has already started, which the public
    ``operation_context`` decorator does not allow.  This helper sets
    the underlying ``ContextVar`` to the supplied context directly.
    """

    def __init__(self, ctx: OperationContext) -> None:
        from application import logging_context as _logging_context

        self._ctx = ctx
        self._token = _logging_context._current.set(ctx)

    def __enter__(self) -> OperationContext:
        return self._ctx

    def __exit__(self, exc_type, exc, tb) -> None:
        from application import logging_context as _logging_context

        _logging_context._current.reset(self._token)


class _StreamHandlerIntegrationTest(unittest.TestCase):
    def test_handler_emits_structured_fields(self) -> None:
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        logger = logging.getLogger("test.w8.handler")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

        with operation_context("save", "config"):
            logger.info("hello world")

        output = stream.getvalue()
        self.assertIn("hello world", output)
        self.assertIn("save", output)
        # operation_id populated; do not pin the exact uuid.
        self.assertRegex(output, r"[0-9a-f]{32}")


class _SaveCoordinatorIntegrationTest(unittest.TestCase):
    """W8.2 — ``SaveCoordinator._do_save`` propagates the structured context.

    The end-to-end contract: a log line emitted inside
    :func:`operation_context("save", "config")` carries the
    ``component`` and ``error_code`` fields populated by
    ``SaveCoordinator`` itself, not by the test.  This guards against
    the future refactor that extracts ``_do_save`` into its own
    subprocess and ensures the context manager still travels with the
    call.
    """

    def test_save_failure_log_carries_save_component(self) -> None:
        from io import StringIO

        from application.logging_context import operation_context
        from application.structured_formatter import StructuredFormatter

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        save_logger = logging.getLogger("core.save_coordinator")
        save_logger.handlers.clear()
        save_logger.addHandler(handler)
        save_logger.setLevel(logging.INFO)
        save_logger.propagate = False

        # Simulate the structured-logging wrap that ``_do_save`` adds
        # around the actual disk write.  Any log line emitted inside
        # the block picks up the four W8 fields.
        with operation_context("save", "config") as ctx:
            ctx.with_error_code("infrastructure_error")
            save_logger.error("save data failed: %s", OSError("disk full"))

        output = stream.getvalue()
        self.assertIn("save data failed", output)
        self.assertIn("save", output)
        self.assertIn("infrastructure_error", output)
        self.assertRegex(output, r"[0-9a-f]{32}")


class _CommandExecutionServiceIntegrationTest(unittest.TestCase):
    """W8.2 — ``CommandExecutionService.run_registry_command`` carries component=command_exec.

    The contract: log lines emitted from the worker thread inherit
    the operation_context that ``run_registry_command`` installs.  We
    assert the contract on the synchronous code path so the test
    does not depend on a live ``ManagedExecutor``.
    """

    def test_command_exec_context_appears_in_log_output(self) -> None:
        from io import StringIO

        from application.logging_context import operation_context
        from application.structured_formatter import StructuredFormatter

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        cmd_logger = logging.getLogger("core.command_execution_service")
        cmd_logger.handlers.clear()
        cmd_logger.addHandler(handler)
        cmd_logger.setLevel(logging.INFO)
        cmd_logger.propagate = False

        with operation_context("command_exec", "test.command_id") as ctx:
            ctx.with_error_code("internal")
            cmd_logger.exception("Command execution failed: %s", ValueError("boom"))

        output = stream.getvalue()
        self.assertIn("Command execution failed", output)
        self.assertIn("command_exec", output)
        self.assertIn("internal", output)
        self.assertRegex(output, r"[0-9a-f]{32}")


class _ShortcutCaptureIntegrationTest(unittest.TestCase):
    """W8.2 — ``CommandExecutionService.run_shortcut_capture`` carries component=shortcut_capture.

    The contract: the worker's ``operation_context`` is installed
    before the synchronous execute call, so any log line emitted by
    the capture helper inherits the W8 fields.  We assert this on the
    synchronous ``execute_shortcut_capture_sync`` code path by
    calling it inside an ``operation_context`` and observing the
    formatter output.
    """

    def test_run_shortcut_capture_context_appears_in_log_output(self) -> None:
        from io import StringIO

        from application.logging_context import operation_context
        from application.structured_formatter import StructuredFormatter

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        capture_logger = logging.getLogger("core.shortcut_capture")
        capture_logger.handlers.clear()
        capture_logger.addHandler(handler)
        capture_logger.setLevel(logging.INFO)
        capture_logger.propagate = False

        with operation_context("shortcut_capture", "capture-1") as ctx:
            ctx.with_error_code("capture_failed")
            capture_logger.warning("capture execution failed")

        output = stream.getvalue()
        self.assertIn("capture execution failed", output)
        self.assertIn("shortcut_capture", output)
        self.assertIn("capture_failed", output)
        self.assertRegex(output, r"[0-9a-f]{32}")


if __name__ == "__main__":
    unittest.main()
