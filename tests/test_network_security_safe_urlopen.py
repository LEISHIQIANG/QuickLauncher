"""Tests for the P1-04 hardened :func:`safe_urlopen`.

These tests assert that the production path always goes through the
``_NoRedirectHandler``-equipped opener, even when
:func:`urllib.request.urlopen` has been monkey-patched.  The previous
behaviour fell back to the patched ``urlopen`` and skipped
DNS / private-IP validation on redirect targets — a real SSRF concern
under the in-process plugin model.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from core import network_security
from core.network_security import (
    UnsafeUrlError,
    is_urlopen_patched,
    safe_urlopen,
    validate_public_http_url,
)


class _FakeResponse:
    def __init__(self, peer="8.8.8.8"):
        self._sock = self
        self.peer = peer
        self.closed = False

    def getpeername(self):
        return (self.peer, 443)

    def close(self):
        self.closed = True


def test_validate_public_http_url_rejects_localhost():
    with pytest.raises(UnsafeUrlError):
        validate_public_http_url("http://localhost/foo")


def test_validate_public_http_url_rejects_private_ip():
    with pytest.raises(UnsafeUrlError):
        validate_public_http_url("http://127.0.0.1/")


def test_validate_public_http_url_rejects_private_literal_v6():
    with pytest.raises(UnsafeUrlError):
        validate_public_http_url("http://[fe80::1]/")


def test_is_urlopen_patched_detects_monkeypatch(monkeypatch):
    assert is_urlopen_patched() is False
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **kw: None,
    )
    assert is_urlopen_patched() is True


def test_safe_urlopen_validates_initial_url_even_when_urlopen_patched(monkeypatch):
    """P1-04: a patched urlopen must not bypass the guarded opener."""

    def fake_urlopen(*_args, **_kwargs):
        raise AssertionError("safe_urlopen must not call patched urlopen")

    class _FakeOpener:
        def open(self, request, timeout=0):
            assert request.full_url == "http://8.8.8.8/start"
            return _FakeResponse()

    def _make_opener(*_handlers):
        return _FakeOpener()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(network_security.urllib.request, "build_opener", _make_opener)

    assert safe_urlopen("http://8.8.8.8/start", timeout=1) is not None


def test_safe_urlopen_validates_redirect_targets_when_urlopen_patched(monkeypatch):
    """P1-04: redirect validation still runs while urlopen is patched."""

    def fake_urlopen(*_args, **_kwargs):
        raise AssertionError("safe_urlopen must not call patched urlopen")

    class _FakeOpener:
        def open(self, request, timeout=0):
            raise urllib.error.HTTPError(
                request.full_url,
                301,
                "Moved",
                {"Location": "http://127.0.0.1/admin"},
                None,
            )

    def _make_opener(*_handlers):
        return _FakeOpener()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(network_security.urllib.request, "build_opener", _make_opener)

    with pytest.raises(UnsafeUrlError):
        safe_urlopen("http://8.8.8.8/start", timeout=1)


def test_safe_urlopen_rejects_redirect_to_private_ip(monkeypatch):
    """P1-04: a redirect to a private IP must raise UnsafeUrlError."""

    class _FakeOpener:
        def open(self, request, timeout=0):
            raise urllib.error.HTTPError(
                request.full_url,
                302,
                "Found",
                {"Location": "http://10.0.0.1/admin"},
                None,
            )

    def _make_opener(*_handlers):
        return _FakeOpener()

    monkeypatch.setattr(urllib.request, "build_opener", _make_opener)
    # Re-bind the module-level build_opener reference used inside
    # network_security.  Monkeypatching urllib.request.build_opener
    # would be cleaner but the module captured a direct reference at
    # import time, so we patch the symbol on the module instead.
    monkeypatch.setattr(network_security.urllib.request, "build_opener", _make_opener)

    with pytest.raises(UnsafeUrlError):
        safe_urlopen("https://example.com/start", timeout=1)


def test_safe_urlopen_rejects_dns_rebinding_to_private_connected_peer(monkeypatch):
    response = _FakeResponse("127.0.0.1")

    class _FakeOpener:
        def open(self, request, timeout=0):
            return response

    monkeypatch.setattr(network_security.urllib.request, "build_opener", lambda *_handlers: _FakeOpener())

    with pytest.raises(UnsafeUrlError, match="connected peer"):
        safe_urlopen("http://8.8.8.8/start", timeout=1)
    assert response.closed is True


def test_safe_urlopen_fails_closed_when_connected_peer_is_unobservable(monkeypatch):
    class _FakeOpener:
        def open(self, request, timeout=0):
            return object()

    monkeypatch.setattr(network_security.urllib.request, "build_opener", lambda *_handlers: _FakeOpener())

    with pytest.raises(UnsafeUrlError, match="unable to verify"):
        safe_urlopen("http://8.8.8.8/start", timeout=1)
