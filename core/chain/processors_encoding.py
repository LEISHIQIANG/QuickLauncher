"""Encoding, system info, and environment processors for action chains."""

from __future__ import annotations

import base64
import html
import json
import os
import socket
import sys
import urllib.parse
from typing import Any

from core.command_registry import CommandResult

from ._proc_helpers import ok, ok_bool, string_values


def execute_extra_encoding_processor(processor_id: str, values: dict[str, Any]) -> CommandResult | None:
    """Handle encoding/decoding processors. Returns None if not an encoding processor."""
    text_values = string_values(values)

    if processor_id == "base64_encode":
        return ok(base64.b64encode(text_values.get("text", "").encode("utf-8")).decode("ascii"))
    if processor_id == "base64_decode":
        return ok(base64.b64decode(text_values.get("text", "")).decode("utf-8"))
    if processor_id == "url_encode":
        return ok(urllib.parse.quote(text_values.get("text", ""), safe=""))
    if processor_id == "url_decode":
        return ok(urllib.parse.unquote(text_values.get("text", "")))
    if processor_id == "html_encode":
        return ok(html.escape(text_values.get("text", "")))
    if processor_id == "html_decode":
        return ok(html.unescape(text_values.get("text", "")))
    if processor_id == "hex_encode":
        return ok(text_values.get("text", "").encode("utf-8").hex())
    if processor_id == "hex_decode":
        return ok(bytes.fromhex(text_values.get("text", "")).decode("utf-8"))

    return None


def execute_extra_system_processor(processor_id: str, values: dict[str, Any]) -> CommandResult | None:
    """Handle system info, network tools, and environment variable processors. Returns None if not a system processor."""
    text_values = string_values(values)

    # -- System info --
    if processor_id == "sys_platform":
        return ok(sys.platform)
    if processor_id == "sys_hostname":
        return ok(socket.gethostname())
    if processor_id == "sys_username":
        import getpass as _gp

        return ok(_gp.getuser())
    if processor_id == "sys_cpu_count":
        return ok(str(os.cpu_count() or 0))
    if processor_id == "sys_current_dir":
        return ok(os.getcwd())
    if processor_id == "sys_home_dir":
        return ok(os.path.expanduser("~"))
    if processor_id == "sys_temp_dir":
        import tempfile as _tf

        return ok(_tf.gettempdir())

    # -- Network tools --
    if processor_id == "net_ip_address":
        host = text_values.get("hostname", "") or socket.gethostname()
        return ok(socket.gethostbyname(host))
    if processor_id == "net_ping":
        host = text_values.get("host", "")
        to = float(text_values.get("timeout", "3") or "3")
        try:
            import subprocess as _sp

            if sys.platform == "win32":
                r = _sp.run(["ping", "-n", "1", "-w", str(int(to * 1000)), host], capture_output=True, timeout=to + 1)
            else:
                r = _sp.run(["ping", "-c", "1", "-W", str(int(to)), host], capture_output=True, timeout=to + 1)
            return ok_bool(r.returncode == 0)
        except Exception:
            return ok_bool(False)
    if processor_id == "net_port_check":
        host = text_values.get("host", "")
        port = int(text_values.get("port", "80") or "80")
        to = float(text_values.get("timeout", "3") or "3")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(to)
            r = sock.connect_ex((host, port))  # type: ignore[assignment]
            sock.close()
            return ok_bool(r == 0)
        except Exception:
            return ok_bool(False)
    if processor_id == "net_url_parse":
        url = text_values.get("url", "")
        p = urllib.parse.urlparse(url)
        return ok(
            json.dumps(
                {
                    "scheme": p.scheme,
                    "hostname": p.hostname or "",
                    "port": str(p.port or ""),
                    "path": p.path,
                    "query": p.query,
                    "fragment": p.fragment,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

    # -- Environment variables --
    if processor_id == "env_get":
        return ok(os.environ.get(text_values.get("key", ""), text_values.get("default", "")))
    if processor_id == "env_set":
        os.environ[text_values.get("key", "")] = text_values.get("value", "")
        return ok(text_values.get("value", ""))
    if processor_id == "env_list":
        return ok(json.dumps(dict(os.environ), ensure_ascii=False, separators=(",", ":")))
    if processor_id == "env_expand":
        return ok(os.path.expandvars(text_values.get("text", "")))

    return None
