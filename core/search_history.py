"""Lightweight search query learning — records and boosts past selections."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_HISTORY_ENTRIES = 500
_MAX_QUERY_KEY_LENGTH = 64
_PERSIST_FILE = "search_history.json"
_SAVE_DELAY = 2.0


class SearchHistory:
    """Records (query → shortcut_id → score) and provides a score bonus.

    Thread-safe. Persisted to JSON with debounced writes.
    """

    def __init__(self, data_dir: str | Path = ""):
        self._data: dict[str, dict[str, float]] = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._save_timer: threading.Timer | None = None
        self._path = os.path.join(str(data_dir), _PERSIST_FILE) if data_dir else ""
        self._load()

    # ---- public API ----

    def record_selection(self, query: str, shortcut_id: str) -> None:
        """Record that the user selected a given shortcut for a given query."""
        if not query or not shortcut_id:
            return
        key = self._normalize(query)
        if len(key) > _MAX_QUERY_KEY_LENGTH:
            key = key[:_MAX_QUERY_KEY_LENGTH]
        with self._lock:
            inner = self._data.get(key)
            if inner is None:
                self._data[key] = {shortcut_id: 1.0}
            else:
                inner[shortcut_id] = inner.get(shortcut_id, 0.0) + 1.0
            self._dirty = True
        self._schedule_save()

    def score_bonus(self, query: str, shortcut_id: str) -> float:
        """Return a bonus score for a (query, shortcut_id) pair."""
        if not query or not shortcut_id:
            return 0.0
        key = self._normalize(query)
        if len(key) > _MAX_QUERY_KEY_LENGTH:
            key = key[:_MAX_QUERY_KEY_LENGTH]
        with self._lock:
            inner = self._data.get(key)
            if inner is None:
                return 0.0
            raw = inner.get(shortcut_id, 0.0)
        return min(30.0, raw * 10.0)

    def prune(self, max_entries: int = _MAX_HISTORY_ENTRIES) -> int:
        """Trim oldest entries when history grows too large."""
        with self._lock:
            if len(self._data) <= max_entries:
                return 0
            # Sort by total score (ascending) and keep top max_entries
            scored = [(sum(v.values()) if isinstance(v, dict) else 0.0, k, v) for k, v in self._data.items()]
            scored.sort(key=lambda x: x[0], reverse=True)
            self._data = {k: v for _, k, v in scored[:max_entries]}
            self._dirty = True
        self._save()
        return len(self._data)

    # ---- persistence ----

    def _load(self) -> None:
        if not self._path or not os.path.isfile(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self._data = raw
        except Exception as e:
            logger.debug("failed to load search history: %s", e)

    def _save(self) -> None:
        if not self._path:
            return
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False)
            self._dirty = False
        except Exception as e:
            logger.debug("failed to save search history: %s", e)

    def _schedule_save(self) -> None:
        if self._save_timer is not None:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(_SAVE_DELAY, self._flush_save)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _flush_save(self) -> None:
        with self._lock:
            if self._dirty:
                self._save()

    @staticmethod
    def _normalize(query: str) -> str:
        return query.strip().lower()[:128]


# Module-level singleton (lazy-initialised)
_search_history: SearchHistory | None = None
_history_lock = threading.Lock()


def get_search_history() -> SearchHistory:
    global _search_history
    if _search_history is None:
        with _history_lock:
            if _search_history is None:
                _search_history = SearchHistory()
    return _search_history


def set_search_history_data_dir(data_dir: str | Path) -> None:
    global _search_history
    with _history_lock:
        _search_history = SearchHistory(data_dir)


def record_search_selection(query: str, shortcut_id: str) -> None:
    get_search_history().record_selection(query, shortcut_id)


def search_history_bonus(query: str, shortcut_id: str) -> float:
    return get_search_history().score_bonus(query, shortcut_id)
