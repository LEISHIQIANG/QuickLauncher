"""Shared fixtures for all tests."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="module")
def qapp():
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    return app
