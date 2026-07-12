"""Application ports for popup search and engine integration.

The popup search is the most-consumed UI surface in QuickLauncher; today
it reaches into :mod:`core.fuzzy_search`, :mod:`core.search_engines`,
:mod:`core.slash_commands` and :mod:`core.executor_manager` directly
(75 UI files × 226 ``from core.*`` import sites, 8 of which live in
``ui/launcher_popup/popup_search.py``).  W6.1 of the optimisation plan
asks for the UI to consume these services through application ports so
the popup depends on contracts, not on implementations.

The protocol here is intentionally narrow.  It exposes the four
operations the popup needs:

* ``match(query, shortcuts)`` — fuzzy match against the live shortcut list
* ``resolve_search_url(query)`` — turn a search-engine query into a
  structured :class:`WebSearchAction` (engine / keyword / url)
* ``find_slash_commands(query)`` — match ``/command`` invocations
* ``get_search_executor()`` — hand out a thread-pool executor that
  matches the cross-process lifecycle (the W3 executor is owned by
  :class:`core.executor_manager.ExecutorManager`)

Each operation is a thin forwarder to the historical core helper, but
the popup only ever imports this module.  Moving the heavy lifting into
adapters is the path the rest of W6.1 will follow; the present module
keeps every call shape identical to the existing core API so the popup
can migrate one call at a time.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class WebSearchAction:
    """Structured return value for :meth:`SearchPort.resolve_search_url`.

    The popup displays both the URL (so the user can open the search
    results in the default browser) and the originating engine plus the
    matched keyword (so the synthetic shortcut can be named
    ``"google: foo"`` instead of an opaque URL).  Returning a structured
    value lets the port stay framework-independent and keeps the popup
    off the historical :class:`core.search_engines.SearchAction` type.
    """

    engine: str
    keyword: str
    url: str


class SearchPort(Protocol):
    """The four call shapes the popup needs from the search subsystem."""

    def match(
        self,
        shortcuts: Sequence[Any],
        query: str,
        *,
        sort_mode: str = "smart",
        limit: int = 50,
    ) -> list[Any]:
        """Return fuzzy matches against ``shortcuts`` for ``query``.

        ``sort_mode`` matches the historical
        :func:`core.fuzzy_search.search_shortcuts` signature so existing
        callers can pass through their current keyword arguments without
        any per-call adaptation.
        """

    def resolve_search_url(self, query: str) -> WebSearchAction | None:
        """Return a :class:`WebSearchAction` for ``query`` (``None`` if no action).

        The popup uses both the resolved URL *and* the originating
        engine / keyword to display ``"google: foo"`` as the shortcut
        name, so the port returns a structured value rather than just
        the URL string.  Callers that only want the URL should read
        :attr:`WebSearchAction.url`.
        """

    def find_slash_commands(self, query: str, registry: Any = None) -> list[Any]:
        """Return slash-command matches for ``query``.

        ``registry`` is the historical
        :class:`core.command_registry.CommandRegistry` injected by the
        popup; the port forwards it so the underlying
        :func:`core.slash_commands.find_matching_commands` call can
        continue to look up command names without the popup knowing
        about the registry type.
        """

    def get_search_executor(self) -> Any:
        """Return the long-lived search coordinator executor."""
