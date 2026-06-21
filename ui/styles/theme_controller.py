"""Central theme resolution for custom QuickLauncher windows."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

VALID_THEMES = frozenset({"dark", "light"})
DEFAULT_THEME = "dark"
_app_theme = DEFAULT_THEME
_theme_provider: Callable[[], Any] | None = None


def normalize_theme(theme: Any, default: str = DEFAULT_THEME) -> str:
    """Return a supported theme name."""
    value = str(theme or "").strip().lower()
    if value in VALID_THEMES:
        return value
    fallback = str(default or DEFAULT_THEME).strip().lower()
    return fallback if fallback in VALID_THEMES else DEFAULT_THEME


def get_app_theme(default: str = DEFAULT_THEME) -> str:
    """Return the theme injected by the GUI composition root."""
    return normalize_theme(_app_theme, default)


def set_app_theme(theme: Any) -> None:
    global _app_theme
    _app_theme = normalize_theme(theme)


def configure_theme_provider(provider: Callable[[], Any] | None) -> None:
    """Inject the call-back that yields the current theme name."""
    global _theme_provider
    _theme_provider = provider


def get_theme_provider() -> Callable[[], Any] | None:
    return _theme_provider


def resolve_theme(owner: Any = None, default: str = DEFAULT_THEME) -> str:
    """Resolve theme from an owner first, then from the global app settings."""
    current = owner
    seen: set[int] = set()
    while current is not None:
        ident = id(current)
        if ident in seen:
            break
        seen.add(ident)

        for attr in ("theme", "_theme", "current_theme"):
            try:
                value = getattr(current, attr, None)
                if value:
                    return normalize_theme(value, default)
            except Exception:
                continue
        try:
            data_manager = getattr(current, "data_manager", None)
            if data_manager is not None:
                return normalize_theme(getattr(data_manager.get_settings(), "theme", ""), default)
        except Exception as exc:
            logger.debug("读取窗口主题失败: %s", exc, exc_info=True)

        try:
            current = current.parent() if hasattr(current, "parent") else None
        except Exception:
            current = None
    return get_app_theme(default)
