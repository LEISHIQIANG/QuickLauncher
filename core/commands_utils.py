"""Built-in misc utilities (qr, explorer, conflict) commands.

Auto-extracted from :mod:`core.commands` in 1.6.3.2 to keep the file size
manageable. Public API stays on :mod:`core.commands`; this module is
internal and may be imported directly by tests.
"""

from __future__ import annotations

import atexit
import functools
import http.server
import io
import logging
import os
import socket
import socketserver
import tempfile
import threading
import urllib.parse

from infrastructure.process import runtime as process_runtime

try:
    import qrcode

    _HAS_QRCODE = True
except ImportError:
    _HAS_QRCODE = False

from .background_tasks import start_background_thread
from .command_registry import CommandAction, CommandContext, CommandResult

logger = logging.getLogger(__name__)


def _qr_get_local_ip() -> str:
    try:
        hostname = socket.gethostname()
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM)
        for info in infos:
            ip = info[4][0]
            if isinstance(ip, str) and not ip.startswith("127."):
                return ip
    except Exception:
        logger.debug("枚举本机IPv4地址失败", exc_info=True)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            sock_ip: object = s.getsockname()[0]
            if isinstance(sock_ip, str) and not sock_ip.startswith("127."):
                return sock_ip
    except Exception:
        logger.debug("通过路由探测本机IPv4地址失败", exc_info=True)
    return "127.0.0.1"


def stop_qr_file_server(port: int):
    with _qr_server_lock:
        entry = _qr_file_servers.pop(port, None)
    if entry:
        httpd = entry[0]
        try:
            httpd.shutdown()
        except Exception as exc:
            logger.debug("关闭二维码文件服务器失败: %s", exc, exc_info=True)


def _stop_all_qr_file_servers():
    with _qr_server_lock:
        ports = list(_qr_file_servers.keys())
    for port in ports:
        stop_qr_file_server(port)


def _cleanup_qr_temp_files():
    for path in _qr_temp_files:
        try:
            if os.path.isfile(path):
                os.unlink(path)
        except OSError:
            logger.debug("清理QR临时文件失败", exc_info=True)
    _qr_temp_files.clear()


atexit.register(_stop_all_qr_file_servers)
atexit.register(_cleanup_qr_temp_files)


def _start_qr_file_server(dir_path: str, file_path: str):

    with socketserver.TCPServer(("0.0.0.0", 0), http.server.SimpleHTTPRequestHandler) as s:
        port = s.server_address[1]

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=dir_path)
    httpd = socketserver.TCPServer(("0.0.0.0", port), handler)
    httpd.timeout = 0.5
    t = start_background_thread(
        name=f"QRFileServer-{port}",
        target=httpd.serve_forever,
        owner="qr-file-server",
    )
    with _qr_server_lock:
        _qr_file_servers[port] = (httpd, file_path, t)
    return port


# ---------------------------------------------------------------------------
# ── /qr ────────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def cmd_qr(context: CommandContext) -> CommandResult:
    if not _HAS_QRCODE:
        return CommandResult(
            success=False, message="二维码生成器 (qrcode) 未安装，打包时请将 qrcode 加入依赖", error="缺少 qrcode 库"
        )
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
        _qr_temp_files.append(tmp.name)
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
        logger.debug("生成二维码失败", exc_info=True)
        return CommandResult(success=False, message=f"生成二维码失败: {e}", error="生成失败")


# ---------------------------------------------------------------------------
# ── /plugin management commands ────────────────────────────────────────────
# ---------------------------------------------------------------------------


def cmd_explorer(context: CommandContext) -> CommandResult:
    import time

    import psutil

    try:
        process_runtime.run(["taskkill", "/f", "/im", "explorer.exe"], creationflags=0x08000000, timeout=5)
    except Exception:
        logger.debug("taskkill终止explorer进程失败", exc_info=True)
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] and proc.info["name"].lower() == "explorer.exe":
                try:
                    proc.kill()
                except Exception as exc:
                    logger.debug("终止explorer进程失败: %s", exc, exc_info=True)

    time.sleep(1.0)

    already_running = False
    try:
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] and proc.info["name"].lower() == "explorer.exe":
                already_running = True
                break
    except Exception as exc:
        logger.debug("检测explorer进程状态失败: %s", exc, exc_info=True)

    if already_running:
        return CommandResult(
            success=True,
            message="Windows 资源管理器已成功自动重启！",
            payload={"_suppress_result_panel": True},
        )

    explorer_path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "explorer.exe")
    if not os.path.exists(explorer_path):
        explorer_path = "explorer.exe"

    try:
        process_runtime.popen([explorer_path], creationflags=0x00000008)  # DETACHED_PROCESS
        return CommandResult(
            success=True,
            message="Windows 资源管理器已安全重启！",
            payload={"_suppress_result_panel": True},
        )
    except Exception as exc:
        logger.debug("重启资源管理器(DETACHED_PROCESS)失败: %s", exc, exc_info=True)
        try:
            process_runtime.popen([explorer_path])
            return CommandResult(
                success=True,
                message="Windows 资源管理器已安全重启！",
                payload={"_suppress_result_panel": True},
            )
        except Exception as e:
            logger.debug("重启资源管理器失败", exc_info=True)
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
        logger.debug("读取配置或检查热键冲突失败", exc_info=True)
        return CommandResult(success=False, message=f"读取配置或检查热键冲突失败: {e}", error="错误")

    if not all_items:
        return CommandResult(success=True, message="当前应用内没有启用任何带有快捷键的快捷方式项目。")

    lines: list[str] = []
    hotkey_to_items: dict[str, list] = {}
    for item in all_items:
        hotkey_to_items.setdefault(item.hotkey.strip().lower(), []).append(item)

    internal_conflicts = []
    for _hk, items in hotkey_to_items.items():
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

        hotkey_keys = list(getattr(item, "hotkey_keys", []) or [])
        if not hotkey_keys and item.hotkey_key:
            hotkey_keys = [item.hotkey_key]
        if item.hotkey_modifiers and len(hotkey_keys) == 1:
            occupied = is_hotkey_registered(item.hotkey_modifiers, hotkey_keys[0])
            if occupied:
                registration_status.append(
                    f"- 项目 '{item.name}' 的快捷键 '{item.hotkey}' 注册失败，已被其他外部软件占用！"
                )

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
        success=True, message=report_msg, actions=[CommandAction(type="copy", label="复制报告", value=report_msg)]
    )


# ---------------------------------------------------------------------------
# ── QR smart helpers (shared by cmd_qr) ────────────────────────────────────
# ---------------------------------------------------------------------------

import re as _re  # noqa: E402  # local alias to avoid name conflict with future imports

_URL_DETECT = _re.compile(r"^(https?://|ftp://)[^\s]+$", _re.I)
_qr_file_servers: dict[int, tuple] = {}
_qr_server_lock = threading.Lock()
_qr_temp_files: list[str] = []


# ---------------------------------------------------------------------------
# ── /selected ─────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------
