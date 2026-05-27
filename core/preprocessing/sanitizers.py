"""Input sanitization functions."""

from __future__ import annotations

_MAX_SIZE_BYTES = 1 * 1024 * 1024


def sanitize_null_bytes(value: str) -> str:
    """Remove null bytes from string."""
    return value.replace("\0", "") if value else ""


def sanitize_control_chars(value: str) -> str:
    """Remove dangerous control characters."""
    if not value:
        return ""
    return "".join(c for c in value if c == "\n" or c == "\r" or c == "\t" or ord(c) >= 32)


def enforce_size_limit(value: str, max_bytes: int = _MAX_SIZE_BYTES) -> str:
    """Truncate string to size limit."""
    if not value:
        return ""
    encoded = value.encode("utf-8", errors="surrogateescape")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="replace")


def normalize_encoding(value: str) -> str:
    """Ensure UTF-8 encoding."""
    if not value:
        return ""
    try:
        return value.encode("utf-8", errors="replace").decode("utf-8")
    except Exception:
        return value


def sanitize_input(value: str, max_bytes: int = _MAX_SIZE_BYTES) -> str:
    """Apply all sanitization steps."""
    value = sanitize_null_bytes(value)
    value = enforce_size_limit(value, max_bytes)
    value = normalize_encoding(value)
    return value
