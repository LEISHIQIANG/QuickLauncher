"""Safety helpers for configuration ZIP import and restore."""

from __future__ import annotations

import os
import zipfile
from pathlib import PurePosixPath

from application.errors import SecurityViolation

MAX_ZIP_ENTRIES = 2048
MAX_ZIP_TOTAL_BYTES = 256 * 1024 * 1024
MAX_CONFIG_BYTES = 10 * 1024 * 1024
MAX_ICON_BYTES = 10 * 1024 * 1024
MAX_BACKGROUND_BYTES = 25 * 1024 * 1024
ALLOWED_ICON_EXTS = {".ico", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
ALLOWED_BACKGROUND_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def new_import_report() -> dict:
    return {
        "dry_run": False,
        "mode": "",
        "skipped_files": [],
        "skipped_settings": [],
        "warnings": [],
        "imported_items": 0,
    }


def add_warning(report: dict | None, message: str):
    if report is not None and message:
        report.setdefault("warnings", []).append(str(message))


def skip_file(report: dict | None, name: str, reason: str):
    if report is not None:
        report.setdefault("skipped_files", []).append({"name": str(name), "reason": str(reason)})
    add_warning(report, f"Skipped {name}: {reason}")


def skip_setting(report: dict | None, name: str, reason: str):
    if report is not None:
        report.setdefault("skipped_settings", []).append({"name": str(name), "reason": str(reason)})
    add_warning(report, f"Skipped setting {name}: {reason}")


def set_imported_items(report: dict | None, count: int):
    if report is not None:
        report["imported_items"] = int(count)


def has_report_warnings(report: dict | None) -> bool:
    if not report:
        return False
    return bool(report.get("warnings") or report.get("skipped_files") or report.get("skipped_settings"))


class UnsafeZipError(ValueError, SecurityViolation):
    """Raised when a ZIP package should not be processed further."""


def normalize_zip_name(name: str) -> str | None:
    raw = str(name or "").replace("\\", "/").strip()
    if not raw:
        return None
    if "\x00" in raw:
        return None
    if raw.startswith("/") or raw.startswith("//"):
        return None
    if len(raw) >= 2 and raw[1] == ":":
        return None
    # Check for empty parts (consecutive slashes) before PurePosixPath normalizes them
    if "//" in raw:
        return None
    # Check for dot components before PurePosixPath normalizes them
    if raw.startswith("./") or raw.startswith("../") or "/./" in raw or "/../" in raw:
        return None
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return None
    return path.as_posix()


def build_safe_zip_index(zf: zipfile.ZipFile, report: dict | None = None) -> dict[str, zipfile.ZipInfo]:
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise UnsafeZipError(f"zip has too many entries: {len(infos)}")

    total = 0
    safe: dict[str, zipfile.ZipInfo] = {}
    seen_targets: set[str] = set()
    for info in infos:
        name = normalize_zip_name(info.filename)
        if info.flag_bits & 0x1:
            skip_file(report, info.filename, "encrypted entries are not supported")
            continue
        if not name:
            skip_file(report, info.filename, "unsafe archive path")
            continue
        total += max(0, int(info.file_size))
        if total > MAX_ZIP_TOTAL_BYTES:
            raise UnsafeZipError("zip uncompressed size exceeds limit")
        key = name.lower()
        if key in safe:
            skip_file(report, info.filename, "duplicate archive path")
            continue
        if name.startswith("icons/") and not name.endswith("/"):
            target_key = os.path.basename(name).lower()
            if target_key in seen_targets:
                skip_file(report, info.filename, "duplicate target file name")
                continue
            seen_targets.add(target_key)
        safe[key] = info
    return safe


def has_zip_entry(index: dict[str, zipfile.ZipInfo], name: str) -> bool:
    normalized = normalize_zip_name(name)
    return bool(normalized and normalized.lower() in index)


def read_zip_bytes(
    zf: zipfile.ZipFile,
    index: dict[str, zipfile.ZipInfo],
    name: str,
    max_bytes: int,
    report: dict | None = None,
    required: bool = False,
) -> bytes | None:
    normalized = normalize_zip_name(name)
    info = index.get(normalized.lower()) if normalized else None
    if info is None:
        if required:
            raise UnsafeZipError(f"Missing required archive entry: {name}")
        return None
    if info.file_size > max_bytes:
        skip_file(report, normalized or name, "file exceeds size limit")
        if required:
            raise UnsafeZipError(f"required entry exceeds size limit: {name}")
        return None
    try:
        return zf.read(info)
    except RuntimeError as exc:
        skip_file(report, normalized or name, str(exc))
        if required:
            raise UnsafeZipError(str(exc)) from exc
        return None


def read_zip_text(
    zf: zipfile.ZipFile,
    index: dict[str, zipfile.ZipInfo],
    name: str,
    max_bytes: int = MAX_CONFIG_BYTES,
    report: dict | None = None,
    required: bool = False,
) -> str | None:
    data = read_zip_bytes(zf, index, name, max_bytes, report, required)
    if data is None:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        skip_file(report, name, "not valid UTF-8")
        if required:
            raise UnsafeZipError(f"required entry is not valid UTF-8: {name}") from None
        return None


def is_allowed_icon_path(name: str) -> bool:
    normalized = normalize_zip_name(name)
    if not normalized or not normalized.lower().startswith("icons/") or normalized.endswith("/"):
        return False
    return os.path.splitext(normalized)[1].lower() in ALLOWED_ICON_EXTS


def is_allowed_background_path(name: str) -> bool:
    normalized = normalize_zip_name(name)
    if not normalized or normalized.endswith("/"):
        return False
    return os.path.splitext(normalized)[1].lower() in ALLOWED_BACKGROUND_EXTS
