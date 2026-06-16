"""Backup / restore / shareable-config import-export service.

Extracted from :class:`core.data_manager.DataManager` in 1.6.3.9 to isolate
the full-config and shareable-config zip I/O flows. The class holds a
reference to the owning DataManager and reads/writes the same private
attributes that the old methods touched (lock, settings, icon dirs,
data_loader journal, save_coordinator save, icon_repository_service).

Public API stays on :class:`DataManager`; this class is internal and may be
called directly by tests.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from .config_repairs import apply_config_repairs
from .config_validation import sanitize_app_data_dict
from .data_models import AppData, Folder, ShortcutItem
from .import_security import (
    MAX_BACKGROUND_BYTES,
    MAX_CONFIG_BYTES,
    MAX_ICON_BYTES,
    UnsafeZipError,
    build_safe_zip_index,
    has_zip_entry,
    is_allowed_background_path,
    is_allowed_icon_path,
    normalize_zip_name,
    read_zip_bytes,
    read_zip_text,
    set_imported_items,
    skip_file,
)
from .path_security import resolve_under, safe_rmtree_child

if TYPE_CHECKING:
    from .data_manager import DataManager

logger = logging.getLogger(__name__)

_HISTORY_DEFAULT = "\u914d\u7f6e\u53d8\u66f4"
_IMPORT_FOLDER_NAME = "\u5bfc\u5165\u56fe\u6807"
_LEGACY_IMPORT_FOLDER_NAMES = {_IMPORT_FOLDER_NAME, "Imported Icons"}


class BackupService:
    """Coordinate full-config backups and shareable-config import/export."""

    def __init__(self, dm: DataManager) -> None:
        self._dm = dm

    # ── full-config backup / restore ──────────────────────────────

    def backup_full(self, save_path: str) -> bool:
        """Write a complete ``.qlzip`` containing data.json + icons + bg."""
        dm = self._dm
        with dm._save_lock:
            try:
                if not dm.save(immediate=True):
                    return False

                with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    data_dict = dm._get_save_coordinator()._main_data_dict()

                    bg_path = getattr(dm.data.settings, "custom_bg_path", "")
                    if bg_path and os.path.exists(bg_path):
                        ext = os.path.splitext(bg_path)[1]
                        arc_bg_name = f"background{ext}"
                        zf.write(bg_path, arc_bg_name)
                        data_dict["settings"]["custom_bg_path"] = arc_bg_name

                    zf.writestr("data.json", json.dumps(data_dict, ensure_ascii=False, indent=2))
                    icon_repo_folder = dm.data.get_folder_by_id("icon_repo")
                    icon_repo_items = [
                        item
                        for item in getattr(icon_repo_folder, "items", [])
                        if not dm._is_system_icon_repo_item(item)
                    ]
                    icon_repo_dict = {
                        "version": "1.0",
                        "items": [item.to_dict() for item in icon_repo_items],
                    }
                    zf.writestr(
                        "icon_repo.json",
                        json.dumps(icon_repo_dict, ensure_ascii=False, indent=2),
                    )

                    dm._get_package_service().write_extra_config_files(zf)

                    if dm.icons_dir.exists():
                        for file_path in dm.icons_dir.iterdir():
                            if file_path.is_file():
                                zf.write(file_path, f"icons/{file_path.name}")

                return True
            except Exception as e:
                logger.error("backup_full_config failed: %s", e)
                return False

    def restore_full(self, backup_path: str) -> bool:
        """Restore a previously-written full-config ``.qlzip``."""
        return self._restore_full_safe(backup_path)

    def _restore_full_safe(self, backup_path: str) -> bool:
        dm = self._dm
        with dm._save_lock:
            # Write pre-transaction journal for crash recovery.
            dm._write_transaction_journal("restore_full_config", {"source": backup_path})
            report = dm._reset_import_report()
            restored_bg_path = None
            try:
                if not os.path.exists(backup_path):
                    return False

                dm._mark_history(_HISTORY_DEFAULT)
                with zipfile.ZipFile(backup_path, "r") as zf:
                    safe_index = build_safe_zip_index(zf, report)
                    if not has_zip_entry(safe_index, "data.json"):
                        logger.warning("invalid backup file: missing data.json")
                        return False

                    data_json = read_zip_text(
                        zf,
                        safe_index,
                        "data.json",
                        max_bytes=MAX_CONFIG_BYTES,
                        report=report,
                        required=True,
                    )
                    if data_json is None:
                        return False
                    data_dict = sanitize_app_data_dict(json.loads(data_json), report)
                    restored_icon_repo_items = None
                    if has_zip_entry(safe_index, "icon_repo.json"):
                        icon_repo_json = read_zip_text(
                            zf,
                            safe_index,
                            "icon_repo.json",
                            max_bytes=MAX_CONFIG_BYTES,
                            report=report,
                            required=False,
                        )
                        if icon_repo_json is not None:
                            icon_repo_dict = json.loads(icon_repo_json)
                            icon_items = icon_repo_dict.get("items", []) if isinstance(icon_repo_dict, dict) else []
                            if isinstance(icon_items, list):
                                restored_icon_repo_items = [
                                    ShortcutItem.from_dict(item) for item in icon_items if isinstance(item, dict)
                                ]

                    install_root = Path(dm.install_dir).resolve(strict=False)
                    app_root = Path(dm.app_dir).resolve(strict=False)
                    icons_root = Path(dm.icons_dir).resolve(strict=False)
                    temp_icons_dir = resolve_under(
                        install_root,
                        tempfile.mkdtemp(prefix="ql_restore_icons_", dir=str(install_root)),
                    )
                    bg_rel_path = data_dict.get("settings", {}).get("custom_bg_path", "")
                    if bg_rel_path and not os.path.isabs(bg_rel_path):
                        normalized_bg = normalize_zip_name(bg_rel_path)
                        if (
                            normalized_bg
                            and has_zip_entry(safe_index, normalized_bg)
                            and is_allowed_background_path(normalized_bg)
                        ):
                            bg_bytes = read_zip_bytes(
                                zf,
                                safe_index,
                                normalized_bg,
                                max_bytes=MAX_BACKGROUND_BYTES,
                                report=report,
                            )
                            if bg_bytes is None:
                                data_dict["settings"]["custom_bg_path"] = ""
                            else:
                                target_bg_path = resolve_under(
                                    app_root,
                                    app_root / f"restored_bg_{os.path.basename(bg_rel_path)}",
                                )
                                with open(target_bg_path, "wb") as f:
                                    f.write(bg_bytes)
                                restored_bg_path = target_bg_path
                                data_dict["settings"]["custom_bg_path"] = str(target_bg_path)
                        else:
                            if normalized_bg:
                                skip_file(report, normalized_bg, "missing or unsupported background image")
                            data_dict["settings"]["custom_bg_path"] = ""

                    for name in list(safe_index.keys()):
                        if name.startswith("icons/") and not name.endswith("/"):
                            if not is_allowed_icon_path(name):
                                skip_file(report, name, "unsupported icon extension")
                                continue
                            icon_bytes = read_zip_bytes(
                                zf,
                                safe_index,
                                name,
                                max_bytes=MAX_ICON_BYTES,
                                report=report,
                            )
                            if icon_bytes is None:
                                continue
                            filename = os.path.basename(name)
                            if filename:
                                target_path = resolve_under(temp_icons_dir, temp_icons_dir / filename)
                                with open(target_path, "wb") as f:
                                    f.write(icon_bytes)

                    restored_data = AppData.from_dict(data_dict)
                    legacy_icon_repo = None
                    for folder in list(restored_data.folders):
                        if getattr(folder, "is_icon_repo", False) or folder.id == "icon_repo":
                            restored_data.folders.remove(folder)
                            legacy_icon_repo = folder
                            break
                    if restored_icon_repo_items is None:
                        restored_icon_repo_items = list(getattr(legacy_icon_repo, "items", []) or [])
                    apply_config_repairs(restored_data)

                    old_data = dm.data
                    old_saved = getattr(dm, "_last_saved_data_dict", None)
                    old_config_status = dict(getattr(dm, "_config_status", {}) or {})
                    backup_icons_dir = None
                    try:
                        if dm.icons_dir.exists():
                            backup_icons_dir = resolve_under(
                                icons_root.parent,
                                icons_root.with_name(f"{icons_root.name}_backup_restore"),
                            )
                            if backup_icons_dir.exists():
                                safe_rmtree_child(icons_root.parent, backup_icons_dir)
                            icons_root.replace(backup_icons_dir)

                        icons_root.mkdir(parents=True, exist_ok=True)
                        for item in temp_icons_dir.iterdir():
                            target_icon = resolve_under(icons_root, icons_root / item.name)
                            shutil.move(str(resolve_under(temp_icons_dir, item)), str(target_icon))

                        dm.data = restored_data
                        dm._write_icon_repo_items(restored_icon_repo_items or [])
                        dm._icon_repo_folder = dm._load_icon_repo_folder()
                        dm._attach_icon_repo_folder()
                        if not dm.save(immediate=True):
                            raise RuntimeError("save restored config failed")
                        set_imported_items(report, sum(len(f.items) for f in dm.data.folders))

                        dm._get_package_service().restore_extra_config_files(zf, safe_index, report)
                    except Exception:
                        dm.data = old_data
                        dm._last_saved_data_dict = old_saved
                        dm._config_status = old_config_status
                        if icons_root.exists():
                            safe_rmtree_child(icons_root.parent, icons_root)
                        if backup_icons_dir and backup_icons_dir.exists():
                            backup_icons_dir.replace(icons_root)
                        if restored_bg_path and restored_bg_path.exists():
                            try:
                                restored_bg_path.unlink()
                            except Exception as cleanup_error:
                                logger.debug(
                                    "cleanup restored background failed %s: %s",
                                    restored_bg_path,
                                    cleanup_error,
                                )
                            restored_bg_path = None
                        raise
                    finally:
                        if temp_icons_dir.exists():
                            safe_rmtree_child(install_root, temp_icons_dir)

                    if backup_icons_dir and backup_icons_dir.exists():
                        safe_rmtree_child(backup_icons_dir.parent, backup_icons_dir)

                    # Post-transaction: clear journal and verify consistency.
                    consistency = dm._verify_transaction_consistency()
                    if not consistency["consistent"]:
                        logger.warning("post-restore consistency issues: %s", consistency["issues"])
                    dm._clear_transaction_journal()
                    return True

            except (UnsafeZipError, ValueError, json.JSONDecodeError) as e:
                if restored_bg_path and restored_bg_path.exists():
                    try:
                        restored_bg_path.unlink()
                    except Exception as cleanup_error:
                        logger.debug("cleanup restored background failed %s: %s", restored_bg_path, cleanup_error)
                logger.warning("restore_full_config rejected unsafe backup: %s", e)
                return False
            except Exception as e:
                if restored_bg_path and restored_bg_path.exists():
                    try:
                        restored_bg_path.unlink()
                    except Exception as cleanup_error:
                        logger.debug("cleanup restored background failed %s: %s", restored_bg_path, cleanup_error)
                logger.exception("restore_full_config failed: %s", e)
                return False

    # ── shareable-config export / import ────────────────────────────

    def export_shareable(self, save_path: str) -> bool:
        """Export a portable ``.qlzip`` of hotkey/command/url shortcuts."""
        dm = self._dm
        with dm._save_lock:
            try:
                dm.save(immediate=True)

                data_dict = dm.data.to_dict()
                shareable_dict = {"version": data_dict.get("version", "1.0"), "items": []}
                icon_entries: list[tuple[str, str, str]] = []  # (source_path, mode, archive_name)

                folders = data_dict.get("folders", [])
                for folder in folders:
                    items = folder.get("items", folder.get("shortcuts", []))
                    for shortcut in items:
                        shortcut_type = shortcut.get("type", "file")
                        if shortcut_type in ["hotkey", "command", "url"]:
                            original_id = shortcut.get("id") or str(uuid.uuid4())
                            item_copy = {
                                "id": original_id,
                                "name": shortcut.get("name", ""),
                                "type": shortcut.get("type", ""),
                                "order": shortcut.get("order", 0),
                                "enabled": shortcut.get("enabled", True),
                                "tags": shortcut.get("tags", []),
                                "last_used_at": shortcut.get("last_used_at", 0.0),
                                "use_count": shortcut.get("use_count", 0),
                                "alias": shortcut.get("alias", ""),
                                "target_path": shortcut.get("target_path", ""),
                                "target_args": shortcut.get("target_args", ""),
                                "working_dir": shortcut.get("working_dir", ""),
                                "hotkey": shortcut.get("hotkey", ""),
                                "hotkey_modifiers": shortcut.get("hotkey_modifiers", []),
                                "hotkey_key": shortcut.get("hotkey_key", ""),
                                "hotkey_keys": shortcut.get("hotkey_keys", []),
                                "url": shortcut.get("url", ""),
                                "preferred_browser_path": shortcut.get("preferred_browser_path", ""),
                                "preferred_browser_args": shortcut.get("preferred_browser_args", ""),
                                "command": shortcut.get("command", ""),
                                "command_type": shortcut.get("command_type", "cmd"),
                                "trigger_mode": shortcut.get("trigger_mode", "immediate"),
                                "show_window": shortcut.get("show_window", False),
                                "run_as_admin": shortcut.get("run_as_admin", False),
                                "command_variables_enabled": shortcut.get("command_variables_enabled", False),
                                "icon_data": shortcut.get("icon_data", ""),
                                "icon_invert_light": shortcut.get("icon_invert_light", False),
                                "icon_invert_dark": shortcut.get("icon_invert_dark", False),
                                "icon_invert_with_theme": shortcut.get("icon_invert_with_theme", False),
                                "icon_invert_current": shortcut.get("icon_invert_current", False),
                                "icon_invert_theme_when_set": shortcut.get("icon_invert_theme_when_set", ""),
                            }

                            icon_path = shortcut.get("icon_path", "")
                            if icon_path:
                                actual_path = icon_path.split(",")[0] if "," in icon_path else icon_path
                                if os.path.exists(actual_path):
                                    ext = os.path.splitext(actual_path)[1].lower()
                                    if ext in [".exe", ".dll"]:
                                        new_icon_name = f"{original_id}.png"
                                        icon_entries.append((actual_path, "extract", new_icon_name))
                                    else:
                                        original_ext = os.path.splitext(actual_path)[1] or ".png"
                                        new_icon_name = f"{original_id}{original_ext}"
                                        icon_entries.append((actual_path, "copy", new_icon_name))
                                    item_copy["icon_path"] = f"icons/{new_icon_name}"
                                else:
                                    item_copy["icon_path"] = ""
                            else:
                                item_copy["icon_path"] = ""

                            shareable_dict["items"].append(item_copy)

                with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr(
                        "config.json",
                        json.dumps(shareable_dict, ensure_ascii=False, indent=2),
                    )

                    for orig_path, mode, new_name in icon_entries:
                        try:
                            if mode == "extract":
                                from core.icon_extractor import IconExtractor

                                pixmap = IconExtractor.from_file(orig_path, size=256, return_image=False)
                                if pixmap and not pixmap.isNull():
                                    ext = os.path.splitext(new_name)[1].lower() or ".png"
                                    with tempfile.NamedTemporaryFile(
                                        suffix=ext, prefix="ql_icon_", delete=False
                                    ) as tmp:
                                        tmp_path = tmp.name
                                    try:
                                        success = pixmap.save(tmp_path, "PNG")
                                        if success:
                                            zf.write(tmp_path, f"icons/{new_name}")
                                    finally:
                                        try:
                                            os.remove(tmp_path)
                                        except OSError:
                                            logger.debug("删除临时图标文件失败: %s", tmp_path, exc_info=True)
                            else:
                                zf.write(orig_path, f"icons/{new_name}")
                        except Exception as e:
                            logger.warning("failed to add icon %s: %s", orig_path, e)

                return True
            except Exception as e:
                logger.exception("export_shareable_config failed: %s", e)
                return False

    def import_shareable(self, import_path: str, merge: bool = True) -> bool:
        """Import a portable ``.qlzip`` of hotkey/command/url shortcuts."""
        return self._import_shareable_safe(import_path, merge=merge)

    def _import_shareable_safe(self, import_path: str, merge: bool = True) -> bool:
        dm = self._dm
        report = dm._reset_import_report()
        return self._import_shareable_transactional(import_path, merge, report)

    def _import_shareable_transactional(self, import_path: str, merge: bool, report: dict) -> bool:
        dm = self._dm
        temp_icons_dir = None
        moved_icons: list[Path] = []
        original_data_dict: dict | None = None
        install_root = Path(dm.install_dir).resolve(strict=False)
        try:
            if not os.path.exists(import_path):
                return False
            if not zipfile.is_zipfile(import_path):
                return False

            dm._write_transaction_journal("import_shareable_config", {"source": import_path, "merge": merge})

            with dm._save_lock:
                dm._mark_history(_HISTORY_DEFAULT)
                original_data_dict = dm.data.to_dict()
                icons_root = Path(dm.icons_dir).resolve(strict=False)
                temp_icons_dir = resolve_under(
                    install_root,
                    tempfile.mkdtemp(prefix="ql_import_icons_", dir=str(install_root)),
                )
                with zipfile.ZipFile(import_path, "r") as zf:
                    safe_index = build_safe_zip_index(zf, report)
                    config_text = read_zip_text(
                        zf,
                        safe_index,
                        "config.json",
                        max_bytes=MAX_CONFIG_BYTES,
                        report=report,
                        required=True,
                    )
                    if config_text is None:
                        return False
                    import_dict = json.loads(config_text)
                    import_items = import_dict.get("items", []) if isinstance(import_dict, dict) else []
                    if not isinstance(import_items, list) or not import_items:
                        return False

                    staged_shortcuts: list[ShortcutItem] = []
                    staged_icons: list[tuple[Path, Path]] = []
                    for item_dict in import_items[:2048]:
                        if not isinstance(item_dict, dict):
                            continue
                        item_type = item_dict.get("type", "file")
                        if item_type not in ["hotkey", "command", "url"]:
                            continue
                        item_dict = dict(item_dict)
                        item_dict["id"] = str(uuid.uuid4())
                        item_dict["run_as_admin"] = False
                        icon_path = item_dict.get("icon_path", "")
                        if icon_path and icon_path.startswith("icons/"):
                            if has_zip_entry(safe_index, icon_path) and is_allowed_icon_path(icon_path):
                                icon_ext = os.path.splitext(icon_path)[1] or ".png"
                                icon_filename = f"{item_dict['id']}{icon_ext}"
                                temp_icon_path = resolve_under(temp_icons_dir, temp_icons_dir / icon_filename)
                                local_icon_path = resolve_under(icons_root, icons_root / icon_filename)
                                icon_bytes = read_zip_bytes(
                                    zf,
                                    safe_index,
                                    icon_path,
                                    max_bytes=MAX_ICON_BYTES,
                                    report=report,
                                )
                                if icon_bytes is not None:
                                    with open(temp_icon_path, "wb") as f:
                                        f.write(icon_bytes)
                                    item_dict["icon_path"] = str(local_icon_path)
                                    staged_icons.append((temp_icon_path, local_icon_path))
                                else:
                                    item_dict["icon_path"] = ""
                            else:
                                skip_file(report, icon_path, "missing or unsupported icon")
                                item_dict["icon_path"] = ""
                        else:
                            item_dict["icon_path"] = ""

                        staged_shortcuts.append(ShortcutItem.from_dict(item_dict))

                    imported_count = len(staged_shortcuts)
                    if imported_count <= 0:
                        return False

                    target_folder = None
                    for folder in dm.data.folders:
                        if folder.name in _LEGACY_IMPORT_FOLDER_NAMES:
                            target_folder = folder
                            folder.name = _IMPORT_FOLDER_NAME
                            break

                    if not target_folder:
                        max_folder_order = max((f.order for f in dm.data.folders), default=0)
                        target_folder = Folder(name=_IMPORT_FOLDER_NAME, order=max_folder_order + 1)
                        append_target_folder = True
                    else:
                        append_target_folder = False

                    dm.icons_dir.mkdir(parents=True, exist_ok=True)
                    for temp_icon_path, local_icon_path in staged_icons:
                        shutil.move(str(temp_icon_path), str(local_icon_path))
                        moved_icons.append(local_icon_path)

                    if append_target_folder:
                        dm.data.folders.append(target_folder)
                    if not merge:
                        target_folder.items.clear()
                    max_order = max((s.order for s in target_folder.items), default=-1)
                    for shortcut in staged_shortcuts:
                        max_order += 1
                        shortcut.order = max_order
                        target_folder.items.append(shortcut)

                dm._apply_config_repairs_to_current()
                if not dm.save(immediate=True):
                    raise RuntimeError("failed to save imported shareable config")
                set_imported_items(report, imported_count)

                consistency = dm._verify_transaction_consistency()
                if not consistency["consistent"]:
                    logger.warning("post-import consistency issues: %s", consistency["issues"])
                dm._clear_transaction_journal()
                return imported_count > 0

        except Exception as e:
            if original_data_dict is not None:
                dm.data = AppData.from_dict(original_data_dict)
                dm._pending_history_action = _HISTORY_DEFAULT
                dm._pending_history_summary = ""
            for icon_path in moved_icons:
                try:
                    if icon_path.exists():
                        icon_path.unlink()
                except Exception as cleanup_error:
                    logger.debug("cleanup imported icon failed %s: %s", icon_path, cleanup_error)
            if isinstance(e, UnsafeZipError | ValueError | json.JSONDecodeError):
                logger.warning("import_shareable_config rejected unsafe package: %s", e)
            else:
                logger.exception("import_shareable_config failed: %s", e)
            return False
        finally:
            if temp_icons_dir and temp_icons_dir.exists():
                try:
                    safe_rmtree_child(install_root, temp_icons_dir)
                except Exception as cleanup_error:
                    logger.debug("cleanup import temp icons failed %s: %s", temp_icons_dir, cleanup_error)


__all__ = ["BackupService"]
