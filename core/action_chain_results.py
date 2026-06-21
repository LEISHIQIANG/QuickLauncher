"""Host result factories shared with the action-chain module boundary."""

from __future__ import annotations

from core.command_registry import CommandResult


def unavailable_result(status: str) -> CommandResult:
    messages = {
        "disabled": "动作链模块已禁用。",
        "unlicensed": "动作链模块未授权。",
        "missing": "动作链模块文件缺失。",
        "incompatible": "动作链模块与当前主程序版本不兼容。",
        "broken": "动作链模块加载失败。",
    }
    detail = messages.get(str(status or ""), "动作链模块不可用。")
    return CommandResult(
        success=False,
        message=detail,
        display_type="list",
        payload={
            "items": [
                {
                    "title": "动作链模块",
                    "status": "failed",
                    "detail": detail,
                    "duration": 0.0,
                    "error": str(status or "unavailable"),
                }
            ]
        },
        error=detail,
    )
