"""Action Chain module entrypoint.

The runtime still lives behind compatibility facades for now. This entrypoint
is the stable shape the host can call while the code is gradually moved under
``modules/action_chain``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.chain_canvas_adapter import canonical_canvas, chain_data_field, runtime_chain_data, validation_steps
from core.command_registry import CommandResult

logger = logging.getLogger(__name__)

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
        """Open the action-chain editor dialog.

        Args:
            parent: Parent widget for the dialog
            chain_data: Existing chain data to edit, or None for new chain

        Returns:
            Updated chain data if saved, or None if cancelled
        """
        if self.host_api is not None and not self.host_api.check_permission("chain.editor"):
            return None

        try:
            from ui.config_window.chain_dialog import ChainDialog

            dialog = ChainDialog(parent, chain_data=chain_data, host_api=self.host_api)
            result = dialog.exec_()
            if result == dialog.Accepted:
                return dialog.get_shortcut()
            return None
        except Exception as exc:
            logger.error("Failed to open action-chain editor: %s", exc, exc_info=True)
            return chain_data

    def execute_chain(self, chain_data: Any, context: dict[str, Any], cancel_event=None) -> CommandResult:
        if not self.is_available():
            return unavailable_result(self.availability_status())
        permission_result = self._check_processor_permissions(chain_data)
        if permission_result is not None:
            return permission_result
        from core.shortcut_chain_exec import _execute_shortcut_chain_runtime

        runtime_chain = runtime_chain_data(chain_data)
        data_manager = dict(context or {}).get("data_manager")
        if data_manager is None and self.host_api is not None:
            data_manager = getattr(self.host_api, "data_manager", None)
        max_steps = int(dict(context or {}).get("max_steps") or 0) or None
        kwargs: dict[str, Any] = {"cancel_event": cancel_event}
        if max_steps is not None:
            kwargs["max_steps"] = max_steps
        return _execute_shortcut_chain_runtime(runtime_chain, data_manager, **kwargs)

    def validate_chain(self, chain_data: Any) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        shortcut_map = self._shortcut_map()
        canvas = canonical_canvas(chain_data_field(chain_data, "chain_canvas", {}) or {})
        steps = validation_steps(chain_data, canvas)
        has_canvas_nodes = bool(canvas.get("nodes"))
        if not steps and not has_canvas_nodes:
            issues.append({"level": "error", "code": "chain.empty", "message": "动作链没有步骤。"})
            return issues

        for index, step in enumerate(steps, start=1):
            node_type = str(step.get("node_type") or "shortcut").strip().lower()
            if node_type == "processor":
                error = _validate_processor_step_bindings(steps, index, step, shortcut_map)
                if error:
                    issues.append(_issue("error", "chain.binding", f"步骤 {index}: {error}", step))
                continue
            shortcut_id = str(step.get("shortcut_id") or "")
            target = shortcut_map.get(shortcut_id)
            if target is None:
                issues.append(_issue("error", "chain.step.missing_shortcut", f"步骤 {index}: 引用的快捷方式不存在。", step))
                continue
            error = _validate_shortcut_step_bindings(steps, index, step, target, shortcut_map)
            if error:
                issues.append(_issue("error", "chain.binding", f"步骤 {index}: {error}", step))

        if isinstance(canvas, dict) and (canvas.get("nodes") or canvas.get("connections")):
            try:
                from core.chain_contracts import validate_canvas

                for item in validate_canvas(canvas, shortcut_map):
                    issues.append(
                        {
                            "level": "error",
                            "code": f"chain.canvas.{item.code}",
                            "message": item.message,
                            "connection_id": item.connection_id,
                        }
                    )
            except Exception as exc:
                issues.append({"level": "error", "code": "chain.canvas.validation_failed", "message": str(exc)})
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

    def _check_processor_permissions(self, chain_data: Any) -> CommandResult | None:
        if self.host_api is None:
            return None
        from core.chain_processors import processor_definition, processor_title

        canvas = canonical_canvas(chain_data_field(chain_data, "chain_canvas", {}) or {})
        for index, step in enumerate(validation_steps(chain_data, canvas), start=1):
            if str(step.get("node_type") or "shortcut").strip().lower() != "processor":
                continue
            processor_id = str(step.get("processor_id") or "")
            definition = processor_definition(processor_id)
            capability = str(getattr(getattr(definition, "safety", None), "capability", "") or "")
            if not capability:
                continue
            if _host_allows(self.host_api, capability):
                continue
            title = getattr(definition, "title", "") if definition is not None else processor_title(processor_id)
            detail = f"步骤 {index} 的处理节点未授权: {title} ({capability})"
            return CommandResult(
                success=False,
                message=detail,
                display_type="list",
                payload={
                    "items": [
                        {
                            "title": f"{index}. {title}",
                            "status": "failed",
                            "detail": detail,
                            "duration": 0.0,
                            "node_id": str(step.get("id") or f"step-{index}"),
                            "error": "permission_denied",
                        }
                    ],
                    "node_snapshots": {
                        str(step.get("id") or f"step-{index}"): {
                            "node_id": str(step.get("id") or f"step-{index}"),
                            "order": index,
                            "title": title,
                            "status": "failed",
                            "duration": 0.0,
                            "inputs": {},
                            "outputs": {},
                            "typed_inputs": {},
                            "typed_outputs": {},
                            "message": detail,
                            "error": "permission_denied",
                            "warnings": [],
                        }
                    },
                },
                error=detail,
            )
        return None

    def _shortcut_map(self) -> dict[str, Any]:
        data_manager = getattr(self.host_api, "data_manager", None)
        data = getattr(data_manager, "data", data_manager)
        folders = list(getattr(data, "folders", []) or [])
        mapping: dict[str, Any] = {}
        for folder in folders:
            for item in list(getattr(folder, "items", []) or []):
                if getattr(item, "id", ""):
                    mapping[item.id] = item
        return mapping


def _host_allows(host_api, capability: str) -> bool:
    try:
        return bool(host_api.check_permission(capability))
    except Exception:
        return False


def _validate_processor_step_bindings(steps: list[dict], index: int, step: dict, shortcut_map: dict[str, Any]) -> str:
    from core.chain_contracts import validate_step_bindings

    return validate_step_bindings(steps, index, step, None, shortcut_map)


def _validate_shortcut_step_bindings(
    steps: list[dict],
    index: int,
    step: dict,
    target: Any,
    shortcut_map: dict[str, Any],
) -> str:
    from core.chain_contracts import validate_step_bindings

    return validate_step_bindings(steps, index, step, target, shortcut_map)


def _issue(level: str, code: str, message: str, step: dict) -> dict[str, Any]:
    return {
        "level": level,
        "code": code,
        "message": message,
        "node_id": str(step.get("id") or ""),
        "shortcut_id": str(step.get("shortcut_id") or ""),
        "processor_id": str(step.get("processor_id") or ""),
    }


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
