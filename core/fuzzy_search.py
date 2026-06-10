"""Fuzzy search helpers for launcher shortcuts."""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache

from .pinyin_search import pinyin_variants
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


_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TOKEN_SPLIT_RE = re.compile(r"[\s,;，；、|]+")
_ORDERED_INDEX_CACHE_MAX = 64
_ordered_index_cache: OrderedDict[tuple[str, tuple[tuple[int, int], ...]], tuple[int, ...]] = OrderedDict()


@lru_cache(maxsize=2048)
def _normalize_text(value) -> str:
    """Normalize user-facing text without losing CJK characters."""
    text = unicodedata.normalize("NFKC", _text(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    return " ".join(text.split())


@lru_cache(maxsize=2048)
def _compact_text(value) -> str:
    normalized = _normalize_text(value)
    return "".join(ch for ch in normalized if ch.isalnum())


def _split_query(query: str) -> list[str]:
    normalized = _normalize_text(query)
    return [part for part in _TOKEN_SPLIT_RE.split(normalized) if part]


def _word_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", _text(value))
    text = _CAMEL_BOUNDARY_RE.sub(" ", text)
    chars = []
    for ch in text:
        chars.append(ch if ch.isalnum() else " ")
    return _normalize_text("".join(chars))


@lru_cache(maxsize=1024)
def _word_tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in _word_text(value).split() if token)


def _basename(value: str) -> str:
    parts = re.split(r"[\\/]+", _text(value))
    return parts[-1] if parts else ""


def _stem(value: str) -> str:
    base = _basename(value)
    if "." not in base:
        return base
    return ".".join(base.split(".")[:-1]) or base


@lru_cache(maxsize=1024)
def _field_variants(value: str) -> tuple[str, ...]:
    """Return useful search surfaces for a field, ordered from broad to focused."""
    raw = _text(value)
    if not raw:
        return ()

    variants = [raw]
    base = _basename(raw)
    stem = _stem(raw)
    if base and base != raw:
        variants.append(base)
    if stem and stem not in variants:
        variants.append(stem)

    # A compact variant makes "vs code", "vs-code" and "vscode" feel the same.
    compact = _compact_text(raw)
    if compact:
        variants.append(compact)

    # Word text preserves boundaries from punctuation and CamelCase for acronyms.
    words = _word_text(raw)
    if words and words not in variants:
        variants.append(words)

    for pinyin in pinyin_variants(raw):
        if pinyin and pinyin not in variants:
            variants.append(pinyin)

    result = []
    seen = set()
    for variant in variants:
        normalized = _normalize_text(variant)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(variant)
    return tuple(result)


def _acronym(value: str) -> str:
    tokens = _word_tokens(value)
    return "".join(token[0] for token in tokens if token)


def _iter_fields(shortcut) -> Iterable[tuple[str, str, float]]:
    tags = " ".join(_text(tag) for tag in getattr(shortcut, "tags", []) if _text(tag))
    yield "name", _text(getattr(shortcut, "name", "")), 120.0
    yield "alias", _text(getattr(shortcut, "alias", "")), 110.0
    yield "tags", tags, 95.0
    yield "target_path", _text(getattr(shortcut, "target_path", "")), 55.0
    yield "url", _text(getattr(shortcut, "url", "")), 50.0
    yield "command", _text(getattr(shortcut, "command", "")), 45.0
    yield "hotkey", _text(getattr(shortcut, "hotkey", "")), 35.0


def _word_boundary_bonus(haystack: str, start: int) -> float:
    if start < 0:
        return 0.0
    if start == 0:
        return 18.0
    previous = haystack[start - 1]
    current = haystack[start]
    if previous in " _-./\\()[]{}":
        return 14.0
    if previous.islower() and current.isupper():
        return 10.0
    return 0.0


def _subsequence_score(needle: str, haystack: str) -> float | None:
    if not needle:
        return 0.0
    if not haystack:
        return None

    needle_l = _normalize_text(needle)
    haystack_l = _normalize_text(haystack)

    exact_pos = haystack_l.find(needle_l)
    if exact_pos >= 0:
        score = 70.0 + len(needle_l) * 6.0
        score += max(0.0, 20.0 - exact_pos)
        score += _word_boundary_bonus(haystack_l, exact_pos)
        if exact_pos == 0 and len(needle_l) == len(haystack_l):
            score += 45.0
        return score

    positions = []
    start = 0
    for char in needle_l:
        pos = haystack_l.find(char, start)
        if pos < 0:
            return None
        positions.append(pos)
        start = pos + 1

    span = positions[-1] - positions[0] + 1
    gaps = max(0, span - len(needle_l))
    contiguous_pairs = sum(1 for left, right in zip(positions, positions[1:]) if right == left + 1)
    score = 38.0 + len(needle_l) * 5.0
    score += contiguous_pairs * 8.0
    score += max(0.0, 16.0 - positions[0])
    score += _word_boundary_bonus(haystack_l, positions[0])
    score -= gaps * 2.0
    return max(1.0, score)


def _near_word_score(needle: str, tokens: list[str]) -> float | None:
    if len(needle) < 3:
        return None

    best = 0.0
    for token in tokens:
        if len(token) < 3:
            continue
        ratio = SequenceMatcher(None, needle, token).ratio()
        # Keep typo tolerance conservative so very short or unrelated input does
        # not flood the popup with surprising results.
        if ratio >= 0.78:
            best = max(best, 42.0 + ratio * 38.0)
    return best or None


def _single_term_score(term: str, value: str) -> float | None:
    if not term:
        return 0.0

    best: float | None = None
    term_norm = _normalize_text(term)
    term_compact = _compact_text(term)

    for variant in _field_variants(value):
        normalized = _normalize_text(variant)
        compact = _compact_text(variant)
        tokens = _word_tokens(variant)

        candidates: list[float] = []

        if term_norm == normalized:
            candidates.append(138.0 + len(term_norm) * 7.0)
        if term_norm in tokens:
            candidates.append(122.0 + len(term_norm) * 6.0)
        for token in tokens:
            if token.startswith(term_norm) and term_norm != token:
                candidates.append(104.0 + len(term_norm) * 5.0 + max(0.0, 12.0 - len(token)))

        acronym = _acronym(variant)
        if acronym:
            if acronym == term_compact:
                shortest_token = min((len(token) for token in tokens), default=12)
                candidates.append(118.0 + len(term_compact) * 6.0 + max(0.0, 12.0 - shortest_token))
            elif acronym.startswith(term_compact):
                candidates.append(102.0 + len(term_compact) * 5.0)
            elif term_compact in acronym:
                candidates.append(84.0 + len(term_compact) * 4.0)

        compact_pos = compact.find(term_compact) if term_compact else -1
        if compact_pos >= 0:
            candidates.append(
                76.0 + len(term_compact) * 5.0 + max(0.0, 12.0 - compact_pos) + max(0.0, 24.0 - len(compact)) * 0.5
            )

        subsequence = _subsequence_score(term_norm, normalized)
        if subsequence is not None:
            candidates.append(subsequence)
        if compact != normalized:
            compact_subsequence = _subsequence_score(term_compact, compact)
            if compact_subsequence is not None:
                candidates.append(compact_subsequence - 4.0)

        near_word = _near_word_score(term_norm, tokens)
        if near_word is not None:
            candidates.append(near_word)

        if candidates:
            score = max(candidates)
            best = score if best is None else max(best, score)

    return best


def _shortcut_score(shortcut, query: str) -> tuple[float | None, list[str]]:
    terms = _split_query(query)
    if not terms:
        return None, []

    total = 0.0
    matched_fields: list[str] = []
    seen_fields = set()

    for term in terms:
        best_term_score = None
        best_field = ""
        best_weight = 0.0
        for field_name, field_value, weight in _iter_fields(shortcut):
            field_score = _single_term_score(term, field_value)
            if field_score is None:
                continue
            weighted = field_score + weight
            if best_term_score is None or weighted > best_term_score:
                best_term_score = weighted
                best_field = field_name
                best_weight = weight

        if best_term_score is None:
            return None, []

        total += best_term_score
        if best_field and best_field not in seen_fields:
            seen_fields.add(best_field)
            matched_fields.append(best_field)
        # Prefer queries that are answered by stronger, human-entered metadata.
        total += best_weight / 12.0

    score = total / len(terms)

    query_norm = _normalize_text(query)
    query_compact = _compact_text(query)
    for field_name, field_value, weight in _iter_fields(shortcut):
        phrase_score = _single_term_score(query_norm, field_value)
        compact_score = _single_term_score(query_compact, field_value) if query_compact != query_norm else None
        best_phrase = (
            max(score for score in (phrase_score, compact_score) if score is not None)
            if any(score is not None for score in (phrase_score, compact_score))
            else None
        )
        if best_phrase is None:
            continue
        weighted_phrase = best_phrase + weight + 18.0
        if weighted_phrase > score:
            score = weighted_phrase
            if field_name not in seen_fields:
                matched_fields.append(field_name)
                seen_fields.add(field_name)

    if len(terms) > 1:
        score += min(18.0, (len(terms) - 1) * 6.0)

    # Query history bonus — boost shortcuts the user picked before for similar queries
    shortcut_id = _text(getattr(shortcut, "id", ""))
    if shortcut_id:
        history_bonus = search_history_bonus(query, shortcut_id)
        if history_bonus:
            score += history_bonus

    return score, matched_fields


def _usage_bonus(shortcut) -> float:
    try:
        use_count = max(0, int(getattr(shortcut, "use_count", 0) or 0))
    except (TypeError, ValueError):
        use_count = 0
    try:
        last_used_at = max(0.0, float(getattr(shortcut, "last_used_at", 0.0) or 0.0))
    except (TypeError, ValueError):
        last_used_at = 0.0
    # Time-decay bonus: more recently used shortcuts get a higher score.
    # Half-life ≈ 3 days (259200 seconds).
    time_bonus = 0.0
    if last_used_at > 0:
        elapsed = max(0.0, time.time() - last_used_at)
        time_bonus = 20.0 * (0.5 ** (elapsed / 259200.0))
    return min(35.0, use_count * 1.8) + time_bonus


def _order_value(shortcut, sort_mode: str, original_index: int) -> int:
    if sort_mode == "smart":
        smart_order = getattr(shortcut, "smart_order", None)
        if smart_order is not None:
            try:
                return int(smart_order)
            except (TypeError, ValueError):
                logger.debug("解析smart_order值失败", exc_info=True)
    try:
        return int(getattr(shortcut, "order", original_index))
    except (TypeError, ValueError):
        return int(original_index)


def _ordered_shortcuts(items, sort_mode: str):
    signature = []
    decorated = []
    for idx, shortcut in enumerate(items):
        order = _order_value(shortcut, sort_mode, idx)
        signature.append((id(shortcut), order))
        decorated.append((order, idx, shortcut))

    if not decorated:
        return ()

    cache_key = (sort_mode, tuple(signature))
    cached_indexes = _ordered_index_cache.get(cache_key)
    if cached_indexes is not None:
        _ordered_index_cache.move_to_end(cache_key)
        return tuple(items[idx] for idx in cached_indexes)

    decorated.sort()
    indexes = tuple(idx for _order, idx, _shortcut in decorated)
    _ordered_index_cache[cache_key] = indexes
    _ordered_index_cache.move_to_end(cache_key)
    while len(_ordered_index_cache) > _ORDERED_INDEX_CACHE_MAX:
        _ordered_index_cache.popitem(last=False)
    return tuple(shortcut for _order, _idx, shortcut in decorated)


def search_shortcuts(
    pages, query: str, *, sort_mode: str = "custom", limit: int | None = None
) -> list[FuzzyMatchResult]:
    query = _text(query)
    if not query:
        return []

    results = []
    original_index = 0
    for folder in pages or []:
        folder_id = _text(getattr(folder, "id", ""))
        folder_name = _text(getattr(folder, "name", ""))
        raw_items = getattr(folder, "items", ()) or ()
        for shortcut in _ordered_shortcuts(raw_items, sort_mode):
            if hasattr(shortcut, "is_enabled") and not shortcut.is_enabled():
                original_index += 1
                continue
            if not getattr(shortcut, "enabled", True):
                original_index += 1
                continue

            best_score, matched_fields = _shortcut_score(shortcut, query)

            if best_score is not None:
                best_score += _usage_bonus(shortcut) if sort_mode == "smart" else 0.0
                results.append(
                    FuzzyMatchResult(
                        shortcut=shortcut,
                        folder_id=folder_id,
                        folder_name=folder_name,
                        score=best_score,
                        original_index=original_index,
                        matched_fields=matched_fields,
                    )
                )
            original_index += 1

    results.sort(key=lambda item: (-item.score, item.original_index))
    if limit is not None:
        return results[: max(0, int(limit))]
    return results
