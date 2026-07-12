"""Infrastructure adapter for the Clock port."""

from __future__ import annotations

import time

from application.ports.persistence import Clock  # noqa: F401 — port contract, structural match

__all__ = ["SystemClock", "system_clock"]


class SystemClock:
    """Real-time clock adapter using :func:`time.monotonic`.

    Implements :class:`~application.ports.persistence.Clock`.
    """

    def now(self) -> float:
        return time.monotonic()


#: Singleton instance for dependency injection.
system_clock = SystemClock()
