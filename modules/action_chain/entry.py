"""Action Chain module entrypoint.

The runtime still lives behind compatibility facades for now. This entrypoint
is the stable shape the host can call while the code is gradually moved under
``modules/action_chain``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.command_registry import CommandResult

MODULE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = MODULE_DIR / "module.json"


def load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class ActionChainModule:
    def __init__(self, host_api=None, manifest: dict[str, Any] | None = None):
        self.host_api = host_api
        self.manifest = dict(manifest or load_manifest())
        self.module_version = str(self.manifest.get("module_version") or "0.1.0")
        self.schema_version = int(self.manifest.get("schema_version") or 1)
        self.api_version = str(self.manifest.get("api_version") or "1.0")
        self._available = True
        self._status = "available"

    def is_available(self) -> bool:
        if self.host_api is not None and not self.host_api.check_permission("chain.runtime"):
            return False
        return bool(self._available)

    def availability_status(self) -> str:
        if self.host_api is not None and not self.host_api.check_permission("chain.runtime"):
            return "unlicensed"
        return self._status if self._available else "disabled"

    def open_editor(self, parent, chain_data: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if self.host_api is not None and not self.host_api.check_permission("chain.editor"):
            return None
        return chain_data

    def execute_chain(self, chain_data: Any, context: dict[str, Any], cancel_event=None) -> CommandResult:
        if not self.is_available():
            return unavailable_result(self.availability_status())
        from core.shortcut_chain_exec import _execute_shortcut_chain_runtime

        data_manager = dict(context or {}).get("data_manager")
        if data_manager is None and self.host_api is not None:
            data_manager = getattr(self.host_api, "data_manager", None)
        max_steps = int(dict(context or {}).get("max_steps") or 0) or None
        kwargs: dict[str, Any] = {"cancel_event": cancel_event}
        if max_steps is not None:
            kwargs["max_steps"] = max_steps
        return _execute_shortcut_chain_runtime(chain_data, data_manager, **kwargs)

    def validate_chain(self, chain_data: Any) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        steps = list(getattr(chain_data, "chain_steps", []) or [])
        if not steps:
            issues.append({"level": "error", "code": "chain.empty", "message": "动作链没有步骤。"})
        return issues

    def migrate_chain_data(self, chain_data: dict[str, Any], from_schema: int) -> dict[str, Any]:
        data = dict(chain_data or {})
        data.setdefault("schema_version", self.schema_version)
        data.setdefault("module_id", str(self.manifest.get("id") or "quicklauncher.action_chain"))
        data.setdefault("module_version", self.module_version)
        return data

    def list_processors(self) -> list[dict[str, Any]]:
        from core.chain_processors import processor_definitions

        return [
            {
                "id": item.id,
                "title": item.title,
                "category": item.category,
                "description": item.description,
                "inputs": [port.to_dict() for port in item.inputs],
                "outputs": [port.to_dict() for port in item.outputs],
                "params": [param.to_dict() for param in item.params],
                "safety": item.safety.to_dict(),
                "examples": [example.to_dict() for example in item.examples],
                "source": item.source,
            }
            for item in processor_definitions()
        ]


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
