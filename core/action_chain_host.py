"""Host-side adapter for the action-chain module.

This module provides the ``DefaultActionChainHostAPI`` class which implements
the ``ActionChainHostAPI`` protocol defined in
``modules/action_chain/host_contracts.py``. It acts as a bridge between the
action-chain module and the main application, encapsulating all access to
internal data structures.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core.command_registry import CommandResult
from core.data_models import ShortcutItem, ShortcutType
from core.version import APP_VERSION

logger = logging.getLogger(__name__)


class DefaultActionChainHostAPI:
    """Default implementation of the ActionChainHostAPI protocol.

    This class provides all host capabilities that the action-chain module
    needs, without exposing internal data structures directly.
    """

    host_version = APP_VERSION
    api_version = "1.0"

    def __init__(self, data_manager: Any = None):
        self.data_manager = data_manager

    # ── Shortcut access ────────────────────────────────────────────────

    def list_shortcuts(self) -> list[dict[str, Any]]:
        """Return a list of all shortcuts as lightweight dicts."""
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
        """Return a single shortcut by ID, or None if not found."""
        return self._shortcut_map().get(str(shortcut_id or ""))

    def execute_shortcut(self, shortcut_id: str, invocation: dict[str, Any], cancel_event=None) -> dict[str, Any]:
        """Execute a shortcut and return a result dict.

        Returns:
            Dict with keys: success, message, error, payload
        """
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

    # ── Settings and theme ─────────────────────────────────────────────

    def get_settings(self) -> dict[str, Any]:
        """Return the current application settings as a dict."""
        data = getattr(self.data_manager, "data", self.data_manager)
        settings = getattr(data, "settings", None)
        to_dict = getattr(settings, "to_dict", None)
        if callable(to_dict):
            return to_dict()
        return {}

    def get_theme(self) -> str:
        """Return the current theme name ('dark' or 'light')."""
        return str(self.get_settings().get("theme") or "dark")

    # ── UI interactions ────────────────────────────────────────────────

    def show_toast(self, message: str, level: str = "info") -> None:
        """Show a toast notification to the user."""
        logger.info("action_chain_toast[%s]: %s", level, message)

    def choose_file(self, options: dict[str, Any]) -> str:
        """Open a file chooser dialog and return the selected path.

        Args:
            options: Dict with optional keys:
                - title: Dialog title
                - filter: File type filter (e.g., "Images (*.png *.jpg)")
                - default_dir: Default directory to open

        Returns:
            Selected file path, or empty string if cancelled.
        """
        return ""

    def choose_folder(self, options: dict[str, Any]) -> str:
        """Open a folder chooser dialog and return the selected path.

        Args:
            options: Dict with optional keys:
                - title: Dialog title
                - default_dir: Default directory to open

        Returns:
            Selected folder path, or empty string if cancelled.
        """
        return ""

    # ── Logging ────────────────────────────────────────────────────────

    def log_event(self, event: dict[str, Any]) -> None:
        """Log an action-chain event for diagnostics."""
        logger.info("action_chain_event: %s", event)

    # ── Permissions and confirmation ───────────────────────────────────

    def check_permission(self, capability: str) -> bool:
        """Check if the host allows the given capability.

        Args:
            capability: Capability string (e.g., "chain.runtime",
                "chain.editor", "chain.script_cell")

        Returns:
            True if the capability is allowed.
        """
        return True

    def request_confirmation(self, request: dict[str, Any]) -> bool:
        """Request user confirmation for a dangerous operation.

        Args:
            request: Dict with keys:
                - title: Confirmation dialog title
                - message: Description of the operation
                - details: Optional detailed explanation
                - risk_level: "caution" or "dangerous"

        Returns:
            True if the user confirmed.
        """
        return True

    # ── Internal helpers ───────────────────────────────────────────────

    def _shortcut_map(self) -> dict[str, ShortcutItem]:
        """Build a mapping of shortcut ID -> ShortcutItem."""
        data = getattr(self.data_manager, "data", self.data_manager)
        folders = list(getattr(data, "folders", []) or [])
        mapping: dict[str, ShortcutItem] = {}
        for folder in folders:
            for item in list(getattr(folder, "items", []) or []):
                if getattr(item, "id", ""):
                    mapping[item.id] = item
        return mapping


def command_result_to_host_dict(result: CommandResult) -> dict[str, Any]:
    """Convert a CommandResult to a plain dict for the host API boundary."""
    return {
        "success": bool(result.success),
        "message": str(result.message or ""),
        "error": str(result.error or ""),
        "display_type": str(result.display_type or "text"),
        "payload": dict(result.payload or {}),
    }
