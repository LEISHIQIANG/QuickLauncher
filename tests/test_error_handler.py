"""
测试 error_handler 模块
"""

import pytest
from core.error_handler import safe_execute, safe_method


def test_safe_execute_success():
    """测试 safe_execute 正常执行"""
    result = safe_execute(
        lambda: 1 + 1,
        "测试错误",
        default=0
    )
    assert result == 2


def test_safe_execute_catches_exception():
    """测试 safe_execute 捕获异常"""
    result = safe_execute(
        lambda: 1 / 0,
        "除零错误",
        exceptions=(ZeroDivisionError,),
        default=-1
    )
    assert result == -1


def test_safe_execute_specific_exception():
    """测试 safe_execute 只捕获特定异常"""
    result = safe_execute(
        lambda: int("not_a_number"),
        "转换错误",
        exceptions=(ValueError,),
        default=0
    )
    assert result == 0


def test_safe_method_decorator():
    """测试 safe_method 装饰器"""

    @safe_method("方法执行失败", default="error")
    def risky_method():
        raise RuntimeError("测试异常")

    result = risky_method()
    assert result == "error"


def test_safe_method_decorator_success():
    """测试 safe_method 装饰器正常执行"""

    @safe_method("方法执行失败", default="error")
    def safe_method_test():
        return "success"

    result = safe_method_test()
    assert result == "success"
