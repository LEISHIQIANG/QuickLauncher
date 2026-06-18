"""Configuration schema validation and backup recovery helpers."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace

from .data_models import AppData, AppSettings, ShortcutType
from .import_security import skip_setting
from .trigger_config import normalize_trigger_settings

logger = logging.getLogger(__name__)
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_INT_RANGES = {
    "bg_alpha": (0, 100),
    "dock_bg_alpha": (0, 100),
    "icon_size": (12, 128),
    "cell_size": (28, 192),
    "cols": (1, 20),
    "corner_radius": (0, 64),
    "last_page_index": (0, 1000),
    "dock_height_mode": (0, 8),
    "popup_max_rows": (1, 8),
    "hover_leave_delay": (0, 5000),
    "double_click_interval": (100, 2000),
    "bg_blur_radius": (0, 80),
    "theme_bg_alpha": (0, 100),
    "theme_blur_radius": (0, 80),
    "image_bg_alpha": (0, 100),
    "image_blur_radius": (0, 80),
    "acrylic_bg_alpha": (0, 100),
    "acrylic_blur_radius": (0, 80),
    "shadow_size": (0, 80),
    "shadow_distance": (0, 80),
    "sleep_timeout_seconds": (1, 3600),
    # 颜色滤镜参数 (dark / light 各 6 个)
    "dark_black_point": (0, 100),
    "dark_white_point": (0, 100),
    "dark_mid_gamma": (0, 100),
    "dark_temperature": (0, 100),
    "dark_acrylic": (1, 255),
    "dark_bg_alpha_filter": (1, 255),
    "light_black_point": (0, 100),
    "light_white_point": (0, 100),
    "light_mid_gamma": (0, 100),
    "light_temperature": (0, 100),
    "light_acrylic": (1, 255),
    "light_bg_alpha_filter": (1, 255),
    "ui_scale_percent": (90, 150),
}
_FLOAT_RANGES = {
    "icon_alpha": (0.0, 1.0),
    "theme_edge_opacity": (0.0, 1.0),
    "image_edge_opacity": (0.0, 1.0),
    "acrylic_edge_opacity": (0.0, 1.0),
    "edge_highlight_opacity": (0.0, 1.0),
}
_STRING_CHOICES = {
    "theme": {"dark", "light"},
    "sort_mode": {"custom", "smart"},
    "popup_align_mode": {"mouse_center", "mouse_top_left", "screen_center", "bottom_right"},
    "bg_mode": {"theme", "image", "color", "acrylic"},
    "language": {"zh_CN", "en_US"},
    "popup_trigger_mode": {"keyboard", "mouse", "hybrid"},
    "popup_special_trigger_mode": {"keyboard", "mouse", "hybrid"},
}
_STRING_FIELDS = {
    "last_version",
    "custom_bg_path",
    "bg_solid_color",
    "edge_highlight_color",
    "popup_trigger_button",
    "popup_special_trigger_button",
}
_LIST_STRING_FIELDS = {
    "special_apps",
    "enabled_plugins",
    "favorite_commands",
    "disabled_builtin_commands",
    "popup_trigger_keys",
    "popup_trigger_modifiers",
    "popup_special_trigger_keys",
    "popup_special_trigger_modifiers",
}


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _safe_bool(value, default):
    if isinstance(value, bool):
        return value
    return default


def _safe_int(key: str, value, default, report: dict | None):
    minimum, maximum = _INT_RANGES[key]
    try:
        try:
            converted = int(value)
        except ValueError:
            converted = int(float(value))
    except (TypeError, ValueError):
        skip_setting(report, key, "invalid integer")
        return default
    clamped = _clamp(converted, minimum, maximum)
    if clamped != converted:
        skip_setting(report, key, "integer outside safe range")
    return clamped


def _safe_float(key: str, value, default, report: dict | None):
    minimum, maximum = _FLOAT_RANGES[key]
    try:
        converted = float(value)
    except (TypeError, ValueError):
        skip_setting(report, key, "invalid float")
        return default
    clamped = _clamp(converted, minimum, maximum)
    if clamped != converted:
        skip_setting(report, key, "float outside safe range")
    return clamped


def _safe_string_list(key: str, value, default, report: dict | None) -> list[str]:
    if not isinstance(value, list):
        skip_setting(report, key, "expected list")
        return list(default)
    result = []
    seen = set()
    for item in value[:256]:
        text = str(item or "").strip()
        if not text or len(text) > 256:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(text)
    return result


def sanitize_settings_dict(settings: object, report: dict | None = None) -> dict:
    """Return a settings dictionary with safe types and bounded values."""
    defaults = AppSettings().to_dict()
    if not isinstance(settings, dict):
        skip_setting(report, "settings", "expected object")
        return defaults

    sanitized = dict(defaults)
    for key, value in settings.items():
        if key not in defaults:
            continue
        default = defaults[key]
        if key in _INT_RANGES:
            sanitized[key] = _safe_int(key, value, default, report)
        elif key in _FLOAT_RANGES:
            sanitized[key] = _safe_float(key, value, default, report)
        elif isinstance(default, bool):
            sanitized[key] = _safe_bool(value, default)
            if sanitized[key] is default and not isinstance(value, bool):
                skip_setting(report, key, "expected boolean")
        elif key in _STRING_CHOICES:
            text = str(value or "")
            if text in _STRING_CHOICES[key]:
                sanitized[key] = text
            else:
                skip_setting(report, key, "invalid option")
        elif key in _LIST_STRING_FIELDS:
            sanitized[key] = _safe_string_list(key, value, default, report)
        elif key in _STRING_FIELDS:
            text = str(value or "")
            if len(text) > 2048:
                skip_setting(report, key, "string too long")
                continue
            if key.endswith("_color") and text and not _HEX_COLOR_RE.match(text):
                skip_setting(report, key, "invalid color")
                continue
            sanitized[key] = text
    sanitized.update(normalize_trigger_settings(SimpleNamespace(**sanitized)))
    return sanitized


def sanitize_app_data_dict(data: object, report: dict | None = None) -> dict:
    """Sanitize imported AppData dictionaries before deserialization."""
    if not isinstance(data, dict):
        raise ValueError("root_not_object")
    sanitized = dict(data)
    sanitized["settings"] = sanitize_settings_dict(data.get("settings", {}), report)
    folders = data.get("folders", [])
    if not isinstance(folders, list):
        raise ValueError("folders_not_list")
    sanitized_folders = []
    for folder in folders[:512]:
        if not isinstance(folder, dict):
            continue
        folder_copy = dict(folder)
        items = folder_copy.get("items", [])
        folder_copy["items"] = (
            [dict(item) for item in items[:2048] if isinstance(item, dict)] if isinstance(items, list) else []
        )
        sanitized_folders.append(folder_copy)
    sanitized["folders"] = sanitized_folders
    return sanitized


def validate_app_data_dict(data: object) -> list[str]:
    """Return validation issues for an AppData dictionary."""
    issues: list[str] = []
    if not isinstance(data, dict):
        return ["root_not_object"]

    settings = data.get("settings", {})
    if settings is not None and not isinstance(settings, dict):
        issues.append("settings_not_object")

    folders = data.get("folders", [])
    if not isinstance(folders, list):
        return issues + ["folders_not_list"]

    folder_ids: set[str] = set()
    shortcut_ids: set[str] = set()
    valid_types = {item.value for item in ShortcutType}
    for folder_index, folder in enumerate(folders):
        if not isinstance(folder, dict):
            issues.append(f"folder_{folder_index}_not_object")
            continue
        folder_id = str(folder.get("id") or "")
        if folder_id:
            if folder_id in folder_ids:
                issues.append(f"duplicate_folder_id:{folder_id}")
            folder_ids.add(folder_id)
        items = folder.get("items", [])
        if not isinstance(items, list):
            issues.append(f"folder_{folder_index}_items_not_list")
            continue
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                issues.append(f"folder_{folder_index}_item_{item_index}_not_object")
                continue
            shortcut_id = str(item.get("id") or "")
            if shortcut_id:
                if shortcut_id in shortcut_ids:
                    issues.append(f"duplicate_shortcut_id:{shortcut_id}")
                shortcut_ids.add(shortcut_id)
            item_type = str(item.get("type") or "file")
            if item_type not in valid_types:
                issues.append(f"invalid_shortcut_type:{item_type}")
    return issues


def validate_app_data(data: AppData) -> list[str]:
    return validate_app_data_dict(data.to_dict())


def load_valid_data_file(path: Path | str) -> tuple[AppData, list[str]]:
    """Load, validate, and deserialize an AppData file."""
    file_path = Path(path)
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    issues = validate_app_data_dict(raw)
    if "root_not_object" in issues or "folders_not_list" in issues:
        raise ValueError(f"fatal config schema issues: {issues}")
    return AppData.from_dict(sanitize_app_data_dict(raw)), issues


def latest_valid_backup(backup_dir: Path | str) -> Path | None:
    """Return the newest auto-backup that can be loaded as AppData."""
    backup_path = Path(backup_dir)
    if not backup_path.exists():
        return None
    candidates: Iterable[Path] = sorted(
        backup_path.glob("data_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        try:
            load_valid_data_file(candidate)
            return candidate
        except Exception as exc:
            logger.debug("skip invalid config backup %s: %s", candidate, exc)
    return None
