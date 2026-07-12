"""Tests for core.preprocessing.rate_limiter."""

from __future__ import annotations

from core.preprocessing.rate_limiter import (
    CommandRateLimiter,
    get_rate_limiter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_limiter(**kwargs) -> CommandRateLimiter:
    """Create a limiter with small limits for easy testing."""
    defaults = {"global_limit": 5, "per_shortcut_limit": 3, "admin_limit": 2, "window_seconds": 60}
    defaults.update(kwargs)
    return CommandRateLimiter(**defaults)


# ---------------------------------------------------------------------------
# check_rate_limit - basic
# ---------------------------------------------------------------------------


def test_check_allows_when_empty():
    lim = _make_limiter()
    allowed, reason = lim.check_rate_limit()
    assert allowed is True
    assert reason == ""


def test_check_allows_with_shortcut():
    lim = _make_limiter()
    allowed, reason = lim.check_rate_limit(shortcut_id="s1")
    assert allowed is True


def test_check_blocks_when_global_full(monkeypatch):
    lim = _make_limiter(global_limit=2)
    t = [1000.0]

    def fake_time():
        return t[0]

    monkeypatch.setattr("core.preprocessing.rate_limiter.time.time", fake_time)

    lim.record_execution("a")
    t[0] += 0.01
    lim.record_execution("b")
    t[0] += 0.01

    allowed, reason = lim.check_rate_limit()
    assert allowed is False
    assert "全局" in reason


def test_check_blocks_when_shortcut_full(monkeypatch):
    lim = _make_limiter(per_shortcut_limit=2)
    t = [1000.0]

    monkeypatch.setattr("core.preprocessing.rate_limiter.time.time", lambda: t[0])

    lim.record_execution("s1")
    t[0] += 0.01
    lim.record_execution("s1")
    t[0] += 0.01

    allowed, reason = lim.check_rate_limit(shortcut_id="s1")
    assert allowed is False
    assert "快捷方式" in reason


def test_check_admin_uses_admin_limit(monkeypatch):
    lim = _make_limiter(per_shortcut_limit=10, admin_limit=2)
    t = [1000.0]

    monkeypatch.setattr("core.preprocessing.rate_limiter.time.time", lambda: t[0])

    lim.record_execution("s1")
    t[0] += 0.01
    lim.record_execution("s1")
    t[0] += 0.01

    allowed, _ = lim.check_rate_limit(shortcut_id="s1", is_admin=True)
    assert allowed is False

    # Non-admin with per_shortcut_limit=10 should still be allowed
    lim2 = _make_limiter(per_shortcut_limit=10, admin_limit=2)
    t2 = [1000.0]
    monkeypatch.setattr("core.preprocessing.rate_limiter.time.time", lambda: t2[0])
    lim2.record_execution("s1")
    t2[0] += 0.01
    lim2.record_execution("s1")
    t2[0] += 0.01
    allowed2, _ = lim2.check_rate_limit(shortcut_id="s1", is_admin=False)
    assert allowed2 is True


# ---------------------------------------------------------------------------
# check_rate_limit - window expiry
# ---------------------------------------------------------------------------


def test_old_tokens_expire(monkeypatch):
    lim = _make_limiter(global_limit=1, window_seconds=10)
    t = [1000.0]

    monkeypatch.setattr("core.preprocessing.rate_limiter.time.time", lambda: t[0])

    lim.record_execution()
    t[0] += 0.01

    # Now blocked
    allowed, _ = lim.check_rate_limit()
    assert allowed is False

    # Advance past window
    t[0] += 11
    allowed, _ = lim.check_rate_limit()
    assert allowed is True


def test_shortcut_tokens_expire(monkeypatch):
    lim = _make_limiter(per_shortcut_limit=1, window_seconds=5)
    t = [1000.0]

    monkeypatch.setattr("core.preprocessing.rate_limiter.time.time", lambda: t[0])

    lim.record_execution("s1")
    t[0] += 0.01

    allowed, _ = lim.check_rate_limit(shortcut_id="s1")
    assert allowed is False

    t[0] += 6
    allowed, _ = lim.check_rate_limit(shortcut_id="s1")
    assert allowed is True


# ---------------------------------------------------------------------------
# record_execution
# ---------------------------------------------------------------------------


def test_record_execution_adds_to_global():
    lim = _make_limiter()
    lim.record_execution()
    assert len(lim._global_tokens) == 1


def test_record_execution_adds_to_shortcut():
    lim = _make_limiter()
    lim.record_execution("s1")
    assert len(lim._shortcut_tokens["s1"]) == 1
    assert len(lim._global_tokens) == 1


def test_record_execution_empty_shortcut_only_global():
    lim = _make_limiter()
    lim.record_execution("")  # empty shortcut_id
    assert len(lim._global_tokens) == 1
    assert "" not in lim._shortcut_tokens


def test_record_execution_multiple_shortcuts():
    lim = _make_limiter()
    lim.record_execution("a")
    lim.record_execution("b")
    lim.record_execution("a")
    assert len(lim._shortcut_tokens["a"]) == 2
    assert len(lim._shortcut_tokens["b"]) == 1
    assert len(lim._global_tokens) == 3


# ---------------------------------------------------------------------------
# get_remaining_quota
# ---------------------------------------------------------------------------


def test_get_remaining_quota_shortcut(monkeypatch):
    lim = _make_limiter(per_shortcut_limit=3)
    t = [1000.0]
    monkeypatch.setattr("core.preprocessing.rate_limiter.time.time", lambda: t[0])

    assert lim.get_remaining_quota("s1") == 3
    lim.record_execution("s1")
    t[0] += 0.01
    assert lim.get_remaining_quota("s1") == 2
    lim.record_execution("s1")
    t[0] += 0.01
    assert lim.get_remaining_quota("s1") == 1


def test_get_remaining_quota_global(monkeypatch):
    lim = _make_limiter(global_limit=5)
    t = [1000.0]
    monkeypatch.setattr("core.preprocessing.rate_limiter.time.time", lambda: t[0])

    assert lim.get_remaining_quota() == 5
    lim.record_execution()
    t[0] += 0.01
    assert lim.get_remaining_quota() == 4


def test_get_remaining_quota_admin(monkeypatch):
    lim = _make_limiter(per_shortcut_limit=10, admin_limit=2)
    t = [1000.0]
    monkeypatch.setattr("core.preprocessing.rate_limiter.time.time", lambda: t[0])

    assert lim.get_remaining_quota("s1", is_admin=True) == 2
    lim.record_execution("s1")
    t[0] += 0.01
    assert lim.get_remaining_quota("s1", is_admin=True) == 1


def test_get_remaining_quota_never_negative(monkeypatch):
    lim = _make_limiter(per_shortcut_limit=1, global_limit=1)
    t = [1000.0]
    monkeypatch.setattr("core.preprocessing.rate_limiter.time.time", lambda: t[0])

    lim.record_execution("s1")
    t[0] += 0.01
    lim.record_execution("s1")
    t[0] += 0.01

    assert lim.get_remaining_quota("s1") == 0


def test_get_remaining_quota_expired_tokens_restored(monkeypatch):
    lim = _make_limiter(per_shortcut_limit=3, window_seconds=5)
    t = [1000.0]
    monkeypatch.setattr("core.preprocessing.rate_limiter.time.time", lambda: t[0])

    lim.record_execution("s1")
    t[0] += 0.01
    assert lim.get_remaining_quota("s1") == 2

    # Advance past window
    t[0] += 6
    assert lim.get_remaining_quota("s1") == 3


# ---------------------------------------------------------------------------
# get_rate_limiter singleton
# ---------------------------------------------------------------------------


def test_get_rate_limiter_returns_same_instance():
    import core.preprocessing.rate_limiter as mod

    # Reset singleton
    mod._default_limiter = None

    a = get_rate_limiter()
    b = get_rate_limiter()
    assert a is b
    assert isinstance(a, CommandRateLimiter)

    # Cleanup
    mod._default_limiter = None


def test_get_rate_limiter_default_params():
    import core.preprocessing.rate_limiter as mod

    mod._default_limiter = None

    limiter = get_rate_limiter()
    assert limiter.global_limit == 100
    assert limiter.per_shortcut_limit == 10
    assert limiter.admin_limit == 5
    assert limiter.window_seconds == 60

    mod._default_limiter = None
