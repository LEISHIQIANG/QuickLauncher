"""Lightweight typed event bus — replacement for the deleted ``_callbacks`` dict.

The old ``core/__init__.py`` ``_callbacks`` dictionary was removed during the
W2 refactoring with no replacement. This module provides a strongly-typed
publish/subscribe mechanism that fulfills the target architecture's rule 5:
"跨模块通信使用强类型命令、查询、结果和事件" (§4.1).

Usage::

    from application.events import Event, EventBus, event_bus

    @dataclass
    class ConfigSaved(Event):
        revision: int
        file_path: str

    def on_saved(event: ConfigSaved) -> None:
        print(f"Config saved at revision {event.revision}")

    event_bus.subscribe(ConfigSaved, on_saved)
    event_bus.publish(ConfigSaved(revision=42, file_path="data.json"))
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Base class for all domain events.

    Subclass with specific payload fields::

        @dataclass
        class ShortcutLaunched(Event):
            shortcut_id: str
            shortcut_name: str
    """

    #: Monotonic timestamp set automatically on instantiation.
    timestamp: float = field(default_factory=time.monotonic, init=False)


class EventListener(Protocol):
    """A callable that receives typed events.

    Implementations should accept a single :class:`Event` subclass as argument.
    """

    def __call__(self, event: Event) -> None: ...


class EventBus:
    """Thread-safe publish/subscribe event bus.

    Listeners register for specific :class:`Event` subclasses. On
    :meth:`publish`, all matching listeners are called synchronously
    in registration order. Exceptions in listeners are logged but
    never propagated — a single misbehaving listener must not block
    other subscribers.

    The bus is deliberately minimal: no async, no priority queues,
    no middleware. Complexity can be added later when real patterns
    emerge.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._listeners: dict[type[Event], list[EventListener]] = defaultdict(list)

    def subscribe(self, event_type: type[Event], listener: EventListener) -> None:
        """Register *listener* to be called for events of type *event_type*."""
        with self._lock:
            self._listeners[event_type].append(listener)

    def unsubscribe(self, event_type: type[Event], listener: EventListener) -> None:
        """Remove *listener* from *event_type* subscriptions.

        Does nothing if the listener was not registered.
        """
        with self._lock:
            bucket = self._listeners.get(event_type)
            if bucket and listener in bucket:
                bucket.remove(listener)

    def publish(self, event: Event) -> None:
        """Deliver *event* to all registered listeners for its type.

        Listeners are called synchronously. Exceptions are caught,
        logged, and suppressed — they never propagate to the publisher.
        """
        event_type = type(event)
        with self._lock:
            listeners = list(self._listeners.get(event_type, []))
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("Event listener %s failed for %s", listener, event_type.__name__)


#: Global singleton event bus. Modules that do not yet receive the bus
#: via dependency injection can import this instance directly.
event_bus = EventBus()


# ── built-in domain events ──────────────────────────────────────────


@dataclass
class ConfigSaved(Event):
    """Emitted after a successful configuration save to disk."""

    revision: int
    file_path: str
    trigger_settings_preserved: bool = False


@dataclass
class ConfigLoaded(Event):
    """Emitted after configuration is loaded from disk."""

    version: str
    schema_version: int


@dataclass
class ShortcutExecuted(Event):
    """Emitted when a shortcut is executed (before the handler runs)."""

    shortcut_id: str
    shortcut_name: str
    shortcut_type: str
