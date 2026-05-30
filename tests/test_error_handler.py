"""
测试 error_handler 模块
"""

from core.error_handler import safe_execute, safe_method


def test_safe_execute_success():
    """测试 safe_execute 正常执行"""
    result = safe_execute(lambda: 1 + 1, "测试错误", default=0)
    assert result == 2


def test_safe_execute_catches_exception():
    """测试 safe_execute 捕获异常"""
    result = safe_execute(lambda: 1 / 0, "除零错误", exceptions=(ZeroDivisionError,), default=-1)
    assert result == -1


def test_safe_execute_specific_exception():
    """测试 safe_execute 只捕获特定异常"""
    result = safe_execute(lambda: int("not_a_number"), "转换错误", exceptions=(ValueError,), default=0)
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


# ── appended tests ──────────────────────────────────────────────


def test_safe_execute_catches_value_error():
    """safe_execute 捕获 ValueError"""
    result = safe_execute(lambda: int("abc"), "值错误", exceptions=(ValueError,), default=0)
    assert result == 0


def test_safe_execute_catches_key_error():
    """safe_execute 捕获 KeyError"""
    result = safe_execute(lambda: {}["missing"], "键错误", exceptions=(KeyError,), default="fallback")
    assert result == "fallback"


def test_safe_execute_catches_os_error():
    """safe_execute 捕获 OSError"""

    def raise_os():
        raise OSError("磁盘错误")

    result = safe_execute(raise_os, "系统错误", exceptions=(OSError,), default=None)
    assert result is None


def test_safe_execute_log_level_debug(caplog):
    """safe_execute 使用 debug 日志级别"""
    import logging

    with caplog.at_level(logging.DEBUG, logger="core.error_handler"):
        safe_execute(lambda: 1 / 0, "除零", exceptions=(ZeroDivisionError,), default=0, log_level="debug")
    assert any("除零" in r.message for r in caplog.records)


def test_safe_execute_log_level_info(caplog):
    """safe_execute 使用 info 日志级别"""
    import logging

    with caplog.at_level(logging.INFO, logger="core.error_handler"):
        safe_execute(lambda: 1 / 0, "除零", exceptions=(ZeroDivisionError,), default=0, log_level="info")
    assert any("除零" in r.message for r in caplog.records)


def test_safe_execute_log_level_error(caplog):
    """safe_execute 使用 error 日志级别"""
    import logging

    with caplog.at_level(logging.ERROR, logger="core.error_handler"):
        safe_execute(lambda: 1 / 0, "除零", exceptions=(ZeroDivisionError,), default=0, log_level="error")
    assert any("除零" in r.message for r in caplog.records)


def test_safe_execute_returns_string():
    """safe_execute 正常返回字符串"""
    result = safe_execute(lambda: "hello", "错误", default="")
    assert result == "hello"


def test_safe_execute_returns_list():
    """safe_execute 正常返回列表"""
    result = safe_execute(lambda: [1, 2, 3], "错误", default=[])
    assert result == [1, 2, 3]


def test_safe_execute_returns_dict():
    """safe_execute 正常返回字典"""
    result = safe_execute(lambda: {"a": 1}, "错误", default={})
    assert result == {"a": 1}


def test_safe_execute_returns_none_normally():
    """safe_execute 函数正常返回 None"""
    result = safe_execute(lambda: None, "错误", default="fallback")
    assert result is None


def test_safe_method_with_value_error():
    """safe_method 捕获 ValueError"""

    @safe_method("值错误", default=0, exceptions=(ValueError,))
    def convert(x):
        return int(x)

    assert convert("42") == 42
    assert convert("not_int") == 0


def test_safe_method_does_not_catch_key_error():
    """safe_method 仅捕获指定异常，KeyError 不被捕获"""

    @safe_method("值错误", default=0, exceptions=(ValueError,))
    def lookup(d):
        return d["missing"]

    import pytest

    with pytest.raises(KeyError):
        lookup({})


def test_safe_method_none_default():
    """safe_method 默认值为 None"""

    @safe_method("失败")
    def fail():
        raise RuntimeError("boom")

    assert fail() is None


def test_safe_execute_tuple_of_multiple_exception_types():
    """safe_execute 异常参数为包含多种类型的元组"""
    result = safe_execute(lambda: int("abc"), "转换错误", exceptions=(ValueError, TypeError), default=-1)
    assert result == -1

    result2 = safe_execute(lambda: 1 + "s", "类型错误", exceptions=(ValueError, TypeError), default=-1)
    assert result2 == -1
