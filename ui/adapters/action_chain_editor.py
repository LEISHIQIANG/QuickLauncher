"""Qt implementation of the action-chain editor host port."""

from __future__ import annotations

from typing import Any

from core.data_models import ShortcutItem
from ui.config_window.chain_dialog import ChainDialog


def open_action_chain_editor(
    parent: Any,
    chain_data: dict[str, Any] | None,
    host_api: Any,
) -> dict[str, Any] | None:
    shortcut = ShortcutItem.from_dict(chain_data) if isinstance(chain_data, dict) else None
    dialog = ChainDialog(parent, shortcut)
    if dialog.exec_() == dialog.Accepted:
        return dialog.get_shortcut().to_dict()
    return None
