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
    # Truncate at character boundary to avoid breaking multibyte chars
    truncated = encoded[:max_bytes]
    # Back up to find a valid UTF-8 character boundary (at most 3 bytes)
    end = len(truncated)
    # Step 1: back up past continuation bytes (10xxxxxx)
    while end > 0 and (truncated[end - 1] & 0xC0) == 0x80:
        end -= 1
    # Step 2: if the lead byte starts a multi-byte sequence that was
    # truncated, skip it too
    if end > 0:
        lead = truncated[end - 1]
        if (lead & 0x80) != 0:
            # Determine expected byte count from lead byte
            if (lead & 0xE0) == 0xC0:
                expected = 2
            elif (lead & 0xF0) == 0xE0:
                expected = 3
            elif (lead & 0xF8) == 0xF0:
                expected = 4
            else:
                expected = 1
            # If the full character doesn't fit, skip the lead byte
            if end - 1 + expected > max_bytes:
                end -= 1
    if end == 0:
        return ""
    return truncated[:end].decode("utf-8", errors="strict")


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
    value = sanitize_control_chars(value)
    value = enforce_size_limit(value, max_bytes)
    value = normalize_encoding(value)
    return value
