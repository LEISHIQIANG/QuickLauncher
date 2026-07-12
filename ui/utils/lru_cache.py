"""Small LRU cache helpers used across the UI layer.

Two flavours are provided:

* :func:`lru_cache` – a thin wrapper around :func:`functools.lru_cache`
  that gracefully handles ``QColor`` / ``QSize`` arguments (which are
  not hashable on older PyQt5 builds) by routing them through a stable
  ``key_fn``.

* :func:`pixmap_cache` – a small decorator tailored to ``QPixmap``
  rendering pipelines. The cache key is the tuple produced by ``key_fn``
  applied to the wrapped function's arguments. The cache is bounded
  (default 200 entries) and exposes a ``cache_clear()`` method to
  release memory when the owning widget is destroyed.

Example
-------
::

    @pixmap_cache(maxsize=200, key=lambda size, hash_: (size, hash_))
    def render_thumbnail(path, size, hash_):
        ...
"""

from __future__ import annotations

import functools
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

__all__ = [
    "lru_cache",
    "pixmap_cache",
    "CacheInfo",
]

F = TypeVar("F", bound=Callable[..., Any])
K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class CacheInfo:
    """Snapshot of cache statistics (used in tests / diagnostics)."""

    __slots__ = ("hits", "misses", "maxsize", "currsize")

    def __init__(self, hits: int = 0, misses: int = 0, maxsize: int = 0, currsize: int = 0):
        self.hits = hits
        self.misses = misses
        self.maxsize = maxsize
        self.currsize = currsize

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return (
            f"CacheInfo(hits={self.hits}, misses={self.misses}, " f"maxsize={self.maxsize}, currsize={self.currsize})"
        )


class _LRUStore:
    """Thread-safe LRU store keyed on hashable objects."""

    def __init__(self, maxsize: int = 128):
        if maxsize <= 0:
            raise ValueError("maxsize must be > 0")
        self._maxsize = int(maxsize)
        self._lock = threading.RLock()
        self._data: OrderedDict[Hashable, Any] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: Hashable) -> tuple[bool, Any]:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self._hits += 1
                return True, self._data[key]
            self._misses += 1
            return False, None

    def put(self, key: Hashable, value: Any) -> None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self._data[key] = value
                return
            self._data[key] = value
            if len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0

    def info(self) -> CacheInfo:
        with self._lock:
            return CacheInfo(self._hits, self._misses, self._maxsize, len(self._data))

    @property
    def maxsize(self) -> int:
        return self._maxsize


def lru_cache(maxsize: int = 128, key_fn: Callable[..., Hashable] | None = None) -> Callable[[F], F]:
    """Wrap ``func`` with a thread-safe LRU cache.

    ``key_fn(*args, **kwargs)`` produces the cache key. If ``key_fn`` is
    ``None`` the function arguments are used directly (positional only).
    """

    def decorator(func: F) -> F:
        store = _LRUStore(maxsize=maxsize)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if key_fn is not None:
                key = key_fn(*args, **kwargs)
            else:
                key = args
            hit, value = store.get(key)
            if hit:
                return value
            value = func(*args, **kwargs)
            store.put(key, value)
            return value

        wrapper.cache_clear = store.clear  # type: ignore[attr-defined]
        wrapper.cache_info = store.info  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def pixmap_cache(maxsize: int = 200, key: Callable[..., Hashable] | None = None) -> Callable[[F], F]:
    """Decorator tailored to ``QPixmap`` rendering pipelines.

    The wrapped function is expected to return a value that should not be
    copied (such as a :class:`QPixmap` or a cached ``bytes`` blob). The
    cache evicts the least-recently-used entry when ``maxsize`` is
    exceeded.
    """

    key_fn = key
    if key_fn is None:
        # Default: hash on the first positional arg + a tuple of remaining
        # args – mirrors ``functools.lru_cache`` for the common case.
        def default_key(*args, **kwargs):
            return (args[0], args[1:])

        key_fn = default_key

    return lru_cache(maxsize=maxsize, key_fn=key_fn)
