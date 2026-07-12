"""Batch-launch executor."""

from __future__ import annotations

import logging
import time
from typing import Any

from core.command_registry import CommandResult
from core.data_models import ShortcutItem, ShortcutType
from core.runtime_constants import COMMAND_CHAIN_MAX_STEPS

logger = logging.getLogger(__name__)


def execute_batch_launch(
    batch: ShortcutItem,
    data_manager: Any = None,
    *,
    cancel_event=None,
    max_steps: int = COMMAND_CHAIN_MAX_STEPS,
) -> CommandResult:
    """Execute a batch-launch shortcut by starting each referenced shortcut in order."""

    from core import ShortcutExecutor

    started = time.perf_counter()
    steps = ShortcutItem._normalize_chain_steps(getattr(batch, "batch_launch_steps", None) or [])
    items: list[dict[str, Any]] = []
    shortcut_map = _shortcut_map(data_manager)
    success = True
    error = ""

    logger.info(
        "开始批量启动: id=%s name=%r steps=%s",
        getattr(batch, "id", ""),
        getattr(batch, "name", ""),
        len(steps),
    )

    if len(steps) > max_steps:
        steps = steps[:max_steps]
        success = False
        error = f"批量启动超过 {max_steps} 个项目，已忽略超出的项目。"
        items.append({"title": "批量启动保护", "status": "failed", "detail": error, "duration": 0.0})

    for index, step in enumerate(steps, start=1):
        title_prefix = f"{index}. "
        if not step.get("enabled", True):
            items.append(
                {
                    "title": title_prefix + "已禁用项目",
                    "status": "skipped",
                    "detail": "项目已禁用。",
                    "duration": 0.0,
                    "shortcut_id": step.get("shortcut_id", ""),
                }
            )
            continue

        if _is_cancelled(cancel_event):
            success = False
            error = "已取消"
            items.append(
                {
                    "title": title_prefix + "已取消",
                    "status": "failed",
                    "detail": "批量启动已取消。",
                    "duration": 0.0,
                    "shortcut_id": step.get("shortcut_id", ""),
                    "error": error,
                }
            )
            break

        delay_ms = int(step.get("delay_ms", 0) or 0)
        if delay_ms > 0 and not _sleep_with_cancel(delay_ms / 1000.0, cancel_event):
            success = False
            error = "已取消"
            items.append(
                {
                    "title": title_prefix + "等待",
                    "status": "failed",
                    "detail": "等待期间已取消。",
                    "duration": 0.0,
                    "shortcut_id": step.get("shortcut_id", ""),
                    "error": error,
                }
            )
            break

        shortcut_id = str(step.get("shortcut_id") or "")
        target = shortcut_map.get(shortcut_id)
        item_started = time.perf_counter()
        title = title_prefix + (getattr(target, "name", "") if target is not None else shortcut_id or "缺失项目")

        if target is None:
            ok = False
            detail = "引用的快捷方式不存在。"
            logger.warning(
                "批量启动引用缺失: batch_id=%s step=%s shortcut_id=%s",
                getattr(batch, "id", ""),
                index,
                shortcut_id,
            )
        elif target.id == batch.id or target.type == ShortcutType.BATCH_LAUNCH:
            ok = False
            detail = "暂不支持嵌套或循环引用批量启动。"
            logger.warning(
                "批量启动拒绝嵌套或循环引用: batch_id=%s step=%s target_id=%s target_type=%s",
                getattr(batch, "id", ""),
                index,
                getattr(target, "id", ""),
                getattr(getattr(target, "type", ""), "value", getattr(target, "type", "")),
            )
        else:
            ok, detail = ShortcutExecutor.execute(target, False)
            detail = "已启动。" if ok else (detail or "启动失败。")
            if not ok:
                logger.warning(
                    "批量启动项目失败: batch_id=%s step=%s target_id=%s target_name=%r error=%s",
                    getattr(batch, "id", ""),
                    index,
                    getattr(target, "id", ""),
                    getattr(target, "name", ""),
                    detail,
                )

        duration = time.perf_counter() - item_started
        items.append(
            {
                "title": title,
                "status": "ok" if ok else "failed",
                "detail": detail,
                "duration": duration,
                "shortcut_id": shortcut_id,
                "error": "" if ok else detail,
            }
        )
        if not ok:
            success = False
            error = detail
            if step.get("stop_on_error", True):
                break

    duration = time.perf_counter() - started
    if not steps:
        success = False
        error = "批量启动没有项目。"
        logger.warning("批量启动为空: id=%s name=%r", getattr(batch, "id", ""), getattr(batch, "name", ""))
    message = "批量启动已完成。" if success else error or "批量启动失败。"
    logger.info(
        "批量启动结束: id=%s name=%r success=%s duration=%.3fs error=%s",
        getattr(batch, "id", ""),
        getattr(batch, "name", ""),
        success,
        duration,
        error,
    )
    return CommandResult(
        success=success,
        message=message,
        display_type="list",
        error="" if success else error,
        payload={"items": items, "duration": duration, "kind": "batch_launch"},
    )


def _shortcut_map(data_manager: Any) -> dict[str, ShortcutItem]:
    data = getattr(data_manager, "data", data_manager)
    result: dict[str, ShortcutItem] = {}
    for folder in list(getattr(data, "folders", []) or []):
        for item in list(getattr(folder, "items", []) or []):
            shortcut_id = str(getattr(item, "id", "") or "")
            if shortcut_id:
                result[shortcut_id] = item
    return result


def _is_cancelled(cancel_event) -> bool:
    return bool(cancel_event is not None and cancel_event.is_set())


def _sleep_with_cancel(seconds: float, cancel_event) -> bool:
    if seconds <= 0:
        return True
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        if _is_cancelled(cancel_event):
            return False
        time.sleep(min(0.05, max(0.0, deadline - time.perf_counter())))
    return not _is_cancelled(cancel_event)
