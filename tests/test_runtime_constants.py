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
from core.shortcut_health import MAX_CHAIN_STEPS as HEALTH_CHAIN_MAX_STEPS


def test_command_and_chain_limits_are_shared():
    assert ShortcutItem.MAX_CHAIN_STEPS == COMMAND_CHAIN_MAX_STEPS
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


def test_normalize_command_timeout_with_none():
    assert normalize_command_timeout_seconds(None) == DEFAULT_COMMAND_TIMEOUT_SECONDS
    assert normalize_command_timeout_seconds(None, 5.0) == 5.0


def test_normalize_command_timeout_with_valid_values():
    assert normalize_command_timeout_seconds(5.0) == 5.0
    assert normalize_command_timeout_seconds("10.5") == 10.5


def test_normalize_command_output_with_none():
    assert normalize_command_output_max_chars(None) == DEFAULT_COMMAND_OUTPUT_MAX_CHARS
    assert normalize_command_output_max_chars(None, 5000) == 5000


def test_normalize_command_output_with_valid_values():
    assert normalize_command_output_max_chars(5000) == 5000
    assert normalize_command_output_max_chars("10000") == 10000


def test_normalize_chain_step_delay_with_none():
    assert normalize_chain_step_delay_ms(None) == 0


def test_normalize_chain_step_delay_with_valid_values():
    assert normalize_chain_step_delay_ms(100) == 100
    assert normalize_chain_step_delay_ms("500") == 500
    assert normalize_chain_step_delay_ms(-10) == 0
