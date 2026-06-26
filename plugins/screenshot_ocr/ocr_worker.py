"""Persistent screenshot OCR worker."""

from __future__ import annotations

import ctypes
import importlib
import os
import sys
import threading
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent
RUNTIME_SITE = PLUGIN_DIR / "runtime" / "site-packages"
RUNTIME_WX = RUNTIME_SITE / "wx"
for runtime_path in (RUNTIME_WX, RUNTIME_SITE):
    runtime_str = str(runtime_path)
    if runtime_path.is_dir() and runtime_str not in sys.path:
        sys.path.insert(0, runtime_str)
    if runtime_path.is_dir():
        os.environ["PATH"] = runtime_str + os.pathsep + os.environ.get("PATH", "")
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory:
            try:
                add_dll_directory(runtime_str)
            except OSError:
                pass


def _import_wxpython():
    old_path = list(sys.path)
    try:
        sys.path = [entry for entry in old_path if not _is_plugin_dir(entry)]
        sys.modules.pop("wx", None)
        return importlib.import_module("wx")
    finally:
        sys.path = old_path


def _is_plugin_dir(entry: str) -> bool:
    try:
        return Path(entry or os.getcwd()).resolve() == PLUGIN_DIR
    except OSError:
        return False


wx = _import_wxpython()

from ocr_service import OCRService, process_ocr_result  # noqa: E402
from screenshot import ScreenshotFrame  # noqa: E402


def _set_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class PersistentOcrWorker:
    def __init__(self, channel, token: str):
        self.channel = channel
        self.token = token
        self.app = None
        self.ocr_service = OCRService(PLUGIN_DIR)
        self.frames = []
        self.active_display_idx = None
        self.active_request_id = ""
        self._busy = False
        self._stopping = False
        self._state_lock = threading.Lock()

    def run(self) -> int:
        _set_dpi_awareness()
        self.app = wx.App(False)
        self.app.SetExitOnFrameDelete(False)
        self.ocr_service.initialize_ocr_manager()
        # wx.MainLoop exits immediately when there are no frames at all
        # (SetExitOnFrameDelete only prevents exit when the *last* frame
        # closes, not when there are zero frames).  A hidden keepalive
        # frame keeps the loop alive until _shutdown() is called.
        self._keepalive = wx.Frame(None, size=(1, 1))
        self._keepalive.Hide()
        self.channel.send({"type": "ready", "token": self.token})
        threading.Thread(target=self._read_requests, name="OcrWorkerIPC", daemon=True).start()
        self.app.MainLoop()
        self._cleanup_engine()
        return 0

    def _read_requests(self) -> None:
        try:
            while not self._stopping:
                message = self.channel.receive()
                message_type = str(message.get("type") or "")
                if message_type == "shutdown":
                    wx.CallAfter(self._shutdown)
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
                    self._send_response(request_id, {"status": "error", "message": "不支持的 OCR 操作"})
                    continue
                with self._state_lock:
                    if self._busy:
                        self._send_response(request_id, {"status": "error", "message": "OCR 正在执行"})
                        continue
                    self._busy = True
                    self.active_request_id = request_id
                wx.CallAfter(self._start_capture)
        except (EOFError, OSError):
            wx.CallAfter(self._shutdown)
        except Exception as exc:
            request_id = self.active_request_id
            if request_id:
                self._send_response(request_id, {"status": "error", "message": str(exc)})
            wx.CallAfter(self._shutdown)

    def _start_capture(self) -> None:
        try:
            self.active_display_idx = None
            self.frames = []
            for display_idx in range(wx.Display.GetCount()):
                frame = ScreenshotFrame(
                    display_idx,
                    self._on_screenshot_captured,
                    active_callback=self._set_active_display,
                    is_active_callback=self._is_active_display,
                )
                self.frames.append(frame)
                frame.Show()
        except Exception as exc:
            self._finish_request({"status": "error", "message": str(exc)})

    def _set_active_display(self, display_idx) -> None:
        if self.active_display_idx == display_idx:
            return
        self.active_display_idx = display_idx
        for frame in list(self.frames):
            try:
                frame.set_interaction_active(frame.display_idx == display_idx)
            except Exception:
                pass

    def _is_active_display(self, display_idx) -> bool:
        return self.active_display_idx == display_idx

    def _on_screenshot_captured(self, temp_path) -> None:
        self._destroy_frames()
        if not temp_path:
            self._finish_request({"status": "cancelled", "message": "已取消截图 OCR"})
            return
        threading.Thread(
            target=self._recognize,
            args=(str(temp_path),),
            name="OcrRecognition",
            daemon=True,
        ).start()

    def _recognize(self, temp_path: str) -> None:
        try:
            results = self.ocr_service.process_ocr(temp_path, timeout=25.0)
            lines = process_ocr_result(results)
            payload = {"status": "ok", "text": "\n".join(lines), "line_count": len(lines)}
        except Exception as exc:
            payload = {"status": "error", "message": str(exc)}
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
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

    def _destroy_frames(self) -> None:
        for frame in list(self.frames):
            try:
                frame.on_capture_callback = None
                frame.Hide()
                frame.Destroy()
            except Exception:
                pass
        self.frames = []

    def _shutdown(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        self._destroy_frames()
        try:
            self._keepalive.Destroy()
        except Exception:
            pass
        if self.app is not None:
            self.app.ExitMainLoop()

    def _cleanup_engine(self) -> None:
        try:
            self.ocr_service.reset_ocr_manager()
        except Exception:
            pass


def run_worker(channel, token: str) -> int:
    return PersistentOcrWorker(channel, token).run()
