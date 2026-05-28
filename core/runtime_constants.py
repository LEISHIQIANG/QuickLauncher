"""Shared runtime limits used by command execution, health checks and models."""

from __future__ import annotations

DEFAULT_COMMAND_TIMEOUT_SECONDS = 10.0
MIN_COMMAND_TIMEOUT_SECONDS = 0.1

DEFAULT_COMMAND_OUTPUT_MAX_CHARS = 20_000
MIN_COMMAND_OUTPUT_MAX_CHARS = 1_000

COMMAND_CHAIN_MAX_STEPS = 128
COMMAND_CHAIN_MAX_STEP_DELAY_MS = 60_000
COMMAND_CHAIN_SUMMARY_MAX_CHARS = 500

COMMAND_CAPTURE_UPDATE_INTERVAL_SECONDS = 0.15
COMMAND_CAPTURE_POLL_SECONDS = 0.03
PROCESS_TERMINATE_WAIT_SECONDS = 2.0


def normalize_command_timeout_seconds(value, default: float = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> float:
    """Return a positive command timeout aligned with the data-model default."""
    try:
        return max(MIN_COMMAND_TIMEOUT_SECONDS, float(value or default))
    except Exception:
        return default


def normalize_command_output_max_chars(value, default: int = DEFAULT_COMMAND_OUTPUT_MAX_CHARS) -> int:
    """Return a bounded output limit aligned with command capture truncation."""
    try:
        return max(MIN_COMMAND_OUTPUT_MAX_CHARS, int(value or default))
    except Exception:
        return default


def normalize_chain_step_delay_ms(value) -> int:
    """Clamp chain step delays to the same range used by health and execution."""
    try:
        return max(0, min(COMMAND_CHAIN_MAX_STEP_DELAY_MS, int(value or 0)))
    except Exception:
        return 0
