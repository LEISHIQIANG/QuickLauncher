"""Central theme resolution for custom QuickLauncher windows."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

VALID_THEMES = frozenset({"dark", "light"})
DEFAULT_THEME = "dark"


def normalize_theme(theme: Any, default: str = DEFAULT_THEME) -> str:
    """Return a supported theme name."""
    value = str(theme or "").strip().lower()
    if value in VALID_THEMES:
        return value
    fallback = str(default or DEFAULT_THEME).strip().lower()
    return fallback if fallback in VALID_THEMES else DEFAULT_THEME


def get_app_theme(default: str = DEFAULT_THEME) -> str:
    """Resolve the persisted application theme without exposing DataManager."""
    try:
        from core import get_data_manager

        settings = get_data_manager().get_settings()
        return normalize_theme(getattr(settings, "theme", ""), default)
    except Exception as exc:
        logger.debug("读取全局主题失败: %s", exc, exc_info=True)
        return normalize_theme(default)


def resolve_theme(owner: Any = None, default: str = DEFAULT_THEME) -> str:
    """Resolve theme from an owner first, then from the global app settings."""
    for attr in ("theme", "_theme", "current_theme"):
        try:
            value = getattr(owner, attr, None) if owner is not None else None
            if value:
                return normalize_theme(value, default)
        except Exception:
            continue
    try:
        data_manager = getattr(owner, "data_manager", None) if owner is not None else None
        if data_manager is not None:
            return normalize_theme(getattr(data_manager.get_settings(), "theme", ""), default)
    except Exception as exc:
        logger.debug("读取窗口主题失败: %s", exc, exc_info=True)
    return get_app_theme(default)
