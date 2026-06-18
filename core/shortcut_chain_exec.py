"""Minimal action-chain executor for shortcut workflows."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from core.chain_canvas_adapter import runtime_steps
from core.chain_contracts import input_port_specs_for_node, output_port_specs_for_node, validate_step_bindings
from core.chain_values import ChainValue, ChainValueKind, make_chain_value, raw_value, typed_mapping
from core.command_io import (
    CommandInvocationSnapshot,
    build_output_artifact,
    chain_values_from_artifact,
    prepare_runtime_shortcut,
)
from core.command_registry import CommandResult
from core.data_models import ShortcutItem, ShortcutType
from core.runtime_constants import (
    COMMAND_CAPTURE_POLL_SECONDS,
    COMMAND_CHAIN_MAX_STEPS,
    COMMAND_CHAIN_SUMMARY_MAX_CHARS,
)

logger = logging.getLogger(__name__)

MAX_CHAIN_STEPS = COMMAND_CHAIN_MAX_STEPS
_PROCESSOR_TIMEOUT_SLOTS = threading.BoundedSemaphore(value=8)


def execute_shortcut_chain(
    chain: ShortcutItem,
    data_manager: Any = None,
    *,
    cancel_event=None,
    max_steps: int = MAX_CHAIN_STEPS,
) -> CommandResult:
    """Execute an action chain through the module boundary."""

    from core.module_registry import ACTION_CHAIN_MODULE_ID, module_registry
    from modules.action_chain.entry import unavailable_result

    record = module_registry.get(ACTION_CHAIN_MODULE_ID, data_manager=data_manager)
    api = record.api
    if api is None or not record.is_available():
        status = record.status
        if api is not None:
            try:
                status = api.availability_status()
            except Exception:
                status = record.status
        return unavailable_result(status)
    result = api.execute_chain(
        chain,
        {"data_manager": data_manager, "max_steps": max_steps},
        cancel_event=cancel_event,
    )
    if isinstance(result, CommandResult):
        return result
    return CommandResult(success=False, message="动作链模块返回了无效结果。", display_type="list", error="类型错误")


def _execute_shortcut_chain_runtime(
    chain: ShortcutItem,
    data_manager: Any = None,
    *,
    cancel_event=None,
    max_steps: int = MAX_CHAIN_STEPS,
    host_api: Any = None,
) -> CommandResult:
    """Execute enabled chain steps sequentially and return a list report."""

    started = time.perf_counter()
    items: list[dict[str, Any]] = []
    steps = runtime_steps(chain)
    success = True
    error = ""
    chain_values: dict[str, str] = {}
    typed_chain_values: dict[str, ChainValue] = {}
    previous_output = ""
    node_snapshots: dict[str, dict[str, Any]] = {}

    if len(steps) > max_steps:
        steps = steps[:max_steps]
        items.append(
            {
                "title": "动作链保护",
                "status": "failed",
                "detail": f"动作链超过 {max_steps} 个步骤，已忽略超出的步骤。",
                "duration": 0.0,
            }
        )
        success = False
        error = f"动作链超过 {max_steps} 个步骤。"

    shortcut_map = _shortcut_map(data_manager)

    for index, step in enumerate(steps, start=1):
        title_prefix = f"{index}. "
        node_id = str(step.get("id") or f"step-{index}")
        step_title = _step_title(step, shortcut_map)
        if not step.get("enabled", True):
            snapshot = _node_snapshot(
                step,
                index,
                step_title,
                "skipped",
                0.0,
                {},
                {},
                "步骤已禁用。",
                "",
            )
            node_snapshots[node_id] = snapshot
            items.append(
                {
                    "title": title_prefix + step_title,
                    "status": "skipped",
                    "detail": "步骤已禁用。",
                    "duration": 0.0,
                    "shortcut_id": step.get("shortcut_id", ""),
                    "node_id": node_id,
                }
            )
            continue

        if _is_cancelled(cancel_event):
            success = False
            error = "已取消"
            snapshot = _node_snapshot(step, index, step_title, "failed", 0.0, {}, {}, "已取消。", error)
            node_snapshots[node_id] = snapshot
            items.append(
                {
                    "title": title_prefix + step_title,
                    "status": "failed",
                    "detail": "已取消。",
                    "duration": 0.0,
                    "shortcut_id": step.get("shortcut_id", ""),
                    "node_id": node_id,
                    "error": error,
                }
            )
            break

        delay_ms = int(step.get("delay_ms", 0) or 0)
        if delay_ms > 0 and not _sleep_with_cancel(delay_ms / 1000.0, cancel_event):
            success = False
            error = "已取消"
            snapshot = _node_snapshot(step, index, step_title, "failed", 0.0, {}, {}, "等待期间已取消。", error)
            node_snapshots[node_id] = snapshot
            items.append(
                {
                    "title": title_prefix + step_title,
                    "status": "failed",
                    "detail": "等待期间已取消。",
                    "duration": 0.0,
                    "shortcut_id": step.get("shortcut_id", ""),
                    "node_id": node_id,
                    "error": error,
                }
            )
            break

        node_type = str(step.get("node_type") or "shortcut").strip().lower()
        target = shortcut_map.get(str(step.get("shortcut_id") or "")) if node_type != "processor" else None
        item_started = time.perf_counter()
        wall_started = time.time()
        step_result = None
        resolved_args: dict[str, Any] = {}
        resolved_inputs: dict[str, Any] = {}
        step_warnings: list[str] = []
        if node_type == "processor":
            contract_error = validate_step_bindings(steps, index, step, None, shortcut_map)
            if contract_error:
                step_success = False
                detail = contract_error
                step_error = contract_error
            else:
                # Get timeout from step definition (default 0 = no timeout)
                timeout_ms = int(step.get("timeout_ms", 0) or 0)
                step_success, detail, step_error, step_result, resolved_args, resolved_inputs = _execute_processor_step(
                    step,
                    chain_values,
                    typed_chain_values,
                    previous_output,
                    cancel_event=cancel_event,
                    timeout_ms=timeout_ms,
                    host_api=host_api,
                )
        elif target is None:
            step_success = False
            detail = "引用的快捷方式不存在。"
            step_error = detail
        elif target.id == chain.id or target.type in (ShortcutType.CHAIN, ShortcutType.BATCH_LAUNCH):
            step_success = False
            detail = "暂不支持嵌套或循环引用动作链。"
            step_error = detail
        else:
            contract_error = validate_step_bindings(steps, index, step, target, shortcut_map)
            if contract_error:
                step_success = False
                detail = contract_error
                step_error = contract_error
                step_result = None
                duration = time.perf_counter() - item_started
                status = "failed"
                snapshot = _node_snapshot(
                    step,
                    index,
                    getattr(target, "name", step_title),
                    status,
                    duration,
                    {},
                    {},
                    detail,
                    step_error,
                )
                node_snapshots[node_id] = snapshot
                items.append(
                    {
                        "title": title_prefix + getattr(target, "name", _step_title(step, shortcut_map)),
                        "status": status,
                        "detail": detail,
                        "duration": duration,
                        "shortcut_id": step.get("shortcut_id", ""),
                        "error": step_error,
                        "node_id": node_id,
                    }
                )
                success = False
                error = step_error
                if step.get("stop_on_error", True):
                    break
                continue
            args, input_values, prepare_error = _prepare_step_values(
                step, chain_values, typed_chain_values, previous_output
            )
            resolved_args = dict(args)
            resolved_inputs = dict(input_values)
            if prepare_error:
                binding_error = prepare_error
                target_for_step = target
            else:
                target_for_step = _prepare_runtime_step_shortcut(target, args, input_values, chain_values)
                binding_error = ""
            if binding_error:
                step_success = False
                detail = binding_error
                step_error = binding_error
            else:
                step_success, detail, step_error, step_result = _execute_step(target_for_step, cancel_event)

        duration = time.perf_counter() - item_started
        status = "ok" if step_success else "failed"
        step_payload = getattr(step_result, "payload", {}) if step_result is not None else {}
        if not isinstance(step_payload, dict):
            step_payload = {}
        artifact = build_output_artifact(
            step_result
            if step_result is not None
            else CommandResult(
                success=step_success,
                message=detail or step_error,
                error=step_error,
                payload=step_payload,
            )
        )
        output = artifact.output
        previous_output = output
        chain_values.update(chain_values_from_artifact(index, artifact))
        raw_outputs = (
            dict(step_payload.get("raw_outputs") or {}) if isinstance(step_payload.get("raw_outputs"), dict) else {}
        )
        output_kinds = _step_output_kinds(step, shortcut_map)
        typed_chain_values.update(_typed_values_from_artifact(index, artifact, raw_outputs, output_kinds))
        outputs = _artifact_outputs(artifact, raw_outputs)
        snapshot_inputs = _snapshot_inputs(resolved_args, resolved_inputs)
        snapshot = _node_snapshot(
            step,
            index,
            getattr(target, "name", "") if target is not None else step_title,
            status,
            duration,
            snapshot_inputs,
            outputs,
            detail or step_error,
            step_error,
            started_at=wall_started,
            typed_inputs=typed_mapping(snapshot_inputs, _step_input_kinds(step, shortcut_map, target)),
            typed_outputs=typed_mapping(outputs, _snapshot_output_kinds(output_kinds)),
            warnings=step_warnings,
        )
        node_snapshots[node_id] = snapshot
        items.append(
            {
                "title": title_prefix
                + (getattr(target, "name", "") if target is not None else _step_title(step, shortcut_map)),
                "status": status,
                "detail": detail or step_error,
                "duration": duration,
                "shortcut_id": step.get("shortcut_id", ""),
                "error": step_error,
                "node_id": node_id,
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
        error = "动作链没有步骤。"
        message = error
    elif success:
        message = f"动作链完成：{len(items)} 个步骤。"
    else:
        message = f"动作链执行出错：{error}"

    crw = getattr(chain, "chain_result_window", "medium")
    window_size = crw if crw in ("small", "medium", "large") else "medium"

    return CommandResult(
        success=success,
        message=message,
        display_type="list",
        payload={"window_size": window_size, "items": items, "duration": duration, "node_snapshots": node_snapshots},
        error=error,
    )


def _execute_step(target: ShortcutItem, cancel_event=None) -> tuple[bool, str, str, CommandResult | None]:
    from core import ShortcutExecutor

    runtime_files = _runtime_input_files(target)
    if runtime_files and target.type in (ShortcutType.FILE, ShortcutType.FOLDER):
        execute_with_files = getattr(ShortcutExecutor, "execute_with_files", None)
        if callable(execute_with_files):
            result = execute_with_files(target, runtime_files)
            if isinstance(result, tuple):
                ok = bool(result[0])
                error = str(result[1] or "") if len(result) > 1 else ""
            else:
                ok = bool(result)
                error = ""
            detail = f"已用输入文件打开：{len(runtime_files)} 个。" if ok else (error or "打开输入文件失败。")
            return ok, detail, "" if ok else detail, None

    if (
        target.type == ShortcutType.COMMAND
        and getattr(target, "command_type", "cmd") in ("cmd", "python", "powershell", "bash")
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
    return bool(ok), "已完成。" if ok else str(error or "执行失败。"), str(error or ""), None


def _prepare_runtime_step_shortcut(
    target: ShortcutItem,
    args: dict[str, Any],
    input_values: dict[str, Any],
    chain_values: dict[str, str],
) -> ShortcutItem:
    snapshot = CommandInvocationSnapshot(
        command_id=getattr(target, "id", ""),
        command_title=getattr(target, "name", ""),
        source="chain",
        args={key: _chain_value_to_text(value) for key, value in args.items()},
        input_values={key: _chain_value_to_text(value) for key, value in input_values.items()},
        chain_values=dict(chain_values),
    )
    return prepare_runtime_shortcut(target, snapshot)


def _prepare_step_values(
    step: dict[str, Any],
    chain_values: dict[str, str],
    typed_chain_values: dict[str, ChainValue] | None,
    previous_output: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    args: dict[str, Any] = {str(k): str(v) for k, v in dict(step.get("args") or {}).items() if str(k)}
    for param_name, binding_key in dict(step.get("param_bindings") or {}).items():
        bindings = _binding_items(binding_key)
        typed_values = dict(typed_chain_values or {})
        missing = [binding for binding in bindings if binding not in chain_values and binding not in typed_values]
        if missing:
            return args, {}, f"绑定不存在: {missing[0]} (目标端口: {param_name})"
        values = [_resolve_bound_value(binding, chain_values, typed_values) for binding in bindings]
        args[str(param_name)] = values if len(values) > 1 else (values[0] if values else "")

    input_values: dict[str, Any] = {}
    input_binding = step.get("input_binding", "")
    if not input_binding and step.get("use_previous_output", False):
        input_binding = "prev.output"
    if input_binding:
        bindings = _binding_items(input_binding)
        typed_values = dict(typed_chain_values or {})
        missing = [binding for binding in bindings if binding not in chain_values and binding not in typed_values]
        if missing:
            return args, input_values, f"绑定不存在: {missing[0]} (目标端口: input)"
        values = [_resolve_bound_value(binding, chain_values, typed_values) for binding in bindings]
        input_values["input"] = values if len(values) > 1 else (values[0] if values else "")
    elif step.get("use_previous_output", False):
        input_values["input"] = previous_output
    return args, input_values, ""


def _resolve_bound_value(binding: str, chain_values: dict[str, str], typed_chain_values: dict[str, ChainValue]) -> Any:
    typed = typed_chain_values.get(str(binding or ""))
    if typed is not None:
        return raw_value(typed)
    return chain_values.get(str(binding or ""), "")


def _binding_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _chain_value_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(_chain_value_to_text(item) for item in value)
    return "" if value is None else str(value)


def _runtime_input_files(target: ShortcutItem) -> list[str]:
    param_values = getattr(target, "_runtime_param_values", {}) or {}
    input_values = getattr(target, "_runtime_input_values", {}) or {}
    raw = param_values.get("open_file")
    if raw is None:
        raw = input_values.get("input")
    if raw is None:
        return []
    if isinstance(raw, list):
        candidates = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return []
        candidates: list[Any]  # type: ignore[no-redef]
        try:
            decoded = json.loads(text)
        except Exception:
            decoded = None
        if isinstance(decoded, list):
            candidates = decoded
        else:
            candidates = text.splitlines() if "\n" in text else [text]
    result: list[str] = []
    for item in candidates:
        path = str(item or "").strip().strip('"')
        if path:
            result.append(path)
    return result


def _execute_processor_step(
    step: dict[str, Any],
    chain_values: dict[str, str],
    typed_chain_values: dict[str, ChainValue],
    previous_output: str,
    cancel_event=None,
    timeout_ms: int = 0,
    host_api: Any = None,
) -> tuple[bool, str, str, CommandResult | None, dict[str, Any], dict[str, Any]]:
    from core.chain_processors import execute_chain_processor

    args, input_values, binding_error = _prepare_step_values(step, chain_values, typed_chain_values, previous_output)
    if binding_error:
        return False, binding_error, binding_error, None, args, input_values
    processor_args = dict(args)
    processor_args.update(input_values)

    # Check for cancellation before execution
    if _is_cancelled(cancel_event):
        return False, "已取消", "已取消", None, args, input_values

    safety_error = _processor_safety_error(step, processor_args, host_api)
    if safety_error:
        return False, safety_error, safety_error, None, args, input_values

    # Execute with timeout if specified
    if timeout_ms > 0:
        result, timeout_error = _execute_processor_with_timeout(step, processor_args, cancel_event, timeout_ms)
        if timeout_error:
            return False, timeout_error, "timeout", None, args, input_values
    else:
        result = execute_chain_processor(
            str(step.get("processor_id") or ""),
            processor_args,
            str(step.get("source") or ""),
            cancel_event=cancel_event,
        )

    return bool(result.success), _capture_summary(result), result.error or "", result, args, input_values  # type: ignore[arg-type, union-attr]


def _execute_processor_with_timeout(
    step: dict[str, Any],
    processor_args: dict[str, Any],
    cancel_event,
    timeout_ms: int,
) -> tuple[CommandResult | None, str]:
    from core.background_tasks import start_background_thread
    from core.chain_processors import execute_chain_processor

    if not _PROCESSOR_TIMEOUT_SLOTS.acquire(blocking=False):
        logger.error("动作链 processor 超时隔离槽已耗尽，拒绝启动新任务")
        return None, "后台处理器仍在退出，请稍后重试"
    done_event = threading.Event()
    processor_cancel_event = threading.Event()
    result_holder: dict[str, Any] = {}

    def _run_processor() -> None:
        try:
            result_holder["result"] = execute_chain_processor(
                str(step.get("processor_id") or ""),
                processor_args,
                str(step.get("source") or ""),
                cancel_event=processor_cancel_event,
            )
        except Exception as exc:
            result_holder["error"] = exc
        finally:
            done_event.set()
            _PROCESSOR_TIMEOUT_SLOTS.release()

    try:
        start_background_thread(
            name="chain-processor",
            target=_run_processor,
            owner="shortcut_chain_exec.processor_timeout",
        )
    except Exception:
        _PROCESSOR_TIMEOUT_SLOTS.release()
        raise
    deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
    while not done_event.is_set():
        if _is_cancelled(cancel_event):
            processor_cancel_event.set()
            return None, "已取消"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            processor_cancel_event.set()
            logger.warning(
                "动作链 processor 超时: processor=%s, timeout=%dms, cancel_event 已设置",
                str(step.get("processor_id") or ""),
                timeout_ms,
            )
            return None, f"执行超时（{timeout_ms}ms）"
        done_event.wait(min(COMMAND_CAPTURE_POLL_SECONDS, remaining))

    if "error" in result_holder:
        exc = result_holder["error"]
        return None, str(exc)
    return result_holder.get("result"), ""


def _processor_safety_error(step: dict[str, Any], processor_args: dict[str, Any], host_api: Any = None) -> str:
    if host_api is None:
        processor_id = str(step.get("processor_id") or "")
        logger.warning(
            "动作链安全检查: host_api 为空, 拒绝执行 processor=%s (node=%s)",
            processor_id,
            str(step.get("id") or ""),
        )
        return "动作链安全检查失败: 缺少主机 API 上下文，无法验证权限"
    try:
        from core.chain_processors import processor_definition, processor_title

        processor_id = str(step.get("processor_id") or "")
        definition = processor_definition(processor_id)
        safety = getattr(definition, "safety", None)
        capability = str(getattr(safety, "capability", "") or "")
        title = getattr(definition, "title", "") if definition is not None else processor_title(processor_id)
        if capability:
            allowed = bool(host_api.check_permission(capability))
            if not allowed:
                _audit_dangerous_processor(processor_id, step, title, capability, "denied")
                return f"处理节点未授权: {title} ({capability})"
        requires_confirmation = (
            bool(getattr(safety, "requires_confirmation", False)) or str(getattr(safety, "level", "")) == "dangerous"
        )
        if not requires_confirmation:
            return ""
        request = {
            "title": "确认危险动作链步骤",
            "message": f"动作链即将执行高风险处理节点: {title}",
            "details": _processor_safety_details(processor_id, processor_args, safety),
            "risk_level": str(getattr(safety, "level", "dangerous") or "dangerous"),
            "processor_id": processor_id,
            "node_id": str(step.get("id") or ""),
            "capability": capability,
        }
        confirm = getattr(host_api, "request_confirmation", None)
        if not callable(confirm):
            return f"处理节点缺少确认通道: {title}"
        confirmed = bool(confirm(request))
        if not confirmed:
            _audit_dangerous_processor(processor_id, step, title, capability, "rejected")
            return f"用户未确认高风险处理节点: {title}"
        _audit_dangerous_processor(processor_id, step, title, capability, "confirmed")
    except Exception as exc:
        return f"动作链安全检查失败: {exc}"
    return ""


def _audit_dangerous_processor(
    processor_id: str,
    step: dict[str, Any],
    title: str,
    capability: str,
    outcome: str,
) -> None:
    """Log an audit entry for dangerous processor execution attempts."""
    try:
        from core.event_log import log_event

        log_event(
            "chain.dangerous_processor",
            f"Dangerous processor {processor_id}: {outcome}",
            {
                "processor_id": processor_id,
                "node_id": str(step.get("id") or ""),
                "title": title,
                "capability": capability,
                "outcome": outcome,
            },
        )
    except Exception as exc:
        logger.debug("审计危险处理器日志失败: %s", exc, exc_info=True)


def _processor_safety_details(processor_id: str, processor_args: dict[str, Any], safety: Any) -> str:
    flags = []
    if bool(getattr(safety, "writes_files", False)):
        flags.append("写入文件")
    if bool(getattr(safety, "reads_files", False)):
        flags.append("读取文件")
    if bool(getattr(safety, "network", False)):
        flags.append("网络请求")
    if bool(getattr(safety, "executes_code", False)):
        flags.append("执行代码")
    args_preview = ", ".join(
        f"{key}={_chain_value_to_text(value)[:80]}" for key, value in list(dict(processor_args or {}).items())[:6]
    )
    parts = [f"processor={processor_id}"]
    if flags:
        parts.append("风险: " + "、".join(flags))
    if args_preview:
        parts.append("参数: " + args_preview)
    return "\n".join(parts)


def _capture_summary(result: CommandResult) -> str:
    payload = result.payload if isinstance(result.payload, dict) else {}
    parts = []
    stdout = str(payload.get("stdout") or "").strip()
    stderr = str(payload.get("stderr") or "").strip()
    if stdout:
        parts.append(stdout[:COMMAND_CHAIN_SUMMARY_MAX_CHARS])
    if stderr:
        parts.append(("stderr: " + stderr)[:COMMAND_CHAIN_SUMMARY_MAX_CHARS])
    if not parts:
        parts.append(result.message or result.error or "")
    return "\n".join(part for part in parts if part)


def _node_snapshot(
    step: dict[str, Any],
    order: int,
    title: str,
    status: str,
    duration: float,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    message: str,
    error: str,
    *,
    started_at: float = 0.0,
    typed_inputs: dict[str, Any] | None = None,
    typed_outputs: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    node_id = str(step.get("id") or f"step-{order}")
    return {
        "node_id": node_id,
        "order": order,
        "title": str(title or _step_title(step, {})),
        "status": str(status or ""),
        "started_at": float(started_at or 0.0),
        "duration": float(duration or 0.0),
        "inputs": _safe_snapshot_mapping(inputs),
        "outputs": _safe_snapshot_mapping(outputs),
        "typed_inputs": dict(typed_inputs or {}),
        "typed_outputs": dict(typed_outputs or {}),
        "message": str(message or ""),
        "error": str(error or ""),
        "warnings": [str(item) for item in list(warnings or []) if str(item)],
    }


def _snapshot_inputs(args: dict[str, Any], input_values: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in dict(args or {}).items():
        values[str(key)] = value
    for key, value in dict(input_values or {}).items():
        values[str(key)] = value
    return values


def _artifact_outputs(artifact, raw_outputs: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_outputs = dict(raw_outputs or {})
    outputs: dict[str, Any] = {
        "success": bool(artifact.success),
        "output": raw_outputs.get("output", artifact.output),
        "stdout": artifact.stdout,
        "stderr": artifact.stderr,
        "exit_code": artifact.exit_code,
        "error": artifact.error,
    }
    for key, value in dict(getattr(artifact, "outputs", {}) or {}).items():
        outputs[str(key)] = raw_outputs.get(str(key), value)
    if getattr(artifact, "files", None):
        outputs["files"] = list(artifact.files)
    if getattr(artifact, "folders", None):
        outputs["folders"] = list(artifact.folders)
    if getattr(artifact, "urls", None):
        outputs["urls"] = list(artifact.urls)
    return outputs


def _typed_values_from_artifact(
    index: int,
    artifact,
    raw_outputs: dict[str, Any],
    output_kinds: dict[str, str],
) -> dict[str, ChainValue]:
    raw_outputs = dict(raw_outputs or {})
    values: dict[str, ChainValue] = {}
    standard_values = {
        "success": bool(artifact.success),
        "exit_code": artifact.exit_code,
        "stdout": artifact.stdout,
        "stderr": artifact.stderr,
        "output": raw_outputs.get("output", artifact.output),
        "text": artifact.text,
        "error": artifact.error,
    }
    standard_kinds = {
        "success": ChainValueKind.BOOL,
        "exit_code": ChainValueKind.NUMBER,
        "stdout": ChainValueKind.TEXT,
        "stderr": ChainValueKind.TEXT,
        "output": output_kinds.get("output", ChainValueKind.TEXT),
        "text": ChainValueKind.TEXT,
        "error": ChainValueKind.TEXT,
    }
    if getattr(artifact, "json_text", ""):
        standard_values["json"] = artifact.json_text
        standard_kinds["json"] = ChainValueKind.JSON
    if getattr(artifact, "table_tsv", ""):
        standard_values["table.tsv"] = artifact.table_tsv
        standard_kinds["table.tsv"] = ChainValueKind.TEXT

    for prefix in (f"{index}", "prev"):
        for name, value in standard_values.items():
            values[f"{prefix}.{name}"] = make_chain_value(value, standard_kinds.get(name, ChainValueKind.TEXT))
        for name, value in dict(getattr(artifact, "outputs", {}) or {}).items():
            raw = raw_outputs.get(str(name), value)
            values[f"{prefix}.outputs.{name}"] = make_chain_value(raw, output_kinds.get(str(name), ChainValueKind.ANY))
        _expand_typed_list(values, prefix, "files", list(getattr(artifact, "files", []) or []), ChainValueKind.FILE)
        _expand_typed_list(
            values, prefix, "folders", list(getattr(artifact, "folders", []) or []), ChainValueKind.FOLDER
        )
        _expand_typed_list(values, prefix, "urls", list(getattr(artifact, "urls", []) or []), ChainValueKind.URL)
    return values


def _expand_typed_list(values: dict[str, ChainValue], prefix: str, name: str, items: list[str], item_kind: str) -> None:
    values[f"{prefix}.{name}.count"] = make_chain_value(len(items), ChainValueKind.NUMBER)
    values[f"{prefix}.{name}"] = make_chain_value(list(items), ChainValueKind.LIST)
    for idx, item in enumerate(items):
        values[f"{prefix}.{name}.{idx}"] = make_chain_value(item, item_kind)


def _step_input_kinds(
    step: dict[str, Any],
    shortcut_map: dict[str, ShortcutItem],
    target: ShortcutItem | None = None,
) -> dict[str, str]:
    if str(step.get("node_type") or "shortcut").strip().lower() == "processor":
        node = step
        shortcuts = shortcut_map
    elif target is not None:
        node = {"node_type": "shortcut", "shortcut_id": target.id}
        shortcuts = {target.id: target}
    else:
        node = step
        shortcuts = shortcut_map
    return {spec.id: spec.kind for spec in input_port_specs_for_node(node, shortcuts)}


def _step_output_kinds(step: dict[str, Any], shortcut_map: dict[str, ShortcutItem]) -> dict[str, str]:
    return {spec.id: spec.kind for spec in output_port_specs_for_node(step, shortcut_map)}


def _snapshot_output_kinds(output_kinds: dict[str, str]) -> dict[str, str]:
    kinds = dict(output_kinds or {})
    kinds.update(
        {
            "success": ChainValueKind.BOOL,
            "stdout": ChainValueKind.TEXT,
            "stderr": ChainValueKind.TEXT,
            "exit_code": ChainValueKind.NUMBER,
            "error": ChainValueKind.TEXT,
            "files": ChainValueKind.LIST,
            "folders": ChainValueKind.LIST,
            "urls": ChainValueKind.LIST,
        }
    )
    kinds.setdefault("output", ChainValueKind.TEXT)
    return kinds


def _safe_snapshot_mapping(values: dict[str, Any], *, max_chars: int = 4000) -> dict[str, Any]:
    result: dict[str, Any] = {}
    used = 0
    for key, value in dict(values or {}).items():
        text = _chain_value_to_text(value)
        remaining = max_chars - used
        if remaining <= 0:
            result["__truncated__"] = "true"
            break
        if len(text) > remaining:
            text = text[:remaining]
            result["__truncated__"] = "true"
        result[str(key)] = text
        used += len(text)
    return result


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
    if str(step.get("node_type") or "shortcut").strip().lower() == "processor":
        try:
            from core.chain_processors import processor_title

            return processor_title(str(step.get("processor_id") or ""))
        except Exception:
            return str(step.get("processor_id") or "处理节点")
    target = shortcut_map.get(str(step.get("shortcut_id") or ""))
    return getattr(target, "name", "") if target is not None else str(step.get("shortcut_id") or "Missing step")


def _is_cancelled(cancel_event) -> bool:
    return bool(cancel_event is not None and cancel_event.is_set())


def _sleep_with_cancel(seconds: float, cancel_event) -> bool:
    end = time.perf_counter() + max(0.0, seconds)
    while time.perf_counter() < end:
        if _is_cancelled(cancel_event):
            return False
        time.sleep(min(COMMAND_CAPTURE_POLL_SECONDS, max(0.0, end - time.perf_counter())))
    return not _is_cancelled(cancel_event)
