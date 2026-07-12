"""Tests for core.command_metadata module."""

from core.command_metadata import (
    _BUILTIN_METADATA_OVERRIDES,
    CommandMetadata,
    builtin_command_metadata,
)


def test_default_construction():
    meta = CommandMetadata()
    assert meta.category == ""
    assert meta.risk_level == "low"
    assert meta.requires_admin is False
    assert meta.uses_network is False
    assert meta.modifies_system is False
    assert meta.requires_confirmation is False


def test_construction_with_values():
    meta = CommandMetadata(
        category="sys",
        risk_level="high",
        requires_admin=True,
        uses_network=True,
        modifies_system=True,
        requires_confirmation=True,
    )
    assert meta.category == "sys"
    assert meta.risk_level == "high"
    assert meta.requires_admin is True
    assert meta.uses_network is True
    assert meta.modifies_system is True
    assert meta.requires_confirmation is True


def test_from_value_with_instance():
    original = CommandMetadata(category="net", risk_level="medium", uses_network=True)
    result = CommandMetadata.from_value(original, category="fallback")
    assert result is original
    assert result.category == "net"
    assert result.risk_level == "medium"


def test_from_value_with_dict():
    data = {
        "category": "sys",
        "risk_level": "high",
        "requires_admin": True,
        "uses_network": False,
        "modifies_system": True,
        "requires_confirmation": True,
    }
    result = CommandMetadata.from_value(data, category="fallback")
    assert result.category == "sys"
    assert result.risk_level == "high"
    assert result.requires_admin is True
    assert result.uses_network is False
    assert result.modifies_system is True
    assert result.requires_confirmation is True


def test_from_value_with_dict_missing_category_uses_fallback():
    data = {"risk_level": "medium"}
    result = CommandMetadata.from_value(data, category="fallback_cat")
    assert result.category == "fallback_cat"
    assert result.risk_level == "medium"


def test_from_value_with_none():
    result = CommandMetadata.from_value(None, category="cat")
    assert result.category == "cat"
    assert result.risk_level == "low"
    assert result.requires_admin is False


def test_from_value_with_invalid_risk_level():
    data = {"risk_level": "extreme"}
    result = CommandMetadata.from_value(data)
    assert result.risk_level == "low"


def test_from_value_with_empty_dict():
    result = CommandMetadata.from_value({}, category="cat")
    assert result.category == "cat"
    assert result.risk_level == "low"


def test_from_value_all_risk_levels():
    for level in ("low", "medium", "high", "critical"):
        result = CommandMetadata.from_value({"risk_level": level})
        assert result.risk_level == level


def test_from_value_preserves_instance_category_when_non_empty():
    original = CommandMetadata(category="existing")
    result = CommandMetadata.from_value(original, category="override")
    assert result.category == "existing"


def test_from_value_empty_category_on_instance_gets_fallback():
    original = CommandMetadata(category="")
    result = CommandMetadata.from_value(original, category="fallback")
    assert result.category == "fallback"


def test_to_dict():
    meta = CommandMetadata(
        category="net",
        risk_level="medium",
        requires_admin=True,
        uses_network=True,
        modifies_system=False,
        requires_confirmation=True,
    )
    d = meta.to_dict()
    assert d == {
        "category": "net",
        "risk_level": "medium",
        "requires_admin": True,
        "uses_network": True,
        "modifies_system": False,
        "requires_confirmation": True,
    }


def test_to_dict_default_values():
    meta = CommandMetadata()
    d = meta.to_dict()
    assert d["category"] == ""
    assert d["risk_level"] == "low"
    assert d["requires_admin"] is False
    assert d["uses_network"] is False
    assert d["modifies_system"] is False
    assert d["requires_confirmation"] is False


def test_builtin_command_metadata_known_id():
    meta = builtin_command_metadata("ip", category="net")
    assert meta.category == "net"
    assert meta.uses_network is True
    assert meta.risk_level == "low"


def test_builtin_command_metadata_dns():
    meta = builtin_command_metadata("dns", category="net")
    assert meta.uses_network is True
    assert meta.modifies_system is True
    assert meta.risk_level == "medium"


def test_builtin_command_metadata_hosts():
    meta = builtin_command_metadata("hosts", category="sys")
    assert meta.requires_admin is True
    assert meta.modifies_system is True
    assert meta.risk_level == "medium"


def test_builtin_command_metadata_unknown_id():
    meta = builtin_command_metadata("nonexistent", category="custom")
    assert meta.category == "custom"
    assert meta.risk_level == "low"
    assert meta.requires_admin is False
    assert meta.uses_network is False
    assert meta.modifies_system is False


def test_builtin_command_metadata_all_overrides_covered():
    for cmd_id, overrides in _BUILTIN_METADATA_OVERRIDES.items():
        meta = builtin_command_metadata(cmd_id, category="test_cat")
        assert meta.category == "test_cat"
        for key, expected_val in overrides.items():
            assert getattr(meta, key) == expected_val, f"{cmd_id}.{key} mismatch"


def test_builtin_command_metadata_empty_id():
    meta = builtin_command_metadata("", category="cat")
    assert meta.category == "cat"
    assert meta.risk_level == "low"
