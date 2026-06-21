from __future__ import annotations

import os
import subprocess
import sys

import pytest

from bootstrap.run_modes import ApplicationBootstrap, RunMode, RunModeRouter


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["quicklauncher"], RunMode.GUI),
        (["quicklauncher", "--safe-mode"], RunMode.GUI),
        (["quicklauncher", "--plugin-helper", "worker.py"], RunMode.PLUGIN_HELPER),
        (["quicklauncher", "--plugin-worker", "worker.py"], RunMode.PLUGIN_WORKER),
        (["quicklauncher", "--smoke-test"], RunMode.SMOKE_TEST),
        (["quicklauncher", "--service-mode"], RunMode.SERVICE),
    ],
)
def test_router_parses_modes_without_loading_implementations(argv, expected):
    request = RunModeRouter().parse(argv)

    assert request.mode == expected
    assert request.safe_mode is ("--safe-mode" in argv)


def test_bootstrap_delegates_to_router():
    calls = []

    class Router:
        def parse(self, argv):
            calls.append(("parse", argv))
            return object()

        def dispatch(self, request):
            calls.append(("dispatch", request))
            return 17

    assert ApplicationBootstrap(Router()).run(["quicklauncher"]) == 17
    assert calls[0] == ("parse", ["quicklauncher"])
    assert calls[1][0] == "dispatch"


def test_plugin_worker_mode_does_not_import_qt_or_ui():
    code = """
import json, sys
from bootstrap.run_modes import RunModeRouter
request = RunModeRouter().parse(['quicklauncher', '--plugin-worker', 'worker.py'])
print(json.dumps({'mode': request.mode.value, 'qt': 'qt_compat' in sys.modules, 'ui': any(n == 'ui' or n.startswith('ui.') for n in sys.modules)}))
"""
    env = os.environ.copy()
    result = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True, env=env)

    assert result.stdout.strip() == '{"mode": "plugin-worker", "qt": false, "ui": false}'
