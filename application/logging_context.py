"""Structured logging context for the W8 observability pass.

W8 requires the log stream to carry ``operation_id`` (an opaque
correlation token propagated through one user-visible action),
``component`` (the subsystem that produced the entry, e.g. ``"save"`` /
``"command_exec"`` / ``"plugin"``), ``duration_ms`` (the wall-clock
duration of the surrounding operation) and ``error_code`` (the
stable taxonomy identifier from :mod:`application.errors`).

The :class:`OperationContext` is a small context-manager around a
:mod:`contextvars` token.  Service code wraps the action body in
``with OperationContext("save", "config")``; the helper installs the
context for the duration of the block, and the structured formatter
(see ``bootstrap/logging_init.py``) reads the values back out via
:meth:`current`.

The context is **opt-in** — log records emitted outside an
``OperationContext`` block still work and the formatter fills the
missing fields with empty strings.  This keeps the rollout
incremental: existing logger calls in :mod:`core` and :mod:`ui` keep
behaving as they do today, and only the call sites that wrap an
operation in ``OperationContext`` opt into the structured fields.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field

_current: ContextVar[OperationContext | None] = ContextVar("ql_operation_context", default=None)


@dataclass
class OperationContext:
    """Structured-logging context attached to one user-visible action.

    Attributes mirror the W8 log contract.  ``operation_id`` is
    generated lazily so callers can opt in with the natural
    ``OperationContext(component, action)`` form and still get a
    unique correlation token per invocation.
    """

    component: str = ""
    action: str = ""
    operation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: float = field(default_factory=time.monotonic)
    error_code: str = ""

    @property
    def duration_ms(self) -> float:
        return (time.monotonic() - self.started_at) * 1000.0

    def with_error_code(self, code: str) -> OperationContext:
        """Mutate the active context's ``error_code`` and return ``self``.

        The legacy contract returned a new dataclass instance, but that
        only updates the caller's local binding.  The structured
        formatter reads the active context through the
        :class:`ContextVar` and is therefore unaffected by Python
        variable rebinding.  Mutating in place (without ``frozen=True``
        on the dataclass) is the only way to make the contract work
        end-to-end.  The ``operation_id`` is preserved so downstream
        log lines still correlate with the original block.
        """
        self.error_code = str(code)
        return self


@contextmanager
def operation_context(component: str, action: str = "") -> Iterator[OperationContext]:
    """Install a fresh :class:`OperationContext` for the duration of the block.

    Usage::

        with operation_context("save", "config") as ctx:
            save_coordinator.save()
            ctx.with_error_code("ok")

    The context-manager returns the same context it installs, so the
    caller can decorate it with ``error_code`` after the operation
    completes.  The token returned by :meth:`ContextVar.set` is used
    to restore the previous context on exit, supporting nesting.
    """
    ctx = OperationContext(component=component, action=action)
    token: Token[OperationContext | None] = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)


def current() -> OperationContext | None:
    """Return the active :class:`OperationContext`, or ``None`` outside one."""
    return _current.get()
