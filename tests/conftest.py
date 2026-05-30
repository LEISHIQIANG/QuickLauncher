"""Shared fixtures for all tests."""

import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Block pynput from importing its native keyboard backend on headless CI runners.
# pynput's platform-specific backends can hang or crash without an interactive
# desktop session, which blocks pytest collection indefinitely.
if os.environ.get("CI") or os.environ.get("PYTEST_CURRENT_TEST"):
    for mod_name in [
        "pynput",
        "pynput.keyboard",
        "pynput.keyboard._win32",
        "pynput._util",
        "pynput._util.win32",
    ]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = MagicMock()

import pytest


@pytest.fixture(scope="module")
def qapp():
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    return app
