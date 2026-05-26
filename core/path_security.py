"""Filesystem boundary checks for destructive operations."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


class UnsafePathError(ValueError):
    """Raised when a path resolves outside the expected root."""


def resolve_existing(path: str | os.PathLike[str]) -> Path:
    """Resolve a path without requiring every component to exist."""
    return Path(path).expanduser().resolve(strict=False)


def is_safe_child(root: str | os.PathLike[str], candidate: str | os.PathLike[str], *, allow_root: bool = False) -> bool:
    try:
        root_path = resolve_existing(root)
        candidate_path = resolve_existing(candidate)
        if candidate_path == root_path:
            return allow_root
        return root_path in candidate_path.parents
    except Exception:
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
    if raw_target.is_symlink():
        raise UnsafePathError(f"Refusing to remove symlink: {raw_target}")
    target_path = resolve_under(root, target, allow_root=False)
    if not target_path.exists():
        if missing_ok:
            return
        raise FileNotFoundError(str(target_path))
    if target_path.is_dir():
        shutil.rmtree(target_path)
        return
    target_path.unlink()
