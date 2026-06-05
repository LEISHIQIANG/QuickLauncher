"""Typed value helpers for action-chain runtime snapshots.

The current chain executor still keeps the legacy string lookup table for
compatibility. These helpers add a small typed layer beside it so UI/debugging
can show whether a value is text, JSON, a list, a file path, and so on.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ChainValueKind:
    ANY = "any"
    TEXT = "text"
    JSON = "json"
    LIST = "list"
    FILE = "file"
    FOLDER = "folder"
    URL = "url"
    NUMBER = "number"
    BOOL = "bool"


KNOWN_KINDS = {
    ChainValueKind.ANY,
    ChainValueKind.TEXT,
    ChainValueKind.JSON,
    ChainValueKind.LIST,
    ChainValueKind.FILE,
    ChainValueKind.FOLDER,
    ChainValueKind.URL,
    ChainValueKind.NUMBER,
    ChainValueKind.BOOL,
}


@dataclass(frozen=True)
class ChainValue:
    kind: str
    value: Any
    text: str
    preview: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": _json_safe(self.value),
            "text": self.text,
            "preview": self.preview,
            "metadata": dict(self.metadata),
        }


def make_chain_value(value: Any, kind: str = ChainValueKind.ANY, *, metadata: dict[str, Any] | None = None) -> ChainValue:
    normalized_kind = _normalize_kind(kind)
    coerced = _coerce_value(value, normalized_kind)
    text = value_to_text(coerced)
    if normalized_kind == ChainValueKind.ANY:
        normalized_kind = infer_kind(coerced)
    return ChainValue(
        kind=normalized_kind,
        value=coerced,
        text=text,
        preview=preview_text(coerced, normalized_kind),
        metadata=dict(metadata or {}),
    )


def chain_value_to_dict(value: Any, kind: str = ChainValueKind.ANY) -> dict[str, Any]:
    if isinstance(value, ChainValue):
        return value.to_dict()
    if isinstance(value, dict) and {"kind", "text", "preview"}.issubset(value.keys()):
        return dict(value)
    return make_chain_value(value, kind).to_dict()


def typed_mapping(values: dict[str, Any], port_kinds: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
    kinds = dict(port_kinds or {})
    return {str(key): make_chain_value(value, kinds.get(str(key), ChainValueKind.ANY)).to_dict() for key, value in dict(values or {}).items()}


def value_to_text(value: Any) -> str:
    if isinstance(value, ChainValue):
        return value.text
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "\n".join(value_to_text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "" if value is None else str(value)


def preview_text(value: Any, kind: str = ChainValueKind.ANY, *, limit: int = 800) -> str:
    if isinstance(value, ChainValue):
        text = value.preview or value.text
    elif kind == ChainValueKind.LIST and isinstance(value, list):
        text = f"{len(value)} items"
        if value:
            text += ": " + ", ".join(value_to_text(item) for item in value[:5])
    elif kind == ChainValueKind.JSON and isinstance(value, dict | list):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = value_to_text(value)
    text = text.replace("\r\n", "\n")
    if len(text) > limit:
        return text[:limit] + f"... ({len(text)} chars)"
    return text


def infer_kind(value: Any) -> str:
    if isinstance(value, ChainValue):
        return value.kind
    if isinstance(value, bool):
        return ChainValueKind.BOOL
    if isinstance(value, int | float) and not isinstance(value, bool):
        return ChainValueKind.NUMBER
    if isinstance(value, list):
        return ChainValueKind.LIST
    if isinstance(value, dict):
        return ChainValueKind.JSON
    return ChainValueKind.TEXT


def raw_value(value: Any) -> Any:
    if isinstance(value, ChainValue):
        return value.value
    if isinstance(value, dict) and {"kind", "value"}.issubset(value.keys()):
        return value.get("value")
    return value


def _normalize_kind(kind: str) -> str:
    value = str(kind or ChainValueKind.ANY).lower().strip()
    return value if value in KNOWN_KINDS else ChainValueKind.ANY


def _coerce_value(value: Any, kind: str) -> Any:
    if isinstance(value, ChainValue):
        value = value.value
    if kind == ChainValueKind.BOOL:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "on", "y", "t", "是", "真"}
    if kind == ChainValueKind.NUMBER:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return value
        text = str(value or "").strip()
        try:
            number = float(text)
        except (TypeError, ValueError):
            return text
        return int(number) if number.is_integer() else number
    if kind == ChainValueKind.JSON:
        if isinstance(value, dict | list):
            return value
        text = str(value or "").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return text
    if kind == ChainValueKind.LIST:
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        text = str(value or "").strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return parsed
            except Exception as exc:
                logger.debug("解析列表 JSON 失败，回退为按行解析: %s", exc, exc_info=True)
        return [line for line in text.splitlines() if line]
    if kind == ChainValueKind.FILE:
        return _coerce_to_path(value)
    if kind == ChainValueKind.FOLDER:
        return _coerce_to_path(value)
    if kind == ChainValueKind.URL:
        return _coerce_to_url(value)
    return "" if value is None else value


def _coerce_to_path(value: Any) -> str:
    """Coerce a value to a file/folder path string."""
    import os
    if isinstance(value, ChainValue):
        value = value.value
    if isinstance(value, str):
        path = value.strip().strip('"')
        return os.path.normpath(path) if path else ""
    if isinstance(value, Path):
        return str(value)
    return str(value or "").strip()


def _coerce_to_url(value: Any) -> str:
    """Coerce a value to a URL string."""
    if isinstance(value, ChainValue):
        value = value.value
    if isinstance(value, str):
        return value.strip()
    return str(value or "").strip()


def _json_safe(value: Any) -> Any:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)
