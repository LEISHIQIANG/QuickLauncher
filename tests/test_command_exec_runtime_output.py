from core.command_exec import (
    decode_command_output,
    is_supported_command_type,
    normalize_command_type,
    truncate_command_output,
)
from core.runtime_constants import MIN_COMMAND_OUTPUT_MAX_CHARS


def test_runtime_normalizes_command_type_aliases():
    assert normalize_command_type("ps") == "powershell"
    assert normalize_command_type("git-bash") == "bash"
    assert normalize_command_type("py") == "python"
    assert normalize_command_type("") == "cmd"
    assert is_supported_command_type("pwsh") is True
    assert is_supported_command_type("unknown-runtime") is False


def test_output_helpers_decode_and_truncate():
    text, encoding, fallback = decode_command_output("ready")
    assert (text, encoding, fallback) == ("ready", "text", False)

    decoded, encoding, fallback = decode_command_output("中文".encode())
    assert decoded == "中文"
    assert encoding == "utf-8"
    assert fallback is False

    truncated, was_truncated = truncate_command_output("x" * (MIN_COMMAND_OUTPUT_MAX_CHARS + 1), 1)
    assert was_truncated is True
    assert "[输出过长，已截断]" in truncated
