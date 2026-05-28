from core.data_models import ShortcutItem
from core.runtime_constants import (
    COMMAND_CHAIN_MAX_STEP_DELAY_MS,
    COMMAND_CHAIN_MAX_STEPS,
    DEFAULT_COMMAND_OUTPUT_MAX_CHARS,
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    MIN_COMMAND_OUTPUT_MAX_CHARS,
    MIN_COMMAND_TIMEOUT_SECONDS,
    normalize_chain_step_delay_ms,
    normalize_command_output_max_chars,
    normalize_command_timeout_seconds,
)
from core.shortcut_chain_exec import MAX_CHAIN_STEPS as EXEC_CHAIN_MAX_STEPS
from core.shortcut_health import MAX_CHAIN_STEPS as HEALTH_CHAIN_MAX_STEPS


def test_command_and_chain_limits_are_shared():
    assert ShortcutItem.MAX_CHAIN_STEPS == COMMAND_CHAIN_MAX_STEPS
    assert EXEC_CHAIN_MAX_STEPS == COMMAND_CHAIN_MAX_STEPS
    assert HEALTH_CHAIN_MAX_STEPS == COMMAND_CHAIN_MAX_STEPS
    assert ShortcutItem().command_timeout_seconds == DEFAULT_COMMAND_TIMEOUT_SECONDS
    assert ShortcutItem().command_output_max_chars == DEFAULT_COMMAND_OUTPUT_MAX_CHARS


def test_runtime_constant_normalizers_clamp_invalid_values():
    assert normalize_command_timeout_seconds(0) == DEFAULT_COMMAND_TIMEOUT_SECONDS
    assert normalize_command_timeout_seconds("0.01") == MIN_COMMAND_TIMEOUT_SECONDS
    assert normalize_command_timeout_seconds("bad") == DEFAULT_COMMAND_TIMEOUT_SECONDS
    assert normalize_command_output_max_chars(1) == MIN_COMMAND_OUTPUT_MAX_CHARS
    assert normalize_command_output_max_chars("bad") == DEFAULT_COMMAND_OUTPUT_MAX_CHARS
    assert normalize_chain_step_delay_ms(COMMAND_CHAIN_MAX_STEP_DELAY_MS + 1) == COMMAND_CHAIN_MAX_STEP_DELAY_MS
    assert normalize_chain_step_delay_ms("bad") == 0
