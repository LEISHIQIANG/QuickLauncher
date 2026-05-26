"""Minimal action-chain executor for shortcut workflows."""

from __future__ import annotations

import copy
import time
from typing import Any

from core.command_registry import CommandResult
from core.data_models import ShortcutItem, ShortcutType

MAX_CHAIN_STEPS = 50


def execute_shortcut_chain(
    chain: ShortcutItem,
    data_manager: Any = None,
    *,
    cancel_event=None,
    max_steps: int = MAX_CHAIN_STEPS,
) -> CommandResult:
    """Execute enabled chain steps sequentially and return a list report."""

    started = time.perf_counter()
    items: list[dict[str, Any]] = []
    steps = list(getattr(chain, "chain_steps", []) or [])
    success = True
    error = ""
    chain_values: dict[str, str] = {}
    previous_output = ""

    if len(steps) > max_steps:
        steps = steps[:max_steps]
        items.append(
            {
                "title": "Chain guard",
                "status": "failed",
                "detail": f"Chain has more than {max_steps} steps; extra steps were ignored.",
                "duration": 0.0,
            }
        )
        success = False
        error = f"Chain has more than {max_steps} steps."

    shortcut_map = _shortcut_map(data_manager)

    for index, step in enumerate(steps, start=1):
        title_prefix = f"{index}. "
        if not step.get("enabled", True):
            items.append(
                {
                    "title": title_prefix + _step_title(step, shortcut_map),
                    "status": "skipped",
                    "detail": "Disabled step.",
                    "duration": 0.0,
                    "shortcut_id": step.get("shortcut_id", ""),
                }
            )
            continue

        if _is_cancelled(cancel_event):
            success = False
            error = "Cancelled"
            items.append(
                {
                    "title": title_prefix + _step_title(step, shortcut_map),
                    "status": "failed",
                    "detail": "Cancelled.",
                    "duration": 0.0,
                    "shortcut_id": step.get("shortcut_id", ""),
                }
            )
            break

        delay_ms = int(step.get("delay_ms", 0) or 0)
        if delay_ms > 0 and not _sleep_with_cancel(delay_ms / 1000.0, cancel_event):
            success = False
            error = "Cancelled"
            items.append(
                {
                    "title": title_prefix + _step_title(step, shortcut_map),
                    "status": "failed",
                    "detail": "Cancelled during delay.",
                    "duration": 0.0,
                    "shortcut_id": step.get("shortcut_id", ""),
                }
            )
            break

        target = shortcut_map.get(str(step.get("shortcut_id") or ""))
        item_started = time.perf_counter()
        step_result = None
        if target is None:
            step_success = False
            detail = "Referenced shortcut was not found."
            step_error = detail
        elif target.id == chain.id or target.type == ShortcutType.CHAIN:
            step_success = False
            detail = "Nested or circular chains are not supported in MVP."
            step_error = detail
        else:
            target_for_step = target
            if target is not None:
                target_for_step = copy.copy(target)
                setattr(target_for_step, "_chain_values", dict(chain_values))
                if step.get("use_previous_output", False):
                    setattr(target_for_step, "_runtime_input_values", {"input": previous_output})
            step_success, detail, step_error, step_result = _execute_step(target_for_step, cancel_event)

        duration = time.perf_counter() - item_started
        status = "ok" if step_success else "failed"
        step_payload = getattr(step_result, "payload", {}) if step_result is not None else {}
        if not isinstance(step_payload, dict):
            step_payload = {}
        stdout = str(step_payload.get("stdout") or "")
        stderr = str(step_payload.get("stderr") or "")
        exit_code = str(step_payload.get("exit_code") if step_payload.get("exit_code") is not None else "")
        output = stdout or str(getattr(step_result, "message", "") if step_result is not None else detail or "")
        previous_output = output
        chain_values.update(
            {
                f"{index}.success": "true" if step_success else "false",
                f"{index}.exit_code": exit_code,
                f"{index}.stdout": stdout,
                f"{index}.stderr": stderr,
                f"{index}.output": output,
                "prev.success": "true" if step_success else "false",
                "prev.exit_code": exit_code,
                "prev.stdout": stdout,
                "prev.stderr": stderr,
                "prev.output": output,
            }
        )
        items.append(
            {
                "title": title_prefix
                + (getattr(target, "name", "") if target is not None else _step_title(step, shortcut_map)),
                "status": status,
                "detail": detail or step_error,
                "duration": duration,
                "shortcut_id": step.get("shortcut_id", ""),
                "error": step_error,
            }
        )
        if not step_success:
            success = False
            error = step_error or detail or "Step failed"
            if step.get("stop_on_error", True):
                break

    duration = time.perf_counter() - started
    if not steps:
        success = False
        error = "Chain has no steps."
        message = error
    elif success:
        message = f"Chain completed: {len(items)} step(s)."
    else:
        message = f"Chain finished with errors: {error}"

    crw = getattr(chain, "chain_result_window", "medium")
    window_size = crw if crw in ("small", "medium", "large") else "medium"

    return CommandResult(
        success=success,
        message=message,
        display_type="list",
        payload={"window_size": window_size, "items": items, "duration": duration},
        error=error,
    )


def _execute_step(target: ShortcutItem, cancel_event=None) -> tuple[bool, str, str, CommandResult | None]:
    from core import ShortcutExecutor

    if (
        target.type == ShortcutType.COMMAND
        and getattr(target, "command_type", "cmd") in ("cmd", "python")
        and bool(getattr(target, "capture_output", False))
        and not bool(getattr(target, "show_window", False))
        and not bool(getattr(target, "run_as_admin", False))
    ):
        try:
            result = ShortcutExecutor.run_command_capture(target, cancel_event=cancel_event)
        except TypeError:
            result = ShortcutExecutor.run_command_capture(target)
        summary = _capture_summary(result)
        return bool(result.success), summary, result.error or "", result

    ok, error = ShortcutExecutor.execute(target, False)
    return bool(ok), "Completed." if ok else str(error or "Failed."), str(error or ""), None


def _capture_summary(result: CommandResult) -> str:
    payload = result.payload if isinstance(result.payload, dict) else {}
    parts = []
    stdout = str(payload.get("stdout") or "").strip()
    stderr = str(payload.get("stderr") or "").strip()
    if stdout:
        parts.append(stdout[:500])
    if stderr:
        parts.append(("stderr: " + stderr)[:500])
    if not parts:
        parts.append(result.message or result.error or "")
    return "\n".join(part for part in parts if part)


def _shortcut_map(data_manager: Any) -> dict[str, ShortcutItem]:
    data = getattr(data_manager, "data", data_manager)
    folders = list(getattr(data, "folders", []) or [])
    mapping: dict[str, ShortcutItem] = {}
    for folder in folders:
        for item in list(getattr(folder, "items", []) or []):
            if getattr(item, "id", ""):
                mapping[item.id] = item
    return mapping


def _step_title(step: dict, shortcut_map: dict[str, ShortcutItem]) -> str:
    target = shortcut_map.get(str(step.get("shortcut_id") or ""))
    return getattr(target, "name", "") if target is not None else str(step.get("shortcut_id") or "Missing step")


def _is_cancelled(cancel_event) -> bool:
    return bool(cancel_event is not None and cancel_event.is_set())


def _sleep_with_cancel(seconds: float, cancel_event) -> bool:
    end = time.perf_counter() + max(0.0, seconds)
    while time.perf_counter() < end:
        if _is_cancelled(cancel_event):
            return False
        time.sleep(min(0.05, max(0.0, end - time.perf_counter())))
    return not _is_cancelled(cancel_event)
