"""Side-effect-free run-mode parsing and lazy process dispatch."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from enum import Enum


class RunMode(str, Enum):
    GUI = "gui"
    SMOKE_TEST = "smoke-test"
    FILE_DIALOG = "file-dialog"
    PLUGIN_HELPER = "plugin-helper"
    PLUGIN_WORKER = "plugin-worker"
    INSTALL_SERVICE = "install-service"
    UNINSTALL_SERVICE = "uninstall-service"
    SERVICE = "service"
    CONFIGURE_AUTOSTART = "configure-autostart"
    AUTOSTART_HELPER = "autostart-helper"
    AUTOSTART_LAUNCH = "autostart-launch"


_MODE_FLAGS: dict[str, RunMode] = {
    "--smoke-test": RunMode.SMOKE_TEST,
    "--file-dialog": RunMode.FILE_DIALOG,
    "--plugin-helper": RunMode.PLUGIN_HELPER,
    "--plugin-worker": RunMode.PLUGIN_WORKER,
    "--install-service": RunMode.INSTALL_SERVICE,
    "--uninstall-service": RunMode.UNINSTALL_SERVICE,
    "--service-mode": RunMode.SERVICE,
    "--configure-autostart": RunMode.CONFIGURE_AUTOSTART,
    "--autostart-helper": RunMode.AUTOSTART_HELPER,
    "--autostart-launch": RunMode.AUTOSTART_LAUNCH,
}


@dataclass(frozen=True)
class RunRequest:
    mode: RunMode
    argv: tuple[str, ...]
    safe_mode: bool = False


class RunModeRouter:
    """Parse process mode without importing its implementation graph."""

    def parse(self, argv: list[str]) -> RunRequest:
        if not argv:
            argv = ["QuickLauncher"]
        safe_mode = "--safe-mode" in argv
        cleaned = tuple(arg for arg in argv if arg != "--safe-mode")
        mode = RunMode.GUI
        for arg in cleaned[1:]:
            candidate = _MODE_FLAGS.get(arg)
            if candidate is not None:
                mode = candidate
                break
        return RunRequest(mode=mode, argv=cleaned, safe_mode=safe_mode)

    def dispatch(self, request: RunRequest) -> int:
        if request.safe_mode:
            os.environ["QL_SAFE_MODE"] = "1"
        argv = list(request.argv)
        if request.mode == RunMode.GUI:
            from bootstrap.gui_application import main

            return int(main())
        if request.mode == RunMode.SMOKE_TEST:
            from bootstrap.process_handlers import run_smoke_test

            return run_smoke_test(argv)
        from bootstrap.process_handlers import run_process_mode

        return run_process_mode(request.mode, argv)


class ApplicationBootstrap:
    """Single process bootstrap used by the executable entrypoint."""

    def __init__(self, router: RunModeRouter | None = None) -> None:
        self._router = router or RunModeRouter()

    def run(self, argv: list[str] | None = None) -> int:
        request = self._router.parse(list(sys.argv if argv is None else argv))
        return self._router.dispatch(request)
