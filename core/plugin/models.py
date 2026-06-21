"""Stable plugin manifest and lifecycle DTOs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .constants import PLUGIN_TRUST_LEVELS

logger = logging.getLogger(__name__)


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    entry: str = "main.py"
    icon: str = ""
    keywords: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    trust_level: str = "community-unverified"
    install_source: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        trust = str(data.get("trust_level", "")).lower().replace(" ", "-")
        if trust not in PLUGIN_TRUST_LEVELS:
            trust = "community-unverified"
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            version=str(data.get("version", "")),
            description=str(data.get("description", "")),
            author=str(data.get("author", "")),
            entry=str(data.get("entry", "main.py")),
            icon=str(data.get("icon", "")),
            keywords=list(data.get("keywords", []) or []),
            permissions=list(data.get("permissions", []) or []),
            commands=list(data.get("commands", []) or []),
            trust_level=trust,
            install_source=str(data.get("install_source", "") or "").strip(),
        )


@dataclass
class PluginInfo:
    manifest: PluginManifest
    directory: str
    status: str = "loaded"
    error: str = ""
    registered_commands: list[str] = field(default_factory=list)
    registered_search_sources: list[str] = field(default_factory=list)
    registered_modules: dict[str, str] = field(default_factory=dict)
    registered_chain_processors: list[str] = field(default_factory=list)
    enabled_at: float = 0.0
    last_error_at: float = 0.0
    last_run_at: float = 0.0
    failure_count: int = 0
    last_error_stage: str = ""
    last_error_trace: str = ""
    disabled_reason: str = ""
    quarantined: bool = False


_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "loaded": frozenset({"enabled", "error", "disabled"}),
    "enabled": frozenset({"disabled", "error", "quarantined"}),
    "disabled": frozenset({"enabled", "error", "quarantined"}),
    "error": frozenset({"enabled", "disabled", "quarantined"}),
    "quarantined": frozenset({"disabled"}),
}


def validate_state_transition(info: PluginInfo, target_status: str) -> bool:
    if target_status == "quarantined" and info.status == "quarantined":
        return False
    if target_status == "quarantined":
        return True
    allowed = _VALID_TRANSITIONS.get(info.status, frozenset())
    if target_status not in allowed:
        logger.warning(
            "Invalid plugin state transition: %s -> %s (plugin=%s)",
            info.status,
            target_status,
            info.manifest.id,
        )
        return False
    return True
