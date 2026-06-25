"""Base classes for QThread + QObject worker patterns with error handling.

Provides ``BaseLoggedWorker`` (structured error reporting + cancellation) and
``WorkerController`` (generation counter + thread lifecycle), reducing
boilerplate across UI icon-loading and favicon-fetching workers.
"""

from __future__ import annotations

import logging

from qt_compat import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class BaseLoggedWorker(QObject):
    """Base worker with structured error reporting and cancellation.

    Subclass must override ``run()``.  Callers connect to ``completed``
    and optionally ``error_occurred``.
    """

    error_occurred = pyqtSignal(str)
    completed = pyqtSignal()

    def __init__(self, name: str = "") -> None:
        super().__init__()
        self._name = name or self.__class__.__name__
        self._cancel_requested = False

    def cancel(self) -> None:
        """Request cooperative cancellation.  Subclasses should check
        ``self._cancel_requested`` at natural breakpoints."""
        self._cancel_requested = True

    @property
    def worker_name(self) -> str:
        return self._name

    def run(self) -> None:
        """Override with the actual work.  Base class wraps the call in
        a try/except that emits ``error_occurred`` on failure."""
        raise NotImplementedError

    # ── COM helpers for icon workers ────────────────────────────────────

    @staticmethod
    def com_initialize() -> bool:
        """Initialize COM for this thread.  Returns True on success."""
        try:
            import pythoncom

            pythoncom.CoInitialize()
            return True
        except Exception as exc:
            logger.debug("COM初始化: %s", exc, exc_info=True)
            return False

    @staticmethod
    def com_uninitialize() -> None:
        """Uninitialize COM for this thread."""
        try:
            import pythoncom

            pythoncom.CoUninitialize()
        except Exception as exc:
            logger.debug("COM反初始化: %s", exc, exc_info=True)


class WorkerController:
    """Manages generation counter + thread lifecycle for one QThread.

    Usage::

        controller = WorkerController(owner=self, name="icon-loader")
        controller.start(worker_factory, tasks)

    The controller owns the generation counter, stops any prior thread,
    wires the worker's ``completed`` signal to the thread's ``quit``,
    and cleans up references when the thread finishes.
    """

    def __init__(self, owner: object, name: str) -> None:
        self._owner = owner
        self._name = name
        # Generation & refs stored on the owner object via unique attrs
        self._gen_attr = f"_{name}_generation"
        self._thread_attr = f"_{name}_thread"
        self._worker_attr = f"_{name}_worker"

    def start(
        self,
        worker: BaseLoggedWorker,
    ) -> None:
        """Stop the prior thread, create a new QThread+worker, and start it.

        The worker is moved to the new QThread.  ``worker.completed``
        triggers ``thread.quit()``.  The thread's ``finished`` calls
        ``_on_thread_finished`` which clears the refs on the owner.
        """
        from qt_compat import QThread

        self._stop()

        owner = self._owner
        gen = getattr(owner, self._gen_attr, 0) + 1
        setattr(owner, self._gen_attr, gen)

        worker = worker
        thread = QThread()
        worker.moveToThread(thread)
        worker.completed.connect(thread.quit)
        thread.finished.connect(lambda: self._on_thread_finished(gen, thread, worker))
        thread.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run)

        setattr(owner, self._thread_attr, thread)
        setattr(owner, self._worker_attr, worker)
        thread.start()

    def _stop(self) -> None:
        """Stop the currently running thread, if any."""
        owner = self._owner
        thread = getattr(owner, self._thread_attr, None)
        worker = getattr(owner, self._worker_attr, None)

        from ui.utils.qt_thread_cleanup import stop_qthread_nonblocking

        stopped = stop_qthread_nonblocking(
            thread,
            worker=worker,
            owner=self._name,
            wait_ms=0,
            disconnect_thread_signals=("finished",),
            disconnect_worker_signals=("completed", "error_occurred"),
        )
        if stopped:
            setattr(owner, self._thread_attr, None)
            setattr(owner, self._worker_attr, None)

    def _on_thread_finished(self, generation: int, thread: object, worker: object) -> None:
        """Clear refs on the owner if this is the current generation."""
        owner = self._owner
        if generation != getattr(owner, self._gen_attr, -1):
            return
        if getattr(owner, self._thread_attr, None) is thread:
            setattr(owner, self._thread_attr, None)
        if getattr(owner, self._worker_attr, None) is worker:
            setattr(owner, self._worker_attr, None)

    @property
    def generation(self) -> int:
        return getattr(self._owner, self._gen_attr, 0)


class IconLoadWorker(BaseLoggedWorker):
    """Icon loading worker with COM init, cancellation, and error reporting.

    Emits ``finished(sid, QImage)`` for each loaded icon.
    """

    finished = pyqtSignal(str, object)  # (shortcut_id, QImage | None)

    def __init__(self, tasks: list | None = None, *, name: str = "") -> None:
        super().__init__(name=name or "IconLoadWorker")
        self._tasks = tasks or []

    def run(self) -> None:
        tasks = getattr(self, "_tasks", None)
        if tasks is None:
            self.completed.emit()
            return

        from core.icon_extractor import IconExtractor
        from core.shortcut_icon_helpers import default_folder_icon_path, shortcut_uses_folder_icon

        com_ok = self.com_initialize()
        try:
            for sid, icon_path, target_path, size, stype in tasks:
                if self._cancel_requested:
                    break
                image = None
                if not icon_path and shortcut_uses_folder_icon(stype, target_path):
                    folder_icon = default_folder_icon_path()
                    if folder_icon:
                        icon_path = folder_icon
                        target_path = None
                try:
                    image = self._load_one(IconExtractor, icon_path, target_path, size)
                except Exception as exc:
                    logger.debug(
                        "[IconLoadWorker] exception sid=%s icon_path=%r size=%s error=%s",
                        sid,
                        icon_path,
                        size,
                        exc,
                    )
                if self._cancel_requested:
                    break
                self.finished.emit(sid, image)
        except Exception as exc:
            logger.exception("[IconLoadWorker] fatal error: %s", exc)
            self.error_occurred.emit(str(exc))
        finally:
            if com_ok:
                self.com_uninitialize()
            self.completed.emit()

    @staticmethod
    def _load_one(extractor, icon_path, target_path, size):
        if icon_path:
            if extractor._is_pixmap_preferred_resource(icon_path):
                return None
            image = extractor.from_file(icon_path, size, return_image=True)
            if image and not image.isNull():
                return image
        if target_path:
            if extractor._is_pixmap_preferred_resource(target_path):
                return None
            image = extractor.extract(target_path, target_path, size, return_image=True, fallback_to_default=False)
            if image and not image.isNull():
                return image
        return None
