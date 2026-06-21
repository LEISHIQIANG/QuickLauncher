"""Shared fixtures for all tests."""

import os
import sys
import tempfile
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
        "win32ui",
        "win32gui",
        "win32com",
        "win32com.client",
        "pythoncom",
    ]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = MagicMock()

import pytest


def pytest_configure(config):
    if os.name != "nt":
        return

    import _pytest.pathlib as pytest_pathlib
    import _pytest.tmpdir as pytest_tmpdir

    original_getbasetemp = pytest_tmpdir.TempPathFactory.getbasetemp
    if not getattr(original_getbasetemp, "_quicklauncher_windows_mode_patch", False):

        def getbasetemp_windows_compatible(self):
            if self._basetemp is not None:
                return self._basetemp

            if self._given_basetemp is not None:
                basetemp = self._given_basetemp
                if basetemp.exists():
                    pytest_pathlib.rm_rf(basetemp)
                basetemp.mkdir(mode=0o777, parents=True)
                self._basetemp = basetemp.resolve()
                self._trace("new basetemp", self._basetemp)
                return self._basetemp

            return original_getbasetemp(self)

        getbasetemp_windows_compatible._quicklauncher_windows_mode_patch = True
        pytest_tmpdir.TempPathFactory.getbasetemp = getbasetemp_windows_compatible

    original_make_numbered_dir = pytest_pathlib.make_numbered_dir
    if getattr(original_make_numbered_dir, "_quicklauncher_windows_mode_patch", False):
        return

    def make_numbered_dir_windows_compatible(root, prefix, mode=0o700):
        return original_make_numbered_dir(root, prefix, 0o777)

    make_numbered_dir_windows_compatible._quicklauncher_windows_mode_patch = True
    pytest_pathlib.make_numbered_dir = make_numbered_dir_windows_compatible
    pytest_tmpdir.make_numbered_dir = make_numbered_dir_windows_compatible

    original_mkdtemp = tempfile.mkdtemp
    if getattr(original_mkdtemp, "_quicklauncher_windows_mode_patch", False):
        return

    def mkdtemp_windows_compatible(suffix=None, prefix=None, dir=None):
        suffix = "" if suffix is None else suffix
        prefix = tempfile.gettempprefix() if prefix is None else prefix
        root = os.path.abspath(tempfile.gettempdir() if dir is None else dir)
        for name in tempfile._get_candidate_names():
            path = os.path.join(root, f"{prefix}{name}{suffix}")
            try:
                os.mkdir(path, 0o777)
            except FileExistsError:
                continue
            return path
        raise FileExistsError("no usable temporary directory name found")

    mkdtemp_windows_compatible._quicklauncher_windows_mode_patch = True
    tempfile.mkdtemp = mkdtemp_windows_compatible


@pytest.fixture(scope="module")
def qapp():
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture(autouse=True)
def _isolate_ui_scale():
    """Prevent module-global UI scale changes from leaking between tests."""
    from ui.utils.ui_scale import set_scale

    set_scale(100)
    try:
        yield
    finally:
        set_scale(100)
