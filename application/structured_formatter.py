"""Logging formatter that emits the W8 structured-logging fields.

The :class:`StructuredFormatter` decorates Python's standard
``LogRecord`` with four extra fields that the W8 contract requires:

* ``operation_id`` — opaque correlation token from the
  :class:`application.logging_context.OperationContext` block
* ``component`` — subsystem that produced the entry
* ``duration_ms`` — wall-clock duration since the block started
* ``error_code`` — stable taxonomy identifier from
  :mod:`application.errors`

Records emitted outside an ``OperationContext`` block use empty
strings for the four fields.  This is the opt-in rollout model
described in ``application.logging_context``.

The formatter does **not** alter the rendered message; it only adds
key/value pairs to the formatted output.  Callers can still grep the
text stream for the original ``logger.info("...")`` payload; the
structured fields appear in a fixed key=value tail so structured
ingestors (Loki / Elasticsearch / Datadog) can parse them.
"""

from __future__ import annotations

import logging


class StructuredFormatter(logging.Formatter):
    """Append ``operation_id`` / ``component`` / ``duration_ms`` / ``error_code``.

    The default ``fmt`` keeps the standard timestamp + level + name +
    message header and adds the four fields as a trailing key=value
    block.  Subclasses can override ``fmt`` if a different layout is
    needed.
    """

    BASE_FMT = (
        "%(asctime)s %(levelname)-5s [%(name)s] "
        "%(operation_id)s %(component)s %(duration_ms).2fms "
        "%(error_code)s %(message)s"
    )
    BASE_DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
    ) -> None:
        super().__init__(
            fmt=fmt if fmt is not None else self.BASE_FMT,
            datefmt=datefmt if datefmt is not None else self.BASE_DATEFMT,
        )

    def format(self, record: logging.LogRecord) -> str:
        # Lazy import keeps the logging context out of any code path
        # that does not need structured fields (e.g. startup banners).
        from application.logging_context import current

        ctx = current()
        record.operation_id = ctx.operation_id if ctx is not None else ""
        record.component = ctx.component if ctx is not None else ""
        record.duration_ms = ctx.duration_ms if ctx is not None else 0.0
        record.error_code = ctx.error_code if ctx is not None else ""
        return super().format(record)


__all__ = ["StructuredFormatter"]
