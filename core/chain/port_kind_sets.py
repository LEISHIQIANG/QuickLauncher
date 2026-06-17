"""Canonical port-kind output sets shared across the chain registry.

The ``TEXT_OUTPUTS`` / ``BOOL_OUTPUTS`` / … collections used to be
duplicated between ``core/chain/registry.py``,
``core/chain/enhanced_definitions.py`` and
``core/chain/extended_definitions.py``.  The duplication made it
tricky to keep the per-processor schema in sync: adding a new port
required touching three files, and the lists occasionally drifted.

This module is the single source of truth.  The three historical
modules keep the same public names by re-exporting the constants
from here, so external callers (``from core.chain.registry import
TEXT_OUTPUTS``) keep working unchanged.
"""

from __future__ import annotations

from core.chain.definitions import ChainPortDefinition

__all__ = [
    "TEXT_OUTPUTS",
    "BOOL_OUTPUTS",
    "LIST_OUTPUTS",
    "NUMBER_OUTPUTS",
    "FILE_OUTPUTS",
    "FOLDER_OUTPUTS",
    "JSON_OUTPUTS",
    "ANY_OUTPUTS",
    "HTTP_OUTPUTS",
]


# ── string-keyed port sets (the historical shape) ────────────────
TEXT_OUTPUTS = ["output", "length", "empty"]
BOOL_OUTPUTS = ["output", "not"]
LIST_OUTPUTS = ["output", "count", "first", "last", "items_json"]
NUMBER_OUTPUTS = ["output"]
FILE_OUTPUTS = ["output", "path", "folder", "filename", "exists"]
FOLDER_OUTPUTS = ["output", "path", "exists"]
JSON_OUTPUTS = ["output"]
HTTP_OUTPUTS = ["output", "status_code", "headers", "length", "empty"]


# ── structured-keyed port sets (used by the core registry) ────────
ANY_OUTPUTS = [ChainPortDefinition("output", label="输出", kind="any", description="任意类型输出。", role="primary")]
