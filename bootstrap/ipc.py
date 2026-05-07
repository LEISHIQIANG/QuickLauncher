import logging
import traceback

logger = logging.getLogger(__name__)


def create_ipc_server(app, server_name: str, on_show_config):
    """创建 IPC 本地服务器，返回 server 对象"""
    from qt_compat import QLocalServer, QLocalSocket, QTimer

    _pending = {'show_config': False}

    def _on_new_connection():
        try:
            while server.hasPendingConnections():
                conn = server.nextPendingConnection()
                if not conn:
                    break
                ready = any(conn.waitForReadyRead(100) for _ in range(12))
                if not ready:
                    conn.disconnectFromServer()
                    conn.deleteLater()
                    continue
                data = bytes(conn.readAll() or b"")
                conn.disconnectFromServer()
                conn.deleteLater()
                try:
                    cmd = data.decode("utf-8", errors="ignore").strip().lower()
                except Exception:
                    cmd = ""
                logger.debug(f"IPC: 收到命令 '{cmd}'")
                if cmd == "show_config":
                    cb = on_show_config()
                    if cb:
                        QTimer.singleShot(0, cb)
                    else:
                        _pending['show_config'] = True
        except Exception as e:
            logger.error(f"IPC处理失败: {e}\n{traceback.format_exc()}")

    server = QLocalServer()
    server.removeServer(server_name)
    if not server.listen(server_name):
        logger.warning(f"无法创建本地服务器: {server.errorString()}")
    server.newConnection.connect(_on_new_connection)
    return server, _pending


def try_connect_existing(server_name: str) -> bool:
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
        except Exception:
            connected = socket.waitForConnected(200)
    if connected:
        try:
            socket.write(b"show_config")
            socket.flush()
            socket.waitForBytesWritten(200)
        except Exception:
            pass
        socket.close()
        return True
    socket.close()
    return False
