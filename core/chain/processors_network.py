"""Network processors for action chains."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from core.command_registry import CommandResult
from core.network_security import (
    ResponseTooLargeError,
    UnsafeUrlError,
    normalize_http_url,
    read_limited_response,
    safe_urlopen,
    sanitize_headers,
)
from core.path_security import assert_safe_user_path, resolve_under

HTTP_RESPONSE_MAX_BYTES = 5 * 1024 * 1024


def http_get(values: dict[str, str]) -> CommandResult:
    url = normalize_http_url(values.get("url", ""))
    headers_str = values.get("headers", "").strip()
    headers = {}
    if headers_str:
        headers = sanitize_headers(json.loads(headers_str))
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with safe_urlopen(req, timeout=10) as response:
            text = read_limited_response(response, HTTP_RESPONSE_MAX_BYTES).decode("utf-8", errors="replace")
            status_code = str(getattr(response, "status", "") or response.getcode() or "")
            response_headers = dict(response.headers.items())
    except (UnsafeUrlError, ResponseTooLargeError) as exc:
        return CommandResult(success=False, message=str(exc), error=str(exc))
    return _ok_outputs(
        {
            "output": text,
            "status_code": status_code,
            "headers": response_headers,
            "length": str(len(text)),
            "empty": _bool_text(not bool(text)),
        }
    )


def http_post(values: dict[str, str]) -> CommandResult:
    url = normalize_http_url(values.get("url", ""))
    data_str = values.get("data", "").strip()
    headers_str = values.get("headers", "").strip()
    headers = {}
    if headers_str:
        headers = sanitize_headers(json.loads(headers_str))

    data_bytes = data_str.encode("utf-8")
    if "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
    try:
        with safe_urlopen(req, timeout=10) as response:
            text = read_limited_response(response, HTTP_RESPONSE_MAX_BYTES).decode("utf-8", errors="replace")
            status_code = str(getattr(response, "status", "") or response.getcode() or "")
            response_headers = dict(response.headers.items())
    except (UnsafeUrlError, ResponseTooLargeError) as exc:
        return CommandResult(success=False, message=str(exc), error=str(exc))
    return _ok_outputs(
        {
            "output": text,
            "status_code": status_code,
            "headers": response_headers,
            "length": str(len(text)),
            "empty": _bool_text(not bool(text)),
        }
    )


def http_download(values: dict[str, str]) -> str:
    url = normalize_http_url(values.get("url", ""))
    save_dir_value = values.get("save_dir", "").strip()
    if not save_dir_value:
        raise ValueError("缺少保存目录")
    save_dir = assert_safe_user_path(save_dir_value, operation="download directory")

    parsed_url = urllib.parse.urlparse(url)
    filename = os.path.basename(parsed_url.path) or "downloaded_file"

    if not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)

    filepath = resolve_under(save_dir, save_dir / filename)
    request = urllib.request.Request(url, method="GET")
    with safe_urlopen(request, timeout=10) as response:
        content = read_limited_response(response, HTTP_RESPONSE_MAX_BYTES)
    with open(filepath, "wb") as handle:
        handle.write(content)
    return str(filepath)


def _ok_outputs(outputs: dict[str, Any]) -> CommandResult:
    raw_outputs = {str(k): v for k, v in dict(outputs or {}).items() if str(k).strip()}
    normalized = {str(k): _value_to_text(v) for k, v in raw_outputs.items()}
    first = next(iter(normalized.values()), "")
    return CommandResult(
        success=True,
        message=first,
        display_type="text",
        payload={"stdout": first, "outputs": normalized, "raw_outputs": raw_outputs},
    )


def _value_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(_value_to_text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"
