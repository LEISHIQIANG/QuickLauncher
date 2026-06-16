"""Tests for the refactored processor dispatch system in core/chain/registry.py.

Covers each ``execute_extra_*`` function in the split processor modules and
verifies that ``_execute_extra_processor()`` correctly delegates to them.
Pure unit tests -- no Qt/GUI required.
"""

from pathlib import Path

import pytest

from core.chain.processors_data import execute_extra_data_processor
from core.chain.processors_datetime import execute_extra_datetime_processor
from core.chain.processors_encoding import execute_extra_encoding_processor, execute_extra_system_processor
from core.chain.processors_math import execute_extra_list_processor, execute_extra_math_processor
from core.chain.processors_text import execute_extra_text_processor
from core.chain.processors_validation import execute_extra_validation_processor
from core.chain.registry import _execute_extra_processor, execute_chain_processor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _output(result):
    """Extract the primary 'output' value from a CommandResult."""
    return result.payload["outputs"]["output"]


def _output_bool(result):
    """Extract the primary 'output' as a boolean string."""
    return result.payload["outputs"]["output"]


# ---------------------------------------------------------------------------
# processors_text  --  execute_extra_text_processor
# ---------------------------------------------------------------------------


class TestTextProcessors:
    """Tests for execute_extra_text_processor."""

    def test_text_trim_strips_whitespace(self):
        result = execute_extra_text_processor("text_trim", {"text": "  hello  "})
        assert result.success is True
        assert _output(result) == "hello"

    def test_text_trim_with_custom_chars(self):
        result = execute_extra_text_processor("text_trim", {"text": "##hello##", "chars": "#"})
        assert result.success is True
        assert _output(result) == "hello"

    def test_text_contains_case_sensitive(self):
        result = execute_extra_text_processor(
            "text_contains", {"text": "Hello World", "substring": "hello", "case_sensitive": "true"}
        )
        assert result.success is True
        assert _output_bool(result) == "false"

    def test_text_contains_case_insensitive(self):
        result = execute_extra_text_processor(
            "text_contains", {"text": "Hello World", "substring": "hello", "case_sensitive": "false"}
        )
        assert result.success is True
        assert _output_bool(result) == "true"

    def test_text_startswith(self):
        result = execute_extra_text_processor("text_startswith", {"text": "QuickLauncher", "prefix": "Quick"})
        assert result.success is True
        assert _output_bool(result) == "true"

    def test_text_endswith(self):
        result = execute_extra_text_processor("text_endswith", {"text": "QuickLauncher", "suffix": "cher"})
        assert result.success is True
        assert _output_bool(result) == "true"

    def test_text_reverse(self):
        result = execute_extra_text_processor("text_reverse", {"text": "abc"})
        assert result.success is True
        assert _output(result) == "cba"

    def test_text_count(self):
        result = execute_extra_text_processor("text_count", {"text": "aabbaabb", "substring": "aa"})
        assert result.success is True
        assert _output(result) == "2"

    def test_text_regex_replace(self):
        result = execute_extra_text_processor(
            "text_regex_replace", {"text": "foo123bar456", "pattern": r"\d+", "replacement": "X"}
        )
        assert result.success is True
        assert _output(result) == "fooXbarX"

    def test_unknown_processor_returns_none(self):
        result = execute_extra_text_processor("nonexistent_processor", {"text": "hello"})
        assert result is None

    def test_text_trim_empty_string(self):
        result = execute_extra_text_processor("text_trim", {"text": ""})
        assert result.success is True
        assert _output(result) == ""

    def test_switch_case(self):
        import json

        cases = json.dumps({"a": "alpha", "b": "beta"})
        result = execute_extra_text_processor("switch_case", {"value": "b", "cases_json": cases, "default": "unknown"})
        assert result.success is True
        assert _output(result) == "beta"

    def test_switch_case_default(self):
        import json

        cases = json.dumps({"a": "alpha"})
        result = execute_extra_text_processor("switch_case", {"value": "z", "cases_json": cases, "default": "fallback"})
        assert result.success is True
        assert _output(result) == "fallback"


# ---------------------------------------------------------------------------
# processors_math  --  execute_extra_math_processor / execute_extra_list_processor
# ---------------------------------------------------------------------------


class TestMathProcessors:
    """Tests for execute_extra_math_processor."""

    def test_math_abs_negative(self):
        result = execute_extra_math_processor("math_abs", {"number": "-42"})
        assert result.success is True
        assert _output(result) == "42.0"

    def test_math_abs_positive(self):
        result = execute_extra_math_processor("math_abs", {"number": "7"})
        assert result.success is True
        assert _output(result) == "7.0"

    def test_math_ceil(self):
        result = execute_extra_math_processor("math_ceil", {"number": "3.2"})
        assert result.success is True
        assert _output(result) == "4"

    def test_math_floor(self):
        result = execute_extra_math_processor("math_floor", {"number": "3.9"})
        assert result.success is True
        assert _output(result) == "3"

    def test_math_round(self):
        result = execute_extra_math_processor("math_round", {"number": "3.14159", "decimals": "2"})
        assert result.success is True
        assert _output(result) == "3.14"

    def test_math_clamp_within_range(self):
        result = execute_extra_math_processor("math_clamp", {"number": "50", "min": "0", "max": "100"})
        assert result.success is True
        assert _output(result) == "50.0"

    def test_math_clamp_below_min(self):
        result = execute_extra_math_processor("math_clamp", {"number": "-5", "min": "0", "max": "100"})
        assert result.success is True
        assert _output(result) == "0.0"

    def test_math_sqrt(self):
        result = execute_extra_math_processor("math_sqrt", {"number": "16"})
        assert result.success is True
        assert _output(result) == "4.0"

    def test_math_factorial(self):
        result = execute_extra_math_processor("math_factorial", {"number": "5"})
        assert result.success is True
        assert _output(result) == "120"

    def test_math_gcd(self):
        result = execute_extra_math_processor("math_gcd", {"a": "12", "b": "8"})
        assert result.success is True
        assert _output(result) == "4"

    def test_math_fibonacci(self):
        result = execute_extra_math_processor("math_fibonacci", {"count": "7"})
        assert result.success is True
        assert result.payload["raw_outputs"]["items_json"] == [0, 1, 1, 2, 3, 5, 8]

    def test_unknown_math_processor_returns_none(self):
        result = execute_extra_math_processor("math_nonexistent", {"number": "1"})
        assert result is None

    @pytest.mark.parametrize(
        "processor_id,number",
        [
            ("math_abs", ""),
            ("math_ceil", ""),
            ("math_floor", ""),
        ],
    )
    def test_math_empty_number_defaults_to_zero(self, processor_id, number):
        result = execute_extra_math_processor(processor_id, {"number": number})
        assert result.success is True


class TestListProcessors:
    """Tests for execute_extra_list_processor."""

    def test_list_count(self):
        result = execute_extra_list_processor("list_count", {"list": "a\nb\na\nc\na", "value": "a"})
        assert result.success is True
        assert _output(result) == "3"

    def test_list_sum(self):
        result = execute_extra_list_processor("list_sum", {"list": "10\n20\n30"})
        assert result.success is True
        assert _output(result) == "60"

    def test_list_min(self):
        result = execute_extra_list_processor("list_min", {"list": "banana\napple\ncherry"})
        assert result.success is True
        assert _output(result) == "apple"

    def test_list_max(self):
        result = execute_extra_list_processor("list_max", {"list": "banana\napple\ncherry"})
        assert result.success is True
        assert _output(result) == "cherry"

    def test_list_avg(self):
        result = execute_extra_list_processor("list_avg", {"list": "10\n20\n30"})
        assert result.success is True
        assert _output(result) == "20"

    def test_list_remove(self):
        result = execute_extra_list_processor("list_remove", {"list": "a\nb\nc\nb", "value": "b"})
        assert result.success is True
        assert result.payload["raw_outputs"]["items_json"] == ["a", "c"]

    def test_list_find_found(self):
        result = execute_extra_list_processor("list_find", {"list": "a\nb\nc", "value": "b"})
        assert result.success is True
        assert _output(result) == "b"

    def test_list_find_not_found(self):
        result = execute_extra_list_processor("list_find", {"list": "a\nb\nc", "value": "z"})
        assert result.success is True
        assert _output(result) == ""

    def test_unknown_list_processor_returns_none(self):
        result = execute_extra_list_processor("list_nonexistent", {"list": "a"})
        assert result is None

    def test_list_avg_empty_list(self):
        result = execute_extra_list_processor("list_avg", {"list": ""})
        assert result.success is True
        assert _output(result) == "0"


# ---------------------------------------------------------------------------
# processors_datetime  --  execute_extra_datetime_processor
# ---------------------------------------------------------------------------


class TestDatetimeProcessors:
    """Tests for execute_extra_datetime_processor."""

    def test_datetime_now_default_format(self):
        result = execute_extra_datetime_processor("datetime_now", {})
        assert result.success is True
        output = _output(result)
        # Default format: YYYY-MM-DD HH:MM:SS
        assert len(output) >= 19
        assert output[4] == "-"
        assert output[10] == " "

    def test_datetime_now_custom_format(self):
        result = execute_extra_datetime_processor("datetime_now", {"format": "%Y%m%d"})
        assert result.success is True
        output = _output(result)
        assert len(output) == 8
        assert output.isdigit()

    def test_timestamp_now(self):
        result = execute_extra_datetime_processor("timestamp_now", {})
        assert result.success is True
        output = _output(result)
        ts = float(output)
        assert ts > 0

    def test_datetime_format(self):
        result = execute_extra_datetime_processor(
            "datetime_format", {"datetime": "2024-06-15 10:30:00", "format": "%Y/%m/%d"}
        )
        assert result.success is True
        assert _output(result) == "2024/06/15"

    def test_datetime_add_days(self):
        result = execute_extra_datetime_processor(
            "datetime_add", {"datetime": "2024-01-01 00:00:00", "days": "10", "format": "%Y-%m-%d"}
        )
        assert result.success is True
        assert _output(result) == "2024-01-11"

    def test_datetime_diff_seconds(self):
        result = execute_extra_datetime_processor(
            "datetime_diff",
            {
                "datetime1": "2024-01-02 00:00:00",
                "datetime2": "2024-01-01 00:00:00",
                "unit": "seconds",
            },
        )
        assert result.success is True
        assert _output(result) == "86400.0"

    def test_datetime_diff_days(self):
        result = execute_extra_datetime_processor(
            "datetime_diff",
            {
                "datetime1": "2024-01-11 00:00:00",
                "datetime2": "2024-01-01 00:00:00",
                "unit": "days",
            },
        )
        assert result.success is True
        assert _output(result) == "10.0"

    def test_unknown_datetime_processor_returns_none(self):
        result = execute_extra_datetime_processor("datetime_nonexistent", {})
        assert result is None


# ---------------------------------------------------------------------------
# processors_encoding  --  execute_extra_encoding_processor / execute_extra_system_processor
# ---------------------------------------------------------------------------


class TestEncodingProcessors:
    """Tests for execute_extra_encoding_processor."""

    def test_base64_encode(self):
        result = execute_extra_encoding_processor("base64_encode", {"text": "hello"})
        assert result.success is True
        assert _output(result) == "aGVsbG8="

    def test_base64_decode(self):
        result = execute_extra_encoding_processor("base64_decode", {"text": "aGVsbG8="})
        assert result.success is True
        assert _output(result) == "hello"

    def test_url_encode(self):
        result = execute_extra_encoding_processor("url_encode", {"text": "hello world&foo=bar"})
        assert result.success is True
        output = _output(result)
        assert "hello%20world" in output
        assert "%26" in output

    def test_url_decode(self):
        result = execute_extra_encoding_processor("url_decode", {"text": "hello%20world%26foo%3Dbar"})
        assert result.success is True
        assert _output(result) == "hello world&foo=bar"

    def test_html_encode(self):
        result = execute_extra_encoding_processor("html_encode", {"text": '<div class="test">'})
        assert result.success is True
        output = _output(result)
        assert "&lt;" in output
        assert "&gt;" in output

    def test_html_decode(self):
        result = execute_extra_encoding_processor("html_decode", {"text": "&lt;b&gt;bold&lt;/b&gt;"})
        assert result.success is True
        assert _output(result) == "<b>bold</b>"

    def test_hex_encode(self):
        result = execute_extra_encoding_processor("hex_encode", {"text": "AB"})
        assert result.success is True
        assert _output(result) == "4142"

    def test_hex_decode(self):
        result = execute_extra_encoding_processor("hex_decode", {"text": "4142"})
        assert result.success is True
        assert _output(result) == "AB"

    def test_base64_roundtrip(self):
        original = "QuickLauncher test 123"
        encoded = execute_extra_encoding_processor("base64_encode", {"text": original})
        decoded = execute_extra_encoding_processor("base64_decode", {"text": _output(encoded)})
        assert _output(decoded) == original

    def test_unknown_encoding_processor_returns_none(self):
        result = execute_extra_encoding_processor("encode_nonexistent", {"text": "hello"})
        assert result is None

    def test_base64_encode_empty_string(self):
        result = execute_extra_encoding_processor("base64_encode", {"text": ""})
        assert result.success is True
        assert _output(result) == ""


class TestSystemProcessors:
    """Tests for execute_extra_system_processor."""

    def test_sys_platform(self):
        result = execute_extra_system_processor("sys_platform", {})
        assert result.success is True
        assert len(_output(result)) > 0

    def test_sys_cpu_count(self):
        result = execute_extra_system_processor("sys_cpu_count", {})
        assert result.success is True
        assert int(_output(result)) >= 0

    def test_sys_current_dir(self):
        result = execute_extra_system_processor("sys_current_dir", {})
        assert result.success is True
        assert len(_output(result)) > 0

    def test_sys_temp_dir(self):
        result = execute_extra_system_processor("sys_temp_dir", {})
        assert result.success is True
        assert len(_output(result)) > 0

    def test_env_get_existing(self):
        import os

        os.environ["_TEST_CHAIN_VAR"] = "chain_test_value"
        try:
            result = execute_extra_system_processor("env_get", {"key": "_TEST_CHAIN_VAR"})
            assert result.success is True
            assert _output(result) == "chain_test_value"
        finally:
            del os.environ["_TEST_CHAIN_VAR"]

    def test_env_get_missing_with_default(self):
        result = execute_extra_system_processor(
            "env_get", {"key": "_NONEXISTENT_CHAIN_VAR_12345", "default": "fallback"}
        )
        assert result.success is True
        assert _output(result) == "fallback"

    def test_unknown_system_processor_returns_none(self):
        result = execute_extra_system_processor("sys_nonexistent", {})
        assert result is None


# ---------------------------------------------------------------------------
# processors_validation  --  execute_extra_validation_processor
# ---------------------------------------------------------------------------


class TestValidationProcessors:
    """Tests for execute_extra_validation_processor."""

    def test_validate_email_valid(self):
        result = execute_extra_validation_processor("validate_email", {"email": "user@example.com"})
        assert result.success is True
        assert _output_bool(result) == "true"

    def test_validate_email_invalid(self):
        result = execute_extra_validation_processor("validate_email", {"email": "not-an-email"})
        assert result.success is True
        assert _output_bool(result) == "false"

    def test_validate_email_empty(self):
        result = execute_extra_validation_processor("validate_email", {"email": ""})
        assert result.success is True
        assert _output_bool(result) == "false"

    def test_validate_url_valid(self):
        result = execute_extra_validation_processor("validate_url", {"url": "https://example.com/path"})
        assert result.success is True
        assert _output_bool(result) == "true"

    def test_validate_url_invalid(self):
        result = execute_extra_validation_processor("validate_url", {"url": "just some text"})
        assert result.success is True
        assert _output_bool(result) == "false"

    def test_validate_ip_v4(self):
        result = execute_extra_validation_processor("validate_ip", {"ip": "192.168.1.1"})
        assert result.success is True
        assert _output_bool(result) == "true"

    def test_validate_ip_invalid(self):
        result = execute_extra_validation_processor("validate_ip", {"ip": "999.999.999.999"})
        assert result.success is True
        assert _output_bool(result) == "false"

    def test_validate_range_in_range(self):
        result = execute_extra_validation_processor("validate_range", {"value": "50", "min": "0", "max": "100"})
        assert result.success is True
        assert _output_bool(result) == "true"

    def test_validate_range_out_of_range(self):
        result = execute_extra_validation_processor("validate_range", {"value": "150", "min": "0", "max": "100"})
        assert result.success is True
        assert _output_bool(result) == "false"

    def test_validate_length_ok(self):
        result = execute_extra_validation_processor("validate_length", {"text": "hello", "min": "1", "max": "10"})
        assert result.success is True
        assert _output_bool(result) == "true"

    def test_validate_length_too_short(self):
        result = execute_extra_validation_processor("validate_length", {"text": "", "min": "1", "max": "10"})
        assert result.success is True
        assert _output_bool(result) == "false"

    def test_validate_regex_match(self):
        result = execute_extra_validation_processor("validate_regex", {"text": "abc123", "pattern": r"^\w+$"})
        assert result.success is True
        assert _output_bool(result) == "true"

    def test_validate_regex_no_match(self):
        result = execute_extra_validation_processor("validate_regex", {"text": "abc 123", "pattern": r"^\w+$"})
        assert result.success is True
        assert _output_bool(result) == "false"

    def test_unknown_validation_processor_returns_none(self):
        result = execute_extra_validation_processor("validate_nonexistent", {"text": "x"})
        assert result is None


# ---------------------------------------------------------------------------
# processors_data  --  execute_extra_data_processor
# ---------------------------------------------------------------------------


class TestDataProcessors:
    """Tests for execute_extra_data_processor."""

    def test_hash_md5(self):
        result = execute_extra_data_processor("hash_md5", {"text": "hello"})
        assert result.success is True
        assert _output(result) == "5d41402abc4b2a76b9719d911017c592"

    def test_hash_sha256(self):
        result = execute_extra_data_processor("hash_sha256", {"text": "hello"})
        assert result.success is True
        assert len(_output(result)) == 64

    def test_hash_sha1(self):
        result = execute_extra_data_processor("hash_sha1", {"text": "hello"})
        assert result.success is True
        assert len(_output(result)) == 40

    def test_hash_crc32(self):
        result = execute_extra_data_processor("hash_crc32", {"text": "hello"})
        assert result.success is True
        assert len(_output(result)) == 8

    def test_hash_uuid(self):
        result = execute_extra_data_processor("hash_uuid", {})
        assert result.success is True
        output = _output(result)
        # UUID4 format: 8-4-4-4-12
        parts = output.split("-")
        assert len(parts) == 5

    def test_color_hex_to_rgb(self):
        result = execute_extra_data_processor("color_hex_to_rgb", {"hex": "#ff8000"})
        assert result.success is True
        assert _output(result) == "(255, 128, 0)"

    def test_color_rgb_to_hex(self):
        result = execute_extra_data_processor("color_rgb_to_hex", {"r": "255", "g": "128", "b": "0"})
        assert result.success is True
        assert _output(result) == "#ff8000"

    def test_set_union(self):
        result = execute_extra_data_processor("set_union", {"set1": "a\nb\nc", "set2": "b\nc\nd"})
        assert result.success is True
        items = set(result.payload["raw_outputs"]["items_json"])
        assert items == {"a", "b", "c", "d"}

    def test_set_intersection(self):
        result = execute_extra_data_processor("set_intersection", {"set1": "a\nb\nc", "set2": "b\nc\nd"})
        assert result.success is True
        items = set(result.payload["raw_outputs"]["items_json"])
        assert items == {"b", "c"}

    def test_set_difference(self):
        result = execute_extra_data_processor("set_difference", {"set1": "a\nb\nc", "set2": "b\nc\nd"})
        assert result.success is True
        items = result.payload["raw_outputs"]["items_json"]
        assert items == ["a"]

    def test_dict_keys(self):
        import json

        result = execute_extra_data_processor("dict_keys", {"json": json.dumps({"a": 1, "b": 2})})
        assert result.success is True
        items = set(result.payload["raw_outputs"]["items_json"])
        assert items == {"a", "b"}

    def test_dict_merge(self):
        import json

        result = execute_extra_data_processor(
            "dict_merge",
            {
                "a": json.dumps({"x": 1}),
                "b": json.dumps({"y": 2}),
            },
        )
        assert result.success is True
        merged = json.loads(_output(result))
        assert merged == {"x": 1, "y": 2}

    def test_str_pad_left(self):
        result = execute_extra_data_processor("str_pad_left", {"text": "42", "width": "5", "fillchar": "0"})
        assert result.success is True
        assert _output(result) == "00042"

    def test_str_truncate(self):
        result = execute_extra_data_processor(
            "str_truncate", {"text": "hello world", "max_length": "8", "suffix": "..."}
        )
        assert result.success is True
        assert _output(result) == "hello..."

    def test_str_repeat(self):
        result = execute_extra_data_processor("str_repeat", {"text": "ab", "count": "3"})
        assert result.success is True
        assert _output(result) == "ababab"

    def test_unknown_data_processor_returns_none(self):
        result = execute_extra_data_processor("hash_nonexistent", {"text": "x"})
        assert result is None

    def test_hash_md5_empty_string(self):
        result = execute_extra_data_processor("hash_md5", {"text": ""})
        assert result.success is True
        # md5 of empty string
        assert _output(result) == "d41d8cd98f00b204e9800998ecf8427e"


# ---------------------------------------------------------------------------
# processors_files  --  copy source boundaries
# ---------------------------------------------------------------------------


class TestFileProcessorSafety:
    def test_file_copy_rejects_protected_source(self, tmp_path):
        source = Path(__file__).resolve()
        destination = tmp_path / "copied.py"

        result = execute_chain_processor("file_copy", {"src": str(source), "dst": str(destination)})

        assert result.success is False
        assert "protected path" in result.message
        assert not destination.exists()


# ---------------------------------------------------------------------------
# processors_network  --  http_download path boundaries
# ---------------------------------------------------------------------------


class TestNetworkProcessors:
    """Tests for network processor safety boundaries."""

    def test_http_download_rejects_empty_save_dir(self, monkeypatch):
        def fail_urlopen(*args, **kwargs):
            raise AssertionError("invalid save_dir must not reach the network")

        monkeypatch.setattr("core.chain.processors_network.safe_urlopen", fail_urlopen)

        result = execute_chain_processor("http_download", {"url": "https://example.com/file.txt", "save_dir": ""})

        assert result.success is False
        assert "保存目录" in result.message

    def test_http_download_rejects_app_root_save_dir(self, monkeypatch):
        def fail_urlopen(*args, **kwargs):
            raise AssertionError("protected save_dir must not reach the network")

        monkeypatch.setattr("core.chain.processors_network.safe_urlopen", fail_urlopen)
        protected_dir = Path(__file__).resolve().parents[1] / "download-target"

        result = execute_chain_processor(
            "http_download",
            {"url": "https://example.com/file.txt", "save_dir": str(protected_dir)},
        )

        assert result.success is False
        assert "protected path" in result.message

    def test_http_download_writes_inside_safe_temp_dir(self, tmp_path, monkeypatch):
        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, _limit):
                return b"downloaded"

        monkeypatch.setattr("core.chain.processors_network.safe_urlopen", lambda *args, **kwargs: _FakeResponse())

        result = execute_chain_processor(
            "http_download",
            {"url": "https://example.com/archive/file.txt", "save_dir": str(tmp_path)},
        )

        target = tmp_path / "file.txt"
        assert result.success is True
        assert _output(result) == str(target.resolve(strict=False))
        assert target.read_bytes() == b"downloaded"


# ---------------------------------------------------------------------------
# registry._execute_extra_processor  --  integration dispatch tests
# ---------------------------------------------------------------------------


class TestExtraProcessorDispatch:
    """Test that _execute_extra_processor() correctly delegates to all modules."""

    @pytest.mark.parametrize(
        "processor_id,values,expected_check",
        [
            # Text processors
            ("text_trim", {"text": "  padded  "}, lambda r: _output(r) == "padded"),
            ("text_reverse", {"text": "abc"}, lambda r: _output(r) == "cba"),
            # Math processors
            ("math_abs", {"number": "-10"}, lambda r: _output(r) == "10.0"),
            ("math_ceil", {"number": "2.1"}, lambda r: _output(r) == "3"),
            # List processors
            ("list_sum", {"list": "1\n2\n3"}, lambda r: _output(r) == "6"),
            # Datetime processors
            ("datetime_now", {}, lambda r: r.success is True and len(_output(r)) >= 10),
            ("timestamp_now", {}, lambda r: float(_output(r)) > 0),
            # Encoding processors
            ("base64_encode", {"text": "test"}, lambda r: _output(r) == "dGVzdA=="),
            ("hex_encode", {"text": "A"}, lambda r: _output(r) == "41"),
            # System processors
            ("sys_platform", {}, lambda r: r.success is True and len(_output(r)) > 0),
            # Validation processors
            ("validate_email", {"email": "a@b.com"}, lambda r: _output_bool(r) == "true"),
            ("validate_ip", {"ip": "10.0.0.1"}, lambda r: _output_bool(r) == "true"),
            # Data processors
            ("hash_md5", {"text": "test"}, lambda r: len(_output(r)) == 32),
            ("hash_sha256", {"text": "test"}, lambda r: len(_output(r)) == 64),
            ("color_hex_to_rgb", {"hex": "#000000"}, lambda r: _output(r) == "(0, 0, 0)"),
        ],
    )
    def test_dispatch_delegates_correctly(self, processor_id, values, expected_check):
        result = _execute_extra_processor(processor_id, values)
        assert result is not None, f"Processor {processor_id} should not return None"
        assert result.success is True, f"Processor {processor_id} should succeed"
        assert expected_check(result), f"Processor {processor_id} output check failed: {_output(result)}"

    @pytest.mark.parametrize(
        "processor_id",
        [
            "totally_unknown_processor",
            "nonexistent_text_op",
            "zzz_fake_processor",
        ],
    )
    def test_unknown_processor_returns_none(self, processor_id):
        result = _execute_extra_processor(processor_id, {"text": "hello"})
        assert result is None

    def test_dispatch_text_trim(self):
        result = _execute_extra_processor("text_trim", {"text": "  hello  "})
        assert result is not None
        assert _output(result) == "hello"

    def test_dispatch_math_abs(self):
        result = _execute_extra_processor("math_abs", {"number": "-42"})
        assert result is not None
        assert _output(result) == "42.0"

    def test_dispatch_datetime_now(self):
        result = _execute_extra_processor("datetime_now", {})
        assert result is not None
        assert result.success is True

    def test_dispatch_base64_encode(self):
        result = _execute_extra_processor("base64_encode", {"text": "hello"})
        assert result is not None
        assert _output(result) == "aGVsbG8="

    def test_dispatch_hash_md5(self):
        result = _execute_extra_processor("hash_md5", {"text": "hello"})
        assert result is not None
        assert _output(result) == "5d41402abc4b2a76b9719d911017c592"

    def test_dispatch_validate_email(self):
        result = _execute_extra_processor("validate_email", {"email": "user@example.com"})
        assert result is not None
        assert _output_bool(result) == "true"

    def test_dispatch_env_get(self):
        import os

        os.environ["_TEST_DISPATCH_VAR"] = "dispatch_val"
        try:
            result = _execute_extra_processor("env_get", {"key": "_TEST_DISPATCH_VAR"})
            assert result is not None
            assert _output(result) == "dispatch_val"
        finally:
            del os.environ["_TEST_DISPATCH_VAR"]

    def test_dispatch_list_sum(self):
        result = _execute_extra_processor("list_sum", {"list": "5\n10\n15"})
        assert result is not None
        assert _output(result) == "30"
