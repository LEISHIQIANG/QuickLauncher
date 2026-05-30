"""Tests for core/search_history.py — SearchHistory class and module helpers."""

from __future__ import annotations

import pytest

from core.search_history import (
    SearchHistory,
    get_search_history,
    record_search_selection,
    search_history_bonus,
    set_search_history_data_dir,
)

# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------


def test_normalize_strips_and_lowercases():
    assert SearchHistory._normalize("  Hello World  ") == "hello world"


def test_normalize_truncates_to_128():
    long_query = "a" * 200
    assert len(SearchHistory._normalize(long_query)) == 128


def test_normalize_empty_string():
    assert SearchHistory._normalize("") == ""


# ---------------------------------------------------------------------------
# record_selection / score_bonus basics
# ---------------------------------------------------------------------------


def test_record_and_score(tmp_path):
    sh = SearchHistory(tmp_path)
    sh.record_selection("test query", "s1")
    # After one selection, raw count is 1.0, bonus = min(30, 1.0 * 10) = 10
    assert sh.score_bonus("test query", "s1") == pytest.approx(10.0)


def test_score_unknown_pair_returns_zero(tmp_path):
    sh = SearchHistory(tmp_path)
    assert sh.score_bonus("nonexistent", "s99") == 0.0


def test_multiple_selections_accumulate(tmp_path):
    sh = SearchHistory(tmp_path)
    for _ in range(5):
        sh.record_selection("q", "s1")
    # raw count = 5.0, bonus = min(30, 5.0 * 10) = 30
    assert sh.score_bonus("q", "s1") == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# score cap at 30
# ---------------------------------------------------------------------------


def test_score_cap_at_30(tmp_path):
    sh = SearchHistory(tmp_path)
    for _ in range(100):
        sh.record_selection("q", "s1")
    assert sh.score_bonus("q", "s1") == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# empty inputs
# ---------------------------------------------------------------------------


def test_record_empty_query_is_noop(tmp_path):
    sh = SearchHistory(tmp_path)
    sh.record_selection("", "s1")
    assert sh.score_bonus("", "s1") == 0.0


def test_record_empty_shortcut_id_is_noop(tmp_path):
    sh = SearchHistory(tmp_path)
    sh.record_selection("q", "")
    assert sh.score_bonus("q", "") == 0.0


def test_score_empty_query_returns_zero(tmp_path):
    sh = SearchHistory(tmp_path)
    sh.record_selection("q", "s1")
    assert sh.score_bonus("", "s1") == 0.0


# ---------------------------------------------------------------------------
# normalization in scoring
# ---------------------------------------------------------------------------


def test_score_uses_normalized_query(tmp_path):
    sh = SearchHistory(tmp_path)
    sh.record_selection("  HELLO  ", "s1")
    assert sh.score_bonus("hello", "s1") == pytest.approx(10.0)
    assert sh.score_bonus("HELLO", "s1") == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------


def test_prune_noop_when_under_limit(tmp_path):
    sh = SearchHistory(tmp_path)
    sh.record_selection("q1", "s1")
    remaining = sh.prune(max_entries=100)
    assert remaining == 1


def test_prune_keeps_highest_scoring(tmp_path):
    sh = SearchHistory(tmp_path)
    # Create 5 distinct query keys with varying scores
    for i in range(5):
        for _ in range(i + 1):
            sh.record_selection(f"q{i}", f"s{i}")
    # Prune to 3 entries — should keep the highest-scored queries
    remaining = sh.prune(max_entries=3)
    assert remaining == 3
    # The top 3 by score should be q4, q3, q2
    assert sh.score_bonus("q4", "s4") > 0
    assert sh.score_bonus("q3", "s3") > 0
    assert sh.score_bonus("q2", "s2") > 0
    assert sh.score_bonus("q0", "s0") == 0.0


# ---------------------------------------------------------------------------
# persistence round-trip
# ---------------------------------------------------------------------------


def test_persistence_round_trip(tmp_path):
    sh1 = SearchHistory(tmp_path)
    sh1.record_selection("persist_q", "s1")
    # Force save directly (bypass debounce timer)
    sh1._save()

    # Load fresh instance from same directory
    sh2 = SearchHistory(tmp_path)
    assert sh2.score_bonus("persist_q", "s1") == pytest.approx(10.0)


def test_load_missing_file_is_ok(tmp_path):
    sh = SearchHistory(tmp_path / "nonexistent_dir")
    assert sh.score_bonus("any", "any") == 0.0


def test_save_creates_parent_dirs(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    sh = SearchHistory(deep)
    sh.record_selection("q", "s1")
    sh._save()
    assert (deep / "search_history.json").is_file()


# ---------------------------------------------------------------------------
# module-level helpers
# ---------------------------------------------------------------------------


def test_set_search_history_data_dir(tmp_path):
    set_search_history_data_dir(tmp_path)
    try:
        record_search_selection("mod_q", "s_mod")
        # Force underlying save so the bonus can read it
        hist = get_search_history()
        hist._save()
        assert search_history_bonus("mod_q", "s_mod") == pytest.approx(10.0)
    finally:
        # Reset global singleton so other tests are unaffected
        import core.search_history as mod

        mod._search_history = None


def test_get_search_history_returns_singleton():
    h1 = get_search_history()
    h2 = get_search_history()
    assert h1 is h2
    # Reset for isolation
    import core.search_history as mod

    mod._search_history = None


def test_query_longer_than_64_characters(tmp_path):
    sh = SearchHistory(tmp_path)
    long_q = "a" * 80
    sh.record_selection(long_q, "s1")
    # Should be truncated to 64 chars
    truncated_key = long_q[:64]
    assert sh.score_bonus(long_q, "s1") == pytest.approx(10.0)
    assert sh.score_bonus(truncated_key, "s1") == pytest.approx(10.0)


def test_save_with_no_path():
    sh = SearchHistory("")
    # Path is empty, save should return early
    assert sh._save() is None


def test_load_corrupt_json_handles_exception(tmp_path):
    sh = SearchHistory(tmp_path)
    file_path = tmp_path / "search_history.json"
    file_path.write_text("invalid json {", encoding="utf-8")

    # loading corrupt json should handle exception gracefully and leave data empty
    sh._load()
    assert sh._data == {}


def test_save_handles_io_exception(tmp_path, monkeypatch):
    sh = SearchHistory(tmp_path)
    # Trigger exception in save by setting path to a directory path
    sh._path = str(tmp_path)  # saving to a directory path raises PermissionError/IsADirectoryError
    sh._save()
    # Should handle exception and not crash


def test_flush_save_called_directly(tmp_path):
    sh = SearchHistory(tmp_path)
    sh.record_selection("q", "s1")
    # dirty is True
    assert sh._dirty is True
    # Directly invoke _flush_save
    sh._flush_save()
    assert sh._dirty is False
