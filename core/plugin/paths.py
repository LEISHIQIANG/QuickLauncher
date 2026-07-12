"""Path helpers for plugin package and manifest validation."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from .constants import PLUGIN_PACKAGE_EXTENSION


def is_plugin_package_path(path: str | os.PathLike[str]) -> bool:
    return Path(path).suffix.lower() == PLUGIN_PACKAGE_EXTENSION


def safe_relative_plugin_path(raw: str) -> str | None:
    value = str(raw or "").replace("\\", "/").strip()
    if not value or value.startswith("/") or value.startswith("//"):
        return None
    if len(value) >= 2 and value[1] == ":":
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return None
    return path.as_posix()
