"""Execution service for the independent command panel."""

from __future__ import annotations

import concurrent.futures
import inspect
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.command_io import (
    CommandInvocationSnapshot,
    build_invocation_snapshot,
    build_output_artifact,
    command_params_from_shortcut,
    has_sensitive_args,
    prepare_runtime_shortcut,
    remembered_args,
)
from core.command_param_validation import validate_param_values
from core.command_registry import CommandContext, CommandDefinition, CommandResult
from core.command_results import CommandResultStore
from core.data_models import ShortcutItem
from core.executor_manager import COMMAND_EXECUTOR, ManagedExecutor, get_executor, shutdown_executor

logger = logging.getLogger(__name__)


@dataclass
class CommandExecutionRequest:
    command_id: str = ""
    args_text: str = ""
    raw_input: str = ""
    context_meta: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    shortcut: ShortcutItem | None = None
    args: dict[str, str] = field(default_factory=dict)
    command_def: CommandDefinition | None = None
    invocation: CommandInvocationSnapshot | None = None


class CommandExecutionHandle:
    """Cancelable handle for a command-panel execution.

    The handle wraps a cooperative ``threading.Event`` for cancellation and
    optionally tracks the underlying ``concurrent.futures.Future`` so callers
    can query status, wait for completion, or register callbacks.
    """

    def __init__(self, request_id: str | None = None):
        self.request_id = request_id or str(uuid.uuid4())
        self._cancel_event = threading.Event()
        self._future: concurrent.futures.Future | None = None
        self._start_time = time.perf_counter()

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel_event

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since handle creation."""
        return time.perf_counter() - self._start_time

    @property
    def is_done(self) -> bool:
        return self._future is not None and self._future.done()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for the underlying future to complete. Returns True if done."""
        if self._future is None:
            return True
        done, _pending = concurrent.futures.wait([self._future], timeout=timeout)
        return self._future in done

    def _bind_future(self, future: concurrent.futures.Future) -> None:
        self._future = future


class CommandExecutionService:
    """Run registry, captured shortcut, and chain commands; persist final results.

    All asynchronous executions are submitted to a bounded ``ThreadPoolExecutor``
    instead of creating ad-hoc daemon threads.  This gives the application a
    predictable concurrency ceiling and a single place to implement graceful
    shutdown.
    """

    @classmethod
    def _get_shared_pool(cls) -> ManagedExecutor:
        return get_executor(COMMAND_EXECUTOR)

    @classmethod
    def shutdown_shared_executor(cls, timeout: float = 5.0) -> None:
        """Shut down the process-wide command execution pool."""
        shutdown_executor(COMMAND_EXECUTOR, timeout=timeout)

    def __init__(
        self,
        result_store: CommandResultStore | None = None,
        executor: concurrent.futures.Executor | None = None,
    ):
        self.result_store = result_store
        self._pool = executor or type(self)._get_shared_pool()
        self._owns_pool = executor is not None
        self._active_futures: dict[str, concurrent.futures.Future] = {}
        self._active_handles: dict[str, CommandExecutionHandle] = {}
        self._futures_lock = threading.Lock()

    # ── internal helpers ──────────────────────────────────────────

    def _submit_worker(
        self,
        worker: Callable[[], None],
        name_prefix: str,
        request_id: str,
        handle: CommandExecutionHandle | None = None,
    ) -> concurrent.futures.Future:
        """Submit *worker* to the shared pool and track the future."""
        future = self._pool.submit(worker)
        with self._futures_lock:
            self._active_futures[request_id] = future
            if handle is not None:
                self._active_handles[request_id] = handle

        def _cleanup(fut: concurrent.futures.Future, rid: str = request_id) -> None:
            with self._futures_lock:
                self._active_futures.pop(rid, None)
                self._active_handles.pop(rid, None)

        future.add_done_callback(_cleanup)
        return future

    def shutdown(self, timeout: float = 5.0, *, shutdown_executor: bool = False) -> None:
        """Gracefully shut down the execution pool.

        Waits up to *timeout* seconds for this service's active tasks, cancels
        their callbacks cooperatively, and optionally closes the underlying
        executor when this service owns it.
        """
        with self._futures_lock:
            handles = list(self._active_handles.values())
            futures = list(self._active_futures.values())
        for handle in handles:
            handle.cancel()
        if futures:
            concurrent.futures.wait(futures, timeout=max(0.0, float(timeout or 0.0)))
        with self._futures_lock:
            pending = [rid for rid, fut in self._active_futures.items() if not fut.done()]
        if pending:
            logger.warning("CommandExecutionService shutdown: %d tasks still pending: %s", len(pending), pending)
        for future in futures:
            if not future.done():
                future.cancel()
        if shutdown_executor or self._owns_pool:
            if self._owns_pool:
                self._pool.shutdown(wait=False, cancel_futures=True)
            else:
                type(self).shutdown_shared_executor(timeout=timeout)

    @property
    def active_count(self) -> int:
        """Number of currently tracked active futures."""
        with self._futures_lock:
            return sum(1 for fut in self._active_futures.values() if not fut.done())

    def run_registry_command(
        self,
        request: CommandExecutionRequest,
        *,
        on_update: Callable[[str, CommandResult, CommandDefinition | None], None] | None = None,
        on_finished: Callable[[str, CommandResult, CommandDefinition | None, float, str], None] | None = None,
    ) -> CommandExecutionHandle:
        handle = CommandExecutionHandle()
        command_def = request.command_def or self._lookup_command(request.command_id)
        invocation = build_invocation_snapshot(request, command_def, request.shortcut)

        def _worker() -> None:
            started = time.perf_counter()
            try:
                if command_def is None:
                    raise ValueError(f"Command not found: {request.command_id}")

                def _update(result: CommandResult) -> None:
                    if not handle.cancelled and on_update is not None:
                        on_update(handle.request_id, result, command_def)

                validation = self._validate_command_params(command_def, invocation.args)
                if validation is not None:
                    result = validation
                else:
                    ctx = CommandContext(
                        raw_input=invocation.raw_input,
                        args_text=invocation.args_text,
                        args=dict(invocation.args or {}),
                        clipboard_text=invocation.clipboard_text,
                        clipboard_kind=invocation.clipboard_kind,
                        clipboard_files=list(invocation.clipboard_files or []),
                        clipboard_html=invocation.clipboard_html,
                        selected_text=invocation.selected_text,
                        selected_text_method=invocation.selected_text_method,
                        selected_files=list(invocation.selected_files or []),
                        context_meta=dict(invocation.context_meta or {}),
                        update_callback=_update,
                    )
                    result = command_def.handler(ctx)
                if not isinstance(result, CommandResult):
                    result = CommandResult(
                        success=False, message="Command returned an invalid result.", error="类型错误"
                    )
            except Exception as e:
                logger.exception("Command execution failed: %s", e)
                result = CommandResult(success=False, message=f"Command failed: {e}", error=str(e))

            duration = time.perf_counter() - started
            if handle.cancelled:
                return
            try:
                result_id = self._store_result(request, result, command_def, duration)
                if on_finished is not None:
                    on_finished(handle.request_id, result, command_def, duration, result_id)
            except Exception as post_err:
                logger.exception("Post-execution processing failed: %s", post_err)
                if on_finished is not None:
                    try:
                        on_finished(handle.request_id, result, command_def, duration, "")
                    except Exception:
                        logger.debug("on_finished fallback callback failed", exc_info=True)

        future = self._submit_worker(_worker, "CmdExec", handle.request_id, handle)
        handle._bind_future(future)
        return handle

    def run_shortcut_capture(
        self,
        request: CommandExecutionRequest,
        *,
        on_finished: Callable[[str, CommandResult, CommandDefinition | None, float, str], None] | None = None,
    ) -> CommandExecutionHandle:
        handle = CommandExecutionHandle()

        def _worker() -> None:
            result, duration, result_id = self.execute_shortcut_capture_sync(request, handle)
            if handle.cancelled and not self._is_cancel_result(result):
                return
            if on_finished is not None:
                try:
                    on_finished(handle.request_id, result, None, duration, result_id)
                except Exception:
                    logger.debug("run_shortcut_capture on_finished callback failed", exc_info=True)

        future = self._submit_worker(_worker, "ShortcutCapture", handle.request_id, handle)
        handle._bind_future(future)
        return handle

    def run_shortcut_chain(
        self,
        request: CommandExecutionRequest,
        *,
        on_finished: Callable[[str, CommandResult, CommandDefinition | None, float, str], None] | None = None,
    ) -> CommandExecutionHandle:
        handle = CommandExecutionHandle()

        def _worker() -> None:
            result, duration, result_id = self.execute_shortcut_chain_sync(request, handle)
            if handle.cancelled and not self._is_cancel_result(result):
                return
            if on_finished is not None:
                try:
                    on_finished(handle.request_id, result, None, duration, result_id)
                except Exception:
                    logger.debug("run_shortcut_chain on_finished callback failed", exc_info=True)

        future = self._submit_worker(_worker, "ShortcutChain", handle.request_id, handle)
        handle._bind_future(future)
        return handle

    def run_shortcut_command(
        self,
        request: CommandExecutionRequest,
        *,
        on_update: Callable[[str, CommandResult, CommandDefinition | None], None] | None = None,
        on_finished: Callable[[str, CommandResult, CommandDefinition | None, float, str], None] | None = None,
    ) -> CommandExecutionHandle:
        handle = CommandExecutionHandle()

        def _worker() -> None:
            result, duration, result_id = self.execute_shortcut_command_sync(request, handle, on_update=on_update)
            if handle.cancelled and not self._is_cancel_result(result):
                return
            if on_finished is not None:
                try:
                    on_finished(handle.request_id, result, None, duration, result_id)
                except Exception:
                    logger.debug("run_shortcut_command on_finished callback failed", exc_info=True)

        future = self._submit_worker(_worker, "ShortcutCommand", handle.request_id, handle)
        handle._bind_future(future)
        return handle

    def execute_shortcut_capture_sync(
        self,
        request: CommandExecutionRequest,
        handle: CommandExecutionHandle | None = None,
    ) -> tuple[CommandResult, float, str]:
        """Run a captured shortcut in the caller's thread and store the result."""
        handle = handle or CommandExecutionHandle()
        started = time.perf_counter()
        invocation = build_invocation_snapshot(request, None, request.shortcut)
        runtime_shortcut = (
            prepare_runtime_shortcut(request.shortcut, invocation) if request.shortcut is not None else None
        )
        try:
            from core import ShortcutExecutor

            # 检查函数签名以决定是否传递 cancel_event，避免宽泛 except TypeError
            _fn = ShortcutExecutor.run_command_capture
            if "cancel_event" in inspect.signature(_fn).parameters:
                result = _fn(runtime_shortcut, cancel_event=handle.cancel_event)
            else:
                result = _fn(runtime_shortcut)
        except Exception as e:
            logger.exception("Captured shortcut execution failed: %s", e)
            result = CommandResult(
                success=False, message=f"Captured command failed: {e}", display_type="log", error=str(e)
            )
        duration = time.perf_counter() - started
        result_id = self._store_result(request, result, None, duration)
        return result, duration, result_id

    def execute_shortcut_command_sync(
        self,
        request: CommandExecutionRequest,
        handle: CommandExecutionHandle | None = None,
        on_update: Callable[[str, CommandResult, CommandDefinition | None], None] | None = None,
    ) -> tuple[CommandResult, float, str]:
        handle = handle or CommandExecutionHandle()
        started = time.perf_counter()
        invocation = build_invocation_snapshot(request, None, request.shortcut)
        runtime_shortcut = (
            prepare_runtime_shortcut(request.shortcut, invocation) if request.shortcut is not None else None
        )
        try:
            from core import ShortcutExecutor

            shortcut = runtime_shortcut
            if (
                shortcut is not None
                and getattr(shortcut, "command_type", "cmd") in ("cmd", "python", "powershell", "bash")
                and not bool(getattr(shortcut, "show_window", False))
                and not bool(getattr(shortcut, "run_as_admin", False))
            ):

                def _update(result: CommandResult) -> None:
                    if not handle.cancelled and on_update is not None:
                        on_update(handle.request_id, result, None)

                result = ShortcutExecutor.run_command_capture(
                    shortcut,
                    cancel_event=handle.cancel_event,
                    on_update=_update if on_update is not None else None,
                )
            else:
                ok, err = ShortcutExecutor.execute(shortcut, False)
                result = CommandResult(
                    success=bool(ok),
                    message="命令已启动。" if ok else str(err or "命令执行失败。"),
                    display_type="text",
                    error="" if ok else str(err or "命令执行失败。"),
                )
        except Exception as e:
            logger.exception("Shortcut command execution failed: %s", e)
            result = CommandResult(success=False, message=f"Command failed: {e}", display_type="log", error=str(e))
        duration = time.perf_counter() - started
        result_id = self._store_result(request, result, None, duration)
        return result, duration, result_id

    def execute_shortcut_chain_sync(
        self,
        request: CommandExecutionRequest,
        handle: CommandExecutionHandle | None = None,
    ) -> tuple[CommandResult, float, str]:
        """Run an action chain in the caller's thread and store the result."""
        handle = handle or CommandExecutionHandle()
        started = time.perf_counter()
        invocation = build_invocation_snapshot(request, None, request.shortcut)
        runtime_shortcut = (
            prepare_runtime_shortcut(request.shortcut, invocation) if request.shortcut is not None else None
        )
        try:
            from core.shortcut_chain_exec import execute_shortcut_chain

            result = execute_shortcut_chain(
                runtime_shortcut,  # type: ignore[arg-type]
                request.context_meta.get("data_manager"),
                cancel_event=handle.cancel_event,
            )
        except Exception as e:
            logger.exception("Shortcut chain execution failed: %s", e)
            result = CommandResult(
                success=False, message=f"Action chain failed: {e}", display_type="list", error=str(e)
            )
        duration = time.perf_counter() - started
        result_id = self._store_result(request, result, None, duration)
        return result, duration, result_id

    def _store_result(
        self,
        request: CommandExecutionRequest,
        result: CommandResult,
        command_def: CommandDefinition | None,
        duration: float,
    ) -> str:
        if self.result_store is None:
            return ""
        invocation = build_invocation_snapshot(request, command_def, request.shortcut)
        params = list(getattr(command_def, "params", []) or [])
        if not params and request.shortcut is not None:
            params = command_params_from_shortcut(request.shortcut)
        artifact = build_output_artifact(result)
        return self.result_store.add(
            result,
            command_id=getattr(command_def, "id", request.command_id),
            command_title=getattr(command_def, "title", "")
            or getattr(request.shortcut, "name", "")
            or request.command_id,
            raw_input=request.raw_input,
            source=getattr(command_def, "source", request.source or ""),
            duration=duration,
            args=remembered_args(invocation.args, params),
            masked_args=invocation.masked_args,
            has_sensitive_args=has_sensitive_args(invocation.args, params),
            context_meta=invocation.context_meta,
            outputs=artifact.outputs,
        )

    @staticmethod
    def _is_cancel_result(result: CommandResult) -> bool:
        text = f"{result.error or ''} {result.message or ''}".lower()
        return "cancel" in text or "已取消" in text

    @staticmethod
    def _lookup_command(command_id: str) -> CommandDefinition | None:
        if not command_id:
            return None
        try:
            from core import registry

            if registry is not None:
                result = registry.get(command_id) or registry.get(registry.get_canonical(command_id))
                if result is not None:
                    return result  # type: ignore[no-any-return]
                return None
        except Exception:
            logger.debug("Command lookup failed: %s", command_id, exc_info=True)
        return None

    @staticmethod
    def _validate_command_params(command_def: CommandDefinition, args: dict[str, str]) -> CommandResult | None:
        errors = validate_param_values(list(getattr(command_def, "params", []) or []), dict(args or {}))
        if not errors:
            return None
        items = [{"title": "命令参数", "status": "failed", "detail": error} for error in errors]
        return CommandResult(
            success=False,
            message="\n".join(errors),
            display_type="list",
            payload={"items": items},
            error="参数校验失败",
        )
