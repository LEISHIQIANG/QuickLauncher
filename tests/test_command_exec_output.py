"""Tests for command output decoding and truncation."""

from core.command_exec.output import decode_command_output, truncate_command_output


def test_decode_str_input_passthrough():
    text, encoding, fallback = decode_command_output("hello")
    assert text == "hello"
    assert encoding == "text"
    assert fallback is False


def test_decode_empty_bytes():
    text, encoding, fallback = decode_command_output(b"")
    assert text == ""
    assert fallback is False


def test_decode_utf8_preferred():
    text, encoding, fallback = decode_command_output(b"\xe4\xb8\xad\xe6\x96\x87", preferred="utf-8")
    assert text == "中文"
    assert encoding == "utf-8"
    assert fallback is False


def test_decode_none_bytes():
    text, encoding, fallback = decode_command_output(None)
    assert text == ""
    assert fallback is False


def test_decode_invalid_utf8_falls_through():
    """Invalid UTF-8 bytes should be decoded with replacement."""
    data = b"\xff\xfe\x00\x01"
    text, encoding, fallback = decode_command_output(data, preferred="utf-8")
    assert isinstance(text, str)
    # Should decode without crashing
    assert len(text) > 0


def test_truncate_command_output_short_text():
    text, truncated = truncate_command_output("hello", 10)
    assert text == "hello"
    assert truncated is False


def test_truncate_command_output_long_text():
    text, truncated = truncate_command_output("x" * 2000, 1000)
    assert truncated is True
    assert "[输出过长，已截断]" in text
    assert len(text) < 2000


def test_truncate_command_output_none():
    text, truncated = truncate_command_output(None, 2000)
    assert text == ""
    assert truncated is False


def test_truncate_at_exact_min_boundary():
    text, truncated = truncate_command_output("x" * 1000, 1000)
    assert text == "x" * 1000
    assert truncated is False


def test_truncate_one_past_min_boundary():
    text, truncated = truncate_command_output("x" * 1001, 1000)
    assert truncated is True
    assert "[输出过长，已截断]" in text


# ── Command-type-aware encoding tests ──────────────────────


def test_decode_cmd_uses_oem_before_utf8(monkeypatch):
    """CMD output on Windows should try OEM code page before UTF-8.

    Bytes that are valid in the system's OEM CP but NOT valid UTF-8
    must decode correctly when command_type='cmd'.
    """
    monkeypatch.setattr("core.command_exec.output.os.name", "nt", raising=False)

    # These bytes are cp936 for 中文 but are NOT valid UTF-8
    oem_bytes = b"\xd6\xd0\xce\xc4"
    text, encoding, fallback = decode_command_output(oem_bytes, command_type="cmd")
    assert text == "中文"
    # The OEM CP (first candidate) should succeed on first try
    assert fallback is False


def test_decode_cmd_oem_bytes_fail_utf8_then_fallback(monkeypatch):
    """CMD OEM-only bytes that fail utf-8 should fallback gracefully."""
    monkeypatch.setattr("core.command_exec.output.os.name", "nt", raising=False)

    # Bytes only valid in cp936/oem, NOT valid UTF-8
    oem_bytes = b"\xd6\xd0\xce\xc4"
    text, encoding, fallback = decode_command_output(oem_bytes, command_type="bash")
    assert text == "中文"
    # For bash, UTF-8 is tried first, then OEM CP (with fallback)
    # On a system with actual OEM CP 936, the fallback to cp936 works


def test_decode_non_cmd_uses_utf8_first(monkeypatch):
    """Non-CMD types should prefer UTF-8 over OEM CP."""
    monkeypatch.setattr("core.command_exec.output.os.name", "nt", raising=False)
    monkeypatch.setattr("core.command_exec.output.ctypes.windll.kernel32.GetOEMCP", lambda: 936, raising=False)

    text, encoding, fallback = decode_command_output(b"hello", command_type="bash")
    assert text == "hello"
    assert encoding == "utf-8"


def test_decode_powershell_uses_utf8_first(monkeypatch):
    """PowerShell output should decode as UTF-8 first."""
    monkeypatch.setattr("core.command_exec.output.os.name", "nt", raising=False)
    monkeypatch.setattr("core.command_exec.output.ctypes.windll.kernel32.GetOEMCP", lambda: 936, raising=False)

    utf8_bytes = "中文".encode("utf-8")  # 中文 in UTF-8
    text, encoding, fallback = decode_command_output(utf8_bytes, command_type="powershell")
    assert text == "中文"
    assert encoding == "utf-8"
    assert fallback is False


def test_decode_cmd_explicit_preferred_overrides_oem(monkeypatch):
    """Explicit preferred encoding should take precedence over OEM CP."""
    monkeypatch.setattr("core.command_exec.output.os.name", "nt", raising=False)
    monkeypatch.setattr("core.command_exec.output.ctypes.windll.kernel32.GetOEMCP", lambda: 936, raising=False)

    utf8_bytes = "hello".encode("utf-8")
    text, encoding, fallback = decode_command_output(utf8_bytes, preferred="utf-8", command_type="cmd")
    assert encoding == "utf-8"


def test_decode_cmd_no_oem_non_windows(monkeypatch):
    """On non-Windows, cmd type should behave the same as other types."""
    monkeypatch.setattr("core.command_exec.output.os.name", "posix", raising=False)

    text, encoding, fallback = decode_command_output(b"hello", command_type="cmd")
    assert text == "hello"
    assert encoding == "utf-8"
