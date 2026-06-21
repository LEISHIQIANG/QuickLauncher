"""Shared thread-safe icon loading worker for configuration dialogs."""

from __future__ import annotations

import logging

from core.shortcut_icon_helpers import default_folder_icon_path, shortcut_uses_folder_icon
from qt_compat import QImage, QObject, pyqtSignal

logger = logging.getLogger(__name__)


class IconLoadWorker(QObject):
    finished = pyqtSignal(str, QImage)
    completed = pyqtSignal()

    def __init__(self, tasks):
        super().__init__()
        self._tasks = tasks
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def run(self):
        from core.icon_extractor import IconExtractor

        try:
            import ctypes

            ctypes.windll.ole32.CoInitialize(None)
        except Exception as exc:
            logger.debug("COM初始化: %s", exc, exc_info=True)

        try:
            for sid, icon_path, target_path, size, stype in self._tasks:
                if self._cancel_requested:
                    break
                image = QImage()
                if not icon_path and shortcut_uses_folder_icon(stype, target_path):
                    folder_icon = default_folder_icon_path()
                    if folder_icon:
                        icon_path = folder_icon
                        target_path = None
                try:
                    image = self._load_one(IconExtractor, icon_path, target_path, size)
                except Exception as exc:
                    logger.debug(
                        "[IconDiag] worker exception sid=%s icon_path=%r target_path=%r size=%s error=%s",
                        sid,
                        icon_path,
                        target_path,
                        size,
                        exc,
                    )
                if self._cancel_requested:
                    break
                self.finished.emit(sid, image if image else QImage())
        finally:
            try:
                import ctypes

                ctypes.windll.ole32.CoUninitialize()
            except Exception as exc:
                logger.debug("COM反初始化: %s", exc, exc_info=True)
            self.completed.emit()

    @staticmethod
    def _load_one(extractor, icon_path, target_path, size):
        if icon_path:
            if extractor._is_pixmap_preferred_resource(icon_path):
                extractor._diag("worker defer resource icon_path=%s size=%s", icon_path, size)
                return None
            image = extractor.from_file(icon_path, size, return_image=True)
            if image and not image.isNull():
                return image
        if target_path:
            if extractor._is_pixmap_preferred_resource(target_path):
                extractor._diag("worker defer resource target_path=%s size=%s", target_path, size)
                return None
            image = extractor.extract(
                target_path,
                target_path,
                size,
                return_image=True,
                fallback_to_default=False,
            )
            if image and not image.isNull():
                return image
        extractor._warn_once(
            f"icon-worker:{icon_path}|{target_path}|{size}",
            "worker failed icon_path=%r target_path=%r size=%s",
            icon_path,
            target_path,
            size,
        )
        return None
