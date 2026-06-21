"""Guard tests for the W6.1 ``SearchPort`` adapter.

The popup currently imports four core helpers (fuzzy_search,
search_engines, slash_commands, executor_manager) directly.  W6.1 asks
the popup to depend on the application port instead.  This test pins
the contract of the adapter and demonstrates the import path; the
follow-up work is to migrate the four call sites in
``ui/launcher_popup/popup_search.py`` to consume this port.
"""

from __future__ import annotations

import unittest
from typing import get_type_hints

from application.ports.search import SearchPort
from ui.adapters.search_port_adapter import CoreSearchPortAdapter, get_search_port


class _SearchPortShapeTest(unittest.TestCase):
    def _assert_protocol_shape(self, instance: object, port: type) -> None:
        annotations = {name: hint for name, hint in get_type_hints(port).items() if not name.startswith("_")}
        for attr in annotations:
            with self.subTest(port=port.__name__, attr=attr):
                self.assertTrue(hasattr(instance, attr))
                self.assertTrue(callable(getattr(instance, attr)))

    def test_factory_returns_search_port(self) -> None:
        self._assert_protocol_shape(get_search_port(), SearchPort)

    def test_direct_construction_satisfies_protocol(self) -> None:
        self._assert_protocol_shape(CoreSearchPortAdapter(), SearchPort)


class _SearchPortSingletonTest(unittest.TestCase):
    def test_get_search_port_is_process_wide(self) -> None:
        first = get_search_port()
        second = get_search_port()
        self.assertIs(first, second)


class _SearchPortResilienceTest(unittest.TestCase):
    def test_resolve_search_url_for_empty_query(self) -> None:
        port = get_search_port()
        # Empty query has no parsed action; the adapter returns
        # ``None`` which is the contract popup_search already depends
        # on.  A non-empty query, in contrast, must yield a structured
        # ``WebSearchAction`` with a usable URL.
        empty_action = port.resolve_search_url("")
        self.assertIsNone(empty_action)
        non_empty = port.resolve_search_url("google hello world")
        self.assertIsNotNone(non_empty)
        self.assertTrue(non_empty.url)
        self.assertTrue(non_empty.engine)
        self.assertTrue(non_empty.keyword)

    def test_find_slash_commands_for_empty_query(self) -> None:
        port = get_search_port()
        commands = port.find_slash_commands("")
        self.assertIsInstance(commands, list)

    def test_get_search_executor_returns_a_managed_executor(self) -> None:
        port = get_search_port()
        executor = port.get_search_executor()
        # The W3 shared executor protocol guarantees an object with a
        # ``submit`` method; we do not pin the concrete type so adapter
        # implementations can swap the backend without test churn.
        self.assertTrue(hasattr(executor, "submit"))


if __name__ == "__main__":
    unittest.main()
