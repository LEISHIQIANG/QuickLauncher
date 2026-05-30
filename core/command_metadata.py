"""Command risk and capability metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CommandMetadata:
    category: str = ""
    risk_level: str = "low"
    requires_admin: bool = False
    uses_network: bool = False
    modifies_system: bool = False
    requires_confirmation: bool = False

    @classmethod
    def from_value(cls, value: CommandMetadata | dict | None, *, category: str = "") -> CommandMetadata:
        if isinstance(value, CommandMetadata):
            metadata = value
        elif isinstance(value, dict):
            metadata = cls(
                category=str(value.get("category") or ""),
                risk_level=str(value.get("risk_level") or "low"),
                requires_admin=bool(value.get("requires_admin", False)),
                uses_network=bool(value.get("uses_network", False)),
                modifies_system=bool(value.get("modifies_system", False)),
                requires_confirmation=bool(value.get("requires_confirmation", False)),
            )
        else:
            metadata = cls()
        if not metadata.category:
            metadata.category = category
        if metadata.risk_level not in {"low", "medium", "high", "critical"}:
            metadata.risk_level = "low"
        return metadata

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "risk_level": self.risk_level,
            "requires_admin": self.requires_admin,
            "uses_network": self.uses_network,
            "modifies_system": self.modifies_system,
            "requires_confirmation": self.requires_confirmation,
        }


_BUILTIN_METADATA_OVERRIDES: dict[str, dict[str, Any]] = {
    "ip": {"uses_network": True},
    "netdiag": {"uses_network": True},
    "tls": {"uses_network": True},
    "dns": {"uses_network": True, "modifies_system": True, "risk_level": "medium"},
    "hosts": {"requires_admin": True, "modifies_system": True, "risk_level": "medium"},
    "process": {"modifies_system": True, "risk_level": "medium"},
    "sysreport": {"risk_level": "medium"},
    "plugin-reload": {"modifies_system": True, "risk_level": "medium"},
    "plugin-new": {"modifies_system": True},
    "clean-cache": {"modifies_system": True, "risk_level": "medium"},
    "config-repair": {"modifies_system": True, "risk_level": "medium"},
    "explorer": {"modifies_system": True, "risk_level": "medium"},
    "git": {"uses_network": True, "modifies_system": True, "risk_level": "medium"},
}


def builtin_command_metadata(command_id: str, category: str = "") -> CommandMetadata:
    values = {"category": category}
    values.update(_BUILTIN_METADATA_OVERRIDES.get(command_id, {}))
    return CommandMetadata.from_value(values, category=category)
