"""Tests for smart type recognition and validation system."""

import json
import pytest

from core.chain.smart_types import (
    SmartType,
    TypeHint,
    SmartTypeRecognizer,
    TypeValidator,
    TypeConverter,
    recognize_type,
    validate_value,
    convert_value,
    get_type_hint,
    get_type_description,
    get_type_examples,
)


class TestSmartTypeRecognizer:
    """Test smart type recognition."""

    def test_recognize_ip_address(self):
        """Test IP address recognition."""
        type_, confidence = recognize_type("192.168.1.1")
        assert type_ == SmartType.IP_ADDRESS
        assert confidence >= 0.8

    def test_recognize_ipv4_valid(self):
        """Test valid IPv4 recognition."""
        test_cases = [
            "10.0.0.1",
            "172.16.0.1",
            "255.255.255.0",
            "0.0.0.0",
        ]
        for ip in test_cases:
            type_, confidence = recognize_type(ip)
            assert type_ == SmartType.IP_ADDRESS, f"Failed for {ip}"

    def test_recognize_ipv4_invalid(self):
        """Test invalid IPv4 recognition."""
        test_cases = [
            "256.1.1.1",  # Out of range
            "1.1.1",  # Too few octets
            "abc.def.ghi.jkl",  # Not numbers
        ]
        for ip in test_cases:
            type_, confidence = recognize_type(ip)
            assert type_ != SmartType.IP_ADDRESS, f"Should not recognize {ip} as IP"

    def test_recognize_email(self):
        """Test email recognition."""
        type_, confidence = recognize_type("user@example.com")
        assert type_ == SmartType.EMAIL
        assert confidence >= 0.9

    def test_recognize_email_variations(self):
        """Test email variations."""
        test_cases = [
            "test@gmail.com",
            "user.name@domain.com",
            "user+tag@example.org",
        ]
        for email in test_cases:
            type_, confidence = recognize_type(email)
            assert type_ == SmartType.EMAIL, f"Failed for {email}"

    def test_recognize_url(self):
        """Test URL recognition."""
        type_, confidence = recognize_type("https://example.com")
        assert type_ == SmartType.HTTP_URL
        assert confidence >= 0.8

    def test_recognize_url_variations(self):
        """Test URL variations."""
        test_cases = [
            "http://localhost",
            "https://www.google.com",
            "http://192.168.1.1:8080/path",
        ]
        for url in test_cases:
            type_, confidence = recognize_type(url)
            assert type_ in (SmartType.HTTP_URL, SmartType.URL), f"Failed for {url}"

    def test_recognize_uuid(self):
        """Test UUID recognition."""
        type_, confidence = recognize_type("550e8400-e29b-41d4-a716-446655440000")
        assert type_ == SmartType.UUID
        assert confidence >= 0.9

    def test_recognize_json(self):
        """Test JSON recognition."""
        type_, confidence = recognize_type('{"key": "value"}')
        assert type_ in (SmartType.JSON, SmartType.JSON_STRING)
        assert confidence >= 0.8

    def test_recognize_json_array(self):
        """Test JSON array recognition."""
        type_, confidence = recognize_type('[1, 2, 3]')
        assert type_ in (SmartType.JSON, SmartType.JSON_STRING)

    def test_recognize_integer(self):
        """Test integer recognition."""
        type_, confidence = recognize_type("42")
        assert type_ == SmartType.INTEGER
        assert confidence >= 0.7

    def test_recognize_float(self):
        """Test float recognition."""
        type_, confidence = recognize_type("3.14")
        assert type_ == SmartType.FLOAT
        assert confidence >= 0.7

    def test_recognize_negative_number(self):
        """Test negative number recognition."""
        type_, confidence = recognize_type("-5")
        assert type_ == SmartType.INTEGER

    def test_recognize_boolean(self):
        """Test boolean recognition."""
        type_, confidence = recognize_type("true")
        assert type_ == SmartType.BOOL
        assert confidence >= 0.7

    def test_recognize_date(self):
        """Test date recognition."""
        type_, confidence = recognize_type("2024-01-01")
        assert type_ == SmartType.DATE
        assert confidence >= 0.7

    def test_recognize_time(self):
        """Test time recognition."""
        type_, confidence = recognize_type("14:30:00")
        assert type_ == SmartType.TIME
        assert confidence >= 0.7

    def test_recognize_color_hex(self):
        """Test hex color recognition."""
        type_, confidence = recognize_type("#FF0000")
        assert type_ == SmartType.COLOR
        assert confidence >= 0.7

    def test_recognize_file_path(self):
        """Test file path recognition."""
        type_, confidence = recognize_type("C:\\Users\\test.txt")
        assert type_ == SmartType.FILE
        assert confidence >= 0.7

    def test_recognize_unix_file_path(self):
        """Test Unix file path recognition."""
        type_, confidence = recognize_type("/home/user/file.txt")
        assert type_ == SmartType.FILE
        assert confidence >= 0.7

    def test_recognize_base64(self):
        """Test Base64 recognition."""
        type_, confidence = recognize_type("SGVsbG8gV29ybGQ=")
        assert type_ == SmartType.BASE64

    def test_recognize_hex(self):
        """Test hex string recognition."""
        type_, confidence = recognize_type("0xFF00FF")
        # 0xFF00FF could be recognized as HEX or BASE64 (both are valid)
        assert type_ in (SmartType.HEX, SmartType.BASE64)

    def test_recognize_empty_string(self):
        """Test empty string recognition."""
        type_, confidence = recognize_type("")
        assert type_ == SmartType.TEXT

    def test_recognize_none(self):
        """Test None recognition."""
        type_, confidence = recognize_type(None)
        assert type_ == SmartType.ANY


class TestTypeValidator:
    """Test type validation."""

    def test_validate_integer_valid(self):
        """Test valid integer validation."""
        valid, msg = TypeValidator.validate_integer("42")
        assert valid is True

    def test_validate_integer_float(self):
        """Test float validation as integer."""
        valid, msg = TypeValidator.validate_integer("3.14")
        assert valid is False
        assert "整数" in msg

    def test_validate_integer_invalid(self):
        """Test invalid integer validation."""
        valid, msg = TypeValidator.validate_integer("abc")
        assert valid is False

    def test_validate_float_valid(self):
        """Test valid float validation."""
        valid, msg = TypeValidator.validate_float("3.14")
        assert valid is True

    def test_validate_float_integer(self):
        """Test integer validation as float."""
        valid, msg = TypeValidator.validate_float("42")
        assert valid is True

    def test_validate_float_invalid(self):
        """Test invalid float validation."""
        valid, msg = TypeValidator.validate_float("abc")
        assert valid is False

    def test_validate_positive_valid(self):
        """Test valid positive validation."""
        valid, msg = TypeValidator.validate_positive("5")
        assert valid is True

    def test_validate_positive_zero(self):
        """Test zero validation as positive."""
        valid, msg = TypeValidator.validate_positive("0")
        assert valid is False
        assert "正数" in msg

    def test_validate_positive_negative(self):
        """Test negative validation as positive."""
        valid, msg = TypeValidator.validate_positive("-5")
        assert valid is False

    def test_validate_negative_valid(self):
        """Test valid negative validation."""
        valid, msg = TypeValidator.validate_negative("-5")
        assert valid is True

    def test_validate_negative_positive(self):
        """Test positive validation as negative."""
        valid, msg = TypeValidator.validate_negative("5")
        assert valid is False
        assert "负数" in msg

    def test_validate_non_negative_valid(self):
        """Test valid non-negative validation."""
        valid, msg = TypeValidator.validate_non_negative("0")
        assert valid is True

    def test_validate_non_negative_positive(self):
        """Test positive validation as non-negative."""
        valid, msg = TypeValidator.validate_non_negative("5")
        assert valid is True

    def test_validate_non_negative_negative(self):
        """Test negative validation as non-negative."""
        valid, msg = TypeValidator.validate_non_negative("-5")
        assert valid is False

    def test_validate_json_valid(self):
        """Test valid JSON validation."""
        valid, msg = TypeValidator.validate_json('{"key": "value"}')
        assert valid is True

    def test_validate_json_invalid(self):
        """Test invalid JSON validation."""
        valid, msg = TypeValidator.validate_json("{invalid json}")
        assert valid is False
        assert "JSON" in msg

    def test_validate_url_valid(self):
        """Test valid URL validation."""
        valid, msg = TypeValidator.validate_url("https://example.com")
        assert valid is True

    def test_validate_url_invalid(self):
        """Test invalid URL validation."""
        valid, msg = TypeValidator.validate_url("not a url")
        assert valid is False

    def test_validate_ip_valid(self):
        """Test valid IP validation."""
        valid, msg = TypeValidator.validate_ip_address("192.168.1.1")
        assert valid is True

    def test_validate_ip_invalid(self):
        """Test invalid IP validation."""
        valid, msg = TypeValidator.validate_ip_address("256.1.1.1")
        assert valid is False

    def test_validate_email_valid(self):
        """Test valid email validation."""
        valid, msg = TypeValidator.validate_email("user@example.com")
        assert valid is True

    def test_validate_email_invalid(self):
        """Test invalid email validation."""
        valid, msg = TypeValidator.validate_email("not-an-email")
        assert valid is False

    def test_validate_uuid_valid(self):
        """Test valid UUID validation."""
        valid, msg = TypeValidator.validate_uuid("550e8400-e29b-41d4-a716-446655440000")
        assert valid is True

    def test_validate_uuid_invalid(self):
        """Test invalid UUID validation."""
        valid, msg = TypeValidator.validate_uuid("not-a-uuid")
        assert valid is False

    def test_validate_color_hex(self):
        """Test hex color validation."""
        valid, msg = TypeValidator.validate_color("#FF0000")
        assert valid is True

    def test_validate_color_rgb(self):
        """Test RGB color validation."""
        valid, msg = TypeValidator.validate_color("rgb(255,0,0)")
        assert valid is True

    def test_validate_color_named(self):
        """Test named color validation."""
        valid, msg = TypeValidator.validate_color("red")
        assert valid is True

    def test_validate_regex_valid(self):
        """Test valid regex validation."""
        valid, msg = TypeValidator.validate_regex("[a-z]+")
        assert valid is True

    def test_validate_regex_invalid(self):
        """Test invalid regex validation."""
        valid, msg = TypeValidator.validate_regex("[invalid")
        assert valid is False


class TestTypeConverter:
    """Test type conversion."""

    def test_to_integer_from_string(self):
        """Test integer conversion from string."""
        assert TypeConverter.to_integer("42") == 42

    def test_to_integer_from_float(self):
        """Test integer conversion from float."""
        assert TypeConverter.to_integer("3.14") == 3

    def test_to_float_from_string(self):
        """Test float conversion from string."""
        assert TypeConverter.to_float("3.14") == 3.14

    def test_to_float_from_integer(self):
        """Test float conversion from integer."""
        assert TypeConverter.to_float("42") == 42.0

    def test_to_bool_true_values(self):
        """Test boolean conversion for true values."""
        true_values = ["true", "1", "yes", "on", "是", "真"]
        for val in true_values:
            assert TypeConverter.to_bool(val) is True, f"Failed for {val}"

    def test_to_bool_false_values(self):
        """Test boolean conversion for false values."""
        false_values = ["false", "0", "no", "off", "否", "假", ""]
        for val in false_values:
            assert TypeConverter.to_bool(val) is False, f"Failed for {val}"

    def test_to_string_from_number(self):
        """Test string conversion from number."""
        assert TypeConverter.to_string(42) == "42"
        assert TypeConverter.to_string(3.14) == "3.14"

    def test_to_string_from_bool(self):
        """Test string conversion from boolean."""
        assert TypeConverter.to_string(True) == "true"
        assert TypeConverter.to_string(False) == "false"

    def test_to_string_from_dict(self):
        """Test string conversion from dict."""
        result = TypeConverter.to_string({"key": "value"})
        assert result == '{"key": "value"}'

    def test_to_json_from_string(self):
        """Test JSON conversion from string."""
        result = TypeConverter.to_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_to_json_from_dict(self):
        """Test JSON conversion from dict."""
        data = {"key": "value"}
        assert TypeConverter.to_json(data) is data

    def test_to_list_from_string(self):
        """Test list conversion from string."""
        result = TypeConverter.to_list("a\nb\nc")
        assert result == ["a", "b", "c"]

    def test_to_list_from_json_array(self):
        """Test list conversion from JSON array."""
        result = TypeConverter.to_list('["a", "b", "c"]')
        assert result == ["a", "b", "c"]


class TestHighLevelFunctions:
    """Test high-level functions."""

    def test_validate_value_with_smart_type(self):
        """Test validate_value with smart type."""
        valid, msg = validate_value("192.168.1.1", SmartType.IP_ADDRESS)
        assert valid is True

    def test_validate_value_invalid(self):
        """Test validate_value with invalid value."""
        valid, msg = validate_value("not-an-ip", SmartType.IP_ADDRESS)
        assert valid is False

    def test_convert_value_to_integer(self):
        """Test convert_value to integer."""
        result = convert_value("42", SmartType.INTEGER)
        assert result == 42

    def test_convert_value_to_float(self):
        """Test convert_value to float."""
        result = convert_value("3.14", SmartType.FLOAT)
        assert result == 3.14

    def test_get_type_hint(self):
        """Test get_type_hint."""
        hint = get_type_hint(SmartType.IP_ADDRESS)
        assert hint is not None
        assert hint.description == "IP地址"

    def test_get_type_description(self):
        """Test get_type_description."""
        desc = get_type_description(SmartType.EMAIL)
        assert desc == "电子邮箱"

    def test_get_type_examples(self):
        """Test get_type_examples."""
        examples = get_type_examples(SmartType.EMAIL)
        assert "user@example.com" in examples


class TestTypeCompatibility:
    """Test type compatibility."""

    def test_same_type_compatible(self):
        """Test same type compatibility."""
        from core.chain.port_types import TypeCompatibility
        assert TypeCompatibility.is_compatible("text", "text") is True

    def test_any_compatible(self):
        """Test any type compatibility."""
        from core.chain.port_types import TypeCompatibility
        assert TypeCompatibility.is_compatible("any", "text") is True
        assert TypeCompatibility.is_compatible("text", "any") is True

    def test_text_to_number_incompatible(self):
        """Test text to number incompatibility."""
        from core.chain.port_types import TypeCompatibility
        assert TypeCompatibility.is_compatible("text", "number") is False

    def test_number_to_text_compatible(self):
        """Test number to text compatibility."""
        from core.chain.port_types import TypeCompatibility
        assert TypeCompatibility.is_compatible("number", "text") is True

    def test_smart_type_compatibility(self):
        """Test smart type compatibility."""
        from core.chain.port_types import TypeCompatibility
        assert TypeCompatibility.is_compatible(
            "number", "number",
            SmartType.INTEGER.value, SmartType.FLOAT.value
        ) is True

    def test_conversion_cost_same(self):
        """Test conversion cost for same type."""
        from core.chain.port_types import TypeCompatibility
        cost = TypeCompatibility.get_conversion_cost("text", "text")
        assert cost == 0

    def test_conversion_cost_any(self):
        """Test conversion cost for any type."""
        from core.chain.port_types import TypeCompatibility
        cost = TypeCompatibility.get_conversion_cost("any", "text")
        assert cost == 0

    def test_conversion_cost_impossible(self):
        """Test conversion cost for impossible conversion."""
        from core.chain.port_types import TypeCompatibility
        cost = TypeCompatibility.get_conversion_cost("text", "number")
        assert cost == -1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
