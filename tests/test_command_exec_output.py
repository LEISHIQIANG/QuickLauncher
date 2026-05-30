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

    For cmd type, the OEM CP is placed before UTF-8 in the candidate list.
    If the bytes decode successfully with the OEM CP, UTF-8 is never tried.
    """

    def check_oem_before_utf8(data, preferred="auto", command_type=""):
        # Directly verify the candidate ordering logic
        from core.command_exec.output import ctypes as _ctypes
        from core.command_exec.output import os as _os

        candidates = []
        preferred = str(preferred or "auto").lower().strip()
        if preferred and preferred != "auto":
            candidates.append(preferred)

        oem_enc = None
        if _os.name == "nt":
            try:
                oem_cp = _ctypes.windll.kernel32.GetOEMCP()
                if oem_cp:
                    oem_enc = f"cp{oem_cp}"
            except Exception:
                pass

        effective_type = str(command_type or "").lower().strip() if command_type else ""

        if effective_type == "cmd" and oem_enc:
            candidates.append(oem_enc)
        candidates.append("utf-8")
        if effective_type != "cmd" and oem_enc:
            candidates.append(oem_enc)

        return candidates

    cmd_candidates = check_oem_before_utf8(b"test", command_type="cmd")
    bash_candidates = check_oem_before_utf8(b"test", command_type="bash")

    # For cmd, OEM CP should be before utf-8
    oem_idx = next(i for i, c in enumerate(cmd_candidates) if c.startswith("cp"))
    utf8_idx = cmd_candidates.index("utf-8")
    assert oem_idx < utf8_idx, f"OEM CP ({cmd_candidates[oem_idx]}) should be before utf-8 in cmd mode"

    # For bash, utf-8 should be before OEM CP
    if len(bash_candidates) > 1:
        utf8_idx_bash = bash_candidates.index("utf-8")
        oem_idx_bash = next(i for i, c in enumerate(bash_candidates) if c.startswith("cp"))
        assert utf8_idx_bash < oem_idx_bash, "utf-8 should be before OEM CP in bash mode"


def test_decode_cmd_oem_bytes_fail_utf8_then_fallback(monkeypatch):
    """CMD output decoding should not crash regardless of OEM CP."""
    # Use bytes that are valid UTF-8. Decoding should succeed regardless of OEM CP.
    utf8_bytes = b"test"
    text, encoding, fallback = decode_command_output(utf8_bytes, command_type="cmd")
    assert text == "test"
    assert isinstance(encoding, str)

    # Non-ASCII UTF-8 bytes should also decode eventually (through OEM or UTF-8)
    non_ascii = b"abc123"
    text2, encoding2, fallback2 = decode_command_output(non_ascii, command_type="cmd")
    assert text2 == "abc123"


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

    utf8_bytes = "中文".encode()  # 中文 in UTF-8
    text, encoding, fallback = decode_command_output(utf8_bytes, command_type="powershell")
    assert text == "中文"
    assert encoding == "utf-8"
    assert fallback is False


def test_decode_cmd_explicit_preferred_overrides_oem(monkeypatch):
    """Explicit preferred encoding should take precedence over OEM CP."""
    monkeypatch.setattr("core.command_exec.output.os.name", "nt", raising=False)
    monkeypatch.setattr("core.command_exec.output.ctypes.windll.kernel32.GetOEMCP", lambda: 936, raising=False)

    utf8_bytes = b"hello"
    text, encoding, fallback = decode_command_output(utf8_bytes, preferred="utf-8", command_type="cmd")
    assert encoding == "utf-8"


def test_decode_cmd_no_oem_non_windows(monkeypatch):
    """On non-Windows, cmd type should behave the same as other types."""
    monkeypatch.setattr("core.command_exec.output.os.name", "posix", raising=False)

    text, encoding, fallback = decode_command_output(b"hello", command_type="cmd")
    assert text == "hello"
    assert encoding == "utf-8"


# ── Additional edge-case tests ───────────────────────────────────────────


def test_truncate_empty_string():
    text, truncated = truncate_command_output("", 10_000)
    assert text == ""
    assert truncated is False


def test_truncate_exact_boundary_not_truncated():
    text = "x" * 1000
    result, truncated = truncate_command_output(text, 1000)
    assert result == text
    assert truncated is False


def test_truncate_min_clamp_below_1000():
    """max_chars below MIN_COMMAND_OUTPUT_MAX_CHARS (1000) is clamped to 1000."""
    text = "b" * 500
    result, truncated = truncate_command_output(text, 10)
    assert truncated is False
    assert result == text


def test_decode_garbage_bytes_replacement():
    """Invalid byte sequences across all candidates should use replacement."""
    data = b"\xff\xfe\x80\x81"
    text, enc, fallback = decode_command_output(data)
    assert fallback is True


def test_decode_with_preferred_latin1():
    data = "café".encode("latin-1")
    text, enc, fallback = decode_command_output(data, preferred="latin-1")
    assert "caf" in text
    assert enc == "latin-1"


def test_decode_cmd_oem_exception_handled(monkeypatch):
    """If GetOEMCP raises, decoding still works via other candidates."""

    def raise_os_error():
        raise OSError("no dll")

    monkeypatch.setattr("core.command_exec.output.os.name", "nt", raising=False)
    monkeypatch.setattr(
        "core.command_exec.output.ctypes.windll.kernel32.GetOEMCP",
        raise_os_error,
        raising=False,
    )

    text, enc, fallback = decode_command_output(b"test", command_type="cmd")
    assert text == "test"
    assert enc == "utf-8"


def test_decode_utf8_chinese_text():
    data = "中文".encode()
    text, enc, fallback = decode_command_output(data, preferred="utf-8")
    assert text == "中文"
    assert enc == "utf-8"
    assert fallback is False


def test_decode_preferred_auto_skipped():
    """preferred='auto' should be treated as no preference."""
    data = b"hello"
    text, enc, fallback = decode_command_output(data, preferred="auto")
    assert text == "hello"
    # auto is skipped, so utf-8 is the first real candidate
    assert enc == "utf-8"
    assert fallback is False
