"""Tests for core/error_handler.py — safe_execute and safe_method.

These tests extend coverage for the error-handling utilities.
"""

from __future__ import annotations

import logging

import pytest

from core.error_handler import safe_execute, safe_method

# ---------------------------------------------------------------------------
# safe_execute — successful execution
# ---------------------------------------------------------------------------


def test_safe_execute_returns_result():
    result = safe_execute(lambda: 42, "err")
    assert result == 42


def test_safe_execute_with_string_return():
    result = safe_execute(lambda: "hello", "err")
    assert result == "hello"


# ---------------------------------------------------------------------------
# safe_execute — exception handling
# ---------------------------------------------------------------------------


def test_safe_execute_returns_default_on_exception():
    result = safe_execute(lambda: 1 / 0, "division error", default=-1)
    assert result == -1


def test_safe_execute_default_is_none():
    result = safe_execute(lambda: 1 / 0, "division error")
    assert result is None


def test_safe_execute_catches_specific_exception():
    result = safe_execute(
        lambda: int("not_a_number"),
        "value error",
        exceptions=(ValueError,),
        default=0,
    )
    assert result == 0


def test_safe_execute_does_not_catch_unmatched_exception():
    with pytest.raises(ZeroDivisionError):
        safe_execute(
            lambda: 1 / 0,
            "error",
            exceptions=(ValueError,),
            default=0,
        )


def test_safe_execute_catches_multiple_exception_types():
    def raise_type_error():
        raise TypeError("bad type")

    result = safe_execute(
        raise_type_error,
        "error",
        exceptions=(ValueError, TypeError),
        default="caught",
    )
    assert result == "caught"


# ---------------------------------------------------------------------------
# safe_execute — log levels
# ---------------------------------------------------------------------------


def test_safe_execute_logs_at_debug(caplog):
    with caplog.at_level(logging.DEBUG, logger="core.error_handler"):
        safe_execute(lambda: 1 / 0, "debug msg", log_level="debug")
    assert "debug msg" in caplog.text


def test_safe_execute_logs_at_info(caplog):
    with caplog.at_level(logging.INFO, logger="core.error_handler"):
        safe_execute(lambda: 1 / 0, "info msg", log_level="info")
    assert "info msg" in caplog.text


def test_safe_execute_logs_at_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="core.error_handler"):
        safe_execute(lambda: 1 / 0, "warn msg", log_level="warning")
    assert "warn msg" in caplog.text


def test_safe_execute_logs_at_error(caplog):
    with caplog.at_level(logging.ERROR, logger="core.error_handler"):
        safe_execute(lambda: 1 / 0, "error msg", log_level="error")
    assert "error msg" in caplog.text


# ---------------------------------------------------------------------------
# safe_method — decorator
# ---------------------------------------------------------------------------


def test_safe_method_returns_result_on_success():
    @safe_method("err", default=0)
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_safe_method_returns_default_on_exception():
    @safe_method("err", default="fallback")
    def fail():
        raise RuntimeError("boom")

    assert fail() == "fallback"


def test_safe_method_catches_specific_exceptions():
    @safe_method("err", default=None, exceptions=(ValueError,))
    def bad_int():
        return int("nope")

    assert bad_int() is None


def test_safe_method_does_not_catch_unmatched():
    @safe_method("err", default=None, exceptions=(ValueError,))
    def zero_div():
        return 1 / 0

    with pytest.raises(ZeroDivisionError):
        zero_div()


def test_safe_method_on_class_method():
    class MyClass:
        @safe_method("method error", default=0)
        def compute(self, x):
            if x < 0:
                raise ValueError("negative")
            return x * 2

    obj = MyClass()
    assert obj.compute(5) == 10
    assert obj.compute(-1) == 0
