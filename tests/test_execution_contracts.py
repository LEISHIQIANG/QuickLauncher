from __future__ import annotations

import pytest

from application.execution import CancellationToken, ExecutionErrorCode, ExecutionPolicy, ExecutionRequest


def test_execution_contract_defaults_are_safe_and_independent():
    first = ExecutionRequest(command_id="one")
    second = ExecutionRequest(command_id="two")

    first.args["value"] = "1"

    assert second.args == {}
    assert first.policy.confirm_dangerous is True
    assert ExecutionErrorCode.TIMEOUT.value == "timeout"


def test_execution_policy_rejects_non_positive_timeout():
    with pytest.raises(ValueError):
        ExecutionPolicy(timeout_seconds=0)


def test_cancellation_token_is_cooperative():
    token = CancellationToken()
    assert token.cancelled is False
    token.cancel()
    assert token.cancelled is True
    assert token.event.is_set()
