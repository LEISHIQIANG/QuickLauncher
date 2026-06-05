"""Smart type recognition and validation system for action chains.

This module provides intelligent type detection, validation, and conversion
for action chain port values. It can automatically recognize patterns like
IP addresses, emails, URLs, file paths, and more.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "SmartType",
    "TypeHint",
    "SmartTypeRecognizer",
    "TypeValidator",
    "TypeConverter",
    "recognize_type",
    "validate_value",
    "convert_value",
]


class SmartType(str, Enum):
    """Extended type system with smart recognition."""

    # Basic types
    ANY = "any"
    TEXT = "text"
    NUMBER = "number"
    BOOL = "bool"
    JSON = "json"
    LIST = "list"

    # Path types
    FILE = "file"
    FOLDER = "folder"
    PATH = "path"  # Generic path (file or folder)

    # Network types
    URL = "url"
    IP_ADDRESS = "ip_address"
    EMAIL = "email"
    HOSTNAME = "hostname"
    HTTP_URL = "http_url"

    # Numeric subtypes
    INTEGER = "integer"
    FLOAT = "float"
    POSITIVE_NUMBER = "positive_number"
    NEGATIVE_NUMBER = "negative_number"
    NON_NEGATIVE_NUMBER = "non_negative_number"

    # Text subtypes
    JSON_STRING = "json_string"
    BASE64 = "base64"
    HEX = "hex"
    UUID = "uuid"
    DATE = "date"
    TIME = "time"
    DATETIME = "datetime"

    # Special types
    COLOR = "color"
    REGEX = "regex"
    COMMAND = "command"
    CODE = "code"


@dataclass(frozen=True)
class TypeHint:
    """Type hint with validation rules."""

    smart_type: SmartType
    base_type: str  # Maps to ChainValueKind
    description: str = ""
    examples: list[str] = field(default_factory=list)
    validator: str = ""  # Validator function name
    converter: str = ""  # Converter function name
    constraints: dict[str, Any] = field(default_factory=dict)


# Type hint registry
TYPE_HINTS: dict[str, TypeHint] = {
    SmartType.ANY: TypeHint(
        smart_type=SmartType.ANY,
        base_type="any",
        description="任意类型",
    ),
    SmartType.TEXT: TypeHint(
        smart_type=SmartType.TEXT,
        base_type="text",
        description="文本字符串",
    ),
    SmartType.NUMBER: TypeHint(
        smart_type=SmartType.NUMBER,
        base_type="number",
        description="数字（整数或小数）",
        examples=["0", "42", "3.14", "-1.5"],
    ),
    SmartType.INTEGER: TypeHint(
        smart_type=SmartType.INTEGER,
        base_type="number",
        description="整数",
        examples=["0", "42", "-1"],
        validator="validate_integer",
        converter="to_integer",
        constraints={"decimal_places": 0},
    ),
    SmartType.FLOAT: TypeHint(
        smart_type=SmartType.FLOAT,
        base_type="number",
        description="浮点数（支持小数）",
        examples=["0.0", "3.14", "-1.5"],
        validator="validate_float",
    ),
    SmartType.POSITIVE_NUMBER: TypeHint(
        smart_type=SmartType.POSITIVE_NUMBER,
        base_type="number",
        description="正数（大于0）",
        examples=["1", "3.14"],
        validator="validate_positive",
        constraints={"min": 0, "exclusive_min": True},
    ),
    SmartType.NEGATIVE_NUMBER: TypeHint(
        smart_type=SmartType.NEGATIVE_NUMBER,
        base_type="number",
        description="负数（小于0）",
        examples=["-1", "-3.14"],
        validator="validate_negative",
        constraints={"max": 0, "exclusive_max": True},
    ),
    SmartType.NON_NEGATIVE_NUMBER: TypeHint(
        smart_type=SmartType.NON_NEGATIVE_NUMBER,
        base_type="number",
        description="非负数（大于等于0）",
        examples=["0", "1", "3.14"],
        validator="validate_non_negative",
        constraints={"min": 0},
    ),
    SmartType.BOOL: TypeHint(
        smart_type=SmartType.BOOL,
        base_type="bool",
        description="布尔值",
        examples=["true", "false", "1", "0"],
    ),
    SmartType.JSON: TypeHint(
        smart_type=SmartType.JSON,
        base_type="json",
        description="JSON数据",
        examples=['{"key": "value"}', '[1, 2, 3]'],
        validator="validate_json",
    ),
    SmartType.JSON_STRING: TypeHint(
        smart_type=SmartType.JSON_STRING,
        base_type="text",
        description="JSON格式字符串",
        examples=['{"key": "value"}'],
        validator="validate_json_string",
    ),
    SmartType.LIST: TypeHint(
        smart_type=SmartType.LIST,
        base_type="list",
        description="列表",
        examples=["item1\nitem2\nitem3", '["a", "b", "c"]'],
    ),
    SmartType.FILE: TypeHint(
        smart_type=SmartType.FILE,
        base_type="file",
        description="文件路径",
        examples=["C:\\Users\\test.txt", "/home/user/file.txt"],
        validator="validate_file_path",
    ),
    SmartType.FOLDER: TypeHint(
        smart_type=SmartType.FOLDER,
        base_type="folder",
        description="文件夹路径",
        examples=["C:\\Users\\Documents", "/home/user/docs"],
        validator="validate_folder_path",
    ),
    SmartType.PATH: TypeHint(
        smart_type=SmartType.PATH,
        base_type="text",
        description="路径（文件或文件夹）",
        examples=["C:\\Users\\test.txt", "/home/user/docs"],
        validator="validate_path",
    ),
    SmartType.URL: TypeHint(
        smart_type=SmartType.URL,
        base_type="url",
        description="URL地址",
        examples=["https://example.com", "http://localhost:8080"],
        validator="validate_url",
    ),
    SmartType.HTTP_URL: TypeHint(
        smart_type=SmartType.HTTP_URL,
        base_type="url",
        description="HTTP/HTTPS URL",
        examples=["https://example.com", "http://localhost:8080"],
        validator="validate_http_url",
        constraints={"schemes": ["http", "https"]},
    ),
    SmartType.IP_ADDRESS: TypeHint(
        smart_type=SmartType.IP_ADDRESS,
        base_type="text",
        description="IP地址",
        examples=["192.168.1.1", "10.0.0.1", "::1"],
        validator="validate_ip_address",
    ),
    SmartType.EMAIL: TypeHint(
        smart_type=SmartType.EMAIL,
        base_type="text",
        description="电子邮箱",
        examples=["user@example.com"],
        validator="validate_email",
    ),
    SmartType.HOSTNAME: TypeHint(
        smart_type=SmartType.HOSTNAME,
        base_type="text",
        description="主机名",
        examples=["localhost", "example.com", "192.168.1.1"],
        validator="validate_hostname",
    ),
    SmartType.BASE64: TypeHint(
        smart_type=SmartType.BASE64,
        base_type="text",
        description="Base64编码字符串",
        examples=["SGVsbG8gV29ybGQ="],
        validator="validate_base64",
    ),
    SmartType.HEX: TypeHint(
        smart_type=SmartType.HEX,
        base_type="text",
        description="十六进制字符串",
        examples=["0x1A2B", "FF00FF"],
        validator="validate_hex",
    ),
    SmartType.UUID: TypeHint(
        smart_type=SmartType.UUID,
        base_type="text",
        description="UUID",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
        validator="validate_uuid",
    ),
    SmartType.DATE: TypeHint(
        smart_type=SmartType.DATE,
        base_type="text",
        description="日期",
        examples=["2024-01-01", "2024/01/01"],
        validator="validate_date",
    ),
    SmartType.TIME: TypeHint(
        smart_type=SmartType.TIME,
        base_type="text",
        description="时间",
        examples=["14:30:00", "14:30"],
        validator="validate_time",
    ),
    SmartType.DATETIME: TypeHint(
        smart_type=SmartType.DATETIME,
        base_type="text",
        description="日期时间",
        examples=["2024-01-01 14:30:00"],
        validator="validate_datetime",
    ),
    SmartType.COLOR: TypeHint(
        smart_type=SmartType.COLOR,
        base_type="text",
        description="颜色值",
        examples=["#FF0000", "rgb(255,0,0)", "red"],
        validator="validate_color",
    ),
    SmartType.REGEX: TypeHint(
        smart_type=SmartType.REGEX,
        base_type="text",
        description="正则表达式",
        examples=["[a-z]+", "\\d{3}-\\d{4}"],
        validator="validate_regex",
    ),
    SmartType.COMMAND: TypeHint(
        smart_type=SmartType.COMMAND,
        base_type="text",
        description="命令行",
        examples=["ls -la", "dir C:\\"],
    ),
    SmartType.CODE: TypeHint(
        smart_type=SmartType.CODE,
        base_type="text",
        description="代码片段",
    ),
}


class SmartTypeRecognizer:
    """Intelligent type recognition from values."""

    # Pattern matchers for automatic type detection
    PATTERNS = {
        # IP addresses
        SmartType.IP_ADDRESS: [
            re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"),  # IPv4
            re.compile(r"^[0-9a-fA-F:]+$"),  # IPv6 (simplified)
        ],
        # Email
        SmartType.EMAIL: [
            re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"),
        ],
        # URLs
        SmartType.HTTP_URL: [
            re.compile(r"^https?://", re.IGNORECASE),
        ],
        SmartType.URL: [
            re.compile(r"^(https?|ftp|file)://", re.IGNORECASE),
            re.compile(r"^www\.", re.IGNORECASE),
        ],
        # UUID
        SmartType.UUID: [
            re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"),
        ],
        # Hex colors
        SmartType.COLOR: [
            re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"),
            re.compile(r"^rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)$", re.IGNORECASE),
            re.compile(r"^rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*[\d.]+\s*\)$", re.IGNORECASE),
        ],
        # Hex string (must start with 0x or have even length)
        SmartType.HEX: [
            re.compile(r"^0x[0-9a-fA-F]+$", re.IGNORECASE),
        ],
        # Base64 (must be multiple of 4 and contain only valid chars)
        SmartType.BASE64: [
            re.compile(r"^[A-Za-z0-9+/]{4,}={0,2}$"),
        ],
        # Date patterns
        SmartType.DATE: [
            re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$"),
        ],
        SmartType.TIME: [
            re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$"),
        ],
        SmartType.DATETIME: [
            re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?$"),
        ],
        # JSON
        SmartType.JSON_STRING: [
            re.compile(r"^[\[{].*[\]}]$", re.DOTALL),
        ],
        # File/Folder paths
        SmartType.FILE: [
            re.compile(r"^[A-Za-z]:\\.*\.\w+$"),  # Windows file
            re.compile(r"^/.*\.\w+$"),  # Unix file
        ],
        SmartType.FOLDER: [
            re.compile(r"^[A-Za-z]:\\.*\\?$"),  # Windows folder
            re.compile(r"^/.*/?$"),  # Unix folder
        ],
    }

    @classmethod
    def recognize(cls, value: Any) -> tuple[SmartType, float]:
        """Recognize the smart type of a value.

        Returns:
            Tuple of (SmartType, confidence) where confidence is 0.0-1.0
        """
        if value is None:
            return SmartType.ANY, 0.0

        text = str(value).strip()
        if not text:
            return SmartType.TEXT, 0.5

        # First try heuristic recognition for common patterns
        heuristic_type, heuristic_confidence = cls._heuristic_recognize(text)
        if heuristic_confidence >= 0.8:
            return heuristic_type, heuristic_confidence

        # Then try pattern matchers
        best_match = SmartType.TEXT
        best_confidence = 0.3

        for smart_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if pattern.match(text):
                    confidence = cls._calculate_confidence(smart_type, text)
                    if confidence > best_confidence:
                        best_match = smart_type
                        best_confidence = confidence
                    break

        # Use heuristic if better
        if heuristic_confidence > best_confidence:
            return heuristic_type, heuristic_confidence

        return best_match, best_confidence

    @classmethod
    def _calculate_confidence(cls, smart_type: SmartType, text: str) -> float:
        """Calculate confidence score for a type match."""
        base_confidence = 0.7

        # Higher confidence for specific patterns
        if smart_type == SmartType.EMAIL:
            return 0.95
        if smart_type == SmartType.UUID:
            return 0.95
        if smart_type == SmartType.HTTP_URL:
            return 0.9
        if smart_type == SmartType.IP_ADDRESS:
            # Validate IPv4 octets
            parts = text.split(".")
            if len(parts) == 4:
                try:
                    if all(0 <= int(p) <= 255 for p in parts):
                        return 0.9
                except ValueError as exc:
                    logger.debug("IPv4 片段解析失败: %s", exc, exc_info=True)
            return 0.3  # Low confidence if validation fails
        if smart_type == SmartType.JSON_STRING:
            try:
                json.loads(text)
                return 0.95
            except json.JSONDecodeError:
                return 0.5
        if smart_type == SmartType.BASE64:
            # Lower confidence for short strings that could be hex
            if len(text) < 8 and re.match(r"^[0-9a-fA-F]+$", text):
                return 0.4  # Could be hex
            return 0.8

        return base_confidence

    @classmethod
    def _heuristic_recognize(cls, text: str) -> tuple[SmartType, float]:
        """Heuristic-based type recognition."""
        # Check if it's a number
        try:
            float(text)
            if "." in text:
                return SmartType.FLOAT, 0.8
            return SmartType.INTEGER, 0.8
        except ValueError as exc:
            logger.debug("智能类型数值识别失败: %s", exc, exc_info=True)

        # Check if it's a boolean
        if text.lower() in {"true", "false", "yes", "no", "1", "0", "on", "off"}:
            return SmartType.BOOL, 0.8

        # Check if it's JSON
        if text.startswith(("{", "[")):
            try:
                json.loads(text)
                return SmartType.JSON, 0.85
            except json.JSONDecodeError as exc:
                logger.debug("智能类型 JSON 识别失败: %s", exc, exc_info=True)

        # Check if it looks like a path
        if os.sep in text or "/" in text:
            if any(text.endswith(ext) for ext in [".txt", ".py", ".json", ".xml", ".csv", ".log"]):
                return SmartType.FILE, 0.7
            return SmartType.PATH, 0.6

        return SmartType.TEXT, 0.3


class TypeValidator:
    """Validation functions for different types."""

    @staticmethod
    def validate_integer(value: Any) -> tuple[bool, str]:
        """Validate that value is an integer."""
        try:
            num = float(str(value))
            if num != int(num):
                return False, f"期望整数，但得到小数 {value}"
            return True, ""
        except (ValueError, TypeError):
            return False, f"无法转换为整数: {value}"

    @staticmethod
    def validate_float(value: Any) -> tuple[bool, str]:
        """Validate that value is a float."""
        try:
            float(str(value))
            return True, ""
        except (ValueError, TypeError):
            return False, f"无法转换为数字: {value}"

    @staticmethod
    def validate_positive(value: Any) -> tuple[bool, str]:
        """Validate that value is a positive number."""
        try:
            num = float(str(value))
            if num <= 0:
                return False, f"期望正数，但得到 {value}"
            return True, ""
        except (ValueError, TypeError):
            return False, f"无法转换为数字: {value}"

    @staticmethod
    def validate_negative(value: Any) -> tuple[bool, str]:
        """Validate that value is a negative number."""
        try:
            num = float(str(value))
            if num >= 0:
                return False, f"期望负数，但得到 {value}"
            return True, ""
        except (ValueError, TypeError):
            return False, f"无法转换为数字: {value}"

    @staticmethod
    def validate_non_negative(value: Any) -> tuple[bool, str]:
        """Validate that value is a non-negative number."""
        try:
            num = float(str(value))
            if num < 0:
                return False, f"期望非负数，但得到 {value}"
            return True, ""
        except (ValueError, TypeError):
            return False, f"无法转换为数字: {value}"

    @staticmethod
    def validate_json(value: Any) -> tuple[bool, str]:
        """Validate that value is valid JSON."""
        text = str(value).strip()
        try:
            json.loads(text)
            return True, ""
        except json.JSONDecodeError as e:
            return False, f"无效的JSON格式: {e}"

    @staticmethod
    def validate_json_string(value: Any) -> tuple[bool, str]:
        """Validate that value is a JSON string."""
        return TypeValidator.validate_json(value)

    @staticmethod
    def validate_url(value: Any) -> tuple[bool, str]:
        """Validate that value is a URL."""
        text = str(value).strip()
        if re.match(r"^(https?|ftp|file)://", text, re.IGNORECASE):
            return True, ""
        if re.match(r"^www\.", text, re.IGNORECASE):
            return True, ""
        return False, f"无效的URL格式: {value}"

    @staticmethod
    def validate_http_url(value: Any) -> tuple[bool, str]:
        """Validate that value is an HTTP/HTTPS URL."""
        text = str(value).strip()
        if re.match(r"^https?://", text, re.IGNORECASE):
            return True, ""
        return False, f"无效的HTTP URL格式: {value}"

    @staticmethod
    def validate_ip_address(value: Any) -> tuple[bool, str]:
        """Validate that value is an IP address."""
        text = str(value).strip()

        # IPv4
        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", text):
            parts = text.split(".")
            if all(0 <= int(p) <= 255 for p in parts):
                return True, ""
            return False, f"IPv4地址的每个部分必须在0-255之间: {value}"

        # IPv6 (simplified check)
        if ":" in text and re.match(r"^[0-9a-fA-F:]+$", text):
            return True, ""

        return False, f"无效的IP地址格式: {value}"

    @staticmethod
    def validate_email(value: Any) -> tuple[bool, str]:
        """Validate that value is an email address."""
        text = str(value).strip()
        if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", text):
            return True, ""
        return False, f"无效的邮箱格式: {value}"

    @staticmethod
    def validate_hostname(value: Any) -> tuple[bool, str]:
        """Validate that value is a hostname."""
        text = str(value).strip()
        # Allow localhost, IP addresses, and domain names
        if text == "localhost":
            return True, ""
        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", text):
            return TypeValidator.validate_ip_address(value)
        if re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$", text):
            return True, ""
        return False, f"无效的主机名格式: {value}"

    @staticmethod
    def validate_base64(value: Any) -> tuple[bool, str]:
        """Validate that value is base64 encoded."""
        text = str(value).strip()
        if re.match(r"^[A-Za-z0-9+/]*={0,2}$", text) and len(text) % 4 == 0:
            return True, ""
        return False, f"无效的Base64格式: {value}"

    @staticmethod
    def validate_hex(value: Any) -> tuple[bool, str]:
        """Validate that value is a hex string."""
        text = str(value).strip()
        if text.startswith("0x"):
            text = text[2:]
        if re.match(r"^[0-9a-fA-F]+$", text):
            return True, ""
        return False, f"无效的十六进制格式: {value}"

    @staticmethod
    def validate_uuid(value: Any) -> tuple[bool, str]:
        """Validate that value is a UUID."""
        text = str(value).strip()
        if re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", text):
            return True, ""
        return False, f"无效的UUID格式: {value}"

    @staticmethod
    def validate_date(value: Any) -> tuple[bool, str]:
        """Validate that value is a date."""
        text = str(value).strip()
        if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$", text):
            return True, ""
        return False, f"无效的日期格式: {value}"

    @staticmethod
    def validate_time(value: Any) -> tuple[bool, str]:
        """Validate that value is a time."""
        text = str(value).strip()
        if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", text):
            return True, ""
        return False, f"无效的时间格式: {value}"

    @staticmethod
    def validate_datetime(value: Any) -> tuple[bool, str]:
        """Validate that value is a datetime."""
        text = str(value).strip()
        if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?$", text):
            return True, ""
        return False, f"无效的日期时间格式: {value}"

    @staticmethod
    def validate_color(value: Any) -> tuple[bool, str]:
        """Validate that value is a color."""
        text = str(value).strip()
        if re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$", text):
            return True, ""
        if re.match(r"^rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)$", text, re.IGNORECASE):
            return True, ""
        if re.match(r"^rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*[\d.]+\s*\)$", text, re.IGNORECASE):
            return True, ""
        # Named colors
        named_colors = {
            "red", "green", "blue", "white", "black", "yellow", "cyan", "magenta",
            "orange", "purple", "pink", "gray", "grey", "brown",
        }
        if text.lower() in named_colors:
            return True, ""
        return False, f"无效的颜色格式: {value}"

    @staticmethod
    def validate_regex(value: Any) -> tuple[bool, str]:
        """Validate that value is a valid regex."""
        import re as regex_module
        try:
            regex_module.compile(str(value))
            return True, ""
        except regex_module.error as e:
            return False, f"无效的正则表达式: {e}"

    @staticmethod
    def validate_file_path(value: Any) -> tuple[bool, str]:
        """Validate that value looks like a file path."""
        text = str(value).strip()
        if not text:
            return False, "路径不能为空"
        # Check for file extension
        if os.path.splitext(text)[1]:
            return True, ""
        return False, f"看起来不像文件路径（缺少扩展名）: {value}"

    @staticmethod
    def validate_folder_path(value: Any) -> tuple[bool, str]:
        """Validate that value looks like a folder path."""
        text = str(value).strip()
        if not text:
            return False, "路径不能为空"
        # Check that it doesn't have a file extension
        if not os.path.splitext(text)[1]:
            return True, ""
        return False, f"看起来不像文件夹路径（包含扩展名）: {value}"

    @staticmethod
    def validate_path(value: Any) -> tuple[bool, str]:
        """Validate that value is a path."""
        text = str(value).strip()
        if not text:
            return False, "路径不能为空"
        return True, ""


class TypeConverter:
    """Conversion functions between types."""

    @staticmethod
    def to_integer(value: Any) -> Any:
        """Convert value to integer."""
        try:
            return int(float(str(value)))
        except (ValueError, TypeError):
            return value

    @staticmethod
    def to_float(value: Any) -> Any:
        """Convert value to float."""
        try:
            return float(str(value))
        except (ValueError, TypeError):
            return value

    @staticmethod
    def to_bool(value: Any) -> Any:
        """Convert value to boolean."""
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y", "on", "是", "真", "对", "启用"}:
            return True
        if text in {"false", "0", "no", "n", "off", "否", "假", "错", "禁用", ""}:
            return False
        try:
            return float(text) != 0.0
        except ValueError:
            return bool(value)

    @staticmethod
    def to_string(value: Any) -> str:
        """Convert value to string."""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int | float):
            return str(value)
        if isinstance(value, dict | list):
            return json.dumps(value, ensure_ascii=False)
        return "" if value is None else str(value)

    @staticmethod
    def to_json(value: Any) -> Any:
        """Convert value to JSON-compatible object."""
        if isinstance(value, dict | list):
            return value
        text = str(value).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    @staticmethod
    def to_list(value: Any) -> list:
        """Convert value to list."""
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        text = str(value).strip()
        if not text:
            return []
        # Try JSON parse
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError as exc:
                logger.debug("列表文本 JSON 解析失败，按换行拆分: %s", exc, exc_info=True)
        # Split by newlines
        return [line.strip() for line in text.splitlines() if line.strip()]


# Validator registry
VALIDATORS: dict[str, Callable] = {
    "validate_integer": TypeValidator.validate_integer,
    "validate_float": TypeValidator.validate_float,
    "validate_positive": TypeValidator.validate_positive,
    "validate_negative": TypeValidator.validate_negative,
    "validate_non_negative": TypeValidator.validate_non_negative,
    "validate_json": TypeValidator.validate_json,
    "validate_json_string": TypeValidator.validate_json_string,
    "validate_url": TypeValidator.validate_url,
    "validate_http_url": TypeValidator.validate_http_url,
    "validate_ip_address": TypeValidator.validate_ip_address,
    "validate_email": TypeValidator.validate_email,
    "validate_hostname": TypeValidator.validate_hostname,
    "validate_base64": TypeValidator.validate_base64,
    "validate_hex": TypeValidator.validate_hex,
    "validate_uuid": TypeValidator.validate_uuid,
    "validate_date": TypeValidator.validate_date,
    "validate_time": TypeValidator.validate_time,
    "validate_datetime": TypeValidator.validate_datetime,
    "validate_color": TypeValidator.validate_color,
    "validate_regex": TypeValidator.validate_regex,
    "validate_file_path": TypeValidator.validate_file_path,
    "validate_folder_path": TypeValidator.validate_folder_path,
    "validate_path": TypeValidator.validate_path,
}

# Converter registry
CONVERTERS: dict[str, Callable] = {
    "to_integer": TypeConverter.to_integer,
    "to_float": TypeConverter.to_float,
    "to_bool": TypeConverter.to_bool,
    "to_string": TypeConverter.to_string,
    "to_json": TypeConverter.to_json,
    "to_list": TypeConverter.to_list,
}


def recognize_type(value: Any) -> tuple[SmartType, float]:
    """Recognize the smart type of a value."""
    return SmartTypeRecognizer.recognize(value)


def validate_value(value: Any, smart_type: str | SmartType) -> tuple[bool, str]:
    """Validate a value against a smart type."""
    if isinstance(smart_type, str):
        smart_type = SmartType(smart_type)

    hint = TYPE_HINTS.get(smart_type)
    if hint is None or not hint.validator:
        return True, ""

    validator = VALIDATORS.get(hint.validator)
    if validator is None:
        return True, ""

    return validator(value)


def convert_value(value: Any, target_type: str | SmartType) -> Any:
    """Convert a value to the target type."""
    if isinstance(target_type, str):
        try:
            target_type = SmartType(target_type)
        except ValueError:
            return value

    hint = TYPE_HINTS.get(target_type)
    if hint is None or not hint.converter:
        # Fall back to base type conversion
        return _convert_to_base_type(value, hint.base_type if hint else "text")

    converter = CONVERTERS.get(hint.converter)
    if converter is None:
        return value

    return converter(value)


def _convert_to_base_type(value: Any, base_type: str) -> Any:
    """Convert value to a base type."""
    if base_type == "bool":
        return TypeConverter.to_bool(value)
    if base_type == "number":
        return TypeConverter.to_float(value)
    if base_type == "json":
        return TypeConverter.to_json(value)
    if base_type == "list":
        return TypeConverter.to_list(value)
    return TypeConverter.to_string(value)


def get_type_hint(smart_type: str | SmartType) -> TypeHint | None:
    """Get the type hint for a smart type."""
    if isinstance(smart_type, str):
        try:
            smart_type = SmartType(smart_type)
        except ValueError:
            return None
    return TYPE_HINTS.get(smart_type)


def get_type_description(smart_type: str | SmartType) -> str:
    """Get the description for a smart type."""
    hint = get_type_hint(smart_type)
    return hint.description if hint else str(smart_type)


def get_type_examples(smart_type: str | SmartType) -> list[str]:
    """Get examples for a smart type."""
    hint = get_type_hint(smart_type)
    return hint.examples if hint else []
