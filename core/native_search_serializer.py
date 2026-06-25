"""Binary serializer for QLsearch.dll's ``QLsearch_loadAll`` protocol (v2).

The DLL computes all variants (NFKC, compact, tokens, acronym, pinyin)
internally.  Python only packs raw field values.
"""

from __future__ import annotations

import logging
import struct
from collections.abc import Sequence

logger = logging.getLogger(__name__)

_PACK_I32 = struct.Struct("<i").pack
_PACK_I64 = struct.Struct("<q").pack
_PACK_F64 = struct.Struct("<d").pack

_WEIGHTS = (120.0, 110.0, 95.0, 55.0, 50.0, 45.0, 35.0)


def _pack_string(s: str) -> bytes:
    b = s.encode("utf-8")
    return _PACK_I32(len(b)) + b


def _text(value) -> str:
    return str(value or "").strip()


def _field_values(shortcut) -> list[str]:
    tags = " ".join(_text(tag) for tag in getattr(shortcut, "tags", []) if _text(tag))
    return [
        _text(getattr(shortcut, "name", "")),
        _text(getattr(shortcut, "alias", "")),
        tags,
        _text(getattr(shortcut, "target_path", "")),
        _text(getattr(shortcut, "url", "")),
        _text(getattr(shortcut, "command", "")),
        _text(getattr(shortcut, "hotkey", "")),
    ]


def serialize_search_data(
    folders: Sequence[object],
) -> tuple[bytes, dict[int, object], dict[int, object]]:
    """Build the v2 binary buffer.

    Layout (little-endian):
      int32 folder_count
      for each folder: int32 id, string name
      int32 shortcut_count
      for each shortcut:
        int32 id / int32 folder_id / int32 enabled / int32 order /
        int32 smart_order / int32 use_count / int64 last_used_at /
        string shortcut_id_str
        for field 0..6: float64 weight, string raw_value
    """
    buf = bytearray()

    folder_map: dict[int, object] = {}

    buf += _PACK_I32(len(folders))
    for fid, folder in enumerate(folders):
        folder_map[fid] = folder
        buf += _PACK_I32(fid)
        buf += _pack_string(_text(getattr(folder, "name", "")))

    shortcut_map: dict[int, object] = {}
    all_shortcuts: list[tuple[object, int]] = []

    next_sid = 0
    for fid, folder in enumerate(folders):
        raw_items = getattr(folder, "items", ()) or ()
        for sc in raw_items:
            shortcut_map[next_sid] = sc
            all_shortcuts.append((sc, fid))
            next_sid += 1

    buf += _PACK_I32(len(all_shortcuts))
    for sid, (sc, fid) in enumerate(all_shortcuts):
        enabled = 1
        if hasattr(sc, "is_enabled") and not sc.is_enabled():
            enabled = 0
        elif not getattr(sc, "enabled", True):
            enabled = 0

        order_val = getattr(sc, "order", None)
        order_val = int(order_val) if order_val is not None else 0
        smart_order = getattr(sc, "smart_order", None)
        smart_order = int(smart_order) if smart_order is not None else -1
        use_count = getattr(sc, "use_count", None)
        use_count = int(use_count) if use_count is not None else 0
        last_used_at = getattr(sc, "last_used_at", None)
        last_used_at = int(last_used_at) if last_used_at is not None else 0
        sid_str = _text(getattr(sc, "id", ""))

        buf += _PACK_I32(sid)
        buf += _PACK_I32(fid)
        buf += _PACK_I32(enabled)
        buf += _PACK_I32(order_val)
        buf += _PACK_I32(smart_order)
        buf += _PACK_I32(use_count)
        buf += _PACK_I64(last_used_at)
        buf += _pack_string(sid_str)

        field_vals = _field_values(sc)
        for i, fv in enumerate(field_vals):
            buf += _PACK_F64(_WEIGHTS[i])
            buf += _pack_string(fv)

    return bytes(buf), folder_map, shortcut_map
