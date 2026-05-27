"""Execution service for the independent command panel."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from core.command_registry import CommandContext, CommandDefinition, CommandResult
from core.command_results import CommandResultStore
from core.data_models import ShortcutItem

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


class CommandExecutionHandle:
    """Cancelable handle for a command-panel execution."""

    def __init__(self, request_id: str | None = None):
        self.request_id = request_id or str(uuid.uuid4())
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel_event


class CommandExecutionService:
    """Run registry, captured shortcut, and chain commands; persist final results."""

    def __init__(self, result_store: CommandResultStore | None = None):
        self.result_store = result_store

    def run_registry_command(
        self,
        request: CommandExecutionRequest,
        *,
        on_update: Callable[[str, CommandResult, CommandDefinition | None], None] | None = None,
        on_finished: Callable[[str, CommandResult, CommandDefinition | None, float, str], None] | None = None,
    ) -> CommandExecutionHandle:
        handle = CommandExecutionHandle()
        command_def = request.command_def or self._lookup_command(request.command_id)

        def _worker() -> None:
            started = time.perf_counter()
            try:
                if command_def is None:
                    raise ValueError(f"Command not found: {request.command_id}")

                def _update(result: CommandResult) -> None:
                    if not handle.cancelled and on_update is not None:
                        on_update(handle.request_id, result, command_def)

                ctx = CommandContext(
                    raw_input=request.raw_input,
                    args_text=request.args_text,
                    args=dict(request.args or {}),
                    clipboard_text=str((request.context_meta or {}).get("clipboard_text") or ""),
                    selected_files=list((request.context_meta or {}).get("selected_files") or []),
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
            result_id = self._store_result(request, result, command_def, duration)
            if on_finished is not None:
                on_finished(handle.request_id, result, command_def, duration, result_id)

        threading.Thread(target=_worker, daemon=True, name="CommandExecutionService").start()
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
                on_finished(handle.request_id, result, None, duration, result_id)

        threading.Thread(target=_worker, daemon=True, name="ShortcutCaptureService").start()
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
                on_finished(handle.request_id, result, None, duration, result_id)

        threading.Thread(target=_worker, daemon=True, name="ShortcutChainService").start()
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
                on_finished(handle.request_id, result, None, duration, result_id)

        threading.Thread(target=_worker, daemon=True, name="ShortcutCommandService").start()
        return handle

    def execute_shortcut_capture_sync(
        self,
        request: CommandExecutionRequest,
        handle: CommandExecutionHandle | None = None,
    ) -> tuple[CommandResult, float, str]:
        """Run a captured shortcut in the caller's thread and store the result."""
        handle = handle or CommandExecutionHandle()
        started = time.perf_counter()
        try:
            from core import ShortcutExecutor

            result = ShortcutExecutor.run_command_capture(request.shortcut, cancel_event=handle.cancel_event)
        except TypeError:
            from core import ShortcutExecutor

            result = ShortcutExecutor.run_command_capture(request.shortcut)
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
        try:
            from core import ShortcutExecutor

            shortcut = request.shortcut
            if shortcut is not None and request.args:
                setattr(shortcut, "_runtime_param_values", dict(request.args))
            if (
                shortcut is not None
                and getattr(shortcut, "command_type", "cmd") in ("cmd", "python", "powershell")
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
        try:
            from core.shortcut_chain_exec import execute_shortcut_chain

            result = execute_shortcut_chain(
                request.shortcut,
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
        return self.result_store.add(
            result,
            command_id=getattr(command_def, "id", request.command_id),
            command_title=getattr(command_def, "title", "")
            or getattr(request.shortcut, "name", "")
            or request.command_id,
            raw_input=request.raw_input,
            source=getattr(command_def, "source", request.source or ""),
            duration=float(duration or 0.0),
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
                return registry.get(command_id) or registry.get(registry.get_canonical(command_id))
        except Exception:
            logger.debug("Command lookup failed: %s", command_id, exc_info=True)
        return None
