"""Adapter that implements :class:`application.ports.search.SearchPort`.

The adapter is the only place :mod:`ui.launcher_popup.popup_search` needs
to reach the search subsystem.  It keeps the existing core helpers
running while letting the popup depend on the application port, which is
the W6.1 migration path.  Each method is a one-line forwarder so the
adapter stays auditable; behaviour changes belong in the core helpers,
not here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from application.ports.search import WebSearchAction

if TYPE_CHECKING:
    pass


class CoreSearchPortAdapter:
    """Adapter backed by ``core.fuzzy_search`` / ``core.search_engines`` etc."""

    def match(
        self,
        shortcuts: Sequence[Any],
        query: str,
        *,
        sort_mode: str = "smart",
        limit: int = 50,
    ) -> list[Any]:
        from core.fuzzy_search import search_shortcuts

        return search_shortcuts(
            shortcuts,
            query,
            sort_mode=sort_mode,
        )

    def resolve_search_url(self, query: str) -> WebSearchAction | None:
        from core.search_engines import build_search_url, parse_search_action

        action = parse_search_action(query)
        if action is None:
            return None
        return WebSearchAction(
            engine=str(action.engine),
            keyword=str(action.keyword),
            url=build_search_url(action),
        )

    def find_slash_commands(self, query: str, registry: Any = None) -> list[Any]:
        from core.slash_commands import find_matching_commands

        return find_matching_commands(query)

    def get_search_executor(self) -> Any:
        from core.executor_manager import (
            PLUGIN_SEARCH_COORDINATOR_EXECUTOR,
            get_executor,
        )

        return get_executor(PLUGIN_SEARCH_COORDINATOR_EXECUTOR)


_default_port: CoreSearchPortAdapter | None = None


def get_search_port() -> CoreSearchPortAdapter:
    """Return the process-wide :class:`SearchPort` adapter."""
    global _default_port
    if _default_port is None:
        _default_port = CoreSearchPortAdapter()
    return _default_port
