"""Built-in command handlers for Phase 2/3 — first non-_CallbackHandler commands."""

from __future__ import annotations

import atexit
import base64
import functools
import hashlib
import io
import ipaddress
import json
import os
import platform
import re
import socket
import ssl
import tempfile
import threading
import time
import uuid
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    import qrcode
    _HAS_QRCODE = True
except ImportError:
    _HAS_QRCODE = False

from .command_registry import CommandAction, CommandContext, CommandResult



# ---------------------------------------------------------------------------
# ── /urlencode ─────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def cmd_urlencode(context: CommandContext) -> CommandResult:
    raw_text = (context.args_text or "").strip()
    clipboard = (context.clipboard_text or "").strip()
    
    is_decode = False
    target = ""
    
    first_word = raw_text.split(None, 1)[0].lower() if raw_text.split(None, 1) else ""
    if first_word in ("decode", "d", "解码"):
        is_decode = True
        parts = raw_text.split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else ""
    elif first_word in ("encode", "e", "编码"):
        is_decode = False
        parts = raw_text.split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else ""
    else:
        mode_arg = context.args.get("mode", "").lower() if context.args else ""
        if mode_arg in ("decode", "d", "解码"):
            is_decode = True
        target = raw_text
        
    if not target:
        target = clipboard
        
    if not target:
        return CommandResult(success=False, message="请输入文本或确保剪贴板有内容", error="缺少输入")
        
    if is_decode:
        try:
            decoded = urllib.parse.unquote(target)
            return CommandResult(
                success=True,
                message=decoded,
                actions=[CommandAction(type="copy", label="复制结果", value=decoded)],
            )
        except Exception:
            return CommandResult(success=False, message="URL 解码失败", error="解码失败")
    else:
        encoded = urllib.parse.quote(target, safe="")
        return CommandResult(
            success=True,
            message=encoded,
            actions=[CommandAction(type="copy", label="复制结果", value=encoded)],
        )


# ---------------------------------------------------------------------------
# ── /color ─────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int, int | None] | None:
    h = hex_str.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    elif len(h) == 4:
        h = "".join(c * 2 for c in h)
    
    if len(h) == 6:
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), None)
        except ValueError:
            return None
    elif len(h) == 8:
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
        except ValueError:
            return None
    return None


def cmd_color(context: CommandContext) -> CommandResult:
    text = (context.args_text or context.clipboard_text or "").strip()
    if not text:
        return CommandResult(success=False, message="请输入 HEX 颜色代码（如 #ff8800）", error="缺少输入")
    rgba = _hex_to_rgb(text)
    if rgba is None:
        return CommandResult(success=False, message=f"无法识别颜色: {text}", error="格式错误")
    r, g, b, a = rgba
    if a is None:
        hex_upper = f"#{r:02X}{g:02X}{b:02X}"
        hex_lower = f"#{r:02x}{g:02x}{b:02x}"
        msg = f"HEX: {hex_upper}\nRGB: rgb({r}, {g}, {b})"
        actions = [
            CommandAction(type="copy", label="复制 HEX", value=hex_lower),
            CommandAction(type="copy", label="复制 RGB", value=f"rgb({r},{g},{b})"),
        ]
    else:
        hex_upper = f"#{r:02X}{g:02X}{b:02X}{a:02X}"
        hex_lower = f"#{r:02x}{g:02x}{b:02x}{a:02x}"
        msg = f"HEX: {hex_upper}\nRGBA: rgba({r}, {g}, {b}, {a/255:.2f})"
        actions = [
            CommandAction(type="copy", label="复制 HEX", value=hex_lower),
            CommandAction(type="copy", label="复制 RGBA", value=f"rgba({r},{g},{b},{a/255:.2f})"),
        ]
    return CommandResult(
        success=True,
        message=msg,
        payload={"r": r, "g": g, "b": b, "a": a},
        actions=actions,
    )


# ---------------------------------------------------------------------------
# ── /ip ────────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def _get_primary_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)


def _get_local_ipv4_addresses() -> list[tuple[str, str]]:
    addresses: list[tuple[str, str]] = []
    seen: set[str] = set()

    try:
        import psutil

        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if getattr(addr, "family", None) != socket.AF_INET:
                    continue
                ip = getattr(addr, "address", "")
                if not ip or ip in seen:
                    continue
                try:
                    parsed = ipaddress.ip_address(ip)
                except ValueError:
                    continue
                if parsed.is_loopback or parsed.is_unspecified:
                    continue
                addresses.append((ip, iface))
                seen.add(ip)
    except Exception:
        pass

    if not addresses:
        try:
            primary = _get_primary_local_ip()
            if primary and not ipaddress.ip_address(primary).is_loopback:
                addresses.append((primary, "primary"))
        except Exception:
            pass

    return addresses


def _fetch_public_ip(timeout: float = 2.0) -> tuple[str, str]:
    endpoints = [
        ("https://api.ipify.org?format=json", "json"),
        ("https://ifconfig.me/ip", "text"),
        ("https://ipinfo.io/ip", "text"),
    ]
    last_error = ""
    for url, response_type in endpoints:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "QuickLauncher/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(4096).decode("utf-8", errors="replace").strip()
            ip_text = json.loads(raw).get("ip", "").strip() if response_type == "json" else raw.split()[0].strip()
            parsed = ipaddress.ip_address(ip_text)
            if parsed.version in (4, 6):
                return ip_text, ""
        except Exception as e:
            last_error = str(e)
    return "", last_error or "公网 IP 服务无响应"


def cmd_ip(context: CommandContext) -> CommandResult:
    mode = (context.args_text or "").strip().lower()
    want_local = mode not in ("public", "wan", "公网", "外网")
    want_public = mode not in ("local", "lan", "内网", "本机")

    local_entries: list[tuple[str, str]] = []
    primary_ip = ""
    try:
        if want_local:
            primary_ip = _get_primary_local_ip()
            local_entries = _get_local_ipv4_addresses()
    except Exception as e:
        if not want_public:
            return CommandResult(success=False, message=f"无法获取内网 IP: {e}", error="网络错误")

    public_ip = ""
    public_error = ""
    if want_public:
        public_ip, public_error = _fetch_public_ip(timeout=2.0)

    lines: list[str] = []
    actions: list[CommandAction] = []

    if want_local:
        lines.append("内网 IP:")
        if local_entries:
            for ip, iface in local_entries:
                suffix = " [当前出口]" if ip == primary_ip else ""
                lines.append(f"- {ip} ({iface}){suffix}")
            copy_local = "\n".join(ip for ip, _ in local_entries)
            actions.append(CommandAction(type="copy", label="复制内网 IP", value=copy_local))
        elif primary_ip:
            lines.append(f"- {primary_ip} [当前出口]")
            actions.append(CommandAction(type="copy", label="复制内网 IP", value=primary_ip))
        else:
            lines.append("- 未检测到可用内网 IPv4")

    if want_public:
        if lines:
            lines.append("")
        if public_ip:
            lines.append(f"公网 IP: {public_ip}")
            actions.append(CommandAction(type="copy", label="复制公网 IP", value=public_ip))
        else:
            lines.append(f"公网 IP: 获取失败（{public_error}）")

    message = "\n".join(lines).strip()
    if not message or (want_public and not public_ip and not local_entries and not primary_ip):
        return CommandResult(success=False, message=message or "无法获取 IP 信息", error=public_error or "网络错误")

    return CommandResult(
        success=True,
        message=message,
        payload={
            "local_ips": [ip for ip, _ in local_entries] or ([primary_ip] if primary_ip else []),
            "public_ip": public_ip,
            "public_error": public_error,
        },
        actions=actions,
    )


# ---------------------------------------------------------------------------
# ── /copy-path ─────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def cmd_copy_path(context: CommandContext) -> CommandResult:
    files = context.selected_files or []
    if not files:
        return CommandResult(success=False, message="未检测到资源管理器选中文件", error="缺少输入")
    mode = context.args.get("mode", "").lower() or context.args_text.strip().lower()
    if mode in ("name", "文件名"):
        parts = [os.path.basename(f) for f in files]
    elif mode in ("dir", "目录", "folder"):
        parts = [os.path.dirname(f) for f in files]
    else:
        parts = files
    result = "\n".join(parts)
    label = "复制路径" if not mode else {"name": "复制文件名", "dir": "复制目录"}.get(mode, "复制")
    return CommandResult(
        success=True,
        message=result,
        actions=[CommandAction(type="copy", label=label, value=result)],
    )


# ---------------------------------------------------------------------------
# ── /hash ──────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def _hash_file(filepath: str, algo: str) -> str:
    h = hashlib.new(algo)
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def cmd_hash(context: CommandContext) -> CommandResult:
    args = context.args_text.strip()
    algo = "md5"
    file_path = None
    
    if args:
        first_word = args.split(None, 1)[0].lower() if args.split(None, 1) else ""
        if first_word in ("md5", "sha1", "sha256"):
            algo = first_word
            file_path = args[len(first_word):].strip()
        else:
            last_word = args.rsplit(None, 1)[-1].lower() if args.rsplit(None, 1) else ""
            if last_word in ("md5", "sha1", "sha256"):
                algo = last_word
                file_path = args[:-len(last_word)].strip()
            else:
                file_path = args
                
    if file_path:
        file_path = file_path.strip('\'"')
        
    if not file_path and context.selected_files:
        file_path = context.selected_files[0]
        
    if not file_path:
        return CommandResult(success=False, message="请指定文件路径或选中文件", error="缺少输入")
    if not os.path.isfile(file_path):
        return CommandResult(success=False, message=f"文件不存在: {file_path}", error="文件未找到")
    try:
        digest = _hash_file(file_path, algo)
        return CommandResult(
            success=True,
            message=f"{algo.upper()}: {digest}",
            actions=[CommandAction(type="copy", label="复制哈希", value=digest)],
        )
    except (OSError, PermissionError) as e:
        return CommandResult(success=False, message=f"无法读取文件: {e}", error="读取失败")


# ---------------------------------------------------------------------------
# ── Phase 2 commands (previous) ────────────────────────────────────────────
# ---------------------------------------------------------------------------


def cmd_uuid(context: CommandContext) -> CommandResult:
    uid = str(uuid.uuid4())
    return CommandResult(
        success=True,
        message=uid,
        display_type="text",
        actions=[CommandAction(type="copy", label="复制", value=uid)],
    )


def cmd_timestamp(context: CommandContext) -> CommandResult:
    args = context.args_text.strip()
    if not args:
        now = datetime.now(timezone.utc)
        local = now.astimezone()
        return CommandResult(
            success=True,
            message=f"{local.strftime('%Y-%m-%d %H:%M:%S')}\n{int(now.timestamp())}",
            display_type="text",
            actions=[CommandAction(type="copy", label="复制时间戳", value=str(int(now.timestamp())))],
        )
    try:
        ts = int(args)
        if ts > 1e12:
            ts /= 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        return CommandResult(
            success=True,
            message=dt.strftime("%Y-%m-%d %H:%M:%S"),
            display_type="text",
            actions=[CommandAction(type="copy", label="复制日期", value=dt.strftime("%Y-%m-%d %H:%M:%S"))],
        )
    except (ValueError, OSError, OverflowError):
        return CommandResult(
            success=False,
            message="无效的时间戳",
            error="请输入秒级或毫秒级 Unix 时间戳",
        )


def cmd_base64(context: CommandContext) -> CommandResult:
    raw_text = (context.args_text or "").strip()
    clipboard = (context.clipboard_text or "").strip()
    
    is_decode = False
    target = ""
    
    first_word = raw_text.split(None, 1)[0].lower() if raw_text.split(None, 1) else ""
    if first_word in ("decode", "d", "解码"):
        is_decode = True
        parts = raw_text.split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else ""
    elif first_word in ("encode", "e", "编码"):
        is_decode = False
        parts = raw_text.split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else ""
    else:
        mode_arg = context.args.get("mode", "").lower() if context.args else ""
        if mode_arg in ("decode", "d", "解码"):
            is_decode = True
        target = raw_text
        
    if not target:
        target = clipboard
        
    if not target:
        return CommandResult(
            success=False,
            message="请输入文本或确保剪贴板有内容",
            error="缺少输入",
        )
        
    if len(target.encode("utf-8")) > 256 * 1024:
        return CommandResult(
            success=False,
            message="输入文本超过 256KB 限制",
            error="输入过大",
        )
        
    if is_decode:
        try:
            missing_padding = len(target) % 4
            padded_target = target
            if missing_padding:
                padded_target += '=' * (4 - missing_padding)
            decoded = base64.b64decode(padded_target.encode("utf-8")).decode("utf-8")
            return CommandResult(
                success=True,
                message=decoded,
                display_type="text",
                actions=[CommandAction(type="copy", label="复制结果", value=decoded)],
            )
        except Exception:
            return CommandResult(
                success=False,
                message="Base64 解码失败，请检查输入是否为合法的 Base64 编码",
                error="解码失败",
            )
    else:
        encoded = base64.b64encode(target.encode("utf-8")).decode("utf-8")
        return CommandResult(
            success=True,
            message=encoded,
            display_type="text",
            actions=[CommandAction(type="copy", label="复制结果", value=encoded)],
        )


# ---------------------------------------------------------------------------
# ── QR smart helpers ──────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

_URL_DETECT = re.compile(r'^(https?://|ftp://)[^\s]+$', re.I)
_qr_file_servers: dict[int, tuple] = {}
_qr_server_lock = threading.Lock()


def _qr_get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def stop_qr_file_server(port: int):
    with _qr_server_lock:
        entry = _qr_file_servers.pop(port, None)
    if entry:
        httpd = entry[0]
        try:
            httpd.shutdown()
        except Exception:
            pass


def _stop_all_qr_file_servers():
    with _qr_server_lock:
        ports = list(_qr_file_servers.keys())
    for port in ports:
        stop_qr_file_server(port)


atexit.register(_stop_all_qr_file_servers)


def _start_qr_file_server(dir_path: str, file_path: str):
    import http.server
    import socketserver

    with socketserver.TCPServer(("0.0.0.0", 0), http.server.SimpleHTTPRequestHandler) as s:
        port = s.server_address[1]

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=dir_path)
    httpd = socketserver.TCPServer(("0.0.0.0", port), handler)
    httpd.timeout = 0.5
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    with _qr_server_lock:
        _qr_file_servers[port] = (httpd, file_path, t)
    return port


# ---------------------------------------------------------------------------
# ── /qr ────────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def cmd_qr(context: CommandContext) -> CommandResult:
    if not _HAS_QRCODE:
        return CommandResult(success=False, message="二维码生成器 (qrcode) 未安装，打包时请将 qrcode 加入依赖", error="缺少 qrcode 库")
    text = context.args_text.strip() or context.clipboard_text.strip()
    if not text:
        return CommandResult(success=False, message="请输入文本或确保剪贴板有内容", error="缺少输入")
    if len(text) > 1024:
        return CommandResult(success=False, message="文本超过 1024 字符限制", error="输入过长")
    try:
        source_for_qr = text
        display_msg = text
        extra_actions: list[CommandAction] = []

        if not context.args_text.strip():
            clip = context.clipboard_text.strip()
            if _URL_DETECT.match(clip):
                source_for_qr = clip
                display_msg = f"扫码打开链接:\n{clip}"
                extra_actions.append(CommandAction(type="open_url", label="打开链接", value=clip))
            elif os.path.isfile(clip):
                file_path = clip
                filename = os.path.basename(file_path)
                dir_path = os.path.dirname(os.path.abspath(file_path))

                ip = _qr_get_local_ip()
                port = _start_qr_file_server(dir_path, file_path)

                download_url = f"http://{ip}:{port}/{urllib.parse.quote(filename)}"
                source_for_qr = download_url
                display_msg = f"扫码下载文件:\n{filename}\n服务器: {ip}:{port}"
                extra_actions.append(CommandAction(type="open_url", label="打开下载页", value=download_url))
                extra_actions.append(CommandAction(type="close_qr_server", label="关闭服务器", value=str(port)))

        qr = qrcode.QRCode(box_size=6, border=1)
        qr.add_data(source_for_qr)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(buf.read())
        tmp.close()
        actions = extra_actions + [
            CommandAction(type="open_file", label="查看图片", value=tmp.name),
            CommandAction(type="save_file", label="保存图片", value=tmp.name),
        ]
        return CommandResult(
            success=True,
            message=display_msg,
            display_type="qr",
            payload={"image_path": tmp.name, "source_text": source_for_qr},
            actions=actions,
        )
    except Exception as e:
        return CommandResult(success=False, message=f"生成二维码失败: {e}", error="生成失败")


# ---------------------------------------------------------------------------
# ── /plugin management commands ────────────────────────────────────────────
# ---------------------------------------------------------------------------


def _text_from_args_or_clipboard(context: CommandContext, args_text: str | None = None) -> str:
    text = (context.args_text if args_text is None else args_text).strip()
    return text or (context.clipboard_text or "").strip()


def cmd_json(context: CommandContext) -> CommandResult:
    raw = context.args_text.strip()
    mode = "pretty"
    if raw:
        first, _, rest = raw.partition(" ")
        first_lower = first.lower()
        if first_lower in ("pretty", "format", "fmt", "min", "minify", "compact", "validate"):
            mode = first_lower
            raw = rest.strip()

    target = _text_from_args_or_clipboard(context, raw)
    if not target:
        return CommandResult(success=False, message="请输入 JSON 文本或确保剪贴板有 JSON 内容", error="缺少输入")

    try:
        parsed = json.loads(target)
    except json.JSONDecodeError as e:
        return CommandResult(
            success=False,
            message=f"JSON 无效: 第 {e.lineno} 行第 {e.colno} 列，{e.msg}",
            error="JSON 解析失败",
        )

    if mode == "validate":
        if isinstance(parsed, dict):
            summary = f"对象，{len(parsed)} 个键"
        elif isinstance(parsed, list):
            summary = f"数组，{len(parsed)} 项"
        else:
            summary = type(parsed).__name__
        return CommandResult(success=True, message=f"JSON 有效: {summary}")

    if mode in ("min", "minify", "compact"):
        result = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    else:
        result = json.dumps(parsed, ensure_ascii=False, indent=2)

    return CommandResult(
        success=True,
        message=result,
        actions=[CommandAction(type="copy", label="复制 JSON", value=result)],
    )


def _decode_base64url_json(part: str) -> dict:
    padded = part + "=" * (-len(part) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("JWT 片段不是 JSON 对象")
    return value


def cmd_jwt(context: CommandContext) -> CommandResult:
    token = _text_from_args_or_clipboard(context)
    if not token:
        return CommandResult(success=False, message="请输入 JWT 或确保剪贴板有 JWT", error="缺少输入")

    parts = token.strip().split(".")
    if len(parts) < 2:
        return CommandResult(success=False, message="JWT 至少需要 header.payload 两段", error="格式错误")

    try:
        header = _decode_base64url_json(parts[0])
        payload = _decode_base64url_json(parts[1])
    except Exception as e:
        return CommandResult(success=False, message=f"JWT 解码失败: {e}", error="解码失败")

    header_text = json.dumps(header, ensure_ascii=False, indent=2)
    payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
    signature_state = "有签名段，未验证签名" if len(parts) >= 3 and parts[2] else "无签名段"
    message = f"Header:\n{header_text}\n\nPayload:\n{payload_text}\n\n提示: {signature_state}"
    return CommandResult(
        success=True,
        message=message,
        payload={"header": header, "payload": payload},
        actions=[
            CommandAction(type="copy", label="复制 Payload", value=payload_text),
            CommandAction(type="copy", label="复制完整解码", value=message),
        ],
    )


def _normalize_host_input(text: str) -> tuple[str, int | None]:
    target = text.strip()
    if not target:
        return "", None
    target_for_parse = target if "://" in target else "http://" + target
    parsed = urllib.parse.urlparse(target_for_parse)
    host = parsed.hostname or target
    return host.strip("[]"), parsed.port


def _parse_ping_summary(output: str) -> str:
    patterns = [
        r"(?:Average|平均)\s*[=：:]\s*([<\d]+ms)",
        r"=\s*[\d.]+/([\d.]+)/[\d.]+/[\d.]+\s*ms",
        r"min/avg/max/(?:mdev|stddev)\s*=\s*[\d.]+/([\d.]+)/[\d.]+/[\d.]+\s*ms",
    ]
    for pattern in patterns:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            value = match.group(1)
            return f"平均延迟: {value}ms" if value.replace(".", "").isdigit() else f"平均延迟: {value}"
    return "未解析到平均延迟"


def cmd_netdiag(context: CommandContext) -> CommandResult:
    host, requested_port = _normalize_host_input(context.args_text or context.clipboard_text)
    if not host:
        return CommandResult(success=False, message="请输入要诊断的域名或 IP，例如 /netdiag example.com", error="缺少目标")

    lines = [f"网络诊断: {host}"]

    resolved_ips: list[str] = []
    try:
        infos = socket.getaddrinfo(host, requested_port or 80, type=socket.SOCK_STREAM)
        for info in infos:
            ip = info[4][0]
            if ip not in resolved_ips:
                resolved_ips.append(ip)
        lines.append("DNS: " + (", ".join(resolved_ips[:6]) if resolved_ips else "无结果"))
    except Exception as e:
        lines.append(f"DNS: 解析失败（{e}）")

    ports = [requested_port] if requested_port else [443, 80]
    for port in ports:
        if not port:
            continue
        start = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=3):
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                lines.append(f"TCP {port}: 可连接（{elapsed_ms} ms）")
        except Exception as e:
            lines.append(f"TCP {port}: 失败（{e}）")

    ping_args = ["ping", "-n" if os.name == "nt" else "-c", "4", host]
    success, out = _run_cmd(ping_args)
    if success:
        lines.append("Ping: " + _parse_ping_summary(out))
    else:
        lines.append("Ping: 失败或超时")

    if resolved_ips:
        lines.append("")
        lines.append("建议: DNS 正常时优先检查 TCP 失败的端口、防火墙或代理设置。")

    message = "\n".join(lines)
    return CommandResult(
        success=True,
        message=message,
        payload={"host": host, "ips": resolved_ips},
        actions=[CommandAction(type="copy", label="复制诊断报告", value=message)],
    )


def cmd_cidr(context: CommandContext) -> CommandResult:
    target = _text_from_args_or_clipboard(context)
    if not target:
        return CommandResult(success=False, message="请输入 CIDR，例如 /cidr 192.168.1.34/24", error="缺少输入")

    try:
        iface = ipaddress.ip_interface(target)
        network = iface.network
    except ValueError as e:
        return CommandResult(success=False, message=f"CIDR 无效: {e}", error="格式错误")

    first_host = last_host = ""
    if network.version == 4:
        if network.num_addresses == 1:
            first_host = last_host = str(network.network_address)
        elif network.num_addresses == 2:
            first_host = str(network.network_address)
            last_host = str(network.broadcast_address)
        else:
            first_host = str(network.network_address + 1)
            last_host = str(network.broadcast_address - 1)
        host_count = max(network.num_addresses - 2, 0) if network.prefixlen < 31 else network.num_addresses
        lines = [
            f"输入地址: {iface.ip}",
            f"网络: {network.with_prefixlen}",
            f"子网掩码: {network.netmask}",
            f"通配符掩码: {network.hostmask}",
            f"广播地址: {network.broadcast_address}",
            f"可用地址: {first_host} - {last_host}",
            f"可用主机数: {host_count}",
        ]
    else:
        lines = [
            f"输入地址: {iface.ip}",
            f"网络: {network.with_prefixlen}",
            f"网络掩码: {network.netmask}",
            f"地址总数: {network.num_addresses}",
            f"压缩写法: {network.compressed}",
            f"展开写法: {network.exploded}",
        ]

    message = "\n".join(lines)
    return CommandResult(
        success=True,
        message=message,
        payload={"network": network.with_prefixlen, "ip": str(iface.ip)},
        actions=[
            CommandAction(type="copy", label="复制网络", value=network.with_prefixlen),
            CommandAction(type="copy", label="复制报告", value=message),
        ],
    )


def _normalize_tls_target(text: str) -> tuple[str, int, str]:
    raw = text.strip()
    if not raw:
        return "", 443, ""

    parts = raw.split()
    target = parts[0]
    port_hint = parts[1] if len(parts) >= 2 and parts[1].isdigit() else ""

    parsed = urllib.parse.urlparse(target if "://" in target else "https://" + target)
    host = (parsed.hostname or target).strip().strip("[]").rstrip(".,;")
    port = parsed.port or (int(port_hint) if port_hint else 443)

    try:
        ascii_host = host.encode("idna").decode("ascii")
    except Exception:
        ascii_host = host
    return ascii_host, port, host


def _format_cert_subject(value) -> str:
    parts: list[str] = []
    for group in value or []:
        for key, val in group:
            if key in ("commonName", "organizationName", "countryName"):
                parts.append(f"{key}={val}")
    return ", ".join(parts) or "-"


def cmd_tls(context: CommandContext) -> CommandResult:
    host, port, display_host = _normalize_tls_target(context.args_text or context.clipboard_text)
    if not host:
        return CommandResult(success=False, message="请输入域名，例如 /tls example.com", error="缺少目标")
    if any(ch.isspace() for ch in host):
        return CommandResult(success=False, message="域名格式无效。示例: /tls example.com 或 /tls example.com 443", error="格式错误")

    try:
        ssl_context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=5) as sock:
            with ssl_context.wrap_socket(sock, server_hostname=host) as tls_sock:
                cert = tls_sock.getpeercert()
                cipher = tls_sock.cipher()
                version = tls_sock.version()
    except socket.gaierror:
        return CommandResult(
            success=False,
            message=(
                f"无法解析域名: {display_host or host}\n"
                "请检查域名是否输入正确，或确认当前网络/DNS 可用。示例: /tls example.com"
            ),
            error="DNS 解析失败",
        )
    except TimeoutError:
        return CommandResult(success=False, message=f"连接 {display_host or host}:{port} 超时，请检查网络或端口。", error="连接超时")
    except ssl.SSLCertVerificationError as e:
        return CommandResult(success=False, message=f"证书校验失败: {e}", error="证书校验失败")
    except ssl.SSLError as e:
        return CommandResult(success=False, message=f"TLS 握手失败: {e}", error="TLS 握手失败")
    except Exception as e:
        return CommandResult(success=False, message=f"TLS 检查失败: {display_host or host}:{port}\n{e}", error="连接失败")

    not_after_raw = cert.get("notAfter", "")
    days_left_text = "未知"
    try:
        expires_at = datetime.strptime(not_after_raw, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days_left = int((expires_at - datetime.now(timezone.utc)).total_seconds() // 86400)
        days_left_text = f"{days_left} 天"
    except Exception:
        pass

    san_entries = [
        value for key, value in cert.get("subjectAltName", [])
        if key.lower() == "dns"
    ]
    san_display = ", ".join(san_entries[:8])
    if len(san_entries) > 8:
        san_display += f" ... (+{len(san_entries) - 8})"

    lines = [
        f"目标: {display_host or host}:{port}",
        f"协议: {version or '-'}",
        f"加密套件: {cipher[0] if cipher else '-'}",
        f"颁发给: {_format_cert_subject(cert.get('subject'))}",
        f"颁发者: {_format_cert_subject(cert.get('issuer'))}",
        f"生效时间: {cert.get('notBefore', '-')}",
        f"到期时间: {not_after_raw or '-'}",
        f"剩余时间: {days_left_text}",
        f"SAN: {san_display or '-'}",
    ]
    message = "\n".join(lines)
    return CommandResult(
        success=True,
        message=message,
        payload={"host": host, "display_host": display_host or host, "port": port, "san": san_entries},
        actions=[CommandAction(type="copy", label="复制报告", value=message)],
    )


def cmd_path_audit(context: CommandContext) -> CommandResult:
    raw_path = (context.args_text or "").strip() or os.environ.get("PATH", "")
    if not raw_path:
        return CommandResult(success=False, message="未检测到 PATH 内容", error="缺少输入")

    parts = [os.path.expandvars(p.strip().strip('"')) for p in raw_path.split(os.pathsep)]
    seen: dict[str, int] = {}
    missing: list[str] = []
    duplicates: list[str] = []
    valid_dirs: list[str] = []

    for part in parts:
        if not part:
            continue
        key = os.path.normcase(os.path.abspath(part))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            duplicates.append(part)
        if os.path.isdir(part):
            valid_dirs.append(part)
        else:
            missing.append(part)

    executable_names: dict[str, list[str]] = {}
    suffixes = [".exe", ".cmd", ".bat", ".ps1"] if os.name == "nt" else [""]
    for directory in valid_dirs[:80]:
        try:
            for name in os.listdir(directory):
                full = os.path.join(directory, name)
                if not os.path.isfile(full):
                    continue
                stem, ext = os.path.splitext(name)
                if os.name == "nt" and ext.lower() not in suffixes:
                    continue
                command_name = stem.lower() if os.name == "nt" else name.lower()
                executable_names.setdefault(command_name, []).append(full)
        except Exception:
            continue

    shadowed = {
        name: paths for name, paths in executable_names.items()
        if len(paths) > 1 and name in {"python", "pip", "node", "npm", "git", "java", "code"}
    }

    lines = [
        "PATH 体检",
        f"条目总数: {len([p for p in parts if p])}",
        f"有效目录: {len(valid_dirs)}",
        f"失效目录: {len(missing)}",
        f"重复目录: {len(duplicates)}",
    ]
    if missing:
        lines.append("")
        lines.append("失效目录:")
        lines.extend(f"- {p}" for p in missing[:10])
        if len(missing) > 10:
            lines.append(f"- ... 另有 {len(missing) - 10} 项")
    if duplicates:
        lines.append("")
        lines.append("重复目录:")
        lines.extend(f"- {p}" for p in duplicates[:10])
        if len(duplicates) > 10:
            lines.append(f"- ... 另有 {len(duplicates) - 10} 项")
    if shadowed:
        lines.append("")
        lines.append("可能被前序 PATH 遮蔽的常用命令:")
        for name, paths in sorted(shadowed.items()):
            lines.append(f"- {name}:")
            lines.extend(f"  {path}" for path in paths[:4])

    if not missing and not duplicates and not shadowed:
        lines.append("")
        lines.append("未发现失效目录、重复目录或常用命令遮蔽。")

    message = "\n".join(lines)
    return CommandResult(
        success=True,
        message=message,
        payload={"missing": missing, "duplicates": duplicates, "shadowed": shadowed},
        actions=[CommandAction(type="copy", label="复制报告", value=message)],
    )


def _format_bytes(value: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value or 0)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def _proc_info_block(info: dict) -> str:
    mem = getattr(info.get("memory_info"), "rss", 0) or 0
    cpu = info.get("cpu_percent")
    lines = [
        f"PID: {info.get('pid')}",
        f"名称: {info.get('name') or '?'}",
        f"内存: {_format_bytes(mem)}",
    ]
    if cpu is not None:
        lines.append(f"CPU: {cpu}%")
    exe = info.get("exe") or ""
    if exe:
        lines.append(f"路径: {exe}")
    return "\n".join(lines)


def cmd_process(context: CommandContext) -> CommandResult:
    import psutil

    args = context.args_text.strip()
    parts = args.split()
    mode = parts[0].lower() if parts else "top"

    if mode == "kill" and len(parts) >= 2:
        try:
            pid = int(parts[1])
            proc = psutil.Process(pid)
            name = proc.name()
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            return CommandResult(success=True, message=f"已终止进程 PID {pid}: {name}")
        except Exception as e:
            return CommandResult(success=False, message=f"终止进程失败: {e}", error="终止失败")

    keyword = ""
    if mode in ("find", "search", "查找") and len(parts) >= 2:
        keyword = " ".join(parts[1:]).lower()
    elif mode not in ("top", "mem", "memory", "cpu", ""):
        keyword = args.lower()

    rows: list[dict] = []
    for proc in psutil.process_iter(["pid", "name", "exe", "memory_info", "cpu_percent"]):
        try:
            info = dict(proc.info)
        except Exception:
            continue
        haystack = f"{info.get('name') or ''} {info.get('exe') or ''}".lower()
        if keyword and keyword not in haystack:
            continue
        rows.append(info)

    if keyword:
        rows.sort(key=lambda item: getattr(item.get("memory_info"), "rss", 0) or 0, reverse=True)
        selected = rows[:20]
        if not selected:
            return CommandResult(success=True, message=f"未找到匹配进程: {keyword}")
        title = f"匹配进程: {keyword}"
    else:
        sort_cpu = mode == "cpu"
        rows.sort(
            key=lambda item: (item.get("cpu_percent") or 0) if sort_cpu else (getattr(item.get("memory_info"), "rss", 0) or 0),
            reverse=True,
        )
        selected = rows[:10]
        title = "CPU 占用最高进程" if sort_cpu else "内存占用最高进程"

    message = title + "\n\n" + "\n\n".join(_proc_info_block(info) for info in selected)
    return CommandResult(
        success=True,
        message=message,
        payload={"rows": selected},
        actions=[CommandAction(type="copy", label="复制进程列表", value=message)],
    )


def cmd_sysreport(context: CommandContext) -> CommandResult:
    import psutil

    try:
        vm = psutil.virtual_memory()
        disk_target = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
        disk = psutil.disk_usage(disk_target)
        net = psutil.net_io_counters()
        boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
        cpu_percent = psutil.cpu_percent(interval=0.1)

        lines = [
            "系统快照",
            f"系统: {platform.platform()}",
            f"启动时间: {boot_time}",
            f"CPU: {cpu_percent:.1f}% | 核心: {psutil.cpu_count(logical=True)}",
            f"内存: {_format_bytes(vm.used)} / {_format_bytes(vm.total)} ({vm.percent:.1f}%)",
            f"磁盘: {_format_bytes(disk.used)} / {_format_bytes(disk.total)} ({disk.percent:.1f}%)",
            f"网络累计: 发送 {_format_bytes(net.bytes_sent)} / 接收 {_format_bytes(net.bytes_recv)}",
        ]
        try:
            battery = psutil.sensors_battery()
            if battery is not None:
                power = "接入电源" if battery.power_plugged else "电池供电"
                lines.append(f"电池: {battery.percent:.1f}% ({power})")
        except Exception:
            pass

        message = "\n".join(lines)
        return CommandResult(
            success=True,
            message=message,
            actions=[CommandAction(type="copy", label="复制系统快照", value=message)],
        )
    except Exception as e:
        return CommandResult(success=False, message=f"生成系统快照失败: {e}", error="系统信息失败")


def _get_plugin_manager():
    try:
        import core
        import types
        pm = getattr(core, "plugin_manager", None)
        if pm is not None and not isinstance(pm, types.ModuleType):
            return pm
        return None
    except Exception:
        return None


def cmd_plugin_list(context: CommandContext) -> CommandResult:
    pm = _get_plugin_manager()
    if pm is None:
        return CommandResult(success=False, message="插件管理器未初始化", error="不可用")
    plugins = pm.list_plugins()
    if not plugins:
        return CommandResult(success=False, message="没有找到插件", error="空")
    lines = []
    for p in plugins:
        m = p.manifest
        status = p.status
        cmd_count = len(p.registered_commands)
        err = f" [{p.error}]" if p.error else ""
        lines.append(f"{m.id} v{m.version} — {status}{err}")
        lines.append(f"  {m.description}")
        if cmd_count:
            lines.append(f"  已注册 {cmd_count} 个命令")
    return CommandResult(
        success=True,
        message="\n".join(lines),
        actions=[CommandAction(type="copy", label="复制列表", value="\n".join(lines))],
    )


def cmd_plugin_reload(context: CommandContext) -> CommandResult:
    pm = _get_plugin_manager()
    if pm is None:
        return CommandResult(success=False, message="插件管理器未初始化", error="不可用")
    args = context.args_text.strip()
    if not args:
        count = 0
        for p in pm.list_plugins():
            if p.status == "enabled":
                if pm.reload_plugin(p.manifest.id):
                    count += 1
        return CommandResult(
            success=True,
            message=f"已重载 {count} 个已启用的插件",
        )
    if pm.reload_plugin(args):
        return CommandResult(success=True, message=f"插件已重载: {args}")
    return CommandResult(success=False, message=f"重载失败: {args}", error="重载错误")


def cmd_plugin_new(context: CommandContext) -> CommandResult:
    pm = _get_plugin_manager()
    if pm is None:
        return CommandResult(success=False, message="插件管理器未初始化", error="不可用")
    plugin_id = context.args_text.strip()
    if not plugin_id:
        return CommandResult(success=False, message="请指定插件 ID", error="缺少输入")
    safe = "".join(c for c in plugin_id if c.isalnum() or c in "-_")
    if safe != plugin_id:
        return CommandResult(success=False, message="插件 ID 只能包含字母、数字、短横线和下划线", error="格式错误")

    import os
    base = pm.plugins_dir
    plugin_dir = os.path.join(base, plugin_id)
    if os.path.exists(plugin_dir):
        return CommandResult(success=False, message=f"插件目录已存在: {plugin_dir}", error="已存在")

    from core.plugin_template import write_plugin_template

    write_plugin_template(plugin_dir, plugin_id)
    return CommandResult(
        success=True,
        message=f"已创建插件模板: {plugin_dir}\n使用 /plugin reload {plugin_id} 加载"
    )


# ---------------------------------------------------------------------------
# ── Phase 3 Power-User Superpower Commands ─────────────────────────────────
# ---------------------------------------------------------------------------

def _run_cmd(args: list[str]) -> tuple[bool, str]:
    """静默执行命令并自动解码输出（动态检测系统 OEM 编码）"""
    import subprocess
    import ctypes
    import locale
    try:
        creationflags = 0x08000000 if os.name == 'nt' else 0
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            timeout=10,
        )
        output = b""
        if proc.stdout:
            output += proc.stdout
        if proc.stderr:
            output += b"\n" + proc.stderr
            
        encodings = []
        if os.name == 'nt':
            try:
                oem_cp = ctypes.windll.kernel32.GetOEMCP()
                if oem_cp:
                    encodings.append(f"cp{oem_cp}")
            except Exception:
                pass
        
        pref_enc = locale.getpreferredencoding(False)
        if pref_enc:
            encodings.append(pref_enc.lower())
        for e in ["gbk", "utf-8", "utf-16", "cp437"]:
            if e not in encodings:
                encodings.append(e)
                
        for encoding in encodings:
            try:
                decoded = output.decode(encoding)
                return proc.returncode == 0, decoded
            except UnicodeDecodeError:
                continue
                
        primary_encoding = encodings[0] if encodings else "utf-8"
        return proc.returncode == 0, output.decode(primary_encoding, errors="replace")
    except Exception as e:
        return False, str(e)


def cmd_wifi(context: CommandContext) -> CommandResult:
    args = context.args_text.strip()
    if not args:
        # 列出所有 Wi-Fi 配置文件
        success, out = _run_cmd(["netsh", "wlan", "show", "profiles"])
        if not success:
            friendly_tip = ""
            out_lower = out.lower()
            if "wlansvc" in out_lower or "没有运行" in out_lower or "not running" in out_lower:
                friendly_tip = "\n\n提示：系统的无线自动配置服务 (wlansvc) 未运行，请尝试在系统服务中启动它并重试。"
            elif "没有无线接口" in out_lower or "no wireless interface" in out_lower or "无无线接口" in out_lower:
                friendly_tip = "\n\n提示：系统上未检测到无线网卡，该命令仅支持带有无线网卡的设备。"
            return CommandResult(
                success=False,
                message=f"无法获取 Wi-Fi 列表：{out}{friendly_tip}",
                error="执行失败"
            )
        
        profiles = []
        for line in out.splitlines():
            if ":" in line or "：" in line:
                delim = ":" if ":" in line else "："
                key, val = line.split(delim, 1)
                key_strip = key.strip()
                val_strip = val.strip()
                if any(k in key_strip for k in ["All User Profile", "所有用户配置文件", "用户配置文件", "User Profile"]):
                    if val_strip:
                        profiles.append(val_strip)
        if not profiles:
            return CommandResult(success=True, message="未找到已保存的 Wi-Fi 配置文件。")
        
        msg = "已保存的 Wi-Fi 配置文件列表：\n" + "\n".join(f"- {p}" for p in profiles)
        msg += "\n\n提示: 输入 '/wifi <名称>' 可查询该 Wi-Fi 的密码"
        return CommandResult(
            success=True,
            message=msg,
            actions=[CommandAction(type="copy", label="复制列表", value="\n".join(profiles))]
        )
    else:
        # 查询特定 Wi-Fi 的明文密码
        name = args
        success, out = _run_cmd(["netsh", "wlan", "show", "profile", f"name={name}", "key=clear"])
        if not success:
            return CommandResult(success=False, message=f"查询失败，未找到名为 '{name}' 的 Wi-Fi 配置文件。", error="未找到")
        
        password = None
        for line in out.splitlines():
            if ":" in line or "：" in line:
                delim = ":" if ":" in line else "："
                key, val = line.split(delim, 1)
                key_strip = key.strip()
                val_strip = val.strip()
                if any(sk in key_strip for sk in ["Security key", "安全密钥", "安全金鑰"]):
                    continue
                if any(k in key_strip for k in ["Key Content", "关键内容", "金鑰內容", "关键", "金鑰", "Key"]):
                    password = val_strip
                    break
        
        if password is not None:
            msg = f"Wi-Fi 名称: {name}\n明文密码: {password}"
            return CommandResult(
                success=True,
                message=msg,
                actions=[CommandAction(type="copy", label="复制密码", value=password)]
            )
        else:
            return CommandResult(
                success=True,
                message=f"Wi-Fi '{name}' 可能为无密码开放网络或未保存密码。",
                error="无密码"
            )


def cmd_hosts(context: CommandContext) -> CommandResult:
    hosts_path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32\\drivers\\etc\\hosts")
    try:
        from core.shortcut_executor import ShortcutExecutor

        ok, error = ShortcutExecutor._launch_with_privilege(
            "notepad.exe",
            hosts_path,
            None,
            show_cmd=1,
            run_as_admin=True,
        )
        if ok:
            return CommandResult(success=True, message="已请求以管理员权限打开 hosts 文件...")
        return CommandResult(success=False, message=error or "管理员权限请求被拒绝或失败", error="打开失败")
    except Exception as e:
        return CommandResult(success=False, message=f"无法打开 hosts 文件: {e}", error="错误")


def cmd_port(context: CommandContext) -> CommandResult:
    import psutil
    args = context.args_text.strip().split()
    if not args:
        return CommandResult(success=False, message="请输入要查询的端口号，如: /port 8080", error="缺少参数")
    
    try:
        port_number = int(args[0])
    except ValueError:
        return CommandResult(success=False, message="端口号必须为整数，如: /port 8080", error="格式错误")
        
    should_kill = False
    if len(args) > 1 and args[1].lower() in ("kill", "free", "杀死", "关闭"):
        should_kill = True
        
    pids = set()
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port_number:
                if conn.pid:
                    pids.add(conn.pid)
    except Exception:
        # Fallback to netstat -ano
        success, out = _run_cmd(["netstat", "-ano"])
        if success:
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 4 and parts[0].upper() in ("TCP", "UDP"):
                    local_addr = parts[1]
                    pid = parts[-1]
                    if ":" in local_addr:
                        addr_parts = local_addr.rsplit(":", 1)
                        if len(addr_parts) == 2:
                            current_port = addr_parts[1].strip()
                            if current_port == str(port_number):
                                try:
                                    pids.add(int(pid))
                                except ValueError:
                                    pass
                                    
    if not pids:
        return CommandResult(success=True, message=f"目前没有进程占用 TCP/UDP 端口 {port_number}。")
        
    process_details = []
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            exe = proc.exe()
            process_details.append({"pid": pid, "name": name, "exe": exe})
        except Exception:
            process_details.append({"pid": pid, "name": "未知进程", "exe": "未知路径"})
            
    if should_kill:
        killed_pids = []
        errors = []
        for details in process_details:
            pid = details["pid"]
            success_term = False
            try:
                proc = psutil.Process(pid)
                proc.terminate()
                proc.wait(timeout=2)
                killed_pids.append(pid)
                success_term = True
            except Exception:
                try:
                    proc = psutil.Process(pid)
                    proc.kill()
                    killed_pids.append(pid)
                    success_term = True
                except Exception:
                    pass
            
            if not success_term:
                import subprocess
                try:
                    proc_kill = subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=0x08000000,
                        timeout=3
                    )
                    if proc_kill.returncode == 0:
                        killed_pids.append(pid)
                    else:
                        errors.append(f"PID {pid}: taskkill 失败")
                except Exception as ex:
                    errors.append(f"PID {pid}: {ex}")
                    
        if killed_pids:
            msg = f"已成功终止占用端口 {port_number} 的进程:\n"
            msg += "\n".join(f"- PID {pid}" for pid in killed_pids)
            if errors:
                msg += f"\n部分进程终止失败:\n" + "\n".join(errors)
            return CommandResult(success=True, message=msg)
        else:
            return CommandResult(success=False, message="终止进程失败:\n" + "\n".join(errors), error="终止失败")
            
    # List occupier details
    lines = [f"端口 {port_number} 被以下进程占用:"]
    for d in process_details:
        lines.append(f"- 进程名称: {d['name']}")
        lines.append(f"  PID 进程号: {d['pid']}")
        lines.append(f"  路径: {d['exe']}")
        lines.append("")
        
    lines.append(f"提示: 输入 '/port {port_number} kill' 可强行终止该占用进程。")
    msg = "\n".join(lines).strip()
    
    first_pid = str(process_details[0]['pid']) if process_details else ""
    return CommandResult(
        success=True,
        message=msg,
        actions=[
            CommandAction(type="copy", label="复制第一个PID", value=first_pid),
            CommandAction(type="copy", label="复制终止命令", value=f"/port {port_number} kill")
        ]
    )


def cmd_env(context: CommandContext) -> CommandResult:
    import subprocess
    try:
        subprocess.Popen(["rundll32.exe", "sysdm.cpl,EditEnvironmentVariables"])
        return CommandResult(success=True, message="已成功启动 Windows 系统环境变量编辑器。")
    except Exception as e:
        return CommandResult(success=False, message=f"启动环境变量编辑器失败: {e}", error="启动失败")


def cmd_dns(context: CommandContext) -> CommandResult:
    success, out = _run_cmd(["ipconfig", "/flushdns"])
    if success:
        return CommandResult(success=True, message="已成功清理 Windows DNS 缓存！")
    else:
        return CommandResult(success=False, message=f"清理 DNS 缓存失败：{out}", error="清理失败")


def cmd_clean_cache(context: CommandContext) -> CommandResult:
    from core import data_manager
    from core.project_cache_cleaner import clean_unused_project_cache

    dry_run = (context.args_text or "").strip().lower() in {"dry-run", "dryrun", "preview", "预览"}
    stats = clean_unused_project_cache(data_manager, dry_run=dry_run)
    removed = int(stats.get("total_removed", 0) or 0)
    freed = float(stats.get("total_size_freed_mb", 0) or 0)
    failed = int(stats.get("failed", 0) or 0)

    lines = ["缓存清理预览:" if dry_run else "缓存清理完成:"]
    lines.append(f"- 可清理/已清理: {removed} 个文件")
    lines.append(f"- 可释放/已释放: {freed:.2f} MB")
    if failed:
        lines.append(f"- 失败: {failed} 项")

    labels = {
        "temp_icons": "临时图标",
        "__pycache__": "Python 字节码",
        ".pytest_cache": "pytest 缓存",
        ".ruff_cache": "ruff 缓存",
        "restore_temp": "恢复临时目录",
        "empty_dirs": "空缓存目录",
    }
    for area, area_stats in sorted((stats.get("by_area") or {}).items()):
        count = int(area_stats.get("files_removed", 0) or 0)
        size = float(area_stats.get("size_freed_mb", 0) or 0)
        if count:
            lines.append(f"- {labels.get(area, area)}: {count} 项，{size:.2f} MB")

    return CommandResult(
        success=failed == 0,
        message="\n".join(lines),
        payload=stats,
        actions=[CommandAction(type="copy", label="复制报告", value="\n".join(lines))],
        error="" if failed == 0 else "部分缓存清理失败",
    )


def cmd_god(context: CommandContext) -> CommandResult:
    import subprocess
    god_mode_guid = "shell:::{ED7BA470-8E54-465E-825C-99712043E01C}"
    try:
        os.startfile(god_mode_guid)
        return CommandResult(success=True, message="已成功打开 Windows 上帝模式 (God Mode) 文件夹。")
    except Exception:
        try:
            subprocess.Popen(["explorer.exe", god_mode_guid])
            return CommandResult(success=True, message="已成功打开 Windows 上帝模式 (God Mode) 文件夹。")
        except Exception as e:
            return CommandResult(success=False, message=f"打开上帝模式失败: {e}", error="打开失败")


def cmd_explorer(context: CommandContext) -> CommandResult:
    import subprocess
    import time
    import psutil
    
    try:
        subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], creationflags=0x08000000, timeout=5)
    except Exception:
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] and proc.info["name"].lower() == "explorer.exe":
                try:
                    proc.kill()
                except Exception:
                    pass
                    
    time.sleep(1.0)
    
    already_running = False
    try:
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] and proc.info["name"].lower() == "explorer.exe":
                already_running = True
                break
    except Exception:
        pass
        
    if already_running:
        return CommandResult(success=True, message="Windows 资源管理器已成功自动重启！")
        
    explorer_path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "explorer.exe")
    if not os.path.exists(explorer_path):
        explorer_path = "explorer.exe"
        
    try:
        subprocess.Popen([explorer_path], creationflags=0x00000008) # DETACHED_PROCESS
        return CommandResult(success=True, message="Windows 资源管理器已安全重启！")
    except Exception:
        try:
            subprocess.Popen([explorer_path])
            return CommandResult(success=True, message="Windows 资源管理器已安全重启！")
        except Exception as e:
            return CommandResult(success=False, message=f"重启资源管理器失败: {e}", error="重启失败")


def cmd_conflict(context: CommandContext) -> CommandResult:
    try:
        from core import data_manager
        from core.hotkey_conflict_checker import check_conflict, is_hotkey_registered
        
        if data_manager is None:
            return CommandResult(success=False, message="数据管理器未初始化", error="不可用")
            
        app_data = data_manager.data
        all_items = []
        for folder in app_data.folders:
            for item in folder.items:
                if item.enabled and item.hotkey:
                    all_items.append(item)
    except Exception as e:
        return CommandResult(success=False, message=f"读取配置或检查热键冲突失败: {e}", error="错误")
                
    if not all_items:
        return CommandResult(success=True, message="当前应用内没有启用任何带有快捷键的快捷方式项目。")
        
    lines = []
    hotkey_to_items = {}
    for item in all_items:
        hotkey_to_items.setdefault(item.hotkey.strip().lower(), []).append(item)
        
    internal_conflicts = []
    for hk, items in hotkey_to_items.items():
        if len(items) > 1:
            names = [it.name for it in items]
            internal_conflicts.append(f"- 快捷键 '{items[0].hotkey}' 被多个项目同时使用: {', '.join(names)}")
            
    if internal_conflicts:
        lines.append("【应用内快捷键冲突】")
        lines.extend(internal_conflicts)
        lines.append("")
        
    system_conflicts = []
    registration_status = []
    
    for item in all_items:
        has_sys_conflict, sys_desc = check_conflict(item.hotkey)
        if has_sys_conflict:
            system_conflicts.append(f"- 项目 '{item.name}' 的快捷键 '{item.hotkey}' {sys_desc}")
            
        if item.hotkey_modifiers and item.hotkey_key:
            occupied = is_hotkey_registered(item.hotkey_modifiers, item.hotkey_key)
            if occupied:
                registration_status.append(f"- 项目 '{item.name}' 的快捷键 '{item.hotkey}' 注册失败，已被其他外部软件占用！")
                
    if system_conflicts:
        lines.append("【与系统快捷键或常用快捷键冲突】")
        lines.extend(system_conflicts)
        lines.append("")
        
    if registration_status:
        lines.append("【系统全局热键占用检查 (Windows API)】")
        lines.extend(registration_status)
        lines.append("")
        
    if not lines:
        return CommandResult(success=True, message="恭喜！所有已启用的快捷键均状态正常，没有发现任何冲突或占用。")
        
    report_msg = "\n".join(lines).strip()
    return CommandResult(
        success=True,
        message=report_msg,
        actions=[CommandAction(type="copy", label="复制报告", value=report_msg)]
    )
