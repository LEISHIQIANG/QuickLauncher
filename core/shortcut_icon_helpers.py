"""Shared shortcut icon classification helpers."""

from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path

from runtime_paths import app_root

from .data_models import ShortcutType

logger = logging.getLogger(__name__)


def default_folder_icon_path() -> str | None:
    """Return QuickLauncher's bundled default folder icon path."""
    possible_paths: list[str] = []
    if hasattr(sys, "_MEIPASS"):
        possible_paths.append(os.path.join(sys._MEIPASS, "assets", "Folder.ico"))
    module_root = Path(__file__).resolve(strict=False).parents[1]
    possible_paths.extend(
        [
            os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "assets", "Folder.ico"),
            str(app_root() / "assets" / "Folder.ico"),
            str(module_root / "assets" / "Folder.ico"),
            str(Path.cwd() / "assets" / "Folder.ico"),
        ]
    )
    for path in dict.fromkeys(possible_paths):
        if os.path.exists(path):
            return path
    return None


def shortcut_target_points_to_folder(target_path: str, *, resolve_lnk: bool = True) -> bool:
    """Return whether a shortcut target path should be treated as a folder."""
    path = _clean_path(target_path)
    if not path:
        return False
    if os.path.isdir(path):
        return True
    if resolve_lnk and path.lower().endswith(".lnk") and os.path.exists(path):
        try:
            parsed_target = _resolve_lnk_target(path, _path_mtime(path))
            return bool(parsed_target and os.path.isdir(_clean_path(parsed_target)))
        except Exception as exc:
            logger.debug("判断 .lnk 是否指向文件夹失败: %s", exc, exc_info=True)
    return False


def shortcut_uses_folder_icon(item_type, target_path: str, *, resolve_lnk: bool = True) -> bool:
    """Return whether the shortcut should use QuickLauncher's default folder icon."""
    if _is_folder_type(item_type):
        return True
    return shortcut_target_points_to_folder(target_path, resolve_lnk=resolve_lnk)


def shortcut_type_for_target(target_path: str, default: ShortcutType = ShortcutType.FILE) -> ShortcutType:
    """Infer FILE/FOLDER shortcut type from the already-resolved target path."""
    return ShortcutType.FOLDER if shortcut_target_points_to_folder(target_path) else default


def _is_folder_type(item_type) -> bool:
    value = getattr(item_type, "value", item_type)
    return value == ShortcutType.FOLDER.value


def _clean_path(path: str) -> str:
    text = str(path or "").strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return os.path.expanduser(os.path.expandvars(text))


def _path_mtime(path: str) -> int:
    try:
        return int(os.path.getmtime(path) * 1000)
    except OSError:
        return 0


@lru_cache(maxsize=256)
def _resolve_lnk_target(path: str, mtime_ms: int) -> str:
    del mtime_ms
    from .shortcut_parser import ShortcutParser

    parsed = ShortcutParser.parse(path)
    if not parsed:
        return ""
    return str(parsed.get("target", "") or "")
