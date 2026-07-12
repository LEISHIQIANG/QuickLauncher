"""Adapter that implements :class:`application.ports.platform.IconProvider`.

The port contract is intentionally narrow — it just exposes
``extract(source, *, size)`` and ``invalidate(source)``.  The QuickLauncher
core caches icons through :class:`core.icon_extractor.IconExtractor` which
exposes a more featureful API (``extract`` with several optional flags,
plus ``clear_cache`` for the whole cache).  This module is the thin
translator so the rest of the application can depend on the port, not on
the implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from application.ports.platform import IconProvider


class CoreIconProviderAdapter(IconProvider):
    """Adapter backed by :class:`core.icon_extractor.IconExtractor`.

    The adapter caches the last error per source so callers can observe
    a failure without re-raising.  The QuickLauncher icon extractor
    itself does not raise on extraction failure (it returns ``None`` and
    logs a warning), so the adapter mirrors that contract.
    """

    def __init__(self) -> None:
        self._last_error: dict[str, str] = {}

    def extract(self, source: str | Path, *, size: int = 32) -> Any:
        from core.icon_extractor import IconExtractor

        normalized = str(source)
        try:
            return IconExtractor.extract(
                normalized,
                target_path=normalized,
                size=int(size),
                return_image=False,
                fallback_to_default=False,
            )
        except (OSError, ValueError, TypeError) as exc:
            # IconExtractor wraps internal Qt errors; surface them as a
            # port-level failure that callers can inspect via last_error.
            self._last_error[normalized] = str(exc)
            return None

    def invalidate(self, source: str | Path) -> None:
        # IconExtractor does not expose per-source invalidation.  The
        # closest operation is to clear the entire cache; the caller
        # is opting into "forget everything", which is acceptable
        # because the cache rebuilds lazily on the next extract.
        from core.icon_extractor import IconExtractor

        try:
            IconExtractor.clear_cache()
        except (OSError, ValueError, TypeError) as exc:
            self._last_error[str(source)] = str(exc)
