import atexit
import ctypes
import json
import logging
import os
import re
import secrets
import tempfile

logger = logging.getLogger(__name__)
_ERROR_ALREADY_EXISTS = 183
_instance_mutex_handles: set[tuple[object, int]] = set()


def create_ipc_server(
    app,
    server_name: str,
    on_show_config,
    *,
    token_path: str | None = None,
    remove_stale: bool = False,
):
    """创建 IPC 本地服务器，返回 server 对象"""
    from qt_compat import QLocalServer, QTimer

    _pending = {"show_config": False}
    session_token = secrets.token_urlsafe(32)
    token_file = token_path or _ipc_token_path(server_name)

    def _on_new_connection():
        handled = 0
        while server.hasPendingConnections():
            try:
                conn = server.nextPendingConnection()
                if not conn:
                    break
                ready = any(conn.waitForReadyRead(100) for _ in range(12))
                if not ready:
                    conn.disconnectFromServer()
                    conn.deleteLater()
                    continue
                data = bytes(conn.readAll() or b"")
                cmd = _parse_ipc_command(data, session_token)
                logger.debug(f"IPC: 收到命令 '{cmd}'")
                if cmd == "show_config":
                    cb = on_show_config()
                    if cb:
                        QTimer.singleShot(0, cb)
                    else:
                        _pending["show_config"] = True
                ack = json.dumps({"ok": cmd == "show_config"}).encode("utf-8")
                conn.write(ack)
                conn.flush()
                conn.waitForBytesWritten(200)
                conn.disconnectFromServer()
                conn.deleteLater()
                handled += 1
            except (OSError, RuntimeError, ValueError):
                logger.exception("IPC单连接处理失败，已处理连接数: %s", handled)

    server = QLocalServer()
    if remove_stale:
        server.removeServer(server_name)
    if not server.listen(server_name):
        logger.warning(f"无法创建本地服务器: {server.errorString()}")
    else:
        _write_ipc_token(token_file, session_token)
        atexit.register(_remove_ipc_token, token_file, session_token)
    server.newConnection.connect(_on_new_connection)
    return server, _pending


def try_connect_existing(server_name: str, *, token_path: str | None = None) -> bool:
    """尝试连接已有实例，成功则发送 show_config 并返回 True"""
    from qt_compat import QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer(server_name)
    connected = socket.waitForConnected(100)
    if not connected:
        try:
            err = (socket.errorString() or "").lower()
            if "not found" not in err and "不存在" not in err:
                connected = socket.waitForConnected(200)
        except RuntimeError:
            connected = socket.waitForConnected(200)
    if connected:
        try:
            token = _read_ipc_token(token_path or _ipc_token_path(server_name))
            if not token:
                logger.warning("IPC token 不存在，拒绝发送未鉴权命令")
                socket.close()
                return False
            payload = json.dumps({"token": token, "command": "show_config"}, ensure_ascii=False).encode("utf-8")
            written = int(socket.write(payload))
            if written != len(payload):
                socket.close()
                return False
            socket.flush()
            if int(socket.bytesToWrite()) > 0 and not socket.waitForBytesWritten(200):
                socket.close()
                return False
            if not socket.waitForReadyRead(500):
                socket.close()
                return False
            ack = json.loads(bytes(socket.readAll() or b"").decode("utf-8"))
            if not isinstance(ack, dict) or ack.get("ok") is not True:
                socket.close()
                return False
        except (OSError, RuntimeError, TypeError, ValueError):
            logger.debug("发送IPC消息失败", exc_info=True)
            socket.close()
            return False
        socket.close()
        return True
    socket.close()
    return False


def acquire_instance_mutex(server_name: str):
    """Atomically claim process ownership on Windows.

    The kernel releases this mutex automatically after a crash, unlike a
    QLocalServer endpoint file.  ``None`` means another process owns it.
    """
    if os.name != "nt":
        return (None, id(server_name))
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(server_name or "quicklauncher"))
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, f"Local\\{safe_name}")
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return None
    token = (kernel32, int(handle))
    _instance_mutex_handles.add(token)
    atexit.register(release_instance_mutex, token)
    return token


def release_instance_mutex(token) -> None:
    if not token or token not in _instance_mutex_handles:
        return
    _instance_mutex_handles.discard(token)
    kernel32, handle = token
    if kernel32 is not None:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def _parse_ipc_command(data: bytes, expected_token: str) -> str:
    text = data.decode("utf-8", errors="ignore").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    token = str(payload.get("token") or "")
    command = str(payload.get("command") or "").strip().lower()
    if token != expected_token:
        logger.warning("IPC: token 校验失败")
        return ""
    return command if command in {"show_config"} else ""


def _ipc_token_path(server_name: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(server_name or "quicklauncher"))
    return os.path.join(tempfile.gettempdir(), f"{safe_name}.token")


def _write_ipc_token(path: str, token: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(token)
    os.replace(tmp_path, path)


def _read_ipc_token(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _remove_ipc_token(path: str, token: str) -> None:
    try:
        if _read_ipc_token(path) == token:
            os.remove(path)
    except OSError:
        logger.debug("清理 IPC token 失败", exc_info=True)
