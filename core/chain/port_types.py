"""Enhanced port type system with smart recognition.

This module provides an enhanced port type system that integrates with
the smart type recognition system for better type handling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .smart_types import (
    SmartType,
    TypeHint,
    TYPE_HINTS,
    recognize_type,
    validate_value,
    convert_value,
    get_type_hint,
)

__all__ = [
    "PortType",
    "EnhancedPortDefinition",
    "TypeCompatibility",
    "get_compatibility",
    "can_connect",
    "get_conversion_cost",
]


@dataclass(frozen=True)
class PortType:
    """Enhanced port type with smart type support."""

    base_kind: str  # Original ChainValueKind
    smart_type: str = ""  # SmartType enum value
    required: bool = False
    multiple: bool = False
    default: str = ""
    description: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_kind": self.base_kind,
            "smart_type": self.smart_type,
            "required": self.required,
            "multiple": self.multiple,
            "default": self.default,
            "description": self.description,
            "constraints": dict(self.constraints or {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PortType:
        return cls(
            base_kind=str(data.get("base_kind") or "text"),
            smart_type=str(data.get("smart_type") or ""),
            required=bool(data.get("required", False)),
            multiple=bool(data.get("multiple", False)),
            default=str(data.get("default") or ""),
            description=str(data.get("description") or ""),
            constraints=dict(data.get("constraints") or {}),
        )


@dataclass(frozen=True)
class EnhancedPortDefinition:
    """Enhanced port definition with smart type support."""

    id: str
    label: str = ""
    kind: str = "text"  # Base kind (backward compatible)
    smart_type: str = ""  # Smart type (new)
    required: bool = False
    multiple: bool = False
    default: str = ""
    description: str = ""
    role: str = "data"
    constraints: dict[str, Any] = field(default_factory=dict)
    validation_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "smart_type": self.smart_type,
            "required": self.required,
            "multiple": self.multiple,
            "default": self.default,
            "description": self.description,
            "role": self.role,
            "constraints": dict(self.constraints or {}),
            "validation_rules": list(self.validation_rules or []),
        }

    @property
    def effective_type(self) -> str:
        """Get the effective type (smart_type if available, else kind)."""
        return self.smart_type if self.smart_type else self.kind

    @property
    def type_hint(self) -> TypeHint | None:
        """Get the type hint for this port."""
        if self.smart_type:
            return get_type_hint(self.smart_type)
        return None

    def validate(self, value: Any) -> tuple[bool, str]:
        """Validate a value against this port definition."""
        # Check required
        if self.required and (value is None or str(value).strip() == ""):
            return False, f"端口 {self.id} 是必填的"

        # If smart type is set, use smart validation
        if self.smart_type:
            valid, msg = validate_value(value, self.smart_type)
            if not valid:
                return valid, msg

        # Apply custom constraints
        if self.constraints:
            valid, msg = self._check_constraints(value)
            if not valid:
                return valid, msg

        return True, ""

    def _check_constraints(self, value: Any) -> tuple[bool, str]:
        """Check custom constraints."""
        constraints = self.constraints

        # Min/max for numbers
        if "min" in constraints or "max" in constraints:
            try:
                num = float(str(value))
                if "min" in constraints:
                    min_val = float(constraints["min"])
                    exclusive = constraints.get("exclusive_min", False)
                    if exclusive and num <= min_val:
                        return False, f"值必须大于 {min_val}"
                    elif not exclusive and num < min_val:
                        return False, f"值必须大于等于 {min_val}"
                if "max" in constraints:
                    max_val = float(constraints["max"])
                    exclusive = constraints.get("exclusive_max", False)
                    if exclusive and num >= max_val:
                        return False, f"值必须小于 {max_val}"
                    elif not exclusive and num > max_val:
                        return False, f"值必须小于等于 {max_val}"
            except (ValueError, TypeError):
                pass

        # Min/max length for strings
        if "min_length" in constraints or "max_length" in constraints:
            text = str(value)
            if "min_length" in constraints and len(text) < int(constraints["min_length"]):
                return False, f"长度不能少于 {constraints['min_length']} 个字符"
            if "max_length" in constraints and len(text) > int(constraints["max_length"]):
                return False, f"长度不能超过 {constraints['max_length']} 个字符"

        # Pattern matching
        if "pattern" in constraints:
            import re
            if not re.match(str(constraints["pattern"]), str(value)):
                return False, f"格式不匹配: {constraints.get('pattern_message', constraints['pattern'])}"

        # Enum values
        if "enum" in constraints:
            allowed = constraints["enum"]
            if str(value) not in allowed:
                return False, f"值必须是以下之一: {', '.join(str(v) for v in allowed)}"

        return True, ""

    def convert(self, value: Any) -> Any:
        """Convert a value to this port's type."""
        if self.smart_type:
            return convert_value(value, self.smart_type)
        return value


class TypeCompatibility:
    """Type compatibility checker with smart type support."""

    # Base compatibility matrix (same as chain_contracts.py)
    BASE_COMPATIBILITY = {
        "any": {"any", "text", "json", "file", "folder", "url", "list", "number", "bool"},
        "text": {"any", "text"},
        "json": {"any", "json", "text"},
        "file": {"any", "file", "text"},
        "folder": {"any", "folder", "text"},
        "url": {"any", "url", "text"},
        "list": {"any", "list", "text"},
        "number": {"any", "number", "text"},
        "bool": {"any", "bool", "text"},
    }

    # Smart type compatibility (extends base)
    SMART_COMPATIBILITY = {
        SmartType.INTEGER: {SmartType.NUMBER, SmartType.FLOAT, SmartType.TEXT},
        SmartType.FLOAT: {SmartType.NUMBER, SmartType.INTEGER, SmartType.TEXT},
        SmartType.POSITIVE_NUMBER: {SmartType.NUMBER, SmartType.FLOAT, SmartType.NON_NEGATIVE_NUMBER, SmartType.TEXT},
        SmartType.NEGATIVE_NUMBER: {SmartType.NUMBER, SmartType.FLOAT, SmartType.TEXT},
        SmartType.NON_NEGATIVE_NUMBER: {SmartType.NUMBER, SmartType.FLOAT, SmartType.POSITIVE_NUMBER, SmartType.TEXT},
        SmartType.IP_ADDRESS: {SmartType.TEXT, SmartType.HOSTNAME},
        SmartType.EMAIL: {SmartType.TEXT},
        SmartType.HOSTNAME: {SmartType.TEXT, SmartType.IP_ADDRESS},
        SmartType.HTTP_URL: {SmartType.URL, SmartType.TEXT},
        SmartType.JSON_STRING: {SmartType.TEXT, SmartType.JSON},
        SmartType.BASE64: {SmartType.TEXT},
        SmartType.HEX: {SmartType.TEXT},
        SmartType.UUID: {SmartType.TEXT},
        SmartType.DATE: {SmartType.TEXT},
        SmartType.TIME: {SmartType.TEXT},
        SmartType.DATETIME: {SmartType.TEXT, SmartType.DATE, SmartType.TIME},
        SmartType.COLOR: {SmartType.TEXT},
        SmartType.REGEX: {SmartType.TEXT},
        SmartType.FILE: {SmartType.PATH, SmartType.TEXT},
        SmartType.FOLDER: {SmartType.PATH, SmartType.TEXT},
        SmartType.PATH: {SmartType.FILE, SmartType.FOLDER, SmartType.TEXT},
    }

    @classmethod
    def is_compatible(cls, source_kind: str, target_kind: str,
                      source_smart: str = "", target_smart: str = "") -> bool:
        """Check if source type is compatible with target type.

        Args:
            source_kind: Source base kind
            target_kind: Target base kind
            source_smart: Source smart type (optional)
            target_smart: Target smart type (optional)

        Returns:
            True if compatible
        """
        # Check base compatibility first
        if cls._check_base_compatible(source_kind, target_kind):
            return True

        # If both have smart types, check smart compatibility
        if source_smart and target_smart:
            return cls._check_smart_compatible(source_smart, target_smart)

        # If only source has smart type, check if it's compatible with target base
        if source_smart:
            return cls._check_smart_to_base_compatible(source_smart, target_kind)

        # If only target has smart type, check if source base is compatible
        if target_smart:
            return cls._check_base_to_smart_compatible(source_kind, target_smart)

        return False

    @classmethod
    def _check_base_compatible(cls, source: str, target: str) -> bool:
        """Check base type compatibility."""
        source = str(source or "text").lower()
        target = str(target or "text").lower()

        if source == target:
            return True

        compatible = cls.BASE_COMPATIBILITY.get(source, set())
        return target in compatible

    @classmethod
    def _check_smart_compatible(cls, source: str, target: str) -> bool:
        """Check smart type compatibility."""
        try:
            source_type = SmartType(source)
            target_type = SmartType(target)
        except ValueError:
            return False

        # Same type
        if source_type == target_type:
            return True

        # Check smart compatibility
        compatible = cls.SMART_COMPATIBILITY.get(source_type, set())
        if target_type in compatible:
            return True

        # Check reverse compatibility
        compatible = cls.SMART_COMPATIBILITY.get(target_type, set())
        if source_type in compatible:
            return True

        return False

    @classmethod
    def _check_smart_to_base_compatible(cls, smart_type: str, base_kind: str) -> bool:
        """Check if smart type is compatible with base kind."""
        hint = get_type_hint(smart_type)
        if hint is None:
            return False

        # Check if the smart type's base is compatible
        return cls._check_base_compatible(hint.base_type, base_kind)

    @classmethod
    def _check_base_to_smart_compatible(cls, base_kind: str, smart_type: str) -> bool:
        """Check if base kind is compatible with smart type."""
        hint = get_type_hint(smart_type)
        if hint is None:
            return False

        # Check if the base kind is compatible with the smart type's base
        return cls._check_base_compatible(base_kind, hint.base_type)

    @classmethod
    def get_conversion_cost(cls, source_kind: str, target_kind: str,
                            source_smart: str = "", target_smart: str = "") -> int:
        """Get the cost of converting from source to target type.

        Returns:
            Cost value (0 = free, 1 = cheap, 2 = moderate, 3 = expensive, -1 = impossible)
        """
        # Same type = free
        if source_kind == target_kind and source_smart == target_smart:
            return 0

        # any = free
        if source_kind == "any" or target_kind == "any":
            return 0

        # Check compatibility
        if not cls.is_compatible(source_kind, target_kind, source_smart, target_smart):
            return -1

        # text to anything = cheap
        if source_kind == "text":
            return 1

        # anything to text = cheap
        if target_kind == "text":
            return 1

        # Same base type, different smart type = cheap
        if source_kind == target_kind:
            return 1

        # Cross-type conversions
        costs = {
            ("number", "bool"): 1,
            ("bool", "number"): 1,
            ("json", "list"): 1,
            ("list", "json"): 1,
            ("file", "folder"): 2,
            ("folder", "file"): 2,
        }

        return costs.get((source_kind, target_kind), 2)


def get_compatibility(source: EnhancedPortDefinition, target: EnhancedPortDefinition) -> dict[str, Any]:
    """Get detailed compatibility information between two ports."""
    compatible = TypeCompatibility.is_compatible(
        source.kind, target.kind,
        source.smart_type, target.smart_type,
    )
    cost = TypeCompatibility.get_conversion_cost(
        source.kind, target.kind,
        source.smart_type, target.smart_type,
    )

    return {
        "compatible": compatible,
        "cost": cost,
        "source_type": source.effective_type,
        "target_type": target.effective_type,
        "needs_conversion": cost > 0,
        "message": _get_compatibility_message(compatible, cost, source, target),
    }


def can_connect(source: EnhancedPortDefinition, target: EnhancedPortDefinition) -> bool:
    """Check if two ports can be connected."""
    return TypeCompatibility.is_compatible(
        source.kind, target.kind,
        source.smart_type, target.smart_type,
    )


def get_conversion_cost(source: EnhancedPortDefinition, target: EnhancedPortDefinition) -> int:
    """Get the cost of converting between two ports."""
    return TypeCompatibility.get_conversion_cost(
        source.kind, target.kind,
        source.smart_type, target.smart_type,
    )


def _get_compatibility_message(compatible: bool, cost: int,
                               source: EnhancedPortDefinition,
                               target: EnhancedPortDefinition) -> str:
    """Get a human-readable compatibility message."""
    if not compatible:
        return f"类型不兼容: {source.effective_type} -> {target.effective_type}"

    if cost == 0:
        return "类型完全匹配"

    if cost == 1:
        return f"可以自动转换: {source.effective_type} -> {target.effective_type}"

    if cost == 2:
        return f"需要类型转换: {source.effective_type} -> {target.effective_type}"

    return f"复杂转换: {source.effective_type} -> {target.effective_type}"
