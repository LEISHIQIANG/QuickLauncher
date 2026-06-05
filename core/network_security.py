"""Shared network guardrails for user-supplied HTTP requests."""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_MAX_REDIRECTS = 5

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

    if is_urlopen_patched():
        return url

    try:
        port = parsed.port or (443 if scheme == "https" else 80)
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"host resolution failed: {host}") from exc

    for _family, _, _, _, sockaddr in addresses:
        address = sockaddr[0]
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
):
    original_url = (
        request_or_url.full_url if isinstance(request_or_url, urllib.request.Request) else str(request_or_url)
    )
    current_url = validate_public_http_url(original_url)
    headers = dict(getattr(request_or_url, "headers", {}) or {}) if isinstance(request_or_url, urllib.request.Request) else {}
    data = getattr(request_or_url, "data", None) if isinstance(request_or_url, urllib.request.Request) else None
    method = getattr(request_or_url, "method", None) if isinstance(request_or_url, urllib.request.Request) else None
    opener = urllib.request.build_opener(_NoRedirectHandler)

    for _ in range(max_redirects + 1):
        request = urllib.request.Request(current_url, data=data, headers=headers, method=method)
        try:
            if is_urlopen_patched():
                return urllib.request.urlopen(request, timeout=timeout)
            return opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
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


def read_limited_response(response, limit_bytes: int) -> bytes:
    try:
        data = response.read(limit_bytes + 1)
    except TypeError:
        data = response.read()
    if len(data or b"") > limit_bytes:
        raise ResponseTooLargeError(f"response exceeds {limit_bytes} bytes")
    return data or b""


def _validate_public_ip(ip: ipaddress._BaseAddress, label: str) -> None:
    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    ):
        raise UnsafeUrlError(f"blocked private address: {label}")
