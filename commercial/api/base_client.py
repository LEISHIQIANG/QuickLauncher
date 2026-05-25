"""基础 API 客户端。供自动更新等非激活模块使用。"""

import json
import logging
import ssl
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.version import APP_VERSION

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """API 调用异常。"""


def _make_unverified_ssl_context() -> ssl.SSLContext:
    """Create an opt-in unverified SSL context for explicit development use."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class ApiClient:
    """轻量 HTTP 客户端，无第三方依赖。"""

    def __init__(self, base_url: str, timeout: int = 10, verify_ssl: bool = True):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._ssl_context = None if verify_ssl else _make_unverified_ssl_context()
        self._headers = {
            "User-Agent": f"QuickLauncher/{APP_VERSION}",
            "Content-Type": "application/json",
        }

    def get(self, path: str, params: dict = None) -> dict:
        url = f"{self._base_url}{path}"
        if params:
            qs = "&".join(
                f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()
            )
            url = f"{url}?{qs}"
        req = Request(url, headers=self._headers, method="GET")
        return self._request(req)

    def post(self, path: str, data: dict = None) -> dict:
        url = f"{self._base_url}{path}"
        body = json.dumps(data or {}).encode("utf-8")
        req = Request(url, data=body, headers=self._headers, method="POST")
        return self._request(req)

    def _request(self, req: Request) -> dict:
        try:
            with urlopen(req, timeout=self._timeout, context=self._ssl_context) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise ApiError(f"HTTP {e.code}: {body}")
        except URLError as e:
            msg = str(e.reason)
            if isinstance(e.reason, ssl.SSLError):
                msg = f"SSL 连接错误: {msg}"
            raise ApiError(f"网络错误: {msg}")
