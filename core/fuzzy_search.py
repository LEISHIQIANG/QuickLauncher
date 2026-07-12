"""Fuzzy search helpers for launcher shortcuts.

All search logic (scoring, normalization, pinyin) is delegated to
the native ``QLsearch.dll`` engine.  This module only bridges
Python data into the DLL and maps results back.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import cast

from .search_history import search_history_bonus

logger = logging.getLogger(__name__)


@dataclass
class FuzzyMatchResult:
    shortcut: object
    folder_id: str
    folder_name: str
    score: float
    original_index: int
    matched_fields: list[str] = field(default_factory=list)


def _text(value) -> str:
    return str(value or "").strip()


def _native_search(pages, query, sort_mode, limit):
    from .native_services import _QLsearchEngine

    engine = _QLsearchEngine.get()
    engine.sync_from_folders(pages, sort_mode)

    bonuses: dict[int, float] = {}
    for sid, sc in engine._id_to_shortcut.items():
        str_id = _text(getattr(sc, "id", ""))
        if str_id:
            bonus = search_history_bonus(query, str_id)
            if bonus:
                bonuses[sid] = bonus
    engine.set_history_bonuses(bonuses)

    mode = {"custom": 0, "smart": 1, "name": 2}.get(sort_mode, 0)
    cap = limit if (limit is not None and limit > 0) else 256
    return cast(list[FuzzyMatchResult], engine.search_with_mapping(query, mode, cap))


def search_shortcuts(
    pages, query: str, *, sort_mode: str = "custom", limit: int | None = None
) -> list[FuzzyMatchResult]:
    query = _text(query)
    if not query:
        return []
    if limit is not None and limit <= 0:
        return []
    return cast(list[FuzzyMatchResult], _native_search(pages, query, sort_mode, limit))
