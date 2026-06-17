"""Project cache cleanup helpers."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from runtime_paths import app_root

from .path_security import UnsafePathError, resolve_under, safe_rmtree_child

logger = logging.getLogger(__name__)

_CACHE_DIR_NAMES = {".pytest_cache", ".ruff_cache", "__pycache__"}
_BYTECODE_SUFFIXES = {".pyc", ".pyo"}


def clean_unused_project_cache(data_manager=None, dry_run: bool = False) -> dict:
    """Clean unused temporary cache files under the project directory."""
    install_dir = _get_install_dir(data_manager)
    data = getattr(data_manager, "data", None)
    protected_paths = _collect_protected_paths(data)
    protected_paths.update(_current_theme_temp_icon_paths(install_dir, data))

    stats = {
        "root": str(install_dir),
        "total_removed": 0,
        "total_size_freed_mb": 0,
        "failed": 0,
        "dry_run": dry_run,
        "by_area": {},
    }

    _clean_temp_icons(install_dir, protected_paths, dry_run, stats)
    _clean_named_cache_dirs(install_dir, dry_run, stats)
    _clean_restore_temp_dirs(install_dir, dry_run, stats)
    _round_stats(stats)
    return stats


def get_project_cache_stats(data_manager=None) -> dict:
    return clean_unused_project_cache(data_manager, dry_run=True)


def _get_install_dir(data_manager) -> Path:
    if data_manager is not None and getattr(data_manager, "install_dir", None):
        return Path(data_manager.install_dir).resolve(strict=False)
    return Path(app_root())


def _collect_protected_paths(data) -> set[str]:
    protected: set[str] = set()
    for value in _iter_values(data):
        if not isinstance(value, str):
            continue
        for candidate in _path_candidates(value):
            if candidate:
                protected.add(_normalize_path(candidate))
    return protected


def _iter_values(value):
    if value is None:
        return
    if hasattr(value, "to_dict"):
        try:
            value = value.to_dict()
        except (TypeError, ValueError):
            logger.debug("转换值为字典失败", exc_info=True)
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_values(item)
    elif isinstance(value, list | tuple | set):
        for item in value:
            yield from _iter_values(item)
    else:
        yield value


def _path_candidates(value: str) -> list[str]:
    raw = str(value or "").strip().strip('"')
    if not raw:
        return []
    candidates = [raw]
    if "," in raw:
        before_comma, suffix = raw.rsplit(",", 1)
        if suffix.strip().lstrip("-").isdigit():
            candidates.append(before_comma.strip())
    return candidates


def _current_theme_temp_icon_paths(root: Path, data) -> set[str]:
    settings = getattr(data, "settings", None)
    theme = str(getattr(settings, "theme", "") or "").strip()
    if not theme:
        return set()

    temp_icons = root / "temp_icons"
    paths = set()
    for prefix in ("ios_radio_thick_v6", "ios_switch_thick_v6", "ios_check_thick_v6"):
        for state in ("on", "off"):
            paths.add(_normalize_path(temp_icons / f"{prefix}_{theme}_{state}.png"))
    return paths


def _clean_temp_icons(root: Path, protected_paths: set[str], dry_run: bool, stats: dict):
    temp_icons = _safe_child_or_none(root, root / "temp_icons")
    if temp_icons is None:
        stats["failed"] += 1
        return
    if not temp_icons.exists():
        return

    for file_path in _iter_files(temp_icons):
        normalized = _normalize_path(file_path)
        if normalized in protected_paths:
            continue
        _remove_file(file_path, "temp_icons", dry_run, stats)
    _remove_empty_dirs(temp_icons, root, dry_run, stats)


def _clean_named_cache_dirs(root: Path, dry_run: bool, stats: dict):
    for dir_path in _iter_dirs(root):
        if dir_path.name not in _CACHE_DIR_NAMES:
            continue
        if dir_path.name == "__pycache__":
            for file_path in _iter_files(dir_path):
                if file_path.suffix.lower() in _BYTECODE_SUFFIXES:
                    _remove_file(file_path, "__pycache__", dry_run, stats)
            _remove_empty_dirs(dir_path, root, dry_run, stats)
        else:
            _remove_dir_tree(dir_path, dir_path.name, dry_run, stats)


def _clean_restore_temp_dirs(root: Path, dry_run: bool, stats: dict):
    for dir_path in root.iterdir() if root.exists() else []:
        if dir_path.is_dir() and dir_path.name.startswith("ql_restore_icons_"):
            _remove_dir_tree(dir_path, "restore_temp", dry_run, stats)


def _iter_files(root: Path):
    try:
        for current, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {".git"}]
            for name in files:
                yield Path(current) / name
    except OSError:
        return


def _iter_dirs(root: Path):
    try:
        for current, dirs, _files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {".git"}]
            for name in list(dirs):
                yield Path(current) / name
    except OSError:
        return


def _remove_file(path: Path, area: str, dry_run: bool, stats: dict):
    root = Path(stats["root"])
    try:
        path = resolve_under(root, path)
    except UnsafePathError:
        stats["failed"] += 1
        return
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    if not dry_run:
        try:
            path.unlink()
        except OSError:
            stats["failed"] += 1
            return
    _add_removed(stats, area, 1, size)


def _remove_dir_tree(path: Path, area: str, dry_run: bool, stats: dict):
    root = Path(stats["root"])
    try:
        path = resolve_under(root, path)
    except UnsafePathError:
        stats["failed"] += 1
        return
    files = list(_iter_files(path))
    count = len(files)
    size = sum(_safe_size(p) for p in files)
    if not dry_run:
        try:
            safe_rmtree_child(root, path)
        except (OSError, UnsafePathError):
            stats["failed"] += 1
            return
    _add_removed(stats, area, count, size)


def _remove_empty_dirs(root: Path, stop_at: Path, dry_run: bool, stats: dict):
    if not root.exists():
        return
    for current, dirs, files in os.walk(root, topdown=False):
        current_path = Path(current)
        if current_path == stop_at:
            continue
        if dirs or files:
            continue
        if not dry_run:
            try:
                current_path.rmdir()
            except OSError:
                continue
        _add_removed(stats, "empty_dirs", 1, 0)


def _add_removed(stats: dict, area: str, count: int, size: int):
    if count <= 0:
        return
    area_stats = stats["by_area"].setdefault(area, {"files_removed": 0, "size_freed_mb": 0})
    area_stats["files_removed"] += count
    area_stats["size_freed_mb"] += size / (1024 * 1024)
    stats["total_removed"] += count
    stats["total_size_freed_mb"] += size / (1024 * 1024)


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _normalize_path(path) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(str(path or ""))))


def _safe_child_or_none(root: Path, candidate: Path) -> Path | None:
    try:
        return resolve_under(root, candidate)
    except UnsafePathError:
        return None


def _round_stats(stats: dict):
    for key, value in list(stats.items()):
        if isinstance(value, float):
            stats[key] = round(value, 2)
    for area_stats in stats.get("by_area", {}).values():
        for key, value in list(area_stats.items()):
            if isinstance(value, float):
                area_stats[key] = round(value, 2)
