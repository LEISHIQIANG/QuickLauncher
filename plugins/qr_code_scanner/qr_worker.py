"""Persistent QR screenshot and decoding worker."""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)
PLUGIN_DIR = Path(__file__).resolve().parent
RUNTIME_SITE = PLUGIN_DIR / "runtime" / "site-packages"
APP_ROOT = Path(sys.executable or "").resolve().parent
for import_path in (RUNTIME_SITE, APP_ROOT):
    import_text = str(import_path)
    if import_path.is_dir() and import_text not in sys.path:
        sys.path.insert(0, import_text)
for dll_path in (RUNTIME_SITE, APP_ROOT, APP_ROOT / "PyQt5"):
    if not dll_path.is_dir():
        continue
    dll_text = str(dll_path)
    os.environ["PATH"] = dll_text + os.pathsep + os.environ.get("PATH", "")
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory:
        try:
            add_dll_directory(dll_text)
        except OSError:
            logger.debug("Failed to register DLL directory: %s", dll_text, exc_info=True)

from capture_qt import CaptureOverlay  # noqa: E402
from PyQt5.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402
from qr_runner import _decode_qr, _set_dpi_awareness  # noqa: E402


class _WorkerBridge(QObject):
    start_capture = pyqtSignal()
    shutdown = pyqtSignal()


class PersistentQrWorker:
    def __init__(self, channel, token: str):
        self.channel = channel
        self.token = token
        self.app = None
        self.overlays: list[CaptureOverlay] = []
        self.active_request_id = ""
        self._busy = False
        self._stopping = False
        self._state_lock = threading.Lock()
        self.bridge = _WorkerBridge()
        self.bridge.start_capture.connect(self._start_capture)
        self.bridge.shutdown.connect(self._shutdown)

    def run(self) -> int:
        _set_dpi_awareness()
        self.app = QApplication.instance() or QApplication([str(PLUGIN_DIR / "qr_worker.py")])
        self.app.setQuitOnLastWindowClosed(False)
        # Force native decoder import and DLL resolution before reporting ready.
        import zxingcpp  # noqa: F401

        self.channel.send({"type": "ready", "token": self.token})
        threading.Thread(target=self._read_requests, name="QrWorkerIPC", daemon=True).start()
        return int(self.app.exec_() or 0)

    def _read_requests(self) -> None:
        try:
            while not self._stopping:
                message = self.channel.receive()
                message_type = str(message.get("type") or "")
                if message_type == "shutdown":
                    self.bridge.shutdown.emit()
                    return
                if message_type != "request":
                    continue
                request_id = str(message.get("id") or "")
                payload = message.get("payload")
                if not isinstance(payload, dict):
                    self._send_response(request_id, {"status": "error", "message": "请求格式无效"})
                    continue
                operation = str(payload.get("operation") or "capture")
                if operation == "ping":
                    self._send_response(request_id, {"status": "ok", "ready": True})
                    continue
                if operation != "capture":
                    self._send_response(request_id, {"status": "error", "message": "不支持的二维码操作"})
                    continue
                with self._state_lock:
                    if self._busy:
                        self._send_response(request_id, {"status": "error", "message": "二维码识别正在执行"})
                        continue
                    self._busy = True
                    self.active_request_id = request_id
                self.bridge.start_capture.emit()
        except (EOFError, OSError):
            self.bridge.shutdown.emit()
        except Exception as exc:
            request_id = self.active_request_id
            if request_id:
                self._send_response(request_id, {"status": "error", "message": str(exc)})
            self.bridge.shutdown.emit()

    def _start_capture(self) -> None:
        try:
            screens = self.app.screens()
            if not screens:
                self._finish_request({"status": "error", "message": "未检测到可用屏幕"})
                return
            self.overlays = []
            for screen in screens:
                overlay = CaptureOverlay(screen, self._on_capture_finished)
                self.overlays.append(overlay)
                overlay.showFullScreen()
                overlay.activateWindow()
                overlay.raise_()
        except Exception as exc:
            self._finish_request({"status": "error", "message": str(exc)})

    def _on_capture_finished(self, image_path: str) -> None:
        self._close_overlays()
        if not image_path:
            self._finish_request({"status": "cancelled", "message": "已取消二维码截图"})
            return
        threading.Thread(
            target=self._decode,
            args=(Path(image_path),),
            name="QrDecode",
            daemon=True,
        ).start()

    def _decode(self, image_path: Path) -> None:
        try:
            text = _decode_qr(image_path)
            payload = {"status": "ok", "text": text} if text else {"status": "no_qr", "message": "未识别到二维码"}
        except Exception as exc:
            payload = {"status": "error", "message": str(exc)}
        finally:
            try:
                image_path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Failed to remove temporary QR image: %s", image_path, exc_info=True)
        self._finish_request(payload)

    def _finish_request(self, payload: dict) -> None:
        with self._state_lock:
            request_id = self.active_request_id
            self.active_request_id = ""
            self._busy = False
        if request_id:
            self._send_response(request_id, payload)

    def _send_response(self, request_id: str, payload: dict) -> None:
        self.channel.send({"type": "response", "id": request_id, "payload": payload})

    def _close_overlays(self) -> None:
        for overlay in list(self.overlays):
            try:
                overlay.hide()
                overlay.close()
                overlay.deleteLater()
            except Exception:
                logger.debug("Failed to close QR capture overlay", exc_info=True)
        self.overlays = []

    def _shutdown(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        self._close_overlays()
        if self.app is not None:
            self.app.quit()


def run_worker(channel, token: str) -> int:
    return PersistentQrWorker(channel, token).run()
