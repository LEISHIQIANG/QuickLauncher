"""Shared network guardrails for user-supplied HTTP requests."""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_MAX_REDIRECTS = 5

# When set to "1", DNS-resolved IP validation is skipped to support
# proxy tools (Surge, Clash, etc.) that use Fake IP mode (198.18.0.0/15).
# Other SSRF protections (scheme check, localhost block, header sanitization)
# remain active.  Enable this only in trusted proxy environments.
_TRUST_PROXY_ENV = "QL_TRUST_PROXY"

logger = logging.getLogger(__name__)

SENSITIVE_REQUEST_HEADERS = {
    "authorization",
    "cookie",
    "host",
    "proxy-authorization",
}


class UnsafeUrlError(ValueError):
    """Raised when a user-supplied URL targets a blocked network location."""


class ResponseTooLargeError(ValueError):
    """Raised when a response exceeds the caller's configured byte limit."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def is_urlopen_patched() -> bool:
    return getattr(urllib.request.urlopen, "__module__", "") != "urllib.request"


def normalize_http_url(url: str) -> str:
    normalized = str(url or "").strip()
    if normalized and not normalized.startswith(("http://", "https://")):
        normalized = "https://" + normalized
    return normalized


def sanitize_headers(headers: dict[str, Any]) -> dict[str, str]:
    sanitized = {}
    for key, value in dict(headers or {}).items():
        name = str(key or "").strip()
        if not name:
            continue
        if name.lower() in SENSITIVE_REQUEST_HEADERS:
            raise UnsafeUrlError(f"blocked sensitive request header: {name}")
        sanitized[name] = str(value)
    return sanitized


def _is_trust_proxy_mode() -> bool:
    """Check if proxy trust mode is enabled via environment variable."""
    return os.environ.get(_TRUST_PROXY_ENV, "").strip() in ("1", "true", "yes")


def validate_public_http_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https") or not parsed.netloc:
        raise UnsafeUrlError("unsupported URL")

    host = parsed.hostname or ""
    if not host:
        raise UnsafeUrlError("missing host")
    if host.lower() == "localhost" or host.lower().endswith(".localhost"):
        raise UnsafeUrlError("local hosts are blocked")

    literal_ip = None
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        _validate_public_ip(literal_ip, host)
        return url

    # Skip DNS-level IP validation when proxy trust mode is enabled.
    # Proxy tools (Surge, Clash, etc.) in Fake IP mode return 198.18.0.0/15
    # addresses from DNS queries, which Python's ipaddress module classifies
    # as is_private=True.  This would trigger the SSRF guard and block all
    # outbound requests.  When QL_TRUST_PROXY=1, we trust that the proxy
    # will route traffic correctly and only keep non-DNS protections.
    if _is_trust_proxy_mode():
        return url

    try:
        port = parsed.port or (443 if scheme == "https" else 80)
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"host resolution failed: {host}") from exc

    for _family, _, _, _, sockaddr in addresses:
        address = str(sockaddr[0])
        try:
            resolved_ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeUrlError(f"invalid resolved address: {address}") from exc
        _validate_public_ip(resolved_ip, address)
    return url


def safe_urlopen(
    request_or_url,
    *,
    timeout: float,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    context=None,
):
    original_url = (
        request_or_url.full_url if isinstance(request_or_url, urllib.request.Request) else str(request_or_url)
    )
    current_url = validate_public_http_url(original_url)
    headers = (
        dict(getattr(request_or_url, "headers", {}) or {}) if isinstance(request_or_url, urllib.request.Request) else {}
    )
    data = getattr(request_or_url, "data", None) if isinstance(request_or_url, urllib.request.Request) else None
    method = getattr(request_or_url, "method", None) if isinstance(request_or_url, urllib.request.Request) else None
    handlers: list[Any] = [_NoRedirectHandler()]
    if not _is_trust_proxy_mode():
        # Keep the verified peer equal to the requested destination.  Proxy
        # environments require the explicit QL_TRUST_PROXY opt-in below.
        handlers.append(urllib.request.ProxyHandler({}))
    if context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=context))
    opener = urllib.request.build_opener(*handlers)

    for _ in range(max_redirects + 1):
        request = urllib.request.Request(current_url, data=data, headers=headers, method=method)
        try:
            response = opener.open(request, timeout=timeout)
            _validate_response_peer(response)
            return response
        except urllib.error.HTTPError as exc:
            _validate_response_peer(exc)
            if exc.code not in (301, 302, 303, 307, 308):
                raise
            location = exc.headers.get("Location")
            if not location:
                raise
            current_url = validate_public_http_url(urllib.parse.urljoin(current_url, location))
            if exc.code == 303:
                data = None
                method = "GET"
    raise UnsafeUrlError("too many redirects")


def _validate_response_peer(response: Any) -> None:
    """Validate the address actually used by urllib after DNS resolution.

    URL validation happens before the socket is opened.  Inspecting the peer
    closes the DNS-rebinding window between that validation and connect().
    Trusted-proxy mode is an explicit opt-in because the visible peer is the
    proxy rather than the destination host.
    """
    if _is_trust_proxy_mode():
        return
    peer = _response_peer_address(response)
    if not peer:
        _close_response_quietly(response)
        raise UnsafeUrlError("unable to verify connected peer address")
    try:
        peer_ip = ipaddress.ip_address(peer)
        _validate_public_ip(peer_ip, peer)
    except (UnsafeUrlError, ValueError):
        _close_response_quietly(response)
        raise UnsafeUrlError(f"blocked connected peer address: {peer}") from None


def _response_peer_address(response: Any) -> str:
    queue = [response]
    seen: set[int] = set()
    for _ in range(16):
        if not queue:
            break
        current = queue.pop(0)
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        getpeername = getattr(current, "getpeername", None)
        if callable(getpeername):
            try:
                peer = getpeername()
                if isinstance(peer, tuple) and peer:
                    return str(peer[0]).split("%", 1)[0]
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                logger.debug("读取响应 peer 地址失败: %s", exc)
        for attr in ("fp", "raw", "_sock", "sock", "_connection", "connection"):
            try:
                child = getattr(current, attr, None)
            except (AttributeError, OSError, RuntimeError):
                child = None
            if child is not None:
                queue.append(child)
    return ""


def _close_response_quietly(response: Any) -> None:
    try:
        response.close()
    except (AttributeError, OSError, RuntimeError) as exc:
        logger.debug("关闭不安全网络响应失败: %s", exc)


def read_limited_response(response, limit_bytes: int) -> bytes:
    try:
        data = response.read(limit_bytes + 1)
    except TypeError:
        data = response.read()
    if len(data or b"") > limit_bytes:
        raise ResponseTooLargeError(f"response exceeds {limit_bytes} bytes")
    return data or b""


def _validate_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, label: str) -> None:
    from .native_services import _QLValidateEngine

    engine = _QLValidateEngine.get()
    if not engine.is_public_ip_string(str(ip)):
        raise UnsafeUrlError(f"blocked private address: {label}")
