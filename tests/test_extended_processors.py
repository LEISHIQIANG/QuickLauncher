"""Tests for extended processors."""

from __future__ import annotations

import pytest

from core.chain.extended_processors import (
    base64_decode,
    # Encoding/Decoding
    base64_encode,
    color_brightness,
    color_complementary,
    # Color
    color_hex_to_rgb,
    color_random,
    color_rgb_to_hex,
    datetime_add,
    datetime_diff,
    datetime_format,
    # Date/Time
    datetime_now,
    datetime_parse,
    datetime_part,
    datetime_to_timestamp,
    dict_filter,
    dict_get,
    # Dict operations
    dict_keys,
    dict_merge,
    dict_set,
    dict_values,
    hash_crc32,
    # Hash
    hash_md5,
    hash_sha1,
    hash_sha256,
    hash_sha512,
    hash_uuid,
    hex_decode,
    hex_encode,
    html_decode,
    html_encode,
    math_cos,
    math_factorial,
    math_fibonacci,
    math_gcd,
    math_lcm,
    # Math extended
    math_sin,
    math_sqrt,
    set_difference,
    set_intersection,
    # Set operations
    set_union,
    set_unique,
    # String formatting
    str_format,
    str_pad_left,
    str_pad_right,
    str_repeat,
    str_truncate,
    sys_current_dir,
    sys_home_dir,
    sys_hostname,
    # System info
    sys_platform,
    sys_temp_dir,
    sys_username,
    timestamp_now,
    timestamp_to_datetime,
    url_decode,
    url_encode,
    # Validation
    validate_email,
    validate_ip,
    validate_length,
    validate_phone,
    validate_range,
    validate_regex,
    validate_url,
)


class TestDateTimeProcessors:
    """Tests for date/time processing functions."""

    def test_datetime_now(self):
        result = datetime_now()
        assert result  # Should return a string
        assert len(result) > 0

    def test_datetime_format(self):
        dt = "2024-01-15 14:30:00"
        result = datetime_format(dt, "%Y/%m/%d")
        assert result == "2024/01/15"

    def test_datetime_parse(self):
        dt = "2024-01-15 14:30:00"
        result = datetime_parse(dt)
        assert result["year"] == 2024
        assert result["month"] == 1
        assert result["day"] == 15
        assert result["hour"] == 14
        assert result["minute"] == 30

    def test_datetime_add(self):
        dt = "2024-01-15 14:30:00"
        result = datetime_add(dt, days=1)
        assert "2024-01-16" in result

    def test_datetime_diff(self):
        dt1 = "2024-01-16 14:30:00"
        dt2 = "2024-01-15 14:30:00"
        result = datetime_diff(dt1, dt2, "days")
        assert result == 1.0

    def test_datetime_part(self):
        dt = "2024-01-15 14:30:00"
        assert datetime_part(dt, "year") == 2024
        assert datetime_part(dt, "month") == 1
        assert datetime_part(dt, "day") == 15

    def test_timestamp_now(self):
        result = timestamp_now()
        assert result > 0

    def test_timestamp_conversion(self):
        dt = "2024-01-15 14:30:00"
        timestamp = datetime_to_timestamp(dt)
        result = timestamp_to_datetime(timestamp, "%Y-%m-%d %H:%M:%S")
        assert result == dt


class TestEncodingProcessors:
    """Tests for encoding/decoding functions."""

    def test_base64_encode_decode(self):
        text = "Hello World"
        encoded = base64_encode(text)
        decoded = base64_decode(encoded)
        assert decoded == text

    def test_url_encode_decode(self):
        text = "Hello World&test=1"
        encoded = url_encode(text)
        decoded = url_decode(encoded)
        assert decoded == text

    def test_html_encode_decode(self):
        text = '<script>alert("test")</script>'
        encoded = html_encode(text)
        decoded = html_decode(encoded)
        assert decoded == text
        assert "<script>" not in encoded

    def test_hex_encode_decode(self):
        text = "Hello World"
        encoded = hex_encode(text)
        decoded = hex_decode(encoded)
        assert decoded == text


class TestValidationProcessors:
    """Tests for validation functions."""

    def test_validate_email(self):
        assert validate_email("test@example.com") is True
        assert validate_email("invalid") is False
        assert validate_email("test@") is False

    def test_validate_url(self):
        assert validate_url("https://example.com") is True
        assert validate_url("http://test.com/path") is True
        assert validate_url("invalid") is False

    def test_validate_ip(self):
        assert validate_ip("192.168.1.1") is True
        assert validate_ip("::1") is True
        assert validate_ip("invalid") is False

    def test_validate_phone(self):
        assert validate_phone("13800138000", "CN") is True
        assert validate_phone("invalid", "CN") is False

    def test_validate_regex(self):
        assert validate_regex("123", r"^\d+$") is True
        assert validate_regex("abc", r"^\d+$") is False

    def test_validate_range(self):
        assert validate_range(5, 0, 10) is True
        assert validate_range(15, 0, 10) is False

    def test_validate_length(self):
        assert validate_length("hello", min_len=3, max_len=10) is True
        assert validate_length("hi", min_len=3) is False


class TestHashProcessors:
    """Tests for hash functions."""

    def test_hash_md5(self):
        result = hash_md5("hello")
        assert len(result) == 32

    def test_hash_sha1(self):
        result = hash_sha1("hello")
        assert len(result) == 40

    def test_hash_sha256(self):
        result = hash_sha256("hello")
        assert len(result) == 64

    def test_hash_sha512(self):
        result = hash_sha512("hello")
        assert len(result) == 128

    def test_hash_crc32(self):
        result = hash_crc32("hello")
        assert len(result) == 8

    def test_hash_uuid(self):
        result = hash_uuid()
        assert len(result) == 36  # UUID format
        assert result.count("-") == 4


class TestColorProcessors:
    """Tests for color functions."""

    def test_color_hex_to_rgb(self):
        assert color_hex_to_rgb("#ff0000") == (255, 0, 0)
        assert color_hex_to_rgb("#00ff00") == (0, 255, 0)
        assert color_hex_to_rgb("#0000ff") == (0, 0, 255)

    def test_color_rgb_to_hex(self):
        assert color_rgb_to_hex(255, 0, 0) == "#ff0000"
        assert color_rgb_to_hex(0, 255, 0) == "#00ff00"

    def test_color_brightness(self):
        assert color_brightness("#ffffff") > 50
        assert color_brightness("#000000") < 50

    def test_color_complementary(self):
        result = color_complementary("#ff0000")
        assert result == "#00ffff"

    def test_color_random(self):
        result = color_random()
        assert result.startswith("#")
        assert len(result) == 7


class TestSetProcessors:
    """Tests for set operations."""

    def test_set_union(self):
        result = set_union([1, 2, 3], [3, 4, 5])
        assert set(result) == {1, 2, 3, 4, 5}

    def test_set_intersection(self):
        result = set_intersection([1, 2, 3], [3, 4, 5])
        assert set(result) == {3}

    def test_set_difference(self):
        result = set_difference([1, 2, 3], [3, 4, 5])
        assert set(result) == {1, 2}

    def test_set_unique(self):
        result = set_unique([1, 2, 2, 3, 3, 3])
        assert result == [1, 2, 3]


class TestDictProcessors:
    """Tests for dictionary operations."""

    def test_dict_keys(self):
        result = dict_keys({"a": 1, "b": 2})
        assert set(result) == {"a", "b"}

    def test_dict_values(self):
        result = dict_values({"a": 1, "b": 2})
        assert set(result) == {1, 2}

    def test_dict_merge(self):
        result = dict_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_dict_get(self):
        result = dict_get({"a": 1, "b": 2}, "a")
        assert result == 1

    def test_dict_set(self):
        result = dict_set({"a": 1}, "b", 2)
        assert result == {"a": 1, "b": 2}

    def test_dict_filter(self):
        result = dict_filter({"a": 1, "b": 2, "c": 3}, ["a", "c"])
        assert result == {"a": 1, "c": 3}


class TestStringFormattingProcessors:
    """Tests for string formatting functions."""

    def test_str_format(self):
        result = str_format("Hello {name}", name="World")
        assert result == "Hello World"

    def test_str_pad_left(self):
        result = str_pad_left("5", 3, "0")
        assert result == "005"

    def test_str_pad_right(self):
        result = str_pad_right("5", 3, "0")
        assert result == "500"

    def test_str_truncate(self):
        result = str_truncate("Hello World", 8)
        assert result == "Hello..."

    def test_str_repeat(self):
        result = str_repeat("ab", 3)
        assert result == "ababab"


class TestMathExtendedProcessors:
    """Tests for extended math functions."""

    def test_math_sin(self):
        import math

        assert abs(math_sin(math.pi / 2) - 1.0) < 1e-10

    def test_math_cos(self):
        assert abs(math_cos(0) - 1.0) < 1e-10

    def test_math_sqrt(self):
        assert math_sqrt(4) == 2.0
        assert math_sqrt(9) == 3.0

    def test_math_factorial(self):
        assert math_factorial(5) == 120
        assert math_factorial(0) == 1

    def test_math_gcd(self):
        assert math_gcd(12, 8) == 4
        assert math_gcd(7, 5) == 1

    def test_math_lcm(self):
        assert math_lcm(4, 6) == 12
        assert math_lcm(3, 5) == 15

    def test_math_fibonacci(self):
        result = math_fibonacci(10)
        assert result == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]


class TestSystemInfoProcessors:
    """Tests for system info functions."""

    def test_sys_platform(self):
        result = sys_platform()
        assert result in ["win32", "linux", "darwin"]

    def test_sys_hostname(self):
        result = sys_hostname()
        assert result  # Should not be empty

    def test_sys_username(self):
        result = sys_username()
        assert result  # Should not be empty

    def test_sys_current_dir(self):
        result = sys_current_dir()
        assert result  # Should not be empty

    def test_sys_home_dir(self):
        result = sys_home_dir()
        assert result  # Should not be empty

    def test_sys_temp_dir(self):
        result = sys_temp_dir()
        assert result  # Should not be empty


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
