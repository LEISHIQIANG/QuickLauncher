"""Unified type conversion system for action chains.

This module provides a centralized type conversion system that handles
all type conversions between ports, including smart type recognition.
"""

from __future__ import annotations

from typing import Any

from .port_types import (
    EnhancedPortDefinition,
    TypeCompatibility,
)
from .smart_types import (
    SmartType,
    TypeConverter,
    convert_value,
    recognize_type,
)

__all__ = [
    "UnifiedTypeConverter",
    "convert_for_port",
    "auto_convert",
    "detect_and_convert",
]


class UnifiedTypeConverter:
    """Unified type conversion system."""

    @staticmethod
    def convert(
        value: Any, source_type: str, target_type: str, source_smart: str = "", target_smart: str = ""
    ) -> tuple[Any, bool, str]:
        """Convert a value from source type to target type.

        Args:
            value: The value to convert
            source_type: Source base type
            target_type: Target base type
            source_smart: Source smart type (optional)
            target_smart: Target smart type (optional)

        Returns:
            Tuple of (converted_value, success, error_message)
        """
        # Same type = no conversion needed
        if source_type == target_type and source_smart == target_smart:
            return value, True, ""

        # Check compatibility
        if not TypeCompatibility.is_compatible(source_type, target_type, source_smart, target_smart):
            return value, False, f"类型不兼容: {source_type} -> {target_type}"

        # Try smart type conversion first
        if target_smart:
            converted = convert_value(value, target_smart)
            if converted is not value:
                return converted, True, ""

        # Fall back to base type conversion
        converted = UnifiedTypeConverter._convert_base(value, source_type, target_type)
        return converted, True, ""

    @staticmethod
    def _convert_base(value: Any, source: str, target: str) -> Any:
        """Convert between base types."""
        # To text
        if target == "text":
            return TypeConverter.to_string(value)

        # To number
        if target == "number":
            return TypeConverter.to_float(value)

        # To bool
        if target == "bool":
            return TypeConverter.to_bool(value)

        # To json
        if target == "json":
            return TypeConverter.to_json(value)

        # To list
        if target == "list":
            return TypeConverter.to_list(value)

        # To file/folder/url (ensure string)
        if target in ("file", "folder", "url"):
            return TypeConverter.to_string(value)

        return value

    @staticmethod
    def auto_convert(value: Any, target_port: EnhancedPortDefinition) -> tuple[Any, bool, str]:
        """Automatically convert a value to match a target port.

        This function will:
        1. Detect the source type using smart recognition
        2. Check compatibility with target
        3. Convert if possible

        Args:
            value: The value to convert
            target_port: The target port definition

        Returns:
            Tuple of (converted_value, success, error_message)
        """
        if value is None:
            if target_port.required:
                return None, False, f"端口 {target_port.id} 是必填的"
            return target_port.default, True, ""

        # Detect source type
        source_smart, confidence = recognize_type(value)
        source_type = _smart_to_base(source_smart)

        # Try to validate as-is
        if target_port.validate(value) == (True, ""):
            return value, True, ""

        # Convert
        return UnifiedTypeConverter.convert(
            value,
            source_type,
            target_port.kind,
            source_smart.value if source_smart else "",
            target_port.smart_type,
        )

    @staticmethod
    def detect_and_convert(value: Any, target_kind: str = "text", target_smart: str = "") -> tuple[Any, str, float]:
        """Detect the type of a value and convert it.

        Args:
            value: The value to process
            target_kind: Target base kind
            target_smart: Target smart type

        Returns:
            Tuple of (converted_value, detected_type, confidence)
        """
        if value is None:
            return None, "any", 0.0

        # Detect type
        detected, confidence = recognize_type(value)

        # Convert to target
        converted, success, _ = UnifiedTypeConverter.convert(
            value,
            _smart_to_base(detected).value,
            target_kind,
            detected.value,
            target_smart,
        )

        if success:
            return converted, detected.value, confidence

        return value, detected.value, confidence


def _smart_to_base(smart_type: SmartType) -> SmartType:
    """Map a smart type to its base type."""
    mapping = {
        SmartType.INTEGER: SmartType.NUMBER,
        SmartType.FLOAT: SmartType.NUMBER,
        SmartType.POSITIVE_NUMBER: SmartType.NUMBER,
        SmartType.NEGATIVE_NUMBER: SmartType.NUMBER,
        SmartType.NON_NEGATIVE_NUMBER: SmartType.NUMBER,
        SmartType.IP_ADDRESS: SmartType.TEXT,
        SmartType.EMAIL: SmartType.TEXT,
        SmartType.HOSTNAME: SmartType.TEXT,
        SmartType.HTTP_URL: SmartType.URL,
        SmartType.JSON_STRING: SmartType.TEXT,
        SmartType.BASE64: SmartType.TEXT,
        SmartType.HEX: SmartType.TEXT,
        SmartType.UUID: SmartType.TEXT,
        SmartType.DATE: SmartType.TEXT,
        SmartType.TIME: SmartType.TEXT,
        SmartType.DATETIME: SmartType.TEXT,
        SmartType.COLOR: SmartType.TEXT,
        SmartType.REGEX: SmartType.TEXT,
        SmartType.FILE: SmartType.FILE,
        SmartType.FOLDER: SmartType.FOLDER,
        SmartType.PATH: SmartType.TEXT,
        SmartType.COMMAND: SmartType.TEXT,
        SmartType.CODE: SmartType.TEXT,
    }
    return mapping.get(smart_type, smart_type)


def convert_for_port(value: Any, port: EnhancedPortDefinition) -> tuple[Any, bool, str]:
    """Convert a value for a specific port.

    This is the main entry point for port-based type conversion.
    """
    return UnifiedTypeConverter.auto_convert(value, port)


def auto_convert(value: Any, target_kind: str, target_smart: str = "") -> Any:
    """Auto-convert a value to a target type.

    Simple wrapper that returns just the converted value.
    """
    converted, success, _ = UnifiedTypeConverter.convert(value, "text", target_kind, "", target_smart)
    return converted if success else value


def detect_and_convert(value: Any, target_kind: str = "text", target_smart: str = "") -> tuple[Any, str]:
    """Detect type and convert.

    Returns:
        Tuple of (converted_value, detected_type)
    """
    converted, detected, _ = UnifiedTypeConverter.detect_and_convert(value, target_kind, target_smart)
    return converted, detected
