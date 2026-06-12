"""Tests for enhanced processors."""

from __future__ import annotations

import pytest

from core.chain.enhanced_processors import (
    # File processors
    file_copy,
    file_list_dir,
    file_move,
    file_size,
    # Logic processors
    is_empty,
    is_json,
    is_numeric,
    json_flatten,
    json_keys,
    json_length,
    # JSON processors
    json_merge,
    json_values,
    list_avg,
    # List processors
    list_count,
    list_max,
    list_min,
    list_remove,
    list_sum,
    # Math processors
    math_abs,
    math_ceil,
    math_clamp,
    math_floor,
    math_round,
    text_contains,
    text_count,
    text_endswith,
    text_regex_replace,
    text_reverse,
    text_startswith,
    # Text processors
    text_trim,
)


class TestTextProcessors:
    """Tests for text processing functions."""

    def test_text_trim(self):
        assert text_trim("  hello  ") == "hello"
        assert text_trim("xxxhelloxxx", "x") == "hello"
        assert text_trim("") == ""

    def test_text_contains(self):
        assert text_contains("Hello World", "World") is True
        assert text_contains("Hello World", "world") is False
        assert text_contains("Hello World", "world", case_sensitive=False) is True

    def test_text_startswith(self):
        assert text_startswith("Hello World", "Hello") is True
        assert text_startswith("Hello World", "hello") is False
        assert text_startswith("Hello World", "hello", case_sensitive=False) is True

    def test_text_endswith(self):
        assert text_endswith("Hello World", "World") is True
        assert text_endswith("Hello World", "world") is False
        assert text_endswith("Hello World", "world", case_sensitive=False) is True

    def test_text_regex_replace(self):
        assert text_regex_replace("Hello 123 World", r"\d+", "NUM") == "Hello NUM World"
        assert text_regex_replace("aaa", "a", "b", count=2) == "bba"

    def test_text_count(self):
        assert text_count("hello hello", "hello") == 2
        assert text_count("Hello hello", "hello") == 1
        assert text_count("Hello hello", "hello", case_sensitive=False) == 2

    def test_text_reverse(self):
        assert text_reverse("hello") == "olleh"
        assert text_reverse("") == ""


class TestLogicProcessors:
    """Tests for logic processing functions."""

    def test_is_empty(self):
        assert is_empty("") is True
        assert is_empty("  ") is True
        assert is_empty(None) is True
        assert is_empty([]) is True
        assert is_empty({}) is True
        assert is_empty("hello") is False
        assert is_empty([1]) is False

    def test_is_numeric(self):
        assert is_numeric("123") is True
        assert is_numeric("3.14") is True
        assert is_numeric("-1") is True
        assert is_numeric("abc") is False
        assert is_numeric("") is False

    def test_is_json(self):
        assert is_json('{"key": "value"}') is True
        assert is_json("[1, 2, 3]") is True
        assert is_json("hello") is False
        assert is_json("") is False


class TestMathProcessors:
    """Tests for math processing functions."""

    def test_math_abs(self):
        assert math_abs(5) == 5
        assert math_abs(-5) == 5
        assert math_abs(0) == 0

    def test_math_ceil(self):
        assert math_ceil(3.2) == 4
        assert math_ceil(3.8) == 4
        assert math_ceil(-3.2) == -3

    def test_math_floor(self):
        assert math_floor(3.2) == 3
        assert math_floor(3.8) == 3
        assert math_floor(-3.2) == -4

    def test_math_round(self):
        assert math_round(3.14159, 2) == 3.14
        assert math_round(3.5) == 4
        assert math_round(2.5) == 2

    def test_math_clamp(self):
        assert math_clamp(5, 0, 10) == 5
        assert math_clamp(-5, 0, 10) == 0
        assert math_clamp(15, 0, 10) == 10


class TestListProcessors:
    """Tests for list processing functions."""

    def test_list_count(self):
        assert list_count([1, 2, 2, 3], 2) == 2
        assert list_count([1, 2, 3], 4) == 0

    def test_list_sum(self):
        assert list_sum([1, 2, 3]) == 6.0
        assert list_sum(["1", "2", "3"]) == 6.0
        assert list_sum([]) == 0.0

    def test_list_min(self):
        assert list_min([3, 1, 2]) == 1
        assert list_min(["b", "a", "c"]) == "a"

    def test_list_max(self):
        assert list_max([3, 1, 2]) == 3
        assert list_max(["b", "a", "c"]) == "c"

    def test_list_avg(self):
        assert list_avg([1, 2, 3]) == 2.0
        assert list_avg([10, 20]) == 15.0

    def test_list_remove(self):
        assert list_remove([1, 2, 3, 2], 2) == [1, 3]
        assert list_remove([1, 2, 3], 4) == [1, 2, 3]


class TestFileProcessors:
    """Tests for file processing functions."""

    def test_file_copy(self, tmp_path):
        src = tmp_path / "source.txt"
        src.write_text("hello")
        dst = tmp_path / "dest.txt"

        result = file_copy(str(src), str(dst))
        assert result == str(dst)
        assert dst.read_text() == "hello"

    def test_file_move(self, tmp_path):
        src = tmp_path / "source.txt"
        src.write_text("hello")
        dst = tmp_path / "dest.txt"

        result = file_move(str(src), str(dst))
        assert result == str(dst)
        assert dst.read_text() == "hello"
        assert not src.exists()

    def test_file_size(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")

        assert file_size(str(test_file)) == 5

    def test_file_list_dir(self, tmp_path):
        (tmp_path / "file1.txt").write_text("1")
        (tmp_path / "file2.txt").write_text("2")
        (tmp_path / "file3.py").write_text("3")

        result = file_list_dir(str(tmp_path), "*.txt")
        assert len(result) == 2


class TestJsonProcessors:
    """Tests for JSON processing functions."""

    def test_json_merge(self):
        result = json_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_json_flatten(self):
        data = {"a": {"b": 1, "c": [2, 3]}}
        result = json_flatten(data)
        assert result["a.b"] == 1
        assert result["a.c.0"] == 2
        assert result["a.c.1"] == 3

    def test_json_keys(self):
        assert json_keys({"a": 1, "b": 2}) == ["a", "b"]
        assert json_keys({}) == []

    def test_json_values(self):
        assert json_values({"a": 1, "b": 2}) == [1, 2]
        assert json_values({}) == []

    def test_json_length(self):
        assert json_length({"a": 1, "b": 2}) == 2
        assert json_length([1, 2, 3]) == 3
        assert json_length("hello") == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
