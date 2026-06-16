"""Shortcut CRUD service.

Extracted from :class:`core.data_manager.DataManager` in 1.6.3.2 to isolate
shortcut lifecycle (add, update, delete, reorder, batch move/copy, smart
ordering, use-tracking) from the rest of the DataManager.

Public API stays on :class:`DataManager`; this class is internal and may be
called directly by tests.
"""

from __future__ import annotations

import copy
import logging
import uuid
from typing import TYPE_CHECKING

from .data_models import ShortcutItem

if TYPE_CHECKING:
    from .data_manager import DataManager
    from .data_models import Folder

logger = logging.getLogger(__name__)

_HISTORY_DEFAULT = "\u914d\u7f6e\u53d8\u66f4"


class ShortcutService:
    """High-level shortcut CRUD with save scheduling and history annotations.

    The class coordinates with DataManager for:

    * **Save scheduling** — via :py:meth:`DataManager.save` and
      :py:meth:`DataManager.save_icon_repo` depending on the target folder.
    * **History** — via :py:meth:`DataManager._mark_history` so the change
      appears as a recoverable snapshot.
    * **System icon tracking** — system icons deleted from the icon_repo
      folder are recorded in ``_deleted_system_ids`` so they do not
      reappear on the next startup.
    """

    def __init__(self, dm: DataManager) -> None:
        self._dm = dm

    # ── lookup ─────────────────────────────────────────────────────────

    def find_with_folder(self, shortcut_id: str) -> tuple[Folder | None, ShortcutItem | None]:
        dm = self._dm
        with dm._save_lock:
            for folder in dm.data.folders:
                for item in folder.items:
                    if item.id == shortcut_id:
                        return folder, item
        return None, None

    def get_by_id(self, shortcut_id: str) -> ShortcutItem | None:
        _, item = self.find_with_folder(shortcut_id)
        return item

    # ── single CRUD ────────────────────────────────────────────────────

    def add(self, folder_id: str, shortcut: ShortcutItem) -> bool:
        dm = self._dm
        with dm._save_lock:
            folder = dm.data.get_folder_by_id(folder_id)
            if folder:
                if getattr(folder, "is_icon_repo", False):
                    shortcut._icon_repo_source = "user"  # type: ignore[attr-defined]
                dm._mark_history(_HISTORY_DEFAULT)
                max_order = max((s.order for s in folder.items), default=-1)
                shortcut.order = max_order + 1
                folder.items.append(shortcut)
                self._persist_folder_changes(folder, immediate=True)
                return True
            return False

    def add_many(self, folder_id: str, shortcuts: list[ShortcutItem]) -> int:
        dm = self._dm
        with dm._save_lock:
            folder = dm.data.get_folder_by_id(folder_id)
            if folder and shortcuts:
                dm._mark_history(_HISTORY_DEFAULT)
                max_order = max((s.order for s in folder.items), default=-1)
                count = 0
                for shortcut in shortcuts:
                    if getattr(folder, "is_icon_repo", False):
                        shortcut._icon_repo_source = "user"  # type: ignore[attr-defined]
                    shortcut.order = max_order + 1 + count
                    folder.items.append(shortcut)
                    count += 1
                self._persist_folder_changes(folder, immediate=True)
                return count
            return 0

    def update(self, folder_id: str, shortcut: ShortcutItem) -> bool:
        dm = self._dm
        with dm._save_lock:
            folder = dm.data.get_folder_by_id(folder_id)
            if folder:
                for i, item in enumerate(folder.items):
                    if item.id == shortcut.id:
                        if self._is_system_icon_repo_item(item):
                            deleted: set = getattr(dm, "_deleted_system_ids", set()) or set()
                            deleted.add(item.id)
                            dm._deleted_system_ids = deleted
                        if getattr(folder, "is_icon_repo", False):
                            shortcut._icon_repo_source = "user"  # type: ignore[attr-defined]
                        dm._mark_history(_HISTORY_DEFAULT)
                        folder.items[i] = shortcut
                        self._persist_folder_changes(folder, immediate=True)
                        return True
            return False

    def delete(self, folder_id: str, shortcut_id: str) -> bool:
        dm = self._dm
        with dm._save_lock:
            folder = dm.data.get_folder_by_id(folder_id)
            if folder:
                for i, item in enumerate(folder.items):
                    if item.id == shortcut_id:
                        if self._is_system_icon_repo_item(item):
                            deleted: set = getattr(dm, "_deleted_system_ids", set()) or set()
                            deleted.add(shortcut_id)
                            dm._deleted_system_ids = deleted
                        dm._mark_history(_HISTORY_DEFAULT)
                        folder.items.pop(i)
                        self._persist_folder_changes(folder, immediate=True)
                        return True
            return False

    def reorder(self, folder_id: str, shortcut_ids: list[str]) -> None:
        dm = self._dm
        with dm._save_lock:
            folder = dm.data.get_folder_by_id(folder_id)
            if folder:
                dm._mark_history(_HISTORY_DEFAULT)
                order_map = {sid: i for i, sid in enumerate(shortcut_ids)}
                for item in folder.items:
                    if item.id in order_map:
                        item.order = order_map[item.id]
                folder.items.sort(key=lambda x: x.order)
                self._persist_folder_changes(folder, immediate=False)

    def move_to_folder(self, shortcut_id: str, target_folder_id: str) -> bool:
        dm = self._dm
        with dm._save_lock:
            source_folder = None
            target_shortcut = None

            for folder in dm.data.folders:
                for item in folder.items:
                    if item.id == shortcut_id:
                        source_folder = folder
                        target_shortcut = item
                        break
                if source_folder:
                    break

            if not source_folder or not target_shortcut:
                return False

            target_folder = dm.data.get_folder_by_id(target_folder_id)
            if not target_folder:
                return False

            if source_folder.id == target_folder.id:
                return False

            dm._mark_history(_HISTORY_DEFAULT)
            source_folder.items.remove(target_shortcut)

            max_order = max((s.order for s in target_folder.items), default=-1)
            target_shortcut.order = max_order + 1
            target_folder.items.append(target_shortcut)

            self._persist_folder_changes(source_folder, target_folder, immediate=True)
            return True

    # ── batch operations ───────────────────────────────────────────────

    def delete_batch(self, shortcut_ids: list[str]) -> dict:
        dm = self._dm
        with dm._save_lock:
            wanted = [sid for sid in shortcut_ids or [] if sid]
            wanted_set = set(wanted)
            removed_ids: list[str] = []
            if not wanted_set:
                return {"requested": 0, "success": 0, "failed": 0, "affected_ids": []}

            icon_touched = False
            with dm.batch_update(immediate=True):
                dm._mark_history(_HISTORY_DEFAULT)
                for folder in dm.data.folders:
                    kept = []
                    for item in folder.items:
                        if item.id in wanted_set:
                            if self._is_system_icon_repo_item(item):
                                deleted: set = getattr(dm, "_deleted_system_ids", set()) or set()
                                deleted.add(item.id)
                                dm._deleted_system_ids = deleted
                            removed_ids.append(item.id)
                            icon_touched = icon_touched or getattr(folder, "is_icon_repo", False)
                        else:
                            kept.append(item)
                    if len(kept) != len(folder.items):
                        folder.items = kept
                if removed_ids:
                    dm._batch_dirty = True
            if icon_touched:
                dm.save_icon_repo()

            return {
                "requested": len(wanted),
                "success": len(removed_ids),
                "failed": len(wanted_set - set(removed_ids)),
                "affected_ids": removed_ids,
            }

    def move_batch(self, shortcut_ids: list[str], target_folder_id: str) -> dict:
        dm = self._dm
        with dm._save_lock:
            target_folder = dm.data.get_folder_by_id(target_folder_id)
            wanted = [sid for sid in shortcut_ids or [] if sid]
            if not target_folder or not wanted:
                return {"requested": len(wanted), "success": 0, "failed": len(wanted), "affected_ids": []}

            moved: list[str] = []
            icon_touched = getattr(target_folder, "is_icon_repo", False)
            with dm.batch_update(immediate=True):
                dm._mark_history(_HISTORY_DEFAULT)
                for shortcut_id in wanted:
                    source_folder, item = self.find_with_folder(shortcut_id)
                    if not source_folder or not item or source_folder.id == target_folder.id:
                        continue
                    if self._is_system_icon_repo_item(item):
                        continue
                    icon_touched = icon_touched or getattr(source_folder, "is_icon_repo", False)
                    source_folder.items.remove(item)
                    if getattr(target_folder, "is_icon_repo", False):
                        item._icon_repo_source = "user"  # type: ignore[attr-defined]
                    elif getattr(source_folder, "is_icon_repo", False):
                        self._strip_icon_repo_runtime_source(item)
                    max_order = max((s.order for s in target_folder.items), default=-1)
                    item.order = max_order + 1
                    target_folder.items.append(item)
                    moved.append(item.id)
                if moved:
                    dm._batch_dirty = True
            if moved and icon_touched:
                dm.save_icon_repo()

            return {
                "requested": len(wanted),
                "success": len(moved),
                "failed": len(set(wanted) - set(moved)),
                "affected_ids": moved,
            }

    def copy_batch(self, shortcut_ids: list[str], target_folder_id: str) -> dict:
        """Copy shortcuts to a folder, assigning fresh ids and preserving the sources."""
        dm = self._dm
        with dm._save_lock:
            target_folder = dm.data.get_folder_by_id(target_folder_id)
            wanted = [sid for sid in shortcut_ids or [] if sid]
            if not target_folder or not wanted:
                return {"requested": len(wanted), "success": 0, "failed": len(wanted), "affected_ids": []}

            copied: list[str] = []
            max_order = max((s.order for s in target_folder.items), default=-1)
            for shortcut_id in wanted:
                source_folder, item = self.find_with_folder(shortcut_id)
                if not source_folder or not item:
                    continue
                new_item = copy.deepcopy(item)
                new_item.id = str(uuid.uuid4())
                if getattr(target_folder, "is_icon_repo", False):
                    new_item._icon_repo_source = "user"  # type: ignore[attr-defined]
                else:
                    self._strip_icon_repo_runtime_source(new_item)
                max_order += 1
                new_item.order = max_order
                target_folder.items.append(new_item)
                copied.append(new_item.id)

            if copied:
                dm._mark_history(_HISTORY_DEFAULT)
                self._persist_folder_changes(target_folder, immediate=True)

            return {
                "requested": len(wanted),
                "success": len(copied),
                "failed": max(0, len(wanted) - len(copied)),
                "affected_ids": copied,
            }

    def set_enabled_batch(self, shortcut_ids: list[str], enabled: bool) -> dict:
        dm = self._dm
        with dm._save_lock:
            wanted = [sid for sid in shortcut_ids or [] if sid]
            wanted_set = set(wanted)
            changed: list[str] = []
            if not wanted_set:
                return {"requested": 0, "success": 0, "failed": 0, "affected_ids": []}

            icon_touched = False
            with dm.batch_update(immediate=True):
                dm._mark_history(_HISTORY_DEFAULT)
                for folder in dm.data.folders:
                    for item in folder.items:
                        if item.id in wanted_set:
                            item.enabled = bool(enabled)
                            changed.append(item.id)
                            icon_touched = icon_touched or getattr(folder, "is_icon_repo", False)
                if changed:
                    dm._batch_dirty = True
            if icon_touched:
                dm.save_icon_repo()

            return {
                "requested": len(wanted),
                "success": len(changed),
                "failed": len(wanted_set - set(changed)),
                "affected_ids": changed,
            }

    # ── usage tracking / smart order ───────────────────────────────────

    def record_used(self, shortcut_id: str) -> bool:
        if not shortcut_id:
            return False
        dm = self._dm
        with dm._save_lock:
            try:
                for folder in getattr(dm.data, "folders", []) or []:
                    for item in getattr(folder, "items", []) or []:
                        if getattr(item, "id", "") == shortcut_id:
                            item.mark_used()
                            dm._suppress_next_history = True
                            settings = getattr(dm.data, "settings", None)
                            smart_sort_enabled = getattr(settings, "sort_mode", "custom") == "smart"
                            if smart_sort_enabled and not getattr(folder, "is_dock", False):
                                self._apply_smart_order(folder)
                                self._persist_folder_changes(folder, immediate=True)
                            else:
                                self._persist_folder_changes(folder, immediate=False)
                            logger.debug(
                                "recorded shortcut usage: id=%s count=%s",
                                shortcut_id,
                                getattr(item, "use_count", 0),
                            )
                            return True
            except Exception as e:
                logger.warning("record shortcut usage failed for %s: %s", shortcut_id, e)
                return False

            logger.debug("shortcut not found when recording usage: %s", shortcut_id)
            return False

    def _apply_smart_order(self, folder) -> int:
        """Update smart_order for one folder without changing custom order."""
        if not folder or getattr(folder, "is_dock", False):
            return 0

        ranked = sorted(
            getattr(folder, "items", []) or [],
            key=lambda item: (
                -max(0, int(getattr(item, "use_count", 0) or 0)),
                -max(0.0, float(getattr(item, "last_used_at", 0.0) or 0.0)),
                int(getattr(item, "order", 0) or 0),
            ),
        )
        updated = 0
        for index, item in enumerate(ranked):
            if getattr(item, "smart_order", None) != index:
                item.smart_order = index
                updated += 1
        return updated

    def recalculate_smart_order(self, folder_id: str | None = None) -> dict:
        dm = self._dm
        with dm._save_lock:
            dm._mark_history(_HISTORY_DEFAULT)
            target_folders: list = []
            if folder_id:
                folder = dm.data.get_folder_by_id(folder_id)
                if folder and not folder.is_dock:
                    target_folders = [folder]
            else:
                target_folders = list(dm.data.get_pages())

            updated = 0
            with dm.batch_update(immediate=True):
                for folder in target_folders:
                    updated += self._apply_smart_order(folder)
                if updated:
                    dm._batch_dirty = True

            return {"folders": len(target_folders), "updated": updated}

    # ── private helpers ────────────────────────────────────────────────

    def _persist_folder_changes(self, *folders, immediate: bool = True) -> bool:
        dm = self._dm
        icon_changed = any(getattr(folder, "is_icon_repo", False) for folder in folders if folder is not None)
        main_changed = any(not getattr(folder, "is_icon_repo", False) for folder in folders if folder is not None)
        ok = True
        if icon_changed:
            ok = dm.save_icon_repo() and ok
        if main_changed:
            ok = dm.save(immediate=immediate) and ok
        return ok

    def _is_system_icon_repo_item(self, item) -> bool:
        return getattr(item, "_icon_repo_source", "") == "system"

    @staticmethod
    def _strip_icon_repo_runtime_source(item: ShortcutItem) -> ShortcutItem:
        try:
            delattr(item, "_icon_repo_source")
        except AttributeError as exc:
            logger.debug("删除运行时属性失败: %s", exc, exc_info=True)
        return item


__all__ = ["ShortcutService"]
