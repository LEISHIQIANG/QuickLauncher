"""Tests for core.preprocessing.sanitizers."""

from __future__ import annotations

from core.preprocessing.sanitizers import (
    enforce_size_limit,
    normalize_encoding,
    sanitize_control_chars,
    sanitize_input,
    sanitize_null_bytes,
)

# ---------------------------------------------------------------------------
# sanitize_null_bytes
# ---------------------------------------------------------------------------


def test_sanitize_null_bytes_empty():
    assert sanitize_null_bytes("") == ""


def test_sanitize_null_bytes_none_like():
    """Falsy non-string input should return empty string."""
    assert sanitize_null_bytes(None) == ""  # type: ignore[arg-type]


def test_sanitize_null_bytes_simple():
    assert sanitize_null_bytes("hello") == "hello"


def test_sanitize_null_bytes_with_nulls():
    assert sanitize_null_bytes("a\0b\0c") == "abc"


def test_sanitize_null_bytes_only_nulls():
    assert sanitize_null_bytes("\0\0\0") == ""


def test_sanitize_null_bytes_unicode():
    assert sanitize_null_bytes("世\0界") == "世界"


# ---------------------------------------------------------------------------
# sanitize_control_chars
# ---------------------------------------------------------------------------


def test_sanitize_control_chars_empty():
    assert sanitize_control_chars("") == ""


def test_sanitize_control_chars_none_like():
    assert sanitize_control_chars(None) == ""  # type: ignore[arg-type]


def test_sanitize_control_chars_keeps_normal():
    assert sanitize_control_chars("hello world") == "hello world"


def test_sanitize_control_chars_keeps_newline():
    assert sanitize_control_chars("a\nb\rc\td") == "a\nb\rc\td"


def test_sanitize_control_chars_removes_bell():
    assert sanitize_control_chars("a\x07b") == "ab"


def test_sanitize_control_chars_removes_backspace():
    assert sanitize_control_chars("a\x08b") == "ab"


def test_sanitize_control_chars_removes_esc():
    assert sanitize_control_chars("a\x1bb") == "ab"


def test_sanitize_control_chars_removes_null():
    assert sanitize_control_chars("a\0b") == "ab"


def test_sanitize_control_chars_keeps_high_unicode():
    text = "世界é"
    assert sanitize_control_chars(text) == text


# ---------------------------------------------------------------------------
# enforce_size_limit
# ---------------------------------------------------------------------------


def test_enforce_size_limit_empty():
    assert enforce_size_limit("") == ""


def test_enforce_size_limit_none_like():
    assert enforce_size_limit(None) == ""  # type: ignore[arg-type]


def test_enforce_size_limit_under_limit():
    assert enforce_size_limit("hello", max_bytes=100) == "hello"


def test_enforce_size_limit_exact_limit():
    text = "a" * 10
    assert enforce_size_limit(text, max_bytes=10) == text


def test_enforce_size_limit_over_limit():
    text = "a" * 20
    result = enforce_size_limit(text, max_bytes=10)
    assert len(result.encode("utf-8")) <= 10
    assert result == "a" * 10


def test_enforce_size_limit_multibyte_truncation():
    """CJK characters are 3 bytes in UTF-8; truncation must not break chars."""
    text = "世" * 10  # 30 bytes
    result = enforce_size_limit(text, max_bytes=10)
    encoded = result.encode("utf-8")
    assert len(encoded) <= 10
    # Result should still be valid UTF-8
    result.encode("utf-8")  # should not raise


def test_enforce_size_limit_default_max():
    """Default max is 1 MB; a small string should pass unchanged."""
    assert enforce_size_limit("short") == "short"


# ---------------------------------------------------------------------------
# normalize_encoding
# ---------------------------------------------------------------------------


def test_normalize_encoding_empty():
    assert normalize_encoding("") == ""


def test_normalize_encoding_none_like():
    assert normalize_encoding(None) == ""  # type: ignore[arg-type]


def test_normalize_encoding_ascii():
    assert normalize_encoding("hello") == "hello"


def test_normalize_encoding_utf8():
    assert normalize_encoding("世界") == "世界"


def test_normalize_encoding_surrogateescape():
    """Surrogate characters should be replaced, not crash."""
    bad = "abc\udc00def"
    result = normalize_encoding(bad)
    assert "abc" in result
    assert "def" in result


# ---------------------------------------------------------------------------
# sanitize_input (integration)
# ---------------------------------------------------------------------------


def test_sanitize_input_empty():
    assert sanitize_input("") == ""


def test_sanitize_input_normal():
    assert sanitize_input("hello world") == "hello world"


def test_sanitize_input_strips_nulls():
    assert sanitize_input("a\0b\0c") == "abc"


def test_sanitize_input_truncates():
    text = "x" * 200
    result = sanitize_input(text, max_bytes=50)
    assert len(result.encode("utf-8")) <= 50


def test_sanitize_input_unicode():
    text = "世界\0你好"
    result = sanitize_input(text)
    assert "\0" not in result
    assert "世界你好" == result


def test_sanitize_input_combined():
    """Null bytes + over-limit should both be handled."""
    text = "a\0" * 100
    result = sanitize_input(text, max_bytes=10)
    assert "\0" not in result
    assert len(result.encode("utf-8")) <= 10
