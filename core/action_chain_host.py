"""Host-side adapter for the action-chain module."""

from __future__ import annotations

import logging
from typing import Any

from core.command_registry import CommandResult
from core.data_models import ShortcutItem, ShortcutType
from core.version import APP_VERSION

logger = logging.getLogger(__name__)


class DefaultActionChainHostAPI:
    host_version = APP_VERSION
    api_version = "1.0"

    def __init__(self, data_manager: Any = None):
        self.data_manager = data_manager

    def list_shortcuts(self) -> list[dict[str, Any]]:
        return [
            {
                "id": getattr(item, "id", ""),
                "name": getattr(item, "name", ""),
                "type": getattr(getattr(item, "type", ""), "value", getattr(item, "type", "")),
                "enabled": bool(getattr(item, "enabled", True)),
            }
            for item in self._shortcut_map().values()
        ]

    def get_shortcut(self, shortcut_id: str) -> ShortcutItem | None:
        return self._shortcut_map().get(str(shortcut_id or ""))

    def execute_shortcut(self, shortcut_id: str, invocation: dict[str, Any], cancel_event=None) -> dict[str, Any]:
        from core.shortcut_chain_exec import _execute_step

        target = self.get_shortcut(shortcut_id)
        if target is None:
            return {"success": False, "message": "引用的快捷方式不存在。", "error": "missing_shortcut"}
        if target.type in (ShortcutType.CHAIN, ShortcutType.BATCH_LAUNCH):
            return {"success": False, "message": "暂不支持嵌套或循环引用动作链。", "error": "nested_chain"}
        success, detail, error, result = _execute_step(target, cancel_event=cancel_event)
        payload = getattr(result, "payload", {}) if result is not None else {}
        return {
            "success": bool(success),
            "message": detail,
            "error": error,
            "payload": payload if isinstance(payload, dict) else {},
        }

    def get_settings(self) -> dict[str, Any]:
        data = getattr(self.data_manager, "data", self.data_manager)
        settings = getattr(data, "settings", None)
        to_dict = getattr(settings, "to_dict", None)
        if callable(to_dict):
            return to_dict()
        return {}

    def get_theme(self) -> str:
        return str(self.get_settings().get("theme") or "dark")

    def show_toast(self, message: str, level: str = "info") -> None:
        logger.info("action_chain_toast[%s]: %s", level, message)

    def choose_file(self, options: dict[str, Any]) -> str:
        return ""

    def choose_folder(self, options: dict[str, Any]) -> str:
        return ""

    def log_event(self, event: dict[str, Any]) -> None:
        logger.info("action_chain_event: %s", event)

    def check_permission(self, capability: str) -> bool:
        return True

    def request_confirmation(self, request: dict[str, Any]) -> bool:
        return True

    def _shortcut_map(self) -> dict[str, ShortcutItem]:
        data = getattr(self.data_manager, "data", self.data_manager)
        folders = list(getattr(data, "folders", []) or [])
        mapping: dict[str, ShortcutItem] = {}
        for folder in folders:
            for item in list(getattr(folder, "items", []) or []):
                if getattr(item, "id", ""):
                    mapping[item.id] = item
        return mapping


def command_result_to_host_dict(result: CommandResult) -> dict[str, Any]:
    return {
        "success": bool(result.success),
        "message": str(result.message or ""),
        "error": str(result.error or ""),
        "display_type": str(result.display_type or "text"),
        "payload": dict(result.payload or {}),
    }
