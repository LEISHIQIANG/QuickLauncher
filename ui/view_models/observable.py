"""Observable collection helpers for the P1-06 view-model layer.

The :class:`ObservableList` and :class:`ObservableDict` wrap the
built-in ``list`` / ``dict`` types and emit a :pyattr:`changed`
signal whenever the collection is mutated.  View-model code can
expose them as ``pyqtProperty`` so the view receives a single
``changed`` notification and refreshes the affected cells.

Python does not allow inheriting from both :class:`QObject` and a
C-implemented builtin (``list`` / ``dict``) because the two have
conflicting C-level instance layouts.  To stay on the safe side the
two helpers *contain* a signal emitter object (``_SignalEmitter``)
and forward the mutating methods explicitly, while still behaving
like a regular collection for reads and iteration.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Any, overload

from qt_compat import QObject, pyqtSignal


class _SignalEmitter(QObject):
    """Tiny :class:`QObject` that owns the :pyattr:`changed` signal."""

    changed = pyqtSignal(object)


class ObservableList:
    """List-like collection that emits :pyattr:`changed` on mutation.

    The class wraps a real ``list`` (held in :pyattr:`_items`) and
    forwards every read / iteration to it.  Only the mutating
    methods (``append`` / ``extend`` / ``__setitem__`` / ``pop`` /
    ``clear`` / …) trigger the :pyattr:`changed` signal.
    """

    def __init__(self, iterable: Iterable[Any] | None = None) -> None:
        self._items: list[Any] = list(iterable or ())
        self._signals = _SignalEmitter()

    # ── signal access ────────────────────────────────────────────────

    @property
    def changed(self):
        return self._signals.changed

    # ── read-only list protocol ──────────────────────────────────────

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._items)

    def __reversed__(self) -> Iterator[Any]:
        return reversed(self._items)

    def __contains__(self, value: Any) -> bool:
        return value in self._items

    def __getitem__(self, index):
        return self._items[index]

    def index(self, value: Any, *args) -> int:
        return self._items.index(value, *args)

    def count(self, value: Any) -> int:
        return self._items.count(value)

    def copy(self) -> list:
        return list(self._items)

    def __repr__(self) -> str:
        return f"ObservableList({self._items!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ObservableList):
            return self._items == other._items
        return self._items == other

    # ── mutating methods ─────────────────────────────────────────────

    def append(self, value: Any) -> None:
        self._items.append(value)
        self._emit("add", index=len(self._items) - 1, key=None, value=value)

    def extend(self, values: Iterable[Any]) -> None:
        start = len(self._items)
        added = list(values)
        self._items.extend(added)
        for offset, value in enumerate(added):
            self._emit("add", index=start + offset, key=None, value=value)
        if added:
            self._emit("reset", index=start, key=None, value=None)

    def insert(self, index: int, value: Any) -> None:
        self._items.insert(index, value)
        self._emit("add", index=index, key=None, value=value)

    def pop(self, index: int = -1) -> Any:
        value = self._items.pop(index)
        self._emit("remove", index=index, key=None, value=value)
        return value

    def remove(self, value: Any) -> None:
        index = self._items.index(value)
        self._items.remove(value)
        self._emit("remove", index=index, key=None, value=value)

    def clear(self) -> None:
        if not self._items:
            return
        self._items.clear()
        self._emit("reset", index=-1, key=None, value=None)

    def __setitem__(self, index, value) -> None:
        if isinstance(index, slice):
            # Slices replace a range.  We emit one ``update`` per
            # element that landed in-bounds (so the view can refresh
            # the affected cells) plus a ``reset`` so any view that
            # only listens to bulk changes still sees the mutation.
            before_len = len(self._items)
            self._items[index] = value
            after_len = len(self._items)
            start = index.start if index.start is not None else 0
            if start < 0:
                start = max(0, before_len + start)
            start = min(start, after_len)
            try:
                added = len(value)
            except TypeError:
                added = 1
            for offset in range(added):
                self._emit("update", index=start + offset, key=None, value=None)
            if after_len != before_len:
                self._emit("reset", index=start, key=None, value=None)
            return
        if not isinstance(index, int):
            raise TypeError(f"ObservableList indices must be int or slice, not {type(index).__name__}")
        # Normalise negative indices so the rest of the method can
        # reason in ``0..len`` space — matches the standard ``list``
        # semantics where ``lst[-1] = x`` overwrites the last item
        # rather than inserting before it.
        size = len(self._items)
        resolved = index
        if resolved < 0:
            resolved = size + resolved
            if resolved < 0:
                raise IndexError("list assignment index out of range")
        if 0 <= resolved < size:
            self._items[resolved] = value
            self._emit("update", index=resolved, key=None, value=value)
            return
        # Out-of-range positive index → append, mirroring the standard
        # ``list`` behaviour for non-existent slots.
        self._items.append(value)
        self._emit("add", index=size, key=None, value=value)

    def __delitem__(self, index) -> None:
        before_len = len(self._items)
        self._items.__delitem__(index)
        after_len = len(self._items)
        removed = before_len - after_len
        if isinstance(index, int):
            resolved = index if index >= 0 else max(0, before_len + index)
            self._emit("remove", index=resolved, key=None, value=None)
            return
        # Slice deletion: emit one ``remove`` event per element so the
        # view can drop the right rows.
        start = index.start if index.start is not None else 0
        if start < 0:
            start = max(0, before_len + start)
        for offset in range(removed):
            self._emit("remove", index=start + offset, key=None, value=None)

    # ── helpers ──────────────────────────────────────────────────────

    def _emit(self, op: str, *, index: int, key: Any, value: Any) -> None:
        self._signals.changed.emit({"op": op, "index": index, "key": key, "value": value})


class ObservableDict:
    """Dict-like collection that emits :pyattr:`changed` on mutation."""

    def __init__(self, mapping: Mapping[Any, Any] | None = None) -> None:
        self._items: dict[Any, Any] = dict(mapping or {})
        self._signals = _SignalEmitter()

    # ── signal access ────────────────────────────────────────────────

    @property
    def changed(self):
        return self._signals.changed

    # ── read-only dict protocol ──────────────────────────────────────

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._items)

    def __contains__(self, key: Any) -> bool:
        return key in self._items

    def __getitem__(self, key: Any) -> Any:
        return self._items[key]

    def keys(self):
        return self._items.keys()

    def values(self):
        return self._items.values()

    def items(self):
        return self._items.items()

    def get(self, key: Any, default: Any = None) -> Any:
        return self._items.get(key, default)

    def copy(self) -> dict:
        return dict(self._items)

    def __repr__(self) -> str:
        return f"ObservableDict({self._items!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ObservableDict):
            return self._items == other._items
        return self._items == other

    # ── mutating methods ─────────────────────────────────────────────

    def __setitem__(self, key: Any, value: Any) -> None:
        op = "update" if key in self._items else "add"
        self._items[key] = value
        self._emit(op, key=key, value=value)

    def __delitem__(self, key: Any) -> None:
        value = self._items.get(key)
        del self._items[key]
        self._emit("remove", key=key, value=value)

    def pop(self, key, *args):
        # Mirror ``dict.pop`` semantics — accepts ``pop(key)`` or
        # ``pop(key, default)`` and raises ``KeyError`` when the key
        # is missing and no default is given.
        if len(args) > 1:
            raise TypeError(f"pop expected at most 2 arguments, got {1 + len(args)}")
        value = self._items.pop(key, *args)
        self._emit("remove", key=key, value=value)
        return value

    def popitem(self) -> tuple:
        key, value = self._items.popitem()
        self._emit("remove", key=key, value=value)
        return key, value

    def clear(self) -> None:
        if not self._items:
            return
        self._items.clear()
        self._emit("reset", key=None, value=None)

    def update(self, *args, **kwargs) -> None:
        before = dict(self._items)
        self._items.update(*args, **kwargs)
        for key, value in self._items.items():
            if key not in before:
                self._emit("add", key=key, value=value)
            elif before[key] != value:
                self._emit("update", key=key, value=value)
        for key in before.keys() - self._items.keys():
            self._emit("remove", key=key, value=None)

    def setdefault(self, key: Any, default: Any = None) -> Any:
        if key in self._items:
            return self._items[key]
        self._items[key] = default
        self._emit("add", key=key, value=default)
        return default

    # ── helpers ──────────────────────────────────────────────────────

    def _emit(self, op: str, *, key: Any, value: Any) -> None:
        self._signals.changed.emit({"op": op, "key": key, "value": value})


@overload
def as_observable_list(items: Iterable[Any]) -> ObservableList: ...
@overload
def as_observable_list(items: None = None) -> ObservableList: ...
def as_observable_list(items: Iterable[Any] | None = None) -> ObservableList:
    """Return a fresh :class:`ObservableList` populated from ``items``."""
    return ObservableList(items)


def as_observable_dict(mapping: Mapping[Any, Any] | None = None) -> ObservableDict:
    """Return a fresh :class:`ObservableDict` populated from ``mapping``."""
    return ObservableDict(mapping)


__all__ = [
    "ObservableDict",
    "ObservableList",
    "as_observable_dict",
    "as_observable_list",
]
