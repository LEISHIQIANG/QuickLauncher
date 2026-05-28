"""Command output decoding and truncation helpers."""

from __future__ import annotations

import ctypes
import locale
import os

from core.runtime_constants import normalize_command_output_max_chars


def decode_command_output(data: bytes | str, preferred: str = "auto") -> tuple[str, str, bool]:
    """Decode command output while reporting the selected encoding and fallback use."""
    if isinstance(data, str):
        return data, "text", False
    data = data or b""
    candidates: list[str] = []
    preferred = str(preferred or "auto").lower().strip()
    if preferred and preferred != "auto":
        candidates.append(preferred)
    candidates.append("utf-8")
    if os.name == "nt":
        try:
            oem_cp = ctypes.windll.kernel32.GetOEMCP()
            if oem_cp:
                candidates.append(f"cp{oem_cp}")
        except Exception:
            pass
    try:
        pref = locale.getpreferredencoding(False)
        if pref:
            candidates.append(pref)
    except Exception:
        pass
    candidates.extend(["mbcs", "gbk"])

    seen = set()
    ordered = []
    for enc in candidates:
        key = enc.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(enc)

    for idx, enc in enumerate(ordered):
        try:
            return data.decode(enc), enc, idx > 0
        except Exception:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8", True


def truncate_command_output(text: str, max_chars: int) -> tuple[str, bool]:
    text = text or ""
    max_chars = normalize_command_output_max_chars(max_chars)
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "\n\n[输出过长，已截断]", True
