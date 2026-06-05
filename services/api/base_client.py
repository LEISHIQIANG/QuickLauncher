"""Small JSON API client used by background service modules."""

import json
import ssl
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.version import APP_VERSION


class ApiError(Exception):
    """Raised when an API request fails."""


def _make_unverified_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _make_verified_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.load_default_certs(ssl.Purpose.SERVER_AUTH)
    return ctx


class ApiClient:
    """Minimal urllib-based JSON client with no third-party dependency."""

    def __init__(self, base_url: str, timeout: int = 10, verify_ssl: bool = True):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._ssl_context = _make_verified_ssl_context() if verify_ssl else _make_unverified_ssl_context()
        self._headers = {
            "User-Agent": f"QuickLauncher/{APP_VERSION}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get(self, path: str = "", params: dict | None = None) -> dict:
        req = Request(self._build_url(path, params), headers=self._headers, method="GET")
        return self._request(req)

    def post(self, path: str = "", data: dict | None = None) -> dict:
        body = json.dumps(data or {}).encode("utf-8")
        req = Request(self._build_url(path), data=body, headers=self._headers, method="POST")
        return self._request(req)

    def _build_url(self, path: str = "", params: dict | None = None) -> str:
        if path and not path.startswith("/"):
            path = "/" + path
        url = f"{self._base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return url

    def _request(self, req: Request) -> dict:
        try:
            with urlopen(req, timeout=self._timeout, context=self._ssl_context) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ApiError(f"HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            msg = str(exc.reason)
            if isinstance(exc.reason, ssl.SSLError):
                msg = f"SSL connection error: {msg}"
            raise ApiError(f"Network error: {msg}") from exc
        except json.JSONDecodeError as exc:
            raise ApiError(f"Invalid JSON response: {exc}") from exc
