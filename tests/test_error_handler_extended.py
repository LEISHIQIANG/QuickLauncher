"""Tests for error_handler.py safe_execute and safe_method."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.error_handler import safe_execute, safe_method


class TestSafeExecute:
    def test_success_returns_result(self):
        result = safe_execute(lambda: 42, "error")
        assert result == 42

    def test_success_returns_string(self):
        result = safe_execute(lambda: "hello", "error")
        assert result == "hello"

    def test_exception_returns_default(self):
        result = safe_execute(lambda: 1 / 0, "division error", default=-1)
        assert result == -1

    def test_exception_default_none(self):
        result = safe_execute(lambda: 1 / 0, "division error")
        assert result is None

    def test_specific_exception_caught(self):
        result = safe_execute(
            lambda: int("abc"),
            "parse error",
            exceptions=(ValueError,),
            default=0,
        )
        assert result == 0

    def test_unmatched_exception_propagates(self):
        with pytest.raises(ValueError):
            safe_execute(
                lambda: int("abc"),
                "error",
                exceptions=(TypeError,),
            )

    def test_multiple_exception_types(self):
        result = safe_execute(
            lambda: 1 / 0,
            "error",
            exceptions=(ValueError, ZeroDivisionError),
            default=0,
        )
        assert result == 0

    def test_log_level_variants(self):
        for level in ("debug", "info", "warning", "error"):
            result = safe_execute(lambda: 1 / 0, "msg", log_level=level, default=0)
            assert result == 0

    def test_with_side_effect(self):
        called = []

        def func():
            called.append(True)
            return "ok"

        result = safe_execute(func, "error")
        assert result == "ok"
        assert called == [True]

    def test_exception_with_args(self):
        def failing():
            raise RuntimeError("detail msg")

        result = safe_execute(failing, "context", default="fallback")
        assert result == "fallback"


class TestSafeMethod:
    def test_success(self):
        @safe_method("error", default=0)
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_exception_returns_default(self):
        @safe_method("error", default=-1)
        def fail():
            raise RuntimeError("boom")

        assert fail() == -1

    def test_preserves_args(self):
        @safe_method("error")
        def greet(name):
            return f"hello {name}"

        assert greet("world") == "hello world"

    def test_specific_exceptions(self):
        @safe_method("error", default=0, exceptions=(ZeroDivisionError,))
        def divide(a, b):
            return a / b

        assert divide(1, 0) == 0

        # ValueError should propagate
        @safe_method("error", default=0, exceptions=(ZeroDivisionError,))
        def parse(x):
            return int(x)

        with pytest.raises(ValueError):
            parse("abc")

    def test_wraps_preserves_name(self):
        @safe_method("error")
        def my_func():
            """my docstring"""
            pass

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "my docstring"

    def test_default_none(self):
        @safe_method("error")
        def fail():
            raise Exception("x")

        assert fail() is None
