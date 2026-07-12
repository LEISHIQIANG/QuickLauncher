"""Presentation contract shared by command-panel helper modules.

The concrete Qt window owns widgets and lifecycle. Focused renderer modules
depend on this structural view boundary instead of importing the window back.
"""

from __future__ import annotations

from typing import Any, Protocol


class CommandPanelView(Protocol):
    """Structural view surface used during the controller migration."""

    _all_actions: Any
    _current_input_values: Any
    _current_result: Any
    _history_menu: Any
    _input_param_names: Any
    _param_widgets: Any
    _rendered_text: Any

    def __getattr__(self, name: str) -> Any: ...
