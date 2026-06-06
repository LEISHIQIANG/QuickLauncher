"""Background task bridge for non-interactive dialog test runs."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from core.background_tasks import start_background_thread
from qt_compat import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class DialogTestTask(QObject):
    """Run a cancellable test callback in a registered background thread."""

    result_ready = pyqtSignal(object)

    def __init__(
        self,
        *,
        name: str,
        callback: Callable[[threading.Event], Any],
        owner: object,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._callback = callback
        self._owner = f"{owner.__class__.__module__}.{owner.__class__.__qualname__}:{id(owner)}"
        self._cancel_event = threading.Event()
        self._done_event = threading.Event()
        self._suppress_signal = False
        self._thread: threading.Thread | None = None

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel_event

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = start_background_thread(
            name=self._name,
            target=self._run,
            owner=self._owner,
        )

    def cancel(self) -> None:
        self._cancel_event.set()

    def suppress_result_signal(self) -> None:
        self._suppress_signal = True

    def isRunning(self) -> bool:  # noqa: N802 - mirrors existing caller API
        thread = self._thread
        return bool(thread and thread.is_alive() and not self._done_event.is_set())

    def wait(self, timeout_ms: int) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(max(0, timeout_ms) / 1000.0)
        return not thread.is_alive()

    def _run(self) -> None:
        try:
            result = self._callback(self._cancel_event)
        except Exception as exc:
            logger.exception("Dialog test task failed: %s", self._name)
            result = {
                "success": False,
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "error": str(exc),
                "duration": 0.0,
            }
        finally:
            self._done_event.set()
        if not self._suppress_signal:
            self.result_ready.emit(result)
