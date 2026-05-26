"""HTTP API Tester plugin — send HTTP requests from QuickLauncher."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from core.command_registry import CommandAction, CommandResult

HISTORY_MAX = 30
REQUEST_TIMEOUT = 8
MAX_RESPONSE_SIZE = 65536
ALLOWED_SCHEMES = ("http", "https")


def register(api):
    data_dir = api.data_dir

    for method in ("get", "post", "put", "patch", "delete"):
        api.register_command(
            id=f"api_tester.{method}",
            title=f"HTTP {method.upper()}",
            aliases=[f"api-{method}", f"http-{method}"],
            description=f"发送 {method.upper()} 请求到指定 URL",
            category="开发",
            handler=lambda ctx, m=method: _handle_request(ctx, m, data_dir),
            search_terms=["api test", "http request", "接口测试", "rest api"],
        )

    api.register_command(
        id="api_tester.history",
        title="请求历史",
        aliases=["api-history", "api-his", "请求历史"],
        description="查看最近的 API 请求记录",
        category="开发",
        handler=lambda ctx: _handle_history(ctx, data_dir),
        search_terms=["request history", "api log", "请求记录"],
    )


def _history_path(data_dir: str) -> Path:
    return Path(data_dir) / "history.json"


def _load_history(data_dir: str) -> list[dict]:
    p = _history_path(data_dir)
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:
            return []
    return []


def _save_history(data_dir: str, history: list[dict]):
    p = _history_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    recent = history[-HISTORY_MAX:]
    p.write_text(json.dumps(recent, ensure_ascii=False, indent=2), "utf-8")


def _format_body(body: bytes, content_type: str) -> str:
    text = body.decode("utf-8", errors="replace")
    if "json" in content_type:
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
    elif "xml" in content_type or "html" in content_type:
        try:
            import xml.dom.minidom
            dom = xml.dom.minidom.parseString(text)
            return dom.toprettyxml(indent="  ")
        except Exception:
            pass
    return text[:MAX_RESPONSE_SIZE]


def _to_curl(url: str, method: str, body: str, headers: dict) -> str:
    parts = ["curl", "-s", "-X", method.upper()]
    for k, v in headers.items():
        if k.lower() in ("user-agent", "accept", "content-type"):
            parts.append(f"-H '{k}: {v}'")
    parts.append(f"'{url}'")
    if body:
        escaped = body.replace("'", "'\\''")
        parts.append(f"-d '{escaped}'")
    return " ".join(parts)


def _handle_request(context, method: str, data_dir: str) -> CommandResult:
    parts = (context.args_text or "").strip().split(None, 1)
    if not parts:
        return CommandResult(
            success=False,
            message=f"用法: /api-{method} <URL> [请求体]\n例如: /api-get https://api.github.com/zen",
            error="缺少 URL",
        )

    url_str = parts[0]
    body_text = parts[1] if len(parts) > 1 else ""

    if "://" not in url_str:
        url_str = "https://" + url_str

    parsed = urllib.parse.urlparse(url_str)
    if parsed.scheme not in ALLOWED_SCHEMES:
        return CommandResult(
            success=False,
            message=f"不支持的协议: {parsed.scheme}，仅允许 http/https",
            error="协议受限",
        )
    if not parsed.netloc:
        return CommandResult(
            success=False,
            message=f"URL 格式无效: {url_str}，请提供有效的主机名",
            error="URL无效",
        )

    start = time.perf_counter()
    data_bytes = body_text.encode("utf-8") if body_text and method in ("post", "put", "patch") else None

    try:
        req = urllib.request.Request(
            url_str,
            data=data_bytes,
            headers={
                "User-Agent": "QuickLauncher-API-Tester/1.0",
                "Accept": "application/json, */*",
            },
            method=method.upper(),
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            raw = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            formatted = _format_body(raw, content_type)

        status = resp.status
    except urllib.error.HTTPError as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        raw = e.read()
        content_type = e.headers.get("Content-Type", "")
        formatted = _format_body(raw, content_type)
        status = e.code
    except urllib.error.URLError as e:
        return CommandResult(
            success=False,
            message=f"请求失败: {e.reason}\nURL: {url_str}",
            error=str(e.reason),
        )
    except Exception as e:
        return CommandResult(
            success=False,
            message=f"请求异常: {e}",
            error=str(e),
        )

    curl_cmd = _to_curl(url_str, method, body_text, {
        "User-Agent": "QuickLauncher-API-Tester/1.0",
        "Accept": "application/json, */*",
    })

    try:
        hist = _load_history(data_dir)
        hist.append({
            "method": method.upper(),
            "url": url_str,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "time": datetime.now().isoformat(),
        })
        _save_history(data_dir, hist)
    except Exception:
        pass

    return CommandResult(
        success=True,
        message=formatted,
        display_type="log",
        payload={
            "window_size": "large",
            "wrap": False,
            "method": method.upper(),
            "url": url_str,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "content_type": content_type,
            "curl": curl_cmd,
        },
        actions=[
            CommandAction(type="copy", label="复制响应", value=formatted),
            CommandAction(type="copy", label="复制 curl", value=curl_cmd),
        ],
    )


def _handle_history(context, data_dir: str) -> CommandResult:
    try:
        hist = _load_history(data_dir)
    except Exception:
        hist = []

    if not hist:
        return CommandResult(success=False, message="还没有 API 请求记录", error="无记录")

    lines = [f"最近 {len(hist)} 条请求:"]
    for h in reversed(hist[-15:]):
        ts = h.get("time", "")[:19]
        lines.append(
            f"[{h['method']:6}] {h['status']}  {h['url']}  "
            f"({h.get('elapsed_ms', '-')}ms)  {ts}"
        )

    result = "\n".join(lines)
    items = [
        {
            "title": f"{h['method']} {h['status']}",
            "status": "success" if int(h.get("status", 0) or 0) < 400 else "warning",
            "detail": f"{h['url']}  ({h.get('elapsed_ms', '-')}ms)  {h.get('time', '')[:19]}",
        }
        for h in reversed(hist[-15:])
    ]
    return CommandResult(
        success=True,
        message=result,
        display_type="list",
        payload={"window_size": "medium", "items": items},
        actions=[CommandAction(type="copy", label="复制历史", value=result)],
    )
