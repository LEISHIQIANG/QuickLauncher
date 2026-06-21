"""Owned background workers used by tray controllers."""

from __future__ import annotations

import logging

from qt_compat import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class IconCacheCleanThread(QThread):
    finished_signal = pyqtSignal(dict, str)

    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager

    def run(self):
        try:
            try:
                from core.icon_extractor import IconExtractor

                if hasattr(IconExtractor, "clear_cache"):
                    IconExtractor.clear_cache()
            except Exception as exc:
                logger.debug("清理图标提取器缓存: %s", exc, exc_info=True)
            self.finished_signal.emit(self.data_manager.clean_icon_cache(dry_run=False), "")
        except Exception as exc:
            self.finished_signal.emit({}, str(exc))
