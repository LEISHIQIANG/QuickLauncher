"""URL execution helpers for ShortcutExecutor."""

from __future__ import annotations

import logging
import os
import re
import socket
import subprocess
import time
import webbrowser
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .clipboard_service import clipboard_service
from .command_variables import fetch_public_wan_ipv4, get_default_lan_ipv4
from .data_models import ShortcutItem

logger = logging.getLogger(__name__)
ShortcutExecutor = None

_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_TOKEN_RE = re.compile(r"(?<!\{)\{\{([^{}\r\n]+)\}\}(?!\})")
_ESCAPED_LEFT = "\0QL_URL_ESCAPED_LEFT\0"
_ESCAPED_RIGHT = "\0QL_URL_ESCAPED_RIGHT\0"
_ALLOWED_SCHEMES = {
    "http",
    "https",
    "file",
    "mailto",
    "tel",
    "ms-settings",
    "steam",
    "vscode",
    "obsidian",
}
_BLOCKED_SCHEMES = {"javascript", "data", "vbscript"}
_URL_LATENCY_TIMEOUT_MS = 5000
_URL_LATENCY_FAST_MS = 500
_URL_LATENCY_USER_AGENT = "QuickLauncher/1.0 URL latency probe"


class UrlExecutionMixin:
    @staticmethod
    def _execute_url(shortcut: ShortcutItem) -> tuple[bool, str]:
        """Execute a URL shortcut."""
        raw_url = shortcut.url or ""
        if not raw_url.strip():
            logger.warning("URL is empty")
            return False, "URL为空"

        url, error = ShortcutExecutor._prepare_url(raw_url, getattr(shortcut, "_runtime_input_values", None))
        if error:
            return False, error

        browser_path = (getattr(shortcut, "preferred_browser_path", "") or "").strip()
        browser_args = (getattr(shortcut, "preferred_browser_args", "") or "").strip()

        try:
            if browser_path:
                return ShortcutExecutor._open_url_with_browser(
                    browser_path,
                    browser_args,
                    url,
                    run_as_admin=bool(getattr(shortcut, "run_as_admin", False)),
                )

            launched, launch_error = ShortcutExecutor._launch_with_privilege(
                url,
                run_as_admin=bool(getattr(shortcut, "run_as_admin", False)),
            )
            if launched:
                logger.info("Opened URL: %s", url)
                return True, ""

            if launch_error:
                return False, launch_error

            if bool(getattr(shortcut, "run_as_admin", False)) or bool(
                getattr(ShortcutExecutor, "_is_launch_context_elevated", lambda: False)()
            ):
                return False, launch_error or "URL launch failed across privilege boundary."

            opened = webbrowser.open(url)
            if not opened:
                return False, "系统未能调用默认浏览器"
            logger.info("Opened URL: %s", url)
            return True, ""
        except Exception as e:
            error_msg = f"打开URL失败: {e}"
            logger.error(error_msg)
            return False, error_msg

    @staticmethod
    def _prepare_url(raw_url: str, input_values: dict | None = None) -> tuple[str, str]:
        try:
            helper = ShortcutExecutor or UrlExecutionMixin
            expanded = helper._resolve_url_variables(raw_url.strip(), input_values or {})
            normalized = helper._normalize_url(expanded)
            error = helper._validate_url(normalized)
            return (normalized, error)
        except Exception as e:
            return "", f"URL解析失败: {e}"

    @staticmethod
    def _normalize_url(url: str) -> str:
        value = (url or "").strip()
        if not value:
            return value
        if _SCHEME_RE.match(value):
            return value
        return "https://" + value

    @staticmethod
    def classify_url_latency(latency_ms: int) -> str:
        if latency_ms is None or latency_ms < 0 or latency_ms > _URL_LATENCY_TIMEOUT_MS:
            return "red"
        if latency_ms <= _URL_LATENCY_FAST_MS:
            return "green"
        return "yellow"

    @staticmethod
    def test_url_latency(
        raw_url: str,
        input_values: dict | None = None,
        timeout_ms: int = _URL_LATENCY_TIMEOUT_MS,
    ) -> dict:
        """Probe an http(s) URL and return a UI-friendly latency result."""
        timeout_ms = min(max(int(timeout_ms or _URL_LATENCY_TIMEOUT_MS), 1), _URL_LATENCY_TIMEOUT_MS)
        url, error = UrlExecutionMixin._prepare_url(raw_url, input_values or {})
        if error:
            return UrlExecutionMixin._latency_result(False, -1, "red", error, url)

        parsed = urlparse(url)
        if (parsed.scheme or "").lower() not in {"http", "https"}:
            return UrlExecutionMixin._latency_result(
                False,
                -1,
                "red",
                "延迟测试仅支持 http/https 网址",
                url,
            )

        timeout_seconds = timeout_ms / 1000.0
        start = time.perf_counter()
        request = Request(url, method="HEAD", headers={"User-Agent": _URL_LATENCY_USER_AGENT})

        try:
            response = urlopen(request, timeout=timeout_seconds)
            try:
                if hasattr(response, "read"):
                    response.read(0)
            finally:
                close = getattr(response, "close", None)
                if close:
                    close()
        except HTTPError as e:
            elapsed_ms = UrlExecutionMixin._elapsed_latency_ms(start)
            if e.code in (405, 501):
                return UrlExecutionMixin._test_url_latency_get(url, start, timeout_seconds, timeout_ms)
            if elapsed_ms > timeout_ms:
                return UrlExecutionMixin._latency_result(False, -1, "red", "访问超时", url)
            return UrlExecutionMixin._latency_result(
                True,
                elapsed_ms,
                UrlExecutionMixin.classify_url_latency(elapsed_ms),
                f"HTTP {e.code}，已收到响应",
                url,
            )
        except TimeoutError:
            return UrlExecutionMixin._latency_result(False, -1, "red", "访问超时", url)
        except URLError as e:
            reason = getattr(e, "reason", e)
            message = "访问超时" if isinstance(reason, TimeoutError | socket.timeout) else f"无法访问: {reason}"
            return UrlExecutionMixin._latency_result(False, -1, "red", message, url)
        except Exception as e:
            return UrlExecutionMixin._latency_result(False, -1, "red", f"无法访问: {e}", url)

        elapsed_ms = UrlExecutionMixin._elapsed_latency_ms(start)
        if elapsed_ms > timeout_ms:
            return UrlExecutionMixin._latency_result(False, -1, "red", "访问超时", url)
        return UrlExecutionMixin._latency_result(
            True,
            elapsed_ms,
            UrlExecutionMixin.classify_url_latency(elapsed_ms),
            "",
            url,
        )

    @staticmethod
    def _test_url_latency_get(url: str, start: float, timeout_seconds: float, timeout_ms: int) -> dict:
        try:
            request = Request(url, method="GET", headers={"User-Agent": _URL_LATENCY_USER_AGENT})
            response = urlopen(request, timeout=timeout_seconds)
            try:
                if hasattr(response, "read"):
                    response.read(1)
            finally:
                close = getattr(response, "close", None)
                if close:
                    close()
        except (HTTPError, URLError, TimeoutError) as e:
            elapsed_ms = UrlExecutionMixin._elapsed_latency_ms(start)
            if isinstance(e, HTTPError) and elapsed_ms <= timeout_ms:
                return UrlExecutionMixin._latency_result(
                    True,
                    elapsed_ms,
                    UrlExecutionMixin.classify_url_latency(elapsed_ms),
                    f"HTTP {e.code}，已收到响应",
                    url,
                )
            return UrlExecutionMixin._latency_result(False, -1, "red", "无法访问或超时", url)
        except Exception as e:
            return UrlExecutionMixin._latency_result(False, -1, "red", f"无法访问: {e}", url)

        elapsed_ms = UrlExecutionMixin._elapsed_latency_ms(start)
        if elapsed_ms > timeout_ms:
            return UrlExecutionMixin._latency_result(False, -1, "red", "访问超时", url)
        return UrlExecutionMixin._latency_result(
            True,
            elapsed_ms,
            UrlExecutionMixin.classify_url_latency(elapsed_ms),
            "",
            url,
        )

    @staticmethod
    def _elapsed_latency_ms(start: float) -> int:
        return max(0, int(round((time.perf_counter() - start) * 1000)))

    @staticmethod
    def _latency_result(success: bool, latency_ms: int, color: str, error: str, url: str) -> dict:
        return {
            "success": bool(success),
            "latency_ms": int(latency_ms),
            "color": color,
            "error": error or "",
            "url": url or "",
            "timeout_ms": _URL_LATENCY_TIMEOUT_MS,
        }

    @staticmethod
    def _validate_url(url: str) -> str:
        if not url:
            return "URL为空"
        if any(ch.isspace() for ch in url):
            return "URL包含空格，请使用参数变量或编码后的地址"

        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        if not scheme:
            return "URL缺少协议"
        if scheme in _BLOCKED_SCHEMES:
            return f"不支持的URL协议: {scheme}"
        if scheme in {"http", "https"} and not parsed.netloc:
            return "URL缺少域名"
        return ""

    @staticmethod
    def _resolve_url_variables(
        text: str,
        input_values: dict[str, str],
        *,
        allow_url_placeholder: bool = False,
    ) -> str:
        if not text:
            return text

        guarded = text.replace("{{{{", _ESCAPED_LEFT).replace("}}}}", _ESCAPED_RIGHT)
        now = datetime.now()

        def repl(match: re.Match) -> str:
            spec = match.group(1).strip()
            base = spec[:-2].strip() if spec.endswith(":q") else spec
            base_key = base.lower()
            if allow_url_placeholder and base_key == "url":
                return match.group(0)
            if base_key == "clipboard":
                value = clipboard_service.read_text_win32()
            elif base_key == "date":
                value = now.strftime("%Y-%m-%d")
            elif base_key == "time":
                value = now.strftime("%H:%M:%S")
            elif base_key == "lan_ip":
                value = get_default_lan_ipv4()
            elif base_key == "wan_ip":
                value = fetch_public_wan_ipv4()
            elif base_key == "input":
                value = input_values.get("input", input_values.get("", ""))
            elif base_key.startswith("input:"):
                prompt = base[6:].strip()
                value = input_values.get(prompt, "")
            else:
                raise ValueError("未知变量: {{" + spec + "}}")
            return quote(value or "", safe="")

        return _TOKEN_RE.sub(repl, guarded).replace(_ESCAPED_LEFT, "{{").replace(_ESCAPED_RIGHT, "}}")

    @staticmethod
    def _open_url_with_browser(
        browser_path: str,
        browser_args: str,
        url: str,
        run_as_admin: bool = False,
    ) -> tuple[bool, str]:
        if not os.path.exists(browser_path):
            return False, f"指定浏览器不存在: {browser_path}"

        try:
            if browser_args:
                browser_args = UrlExecutionMixin._resolve_url_variables(
                    browser_args,
                    {},
                    allow_url_placeholder=True,
                )
            args = ShortcutExecutor._safe_split_args(browser_args) if browser_args else []
            if args:
                had_placeholder = any("{{url}}" in arg for arg in args)
                args = [arg.replace("{{url}}", url) for arg in args]
                if not had_placeholder and not any(arg == url for arg in args):
                    args.append(url)
            else:
                args = [url]

            directory = os.path.dirname(os.path.abspath(browser_path))
            if os.name == "nt":
                launch_fn = getattr(ShortcutExecutor, "_launch_with_privilege", None)
                if callable(launch_fn):
                    launched, launch_error = launch_fn(
                        browser_path,
                        subprocess.list2cmdline(args),
                        directory,
                        show_cmd=1,
                        run_as_admin=run_as_admin,
                    )
                    if launched:
                        return True, ""
                    if launch_error:
                        return False, launch_error

            if run_as_admin or bool(getattr(ShortcutExecutor, "_is_launch_context_elevated", lambda: False)()):
                return False, "Browser launch failed across privilege boundary."

            ShortcutExecutor._popen_silent(
                [browser_path] + args,
                cwd=directory,
                env=ShortcutExecutor._sanitized_child_env(),
                shell=False,
            )
            return True, ""
        except Exception as e:
            return False, f"指定浏览器打开失败: {e}"
