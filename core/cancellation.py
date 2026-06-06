"""Cooperative cancellation token for long-running operations.

This module provides a lightweight ``CancellationToken`` that can be passed
into plugin handlers, chain processors, and other potentially long-running
operations.  The token is a thin wrapper around ``threading.Event`` so that
callers can signal cancellation and workers can poll it at natural checkpoints.
"""

from __future__ import annotations

import threading
from typing import Any


class CancellationToken:
    """A cooperative cancellation token backed by a ``threading.Event``.

    Workers should call ``is_cancelled()`` (or check ``cancelled``) at
    regular intervals — especially inside loops, before blocking I/O, and
    after ``sleep`` calls — and exit early when it returns ``True``.
    """

    __slots__ = ("_event", "_reason")

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason: str = ""

    # ── Query API (for workers) ──────────────────────────────────────

    @property
    def cancelled(self) -> bool:
        """Return ``True`` if cancellation has been requested."""
        return self._event.is_set()

    def is_cancelled(self) -> bool:
        """Alias for ``cancelled`` — explicit method form."""
        return self._event.is_set()

    @property
    def reason(self) -> str:
        """Human-readable reason why cancellation was requested."""
        return self._reason

    # ── Signal API (for callers) ─────────────────────────────────────

    def cancel(self, reason: str = "") -> None:
        """Request cancellation.  Idempotent."""
        if reason:
            self._reason = reason
        self._event.set()

    # ── Integration helpers ──────────────────────────────────────────

    def wait(self, timeout: float | None = None) -> bool:
        """Block until cancelled or *timeout* seconds elapse.

        Returns ``True`` if the token was cancelled within the timeout.
        """
        return self._event.wait(timeout=timeout)

    def as_cancel_event(self) -> threading.Event:
        """Return the underlying ``Event`` for code that expects a raw event."""
        return self._event

    @classmethod
    def from_event(cls, event: Any) -> CancellationToken:
        """Wrap an existing ``threading.Event`` as a ``CancellationToken``.

        This lets legacy code that already passes a ``cancel_event``
        parameter gradually migrate to the token interface.
        """
        if isinstance(event, cls):
            return event
        token = cls()
        if event is not None and hasattr(event, "is_set"):
            if event.is_set():
                token.cancel("inherited")
        return token
