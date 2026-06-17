"""Built-in network diagnostics (ip, netdiag, cidr, tls, wifi, hosts, port, dns, path-audit) commands.

Auto-extracted from :mod:`core.commands` in 1.6.3.2 to keep the file size
manageable. Public API stays on :mod:`core.commands`; this module is
internal and may be imported directly by tests.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import socket
import ssl
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from .command_registry import CommandAction, CommandContext, CommandResult
from .commands_text import _text_from_args_or_clipboard
from .network_security import read_limited_response, safe_urlopen

logger = logging.getLogger(__name__)


def _get_primary_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]  # type: ignore[no-any-return]
        finally:
            s.close()
    except Exception:
        logger.debug("Failed to get primary local IP via UDP, falling back to gethostbyname", exc_info=True)
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
    except Exception as exc:
        logger.debug("通过psutil获取内网IP地址失败: %s", exc, exc_info=True)

    if not addresses:
        try:
            primary = _get_primary_local_ip()
            if primary and not ipaddress.ip_address(primary).is_loopback:
                addresses.append((primary, "primary"))
        except Exception as exc:
            logger.debug("获取主内网IP地址失败: %s", exc, exc_info=True)

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
            with safe_urlopen(req, timeout=timeout) as resp:
                raw = read_limited_response(resp, 4096).decode("utf-8", errors="replace").strip()
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
        return CommandResult(
            success=False, message="请输入要诊断的域名或 IP，例如 /netdiag example.com", error="缺少目标"
        )

    lines = [f"网络诊断: {host}"]

    resolved_ips: list[str] = []
    try:
        infos = socket.getaddrinfo(host, requested_port or 80, type=socket.SOCK_STREAM)
        for info in infos:
            ip = info[4][0]
            if ip not in resolved_ips:
                resolved_ips.append(str(ip))
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

    invalid_format = False
    if len(parts) >= 2:
        if not parts[1].isdigit() or len(parts) > 2:
            invalid_format = True

    parsed = urllib.parse.urlparse(target if "://" in target else "https://" + target)
    host = (parsed.hostname or target).strip().strip("[]").rstrip(".,;")
    port = parsed.port or (int(port_hint) if port_hint else 443)

    if invalid_format:
        host = raw

    try:
        ascii_host = host.encode("idna").decode("ascii")
    except Exception:
        logger.debug("IDNA encoding failed for host %s, using raw value", host, exc_info=True)
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
    structured_args = dict(context.args or {})
    if structured_args:
        raw_host = str(structured_args.get("host") or "").strip()
        raw_port = str(structured_args.get("port") or "").strip()
        host, parsed_port, display_host = _normalize_tls_target(raw_host)
        if raw_port:
            try:
                parsed_port = int(raw_port)
            except ValueError:
                parsed_port = 443
        port = parsed_port
    else:
        host, port, display_host = _normalize_tls_target(context.args_text or context.clipboard_text)
    if not host:
        return CommandResult(success=False, message="请输入域名，例如 /tls example.com", error="缺少目标")
    if any(ch.isspace() for ch in host):
        return CommandResult(
            success=False, message="域名格式无效。示例: /tls example.com 或 /tls example.com 443", error="格式错误"
        )

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
        return CommandResult(
            success=False, message=f"连接 {display_host or host}:{port} 超时，请检查网络或端口。", error="连接超时"
        )
    except ssl.SSLCertVerificationError as e:
        return CommandResult(success=False, message=f"证书校验失败: {e}", error="证书校验失败")
    except ssl.SSLError as e:
        return CommandResult(success=False, message=f"TLS 握手失败: {e}", error="TLS 握手失败")
    except Exception as e:
        return CommandResult(
            success=False, message=f"TLS 检查失败: {display_host or host}:{port}\n{e}", error="连接失败"
        )

    not_after_raw = cert.get("notAfter", "")  # type: ignore[union-attr]
    days_left_text = "未知"
    try:
        expires_at = datetime.strptime(not_after_raw, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)  # type: ignore[arg-type]
        days_left = int((expires_at - datetime.now(UTC)).total_seconds() // 86400)
        days_left_text = f"{days_left} 天"
    except Exception as exc:
        logger.debug("解析TLS证书到期时间失败: %s", exc, exc_info=True)

    san_entries: list[str] = []
    subject_alt_names: object = cert.get("subjectAltName", []) if isinstance(cert, dict) else []
    if isinstance(subject_alt_names, list | tuple):
        for entry in subject_alt_names:
            if isinstance(entry, tuple | list) and len(entry) >= 2:
                key, value = entry[0], entry[1]
                if str(key).lower() == "dns":
                    san_entries.append(str(value))
    san_display = ", ".join(san_entries)

    lines = [
        f"目标: {display_host or host}:{port}",
        f"协议: {version or '-'}",
        f"加密套件: {cipher[0] if cipher else '-'}",
        f"颁发给: {_format_cert_subject(cert.get('subject'))}",  # type: ignore[union-attr]
        f"颁发者: {_format_cert_subject(cert.get('issuer'))}",  # type: ignore[union-attr]
        f"生效时间: {cert.get('notBefore', '-')}",  # type: ignore[union-attr]
        f"到期时间: {not_after_raw or '-'}",
        f"剩余时间: {days_left_text}",
        f"SAN: {san_display or '-'}",
    ]
    message = "\n".join(lines)
    return CommandResult(
        success=True,
        message=message,
        payload={
            "host": host,
            "display_host": display_host or host,
            "port": port,
            "san": san_entries,
            "outputs": {
                "host": host,
                "port": str(port),
                "expires_at": not_after_raw,
                "issuer": _format_cert_subject(cert.get("issuer")),  # type: ignore[union-attr]
            },
        },
        actions=[CommandAction(type="copy", label="复制报告", value=message)],
    )


def _run_cmd(args: list[str]) -> tuple[bool, str]:
    """静默执行命令并自动解码输出（动态检测系统 OEM 编码）"""
    import ctypes
    import locale

    try:
        creationflags = 0x08000000 if os.name == "nt" else 0
        proc = subprocess.run(
            args,
            capture_output=True,
            creationflags=creationflags,
            timeout=10,
        )
        output = b""
        if proc.stdout:
            output += proc.stdout
        if proc.stderr:
            output += b"\n" + proc.stderr

        encodings = []
        if os.name == "nt":
            try:
                oem_cp = ctypes.windll.kernel32.GetOEMCP()
                if oem_cp:
                    encodings.append(f"cp{oem_cp}")
            except Exception as exc:
                logger.debug("获取OEM代码页失败: %s", exc, exc_info=True)

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
            return CommandResult(success=False, message=f"无法获取 Wi-Fi 列表：{out}{friendly_tip}", error="执行失败")

        profiles = []
        for line in out.splitlines():
            if ":" in line or "：" in line:
                delim = ":" if ":" in line else "："
                key, val = line.split(delim, 1)
                key_lower = key.strip().lower()
                val_strip = val.strip()
                if any(
                    k in key_lower for k in ["all user profile", "所有用户配置文件", "用户配置文件", "user profile"]
                ):
                    if val_strip:
                        profiles.append(val_strip)
        if not profiles:
            return CommandResult(success=True, message="未找到已保存的 Wi-Fi 配置文件。")

        msg = "已保存的 Wi-Fi 配置文件列表：\n" + "\n".join(f"- {p}" for p in profiles)
        msg += "\n\n提示: 输入 '/wifi <名称>' 可查询该 Wi-Fi 的密码"
        return CommandResult(
            success=True, message=msg, actions=[CommandAction(type="copy", label="复制列表", value="\n".join(profiles))]
        )
    else:
        # 查询特定 Wi-Fi 的明文密码
        name = args.strip("'\"")
        success, out = _run_cmd(["netsh", "wlan", "show", "profile", f"name={name}", "key=clear"])
        if not success:
            return CommandResult(
                success=False, message=f"查询失败，未找到名为 '{name}' 的 Wi-Fi 配置文件。", error="未找到"
            )

        password = None
        for line in out.splitlines():
            if ":" in line or "：" in line:
                delim = ":" if ":" in line else "："
                key, val = line.split(delim, 1)
                key_lower = key.strip().lower()
                val_strip = val.strip()
                if "security key" in key_lower or "安全密钥" in key_lower or "安全金鑰" in key_lower:
                    continue
                if any(k in key_lower for k in ["key content", "关键内容", "金鑰內容", "关键", "金鑰", "key"]):
                    password = val_strip
                    break

        if password is not None:
            msg = f"Wi-Fi 名称: {name}\n明文密码: {password}"
            return CommandResult(
                success=True, message=msg, actions=[CommandAction(type="copy", label="复制密码", value=password)]
            )
        else:
            return CommandResult(
                success=True, message=f"Wi-Fi '{name}' 可能为无密码开放网络或未保存密码。", error="无密码"
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
            return CommandResult(
                success=True,
                message="已请求以管理员权限打开 hosts 文件...",
                payload={"_suppress_result_panel": True},
            )
        return CommandResult(success=False, message=error or "管理员权限请求被拒绝或失败", error="打开失败")
    except Exception as e:
        return CommandResult(success=False, message=f"无法打开 hosts 文件: {e}", error="错误")


def cmd_port(context: CommandContext) -> CommandResult:
    import psutil

    structured_args = dict(context.args or {})
    if structured_args:
        args = [str(structured_args.get("port") or "").strip()]
        action = str(structured_args.get("action") or "query").lower()
        if action == "kill":
            args.append("kill")
    else:
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
                                    logger.debug("解析端口PID失败", exc_info=True)

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
                except Exception as exc:
                    logger.debug("强制终止进程PID=%s失败: %s", pid, exc, exc_info=True)

            if not success_term:
                import subprocess

                try:
                    proc_kill = subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                        creationflags=0x08000000,
                        timeout=3,
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
                msg += "\n部分进程终止失败:\n" + "\n".join(errors)
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

    first_pid = str(process_details[0]["pid"]) if process_details else ""
    return CommandResult(
        success=True,
        message=msg,
        payload={
            "outputs": {
                "port": str(port_number),
                "pid": first_pid,
                "process": str(process_details[0]["name"]) if process_details else "",
            }
        },
        actions=[
            CommandAction(type="copy", label="复制第一个PID", value=first_pid),
            CommandAction(type="copy", label="复制终止命令", value=f"/port {port_number} kill"),
        ],
    )


def cmd_dns(context: CommandContext) -> CommandResult:
    success, out = _run_cmd(["ipconfig", "/flushdns"])
    if success:
        return CommandResult(
            success=True,
            message="已成功清理 Windows DNS 缓存！",
            payload={"_suppress_result_panel": True},
        )
    else:
        return CommandResult(success=False, message=f"清理 DNS 缓存失败：{out}", error="清理失败")
