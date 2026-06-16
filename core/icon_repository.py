"""Icon repository service.

Extracted from :class:`core.data_manager.DataManager` in 1.6.3.2 to isolate
the icon-cache folder management (icon_repo.json read/write, system vs user
icon merging, cache stats, missing-icon path redirection) from the rest of
the DataManager's responsibilities.

The existing :class:`core.config_services.IconRepository` class is
**unchanged** and still handles the on-disk icon cache directory itself
(``clean()``/``get_stats()``). The new :class:`IconRepositoryService` is a
higher-level coordinator that owns the icon_repo folder lifecycle and
delegates cache maintenance to the existing service.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from .config_services import ConfigDataStore, IconRepository
from .data_models import Folder, ShortcutItem

if TYPE_CHECKING:
    from .data_manager import DataManager

logger = logging.getLogger(__name__)

_ICON_REPO_ID = "icon_repo"
_ICON_REPO_NAME = "\u56fe\u6807\u4ed3\u5e93"


def _split_icon_location(path: str) -> tuple[str, str]:
    """Split ``"<file>,<index>"`` style locations into ``(file, suffix)``."""
    raw = (path or "").strip()
    if not raw:
        return "", ""
    if "," in raw:
        file_part, suffix = raw.rsplit(",", 1)
        suffix = suffix.strip()
        if suffix.lstrip("-").isdigit():
            return file_part.strip(), f",{suffix}"
    return raw, ""


def _normalize_icon_file(path: str) -> str:
    return os.path.abspath(os.path.expanduser(os.path.expandvars(path or "")))


def _supports_icon_index(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in {".exe", ".dll", ".ico"}


class IconRepositoryService:
    """Manage the in-memory icon_repo folder plus the icon_repo.json file.

    The icon_repo folder is a *runtime* concept: the user-facing ``data.json``
    never persists the icon_repo folder, but a standalone ``icon_repo.json``
    file lives next to ``data.json`` and is reread on startup.

    Public API stays on :class:`DataManager`; this class is internal.
    """

    #: Subset of file extensions that count as icon candidates when
    #: searching for a replacement of a missing icon.
    _PREFERRED_ICON_EXTS: ClassVar[tuple[str, ...]] = (
        ".ico",
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".exe",
        ".dll",
    )

    def __init__(self, dm: DataManager) -> None:
        self._dm = dm

    # ── folder lifecycle ──────────────────────────────────────────────

    def detach_folder(self) -> Folder | None:
        """Remove and return the runtime icon_repo folder from ``self.data``."""
        for folder in list(self._dm.data.folders):
            if getattr(folder, "is_icon_repo", False) or folder.id == _ICON_REPO_ID:
                self._dm.data.folders.remove(folder)
                folder.id = _ICON_REPO_ID
                folder.name = _ICON_REPO_NAME
                folder.is_system = True
                folder.is_dock = False
                folder.is_icon_repo = True
                return folder
        return None

    def attach_folder(self) -> None:
        """Attach the icon_repo folder as a runtime-only folder for UI code."""
        dm = self._dm
        dm.data.folders = [
            f for f in dm.data.folders if not getattr(f, "is_icon_repo", False) and f.id != _ICON_REPO_ID
        ]
        max_order = max((f.order for f in dm.data.folders), default=0)
        dm._icon_repo_folder.id = _ICON_REPO_ID
        dm._icon_repo_folder.name = _ICON_REPO_NAME
        dm._icon_repo_folder.order = max_order + 1
        dm._icon_repo_folder.is_system = True
        dm._icon_repo_folder.is_dock = False
        dm._icon_repo_folder.is_icon_repo = True
        dm.data.folders.append(dm._icon_repo_folder)

    def load_folder(self) -> Folder:
        """Load the combined runtime icon_repo folder from system + user sources."""
        dm = self._dm
        legacy_folder = self.detach_folder()
        system_items = self._load_system_items()
        user_folder = self._read_user_file() if dm.icon_repo_file.exists() else None
        user_items = list(getattr(user_folder, "items", []) or [])

        if not user_items and legacy_folder is not None:
            user_items = list(getattr(legacy_folder, "items", []) or [])

        user_items = self._filter_user_items(user_items, system_items)
        self._write_user_items(user_items)

        # Filter out deleted system icons so they don't reappear on restart
        deleted_ids: set = getattr(dm, "_deleted_system_ids", set()) or set()
        system_items = [item for item in system_items if item.id not in deleted_ids]

        for item in system_items:
            item._icon_repo_source = "system"  # type: ignore[attr-defined]
        for item in user_items:
            item._icon_repo_source = "user"  # type: ignore[attr-defined]

        items = sorted(
            system_items + user_items,
            key=lambda item: int(getattr(item, "order", 0) or 0),
        )
        return Folder(
            id=_ICON_REPO_ID,
            name=_ICON_REPO_NAME,
            is_system=True,
            is_icon_repo=True,
            items=items,
        )

    # ── persistence ───────────────────────────────────────────────────

    def _read_user_file(self) -> Folder | None:
        dm = self._dm
        try:
            raw = json.loads(dm.icon_repo_file.read_text(encoding="utf-8"))
            items = raw.get("items", []) if isinstance(raw, dict) else []
            if not isinstance(items, list):
                items = []
            return Folder(
                id=_ICON_REPO_ID,
                name=_ICON_REPO_NAME,
                is_system=True,
                is_icon_repo=True,
                items=[ShortcutItem.from_dict(item) for item in items if isinstance(item, dict)],
            )
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            logger.warning("load icon repository failed: %s", exc)
            return None

    def _load_system_items(self) -> list[ShortcutItem]:
        dm = self._dm
        seed_file = Path(getattr(dm, "system_icons_file", dm.install_dir / "assets" / "system_icons" / "config.json"))
        seed_dir = seed_file.parent
        if not seed_file.exists():
            return []
        try:
            raw = json.loads(seed_file.read_text(encoding="utf-8"))
            items = raw.get("items", []) if isinstance(raw, dict) else []
            result = []
            for item_data in items:
                if not isinstance(item_data, dict):
                    continue
                item_copy = dict(item_data)
                icon_path = str(item_copy.get("icon_path", "") or "")
                if icon_path and not os.path.isabs(icon_path):
                    icon_path = icon_path.replace("/", os.sep).replace("\\", os.sep)
                    item_copy["icon_path"] = str(seed_dir / icon_path)
                result.append(ShortcutItem.from_dict(item_copy))
            return result
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            logger.warning("load system icons failed: %s", exc)
            return []

    def _filter_user_items(
        self,
        user_items: list[ShortcutItem],
        system_items: list[ShortcutItem],
    ) -> list[ShortcutItem]:
        system_ids = {item.id for item in system_items}
        system_names = {item.name for item in system_items}
        filtered = []
        for item in user_items:
            if item.id in system_ids or item.name in system_names:
                continue
            item._icon_repo_source = "user"  # type: ignore[attr-defined]
            filtered.append(item)
        return filtered

    @staticmethod
    def is_system_item(item: ShortcutItem | None) -> bool:
        return getattr(item, "_icon_repo_source", "") == "system"

    @staticmethod
    def is_user_item(item: ShortcutItem | None) -> bool:
        return getattr(item, "_icon_repo_source", "") == "user"

    @staticmethod
    def strip_runtime_source(item: ShortcutItem) -> ShortcutItem:
        try:
            delattr(item, "_icon_repo_source")
        except AttributeError as exc:
            logger.debug("删除运行时属性失败: %s", exc, exc_info=True)
        return item

    def _write_user_items(self, items: list[ShortcutItem]) -> bool:
        dm = self._dm
        dm.app_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": "1.0", "items": [item.to_dict() for item in items]},
            ensure_ascii=False,
            indent=2,
        )
        temp_file = dm.icon_repo_file.with_name(f"{dm.icon_repo_file.stem}.{uuid.uuid4().hex}.tmp")
        try:
            temp_file.write_text(payload, encoding="utf-8")
            icon_repo_store = ConfigDataStore(dm.icon_repo_file)
            icon_repo_store.replace_data_file(temp_file)
            return True
        except (OSError, TypeError, ValueError) as exc:
            logger.error("save icon repository failed: %s", exc)
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except OSError as exc:
                logger.debug("清理临时文件失败: %s", exc, exc_info=True)
            return False

    def save(self) -> bool:
        """Persist the user-owned icon_repo items back to ``icon_repo.json``."""
        dm = self._dm
        with dm._save_lock:
            dm._runtime_revision += 1
            folder = dm.data.get_folder_by_id(_ICON_REPO_ID) or getattr(dm, "_icon_repo_folder", None)
            if folder is None:
                return False
            dm._icon_repo_folder = folder
            items = [item for item in list(folder.items) if not self.is_system_item(item)]
        return self._write_user_items(items)

    # ── cache stats / clean (delegates to existing IconRepository) ─────

    def get_used_icons(self) -> set[str]:
        dm = self._dm
        used = set()
        for folder in dm.data.folders:
            for item in folder.items:
                if item.icon_path:
                    used.add(os.path.normcase(os.path.abspath(item.icon_path)))
        return used

    def clean_cache(self, dry_run: bool = False) -> dict[str, Any]:
        empty: dict[str, Any] = {
            "exe_files_removed": 0,
            "exe_files_size_mb": 0,
            "large_files_removed": 0,
            "large_files_size_mb": 0,
            "orphan_files_removed": 0,
            "orphan_files_size_mb": 0,
            "duplicate_files_removed": 0,
            "duplicate_files_size_mb": 0,
            "total_removed": 0,
            "total_size_freed_mb": 0,
            "dry_run": dry_run,
        }
        dm = self._dm
        if not dm.icons_dir.exists():
            return empty
        with dm._save_lock:
            used = self.get_used_icons()
        repo = IconRepository(dm.icons_dir)
        result: dict[str, Any] = repo.clean(used, dry_run=dry_run)
        return result

    def get_cache_stats(self) -> dict[str, Any]:
        dm = self._dm
        repo = IconRepository(dm.icons_dir)
        result: dict[str, Any] = repo.get_stats()
        return result

    def get_all_cache_paths(self) -> dict[str, Any]:
        import winreg

        dm = self._dm
        cache_info: dict[str, Any] = {
            "app_data_dir": str(dm.app_dir),
            "icons_dir": str(dm.icons_dir),
            "files": [],
            "directories": [],
            "registry_keys": [],
        }
        if dm.app_dir.exists():
            cache_info["directories"].append(str(dm.app_dir))
            for item in dm.app_dir.iterdir():
                cache_info["files"].append(str(item))
        if dm.icons_dir.exists():
            cache_info["directories"].append(str(dm.icons_dir))
        for key_path in (r"Software\Microsoft\Windows\CurrentVersion\Run",):
            try:
                handle = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
                winreg.CloseKey(handle)
                cache_info["registry_keys"].append(key_path)
            except OSError:
                logger.debug("打开注册表键失败: %s", key_path, exc_info=True)
        return cache_info

    # ── missing-icon path redirection ─────────────────────────────────

    def redirect_missing_paths(self, new_icon_path: str) -> int:
        """Replace missing icon paths with a sibling file when one is found.

        When the user fixes a single missing icon (e.g. by browsing to a
        replacement), walk every folder and rewrite other items whose icon
        path no longer resolves to a sibling match of the freshly-fixed file.
        Returns the number of items rewritten.
        """
        if not new_icon_path:
            return 0
        dm = self._dm
        with dm._save_lock:
            new_icon_file, _ = _split_icon_location(new_icon_path)
            new_icon_file = _normalize_icon_file(new_icon_file)
            if not new_icon_file or not os.path.isfile(new_icon_file):
                return 0

            new_dir = os.path.dirname(new_icon_file)
            count = 0

            for folder in dm.data.folders:
                for item in folder.items:
                    if not item.icon_path:
                        continue
                    raw_icon_path = (item.icon_path or "").strip()
                    if os.path.normcase(raw_icon_path) == os.path.normcase(new_icon_path):
                        continue
                    item_icon_file, item_icon_suffix = _split_icon_location(raw_icon_path)
                    item_icon_file = _normalize_icon_file(item_icon_file)
                    if not item_icon_file or os.path.isfile(item_icon_file):
                        continue
                    candidate_file, match_kind = self._candidate_for_missing(item_icon_file, new_dir)
                    if not candidate_file:
                        continue
                    suffix = item_icon_suffix if _supports_icon_index(candidate_file) else ""
                    item.icon_path = f"{candidate_file}{suffix}"
                    count += 1
                    logger.debug(
                        "redirected missing icon path item=%s match=%s old=%r new=%r",
                        item.id,
                        match_kind,
                        raw_icon_path,
                        item.icon_path,
                    )

            if count:
                dm.save(immediate=True)
            return count

    def _candidate_for_missing(self, missing_file: str, search_dir: str) -> tuple[str, str]:
        filename = os.path.basename(missing_file)
        if not filename:
            return "", ""
        exact = self._case_insensitive_child(search_dir, filename)
        if exact:
            return exact, "exact"
        stem_match = self._stem_match_child(search_dir, missing_file)
        if stem_match:
            return stem_match, "stem"
        return "", ""

    @staticmethod
    def _case_insensitive_child(directory: str, filename: str) -> str:
        try:
            wanted = os.path.normcase(filename)
            for entry in os.scandir(directory):
                if entry.is_file() and os.path.normcase(entry.name) == wanted:
                    return entry.path
        except OSError:
            return ""
        direct = os.path.join(directory, filename)
        if os.path.isfile(direct):
            return direct
        return ""

    def _stem_match_child(self, directory: str, missing_file: str) -> str:
        missing_stem = os.path.splitext(os.path.basename(missing_file))[0]
        if not missing_stem:
            return ""
        wanted_stem = os.path.normcase(missing_stem)
        preferred_exts = self._PREFERRED_ICON_EXTS
        matches: list[str] = []
        try:
            for entry in os.scandir(directory):
                if not entry.is_file():
                    continue
                stem, ext = os.path.splitext(entry.name)
                ext = ext.lower()
                if ext not in preferred_exts or os.path.normcase(stem) != wanted_stem:
                    continue
                matches.append(entry.path)
        except OSError:
            return ""
        if not matches:
            return ""
        priority = {ext: index for index, ext in enumerate(preferred_exts)}
        matches.sort(key=lambda path: priority.get(os.path.splitext(path)[1].lower(), 99))
        return matches[0]


__all__ = ["IconRepositoryService", "_split_icon_location", "_normalize_icon_file", "_supports_icon_index"]
