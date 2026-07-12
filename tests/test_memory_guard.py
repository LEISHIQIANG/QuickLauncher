"""Comprehensive tests for core/memory_guard.py."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from core.memory_guard import MemoryGuard


def _make_mock_process(uss_mb: float):
    """Create a mock psutil.Process returning the given USS in MB."""
    mock_proc = MagicMock()
    mock_proc.memory_full_info.return_value = SimpleNamespace(uss=uss_mb * 1024 * 1024)
    return mock_proc


def _make_guard(critical=200, moderate=150, light=100, uss_mb=50.0):
    """Create a MemoryGuard with a mocked process at the given memory level."""
    guard = MemoryGuard(critical_mb=critical, moderate_mb=moderate, light_mb=light)
    guard.process = _make_mock_process(uss_mb)
    return guard


# ── __init__ ────────────────────────────────────────────────────────────────


def test_default_thresholds():
    guard = MemoryGuard()
    assert guard.critical_mb == 200
    assert guard.moderate_mb == 150
    assert guard.light_mb == 100
    assert guard.process is not None
    assert guard._cleanup_callbacks == []


def test_custom_thresholds():
    guard = MemoryGuard(critical_mb=500, moderate_mb=300, light_mb=200)
    assert guard.critical_mb == 500
    assert guard.moderate_mb == 300
    assert guard.light_mb == 200


def test_process_handle_failure():
    with patch("core.memory_guard.psutil.Process", side_effect=RuntimeError("no proc")):
        guard = MemoryGuard()
        assert guard.process is None


# ── get_memory_mb ───────────────────────────────────────────────────────────


def test_get_memory_mb_returns_correct_value():
    guard = _make_guard(uss_mb=123.5)
    assert abs(guard.get_memory_mb() - 123.5) < 0.1


def test_get_memory_mb_returns_zero_when_process_is_none():
    guard = MemoryGuard()
    guard.process = None
    assert guard.get_memory_mb() == 0.0


def test_get_memory_mb_returns_zero_on_exception():
    guard = MemoryGuard()
    mock_proc = MagicMock()
    mock_proc.memory_full_info.side_effect = OSError("process gone")
    guard.process = mock_proc
    assert guard.get_memory_mb() == 0.0


# ── register_cleanup_callback ──────────────────────────────────────────────


def test_register_single_callback():
    guard = MemoryGuard()
    cb = MagicMock()
    guard.register_cleanup_callback(cb)
    assert guard._cleanup_callbacks == [cb]


def test_register_multiple_callbacks():
    guard = MemoryGuard()
    cbs = [MagicMock(name=f"cb{i}") for i in range(4)]
    for cb in cbs:
        guard.register_cleanup_callback(cb)
    assert guard._cleanup_callbacks == cbs


# ── get_status ──────────────────────────────────────────────────────────────


def test_get_status_normal():
    guard = _make_guard(uss_mb=50)
    status = guard.get_status()
    assert status["status"] == "normal"
    assert status["current_mb"] == 50.0
    assert status["light_mb"] == 100
    assert status["moderate_mb"] == 150
    assert status["critical_mb"] == 200


def test_get_status_light():
    guard = _make_guard(uss_mb=120)
    assert guard.get_status()["status"] == "light"


def test_get_status_moderate():
    guard = _make_guard(uss_mb=170)
    assert guard.get_status()["status"] == "moderate"


def test_get_status_critical():
    guard = _make_guard(uss_mb=250)
    assert guard.get_status()["status"] == "critical"


def test_get_status_at_boundary_light():
    guard = _make_guard(uss_mb=100.1)
    assert guard.get_status()["status"] == "light"


def test_get_status_at_boundary_moderate():
    guard = _make_guard(uss_mb=150.1)
    assert guard.get_status()["status"] == "moderate"


def test_get_status_at_boundary_critical():
    guard = _make_guard(uss_mb=200.1)
    assert guard.get_status()["status"] == "critical"


def test_get_status_zero_memory():
    guard = MemoryGuard()
    guard.process = None
    status = guard.get_status()
    assert status["current_mb"] == 0.0
    assert status["status"] == "normal"


def test_get_status_current_mb_is_rounded():
    guard = _make_guard(uss_mb=123.456789)
    assert guard.get_status()["current_mb"] == 123.5


# ── check_and_optimize ─────────────────────────────────────────────────────


def test_check_returns_false_below_light():
    guard = _make_guard(uss_mb=50, light=100, moderate=150, critical=200)
    assert guard.check_and_optimize() is False


def test_check_returns_true_at_light():
    guard = _make_guard(uss_mb=110, light=100, moderate=150, critical=200)
    assert guard.check_and_optimize() is True


def test_check_returns_true_at_moderate():
    guard = _make_guard(uss_mb=160, light=100, moderate=150, critical=200)
    assert guard.check_and_optimize() is True


def test_check_returns_true_at_critical():
    guard = _make_guard(uss_mb=250, light=100, moderate=150, critical=200)
    assert guard.check_and_optimize() is True


def test_check_exact_boundary_no_trigger():
    """Memory exactly at threshold should not trigger (uses strict >)."""
    guard = _make_guard(uss_mb=100, light=100, moderate=150, critical=200)
    assert guard.check_and_optimize() is False


def test_check_just_above_light():
    guard = _make_guard(uss_mb=100.01, light=100, moderate=150, critical=200)
    assert guard.check_and_optimize() is True


@patch("core.memory_guard.gc")
def test_check_light_calls_gc_collect_generation_0(mock_gc):
    guard = _make_guard(uss_mb=110)
    guard.check_and_optimize()
    mock_gc.collect.assert_called_with(0)


@patch("core.memory_guard.gc")
def test_check_moderate_calls_gc_collect_generation_1(mock_gc):
    guard = _make_guard(uss_mb=160)
    guard.check_and_optimize()
    mock_gc.collect.assert_called_with(1)


@patch("core.memory_guard.gc")
def test_check_critical_calls_full_gc_collect(mock_gc):
    guard = _make_guard(uss_mb=250)
    guard.check_and_optimize()
    mock_gc.collect.assert_called_with()


# ── cleanup callbacks ───────────────────────────────────────────────────────


def test_callback_called_with_correct_level_light():
    guard = _make_guard(uss_mb=110)
    calls = []
    guard.register_cleanup_callback(lambda level=None: calls.append(level))
    guard.check_and_optimize()
    assert calls == ["light"]


def test_callback_called_with_correct_level_moderate():
    guard = _make_guard(uss_mb=160)
    calls = []
    guard.register_cleanup_callback(lambda level=None: calls.append(level))
    guard.check_and_optimize()
    assert calls == ["moderate"]


def test_callback_called_with_correct_level_critical():
    guard = _make_guard(uss_mb=250)
    calls = []
    guard.register_cleanup_callback(lambda level=None: calls.append(level))
    guard.check_and_optimize()
    assert calls == ["critical"]


def test_callback_without_args_still_works():
    """Callbacks that accept no positional args should be called via TypeError fallback."""
    guard = _make_guard(uss_mb=250)
    called = []

    def no_arg_callback():
        called.append(True)

    guard.register_cleanup_callback(no_arg_callback)
    guard.check_and_optimize()
    assert called == [True]


def test_callback_typeerror_fallback_calls_twice():
    """When callback raises TypeError with arg, it is retried without arg."""
    guard = _make_guard(uss_mb=250)
    cb = MagicMock(side_effect=[TypeError("takes no arg"), None])
    guard.register_cleanup_callback(cb)
    guard.check_and_optimize()
    assert cb.call_count == 2
    cb.assert_any_call("critical")
    cb.assert_any_call()


def test_multiple_callbacks_all_invoked():
    guard = _make_guard(uss_mb=250)
    results = []
    guard.register_cleanup_callback(lambda level=None: results.append("a"))
    guard.register_cleanup_callback(lambda level=None: results.append("b"))
    guard.register_cleanup_callback(lambda level=None: results.append("c"))
    guard.check_and_optimize()
    assert results == ["a", "b", "c"]


def test_callback_exception_does_not_propagate():
    guard = _make_guard(uss_mb=250)
    good_calls = []

    def bad_callback(level):
        raise RuntimeError("boom")

    def good_callback(level):
        good_calls.append(level)

    guard.register_cleanup_callback(bad_callback)
    guard.register_cleanup_callback(good_callback)
    guard.check_and_optimize()  # should not raise
    assert good_calls == ["critical"]


def test_no_callbacks_no_error():
    guard = _make_guard(uss_mb=250)
    guard.check_and_optimize()  # no callbacks registered, should not raise


# ── _force_cleanup ──────────────────────────────────────────────────────────


@patch.object(MemoryGuard, "_cleanup_icon_cache")
@patch("core.memory_guard.gc")
def test_force_cleanup_light_gc(mock_gc, mock_icon):
    guard = MemoryGuard()
    guard._force_cleanup("light")
    mock_gc.collect.assert_called_with(0)
    mock_icon.assert_called_with("light")


@patch.object(MemoryGuard, "_cleanup_icon_cache")
@patch("core.memory_guard.gc")
def test_force_cleanup_moderate_gc(mock_gc, mock_icon):
    guard = MemoryGuard()
    guard._force_cleanup("moderate")
    mock_gc.collect.assert_called_with(1)


@patch.object(MemoryGuard, "_cleanup_icon_cache")
@patch("core.memory_guard.gc")
def test_force_cleanup_critical_gc(mock_gc, mock_icon):
    guard = MemoryGuard()
    guard._force_cleanup("critical")
    mock_gc.collect.assert_called_with()


@patch.object(MemoryGuard, "_cleanup_icon_cache")
@patch("core.memory_guard.gc")
def test_force_cleanup_callback_receives_level(mock_gc, mock_icon):
    guard = MemoryGuard()
    cb = MagicMock()
    guard.register_cleanup_callback(cb)
    guard._force_cleanup("moderate")
    cb.assert_called_once_with("moderate")


@patch.object(MemoryGuard, "_cleanup_icon_cache")
@patch("core.memory_guard.gc")
def test_force_cleanup_multiple_callbacks(mock_gc, mock_icon):
    guard = MemoryGuard()
    cbs = [MagicMock() for _ in range(3)]
    for cb in cbs:
        guard.register_cleanup_callback(cb)
    guard._force_cleanup("critical")
    for cb in cbs:
        cb.assert_called_once_with("critical")


# ── _cleanup_icon_cache ────────────────────────────────────────────────────


def test_icon_cache_critical_calls_clear_cache():
    guard = MemoryGuard()
    mock_ie = MagicMock()
    with patch.dict("sys.modules", {"core.icon_extractor": MagicMock(IconExtractor=mock_ie)}):
        guard._cleanup_icon_cache("critical")
    mock_ie.clear_cache.assert_called_once()


def test_icon_cache_non_critical_calls_clear_expired():
    guard = MemoryGuard()
    mock_ie = MagicMock()
    with patch.dict("sys.modules", {"core.icon_extractor": MagicMock(IconExtractor=mock_ie)}):
        guard._cleanup_icon_cache("moderate")
    mock_ie.clear_expired_cache.assert_called_once_with("moderate")


def test_icon_cache_light_calls_clear_expired():
    guard = MemoryGuard()
    mock_ie = MagicMock()
    with patch.dict("sys.modules", {"core.icon_extractor": MagicMock(IconExtractor=mock_ie)}):
        guard._cleanup_icon_cache("light")
    mock_ie.clear_expired_cache.assert_called_once_with("light")


def test_icon_cache_import_failure_does_not_raise():
    guard = MemoryGuard()
    original = sys.modules.pop("core.icon_extractor", None)
    try:
        guard._cleanup_icon_cache("critical")  # should not raise
    finally:
        if original is not None:
            sys.modules["core.icon_extractor"] = original
