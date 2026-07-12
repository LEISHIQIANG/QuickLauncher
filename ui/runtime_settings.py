"""Read-only UI settings port configured by the application composition root."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_settings_provider: Callable[[], Any] | None = None


def configure_settings_provider(provider: Callable[[], Any] | None) -> None:
    global _settings_provider
    _settings_provider = provider


def current_settings() -> Any | None:
    return _settings_provider() if _settings_provider is not None else None
