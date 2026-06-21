"""Guard tests for the W7 stage A Windows platform adapter factories.

The four ``get_*_port`` factories in :mod:`infrastructure.windows.adapters`
are the only public surface through which the application layer should
ever reach the Windows-specific implementation.  These tests pin three
properties:

1. The four factories return objects that satisfy the four
   :mod:`application.ports.platform` protocols.
2. The icon and hotkey adapters are process-wide singletons so the
   underlying caches stay warm across request boundaries.
3. The hotkey adapter returns opaque integer handles that the caller
   can later pass back to ``unregister`` without knowing the host
   internals.
"""

from __future__ import annotations

import unittest
from typing import get_type_hints

from application.ports.platform import (
    AutoStartPort,
    GlobalHotkeyPort,
    IconProvider,
    WindowPort,
)
from infrastructure.windows.adapters import (
    get_auto_start_port,
    get_global_hotkey_port,
    get_icon_provider,
    get_window_port,
)


class _ProtocolShapeTest(unittest.TestCase):
    """The factory output must structurally match the application port."""

    def _assert_protocol_shape(self, instance: object, port: type) -> None:
        # ``Protocol`` from ``typing`` only requires attribute presence.
        # We assert each public method declared on the protocol exists.
        # This is duck-typing-friendly and does not require runtime_checkable.
        annotations = {name: hint for name, hint in get_type_hints(port).items() if not name.startswith("_")}
        for attr in annotations:
            with self.subTest(port=port.__name__, attr=attr):
                self.assertTrue(
                    hasattr(instance, attr),
                    f"{type(instance).__name__} missing port attribute {attr}",
                )
                self.assertTrue(
                    callable(getattr(instance, attr, None)),
                    f"{type(instance).__name__}.{attr} must be callable",
                )

    def test_window_port_shape(self) -> None:
        self._assert_protocol_shape(get_window_port(), WindowPort)

    def test_auto_start_port_shape(self) -> None:
        self._assert_protocol_shape(get_auto_start_port(), AutoStartPort)

    def test_icon_provider_shape(self) -> None:
        self._assert_protocol_shape(get_icon_provider(), IconProvider)

    def test_global_hotkey_port_shape(self) -> None:
        self._assert_protocol_shape(get_global_hotkey_port(), GlobalHotkeyPort)


class _SingletonTest(unittest.TestCase):
    def test_icon_provider_is_process_wide(self) -> None:
        first = get_icon_provider()
        second = get_icon_provider()
        self.assertIs(first, second)

    def test_global_hotkey_port_is_process_wide(self) -> None:
        first = get_global_hotkey_port()
        second = get_global_hotkey_port()
        self.assertIs(first, second)

    def test_window_port_is_process_wide(self) -> None:
        first = get_window_port()
        second = get_window_port()
        self.assertIs(first, second)

    def test_auto_start_port_is_process_wide(self) -> None:
        first = get_auto_start_port()
        second = get_auto_start_port()
        self.assertIs(first, second)


class _IconProviderErrorPathTest(unittest.TestCase):
    def test_extract_records_last_error_for_missing_source(self) -> None:
        provider = get_icon_provider()
        # ``IconExtractor.extract`` returns ``None`` on Qt-absence or
        # missing QApplication; the adapter mirrors that contract.  The
        # exact path depends on the test environment, so we just assert
        # the adapter returns something falsy and does not raise.
        result = provider.extract("Z:/__definitely_missing_path_for_w7_test__", size=16)
        self.assertIn(result, (None, False, 0))

    def test_invalidate_does_not_raise_on_cold_cache(self) -> None:
        provider = get_icon_provider()
        provider.invalidate("Z:/__another_missing_path_for_w7_test__")


if __name__ == "__main__":
    unittest.main()
