"""Filesystem boundary checks for destructive operations."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import uuid
from pathlib import Path

from runtime_paths import app_root


class UnsafePathError(ValueError):
    """Raised when a path resolves outside the expected root."""


def resolve_existing(path: str | os.PathLike[str]) -> Path:
    """Resolve a path without requiring every component to exist."""
    return Path(path).expanduser().resolve(strict=False)


def assert_safe_user_path(path: str | os.PathLike[str], *, operation: str = "file operation") -> Path:
    """Reject paths that should never be modified by user-authored chains.

    The action-chain file processors accept values from variables and plugin
    outputs, so destructive/write operations need a host-side boundary even
    when the UI has already shown risk metadata.
    """
    raw = str(path or "").strip().strip('"')
    if not raw:
        raise UnsafePathError(f"Refusing empty path for {operation}")
    target = resolve_existing(raw)
    if _is_drive_or_fs_root(target):
        raise UnsafePathError(f"Refusing to operate on filesystem root: {target}")
    if target.exists() and is_link_or_reparse_point(target):
        raise UnsafePathError(f"Refusing to operate on symlink or reparse point: {target}")
    for protected in _protected_roots():
        if _is_allowed_temp_path(target):
            continue
        if target == protected or protected in target.parents:
            raise UnsafePathError(f"Refusing {operation} inside protected path: {target}")
        if target in protected.parents:
            raise UnsafePathError(f"Refusing {operation} on parent of protected path: {target}")
    return target


def move_to_trash(path: str | os.PathLike[str]) -> Path | None:
    """Move a file/folder to the OS trash or a recoverable app trash folder."""
    target = assert_safe_user_path(path, operation="delete")
    if not target.exists():
        return None
    try:
        from send2trash import send2trash

        send2trash(str(target))
        return None
    except ImportError:
        trash_root = Path(tempfile.gettempdir()) / "QuickLauncherTrash"
        trash_root.mkdir(parents=True, exist_ok=True)
        destination = trash_root / f"{target.name}.{uuid.uuid4().hex}"
        shutil.move(str(target), str(destination))
        return destination


def is_safe_child(root: str | os.PathLike[str], candidate: str | os.PathLike[str], *, allow_root: bool = False) -> bool:
    try:
        root_path = resolve_existing(root)
        candidate_path = resolve_existing(candidate)
        if candidate_path == root_path:
            return allow_root
        return root_path in candidate_path.parents
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def resolve_under(
    root: str | os.PathLike[str],
    candidate: str | os.PathLike[str],
    *,
    allow_root: bool = False,
) -> Path:
    root_path = resolve_existing(root)
    candidate_path = resolve_existing(candidate)
    if candidate_path == root_path and allow_root:
        return candidate_path
    if candidate_path != root_path and root_path in candidate_path.parents:
        return candidate_path
    raise UnsafePathError(f"Refusing path outside root: {candidate_path} (root: {root_path})")


def safe_rmtree_child(
    root: str | os.PathLike[str], target: str | os.PathLike[str], *, missing_ok: bool = False
) -> None:
    raw_target = Path(target).expanduser()
    if is_link_or_reparse_point(raw_target):
        raise UnsafePathError(f"Refusing to remove symlink or reparse point: {raw_target}")
    target_path = resolve_under(root, target, allow_root=False)
    if not target_path.exists():
        if missing_ok:
            return
        raise FileNotFoundError(str(target_path))
    if target_path.is_dir():
        shutil.rmtree(target_path)
        return
    target_path.unlink()


def is_link_or_reparse_point(path: str | os.PathLike[str]) -> bool:
    """Return whether a path is a symlink or Windows reparse point."""
    candidate = Path(path).expanduser()
    try:
        if candidate.is_symlink():
            return True
        attributes = getattr(candidate.lstat(), "st_file_attributes", 0)
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except (FileNotFoundError, OSError):
        return False


def _protected_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    env_names = (
        "SystemRoot",
        "WINDIR",
        "ProgramFiles",
        "ProgramFiles(x86)",
        "ProgramData",
        "APPDATA",
        "LOCALAPPDATA",
    )
    for name in env_names:
        value = os.environ.get(name)
        if value:
            roots.append(resolve_existing(value))
    home = Path.home()
    if str(home):
        roots.append(resolve_existing(home / ".qoderwork"))
    roots.append(app_root())
    deduped: list[Path] = []
    for root in roots:
        if root not in deduped:
            deduped.append(root)
    return tuple(deduped)


def _is_allowed_temp_path(path: Path) -> bool:
    try:
        temp_root = resolve_existing(tempfile.gettempdir())
    except (OSError, RuntimeError):
        return False
    return temp_root in path.parents


def _is_drive_or_fs_root(path: Path) -> bool:
    try:
        return path.parent == path or str(path) == path.anchor
    except (OSError, RuntimeError):
        return False
