"""Network Tools plugin — Ping and DNS lookup with robust command execution."""

import ctypes
import locale
import os
import socket
import subprocess

from core.command_registry import CommandAction, CommandResult


def register(api):
    api.register_command(
        id="network_tools.ping",
        title="Ping",
        aliases=["ping"],
        description="简单 ping 测试（发送 4 个包）",
        category="network",
        handler=handle_ping,
    )
    api.register_command(
        id="network_tools.dns",
        title="DNS 查询",
        aliases=["dns", "nslookup"],
        description="查询域名解析记录",
        category="network",
        handler=handle_dns,
    )


def _run_cmd(args: list[str], timeout: int = 10) -> tuple[bool, str]:
    """Execute a system command silently and robustly decode the output."""
    try:
        creationflags = 0x08000000 if os.name == 'nt' else 0
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            timeout=timeout,
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


def handle_ping(context):
    host = (context.args_text or "").strip()
    if not host:
        return CommandResult(
            success=False,
            message="用法: /ping <主机名>\n例如: /ping example.com",
            error="缺少输入"
        )

    # Sanitize hostname to prevent malicious CLI injection
    host_clean = "".join(c for c in host if c.isalnum() or c in ".-_")
    if not host_clean or host_clean != host:
        return CommandResult(
            success=False,
            message="无效的主机名或 IP 地址",
            error="格式错误"
        )

    try:
        success, output = _run_cmd(["ping", "-n", "4", host_clean], timeout=12)
        return CommandResult(
            success=success,
            message=output[:2000],
            display_type="log",
            payload={
                "window_size": "large",
                "wrap": False,
                "host": host_clean,
                "command": "ping",
                "truncated": len(output) > 2000,
            },
            actions=[CommandAction(type="copy", label="复制结果", value=output)],
        )
    except Exception as e:
        return CommandResult(
            success=False,
            message=f"Ping 失败: {e}",
            error="执行失败"
        )


def handle_dns(context):
    host = (context.args_text or "").strip()
    if not host:
        return CommandResult(
            success=False,
            message="用法: /dns <域名>\n例如: /dns example.com",
            error="缺少输入"
        )

    # Sanitize domain to prevent malicious CLI injection
    host_clean = "".join(c for c in host if c.isalnum() or c in ".-_")
    if not host_clean or host_clean != host:
        return CommandResult(
            success=False,
            message="无效的域名或 IP 地址",
            error="格式错误"
        )

    try:
        success, output = _run_cmd(["nslookup", host_clean], timeout=12)

        # Fallback to socket resolution if output is empty or nslookup failed
        if not output.strip() or not success:
            try:
                ip = socket.gethostbyname(host_clean)
                output = f"{host_clean} -> {ip}"
                success = True
            except socket.gaierror as e:
                if not output.strip():
                    output = f"域名解析失败: {e}"
                success = False

        return CommandResult(
            success=success,
            message=output[:2000],
            display_type="log",
            payload={
                "window_size": "large",
                "wrap": False,
                "host": host_clean,
                "command": "nslookup",
                "truncated": len(output) > 2000,
            },
            actions=[CommandAction(type="copy", label="复制结果", value=output)],
        )
    except Exception as e:
        return CommandResult(
            success=False,
            message=f"DNS 查询失败: {e}",
            error="执行失败"
        )
