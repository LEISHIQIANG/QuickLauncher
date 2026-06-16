"""Folder CRUD service.

Extracted from :class:`core.data_manager.DataManager` in 1.6.3.2. The class
holds a reference to the owning DataManager so folder mutations can coordinate
with save scheduling, history, and icon-repo persistence without duplicating
private state.

Public API stays on :class:`DataManager`; this module is internal and may be
called directly by tests.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .data_models import Folder

if TYPE_CHECKING:
    from .data_manager import DataManager

logger = logging.getLogger(__name__)

_HISTORY_DEFAULT = "\u914d\u7f6e\u53d8\u66f4"


class FolderService:
    """High-level folder CRUD with save scheduling and history annotations."""

    def __init__(self, dm: DataManager) -> None:
        self._dm = dm

    def add(self, name: str) -> Folder:
        with self._dm._save_lock:
            self._dm._mark_history(_HISTORY_DEFAULT)
            max_order = max((f.order for f in self._dm.data.folders), default=0)
            folder = Folder(name=name, order=max_order + 1)
            self._dm.data.folders.append(folder)
            self._dm.save()
            return folder

    def rename(self, folder_id: str, new_name: str) -> bool:
        with self._dm._save_lock:
            folder = self._dm.data.get_folder_by_id(folder_id)
            if folder and folder.is_icon_repo:
                return False
            if folder:
                self._dm._mark_history(_HISTORY_DEFAULT)
                folder.name = new_name
                self._dm.save()
                return True
            return False

    def delete(self, folder_id: str) -> bool:
        with self._dm._save_lock:
            folder = self._dm.data.get_folder_by_id(folder_id)
            if folder and not folder.is_system:
                self._dm._mark_history(_HISTORY_DEFAULT)
                self._dm.data.folders.remove(folder)
                self._dm.save()
                return True
            return False

    def reorder(self, folder_ids: list[str]) -> None:
        with self._dm._save_lock:
            self._dm._mark_history(_HISTORY_DEFAULT)
            order_map = {fid: i for i, fid in enumerate(folder_ids)}
            for folder in self._dm.data.folders:
                if folder.id in order_map:
                    folder.order = order_map[folder.id]
            self._dm.data.folders.sort(key=lambda f: f.order)
            self._dm.save()


__all__ = ["FolderService"]
