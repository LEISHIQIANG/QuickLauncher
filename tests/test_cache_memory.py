from collections import OrderedDict

from core import icon_extractor as icon_module
from core.icon_extractor import IconExtractor
from core.memory_guard import MemoryGuard


def test_icon_cache_stats_ttl_and_lru(monkeypatch):
    IconExtractor.clear_cache()
    monkeypatch.setattr(IconExtractor, "_MAX_CACHE_SIZE", 2)
    monkeypatch.setattr(IconExtractor, "_CACHE_TTL_SECONDS", 10)

    now = {"value": 1000.0}
    monkeypatch.setattr(icon_module.time, "time", lambda: now["value"])

    IconExtractor._remember_cache("a", object())
    IconExtractor._remember_cache("b", object())
    IconExtractor._remember_cache("c", object())

    assert list(IconExtractor._cache.keys()) == ["b", "c"]
    assert IconExtractor.get_cache_stats() == {
        "cache_size": 2,
        "default_icon_cache_size": 0,
        "max_cache_size": 2,
        "ttl_seconds": 10,
    }

    now["value"] = 1011.0
    assert IconExtractor.clear_expired_cache() == 2
    assert IconExtractor.get_cache_stats()["cache_size"] == 0


def test_memory_guard_thresholds_select_cleanup_level(monkeypatch):
    guard = MemoryGuard(light_mb=100, moderate_mb=200, critical_mb=300)
    levels = []
    monkeypatch.setattr(guard, "_force_cleanup", lambda level: levels.append(level))

    monkeypatch.setattr(guard, "get_memory_mb", lambda: 150.0)
    assert guard.check_and_optimize() is True

    monkeypatch.setattr(guard, "get_memory_mb", lambda: 250.0)
    assert guard.check_and_optimize() is True

    monkeypatch.setattr(guard, "get_memory_mb", lambda: 350.0)
    assert guard.check_and_optimize() is True

    monkeypatch.setattr(guard, "get_memory_mb", lambda: 50.0)
    assert guard.check_and_optimize() is False

    assert levels == ["light", "moderate", "critical"]


def test_memory_guard_force_cleanup_runs_callbacks_and_generation_gc(monkeypatch):
    guard = MemoryGuard()
    callback_levels = []
    cleanup_levels = []
    gc_calls = []

    guard.register_cleanup_callback(lambda level: callback_levels.append(level))
    guard.register_cleanup_callback(lambda: callback_levels.append("legacy"))

    monkeypatch.setattr(guard, "_cleanup_icon_cache", lambda level: cleanup_levels.append(level))
    monkeypatch.setattr("core.memory_guard.gc.collect", lambda generation=None: gc_calls.append(generation))

    guard._force_cleanup("light")
    guard._force_cleanup("moderate")
    guard._force_cleanup("critical")

    assert cleanup_levels == ["light", "moderate", "critical"]
    assert callback_levels == ["light", "legacy", "moderate", "legacy", "critical", "legacy"]
    assert gc_calls == [0, 1, None]


def test_icon_cache_cleanup_used_by_memory_guard(monkeypatch):
    IconExtractor.clear_cache()
    IconExtractor._cache = OrderedDict([("expired", object())])
    IconExtractor._cache_timestamps = {"expired": 1.0}
    monkeypatch.setattr(IconExtractor, "_CACHE_TTL_SECONDS", 10)
    monkeypatch.setattr(icon_module.time, "time", lambda: 20.0)

    MemoryGuard()._cleanup_icon_cache("light")

    assert IconExtractor._cache == OrderedDict()
    assert IconExtractor._cache_timestamps == {}
