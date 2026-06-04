"""Run the original wx screenshot flow and print OCR text for QuickLauncher."""

from __future__ import annotations

import ctypes
import importlib
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent


def _import_wxpython():
    old_path = list(sys.path)
    try:
        filtered_path = [e for e in old_path if not _is_plugin_dir(e)]
        sys.path = filtered_path
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

from ocr_service import OCRService, process_ocr_result
from screenshot import ScreenshotFrame

SENTINEL = "QL_SCREENSHOT_OCR_RESULT="


def emit_result(payload: dict) -> None:
    print(SENTINEL + json.dumps(payload, ensure_ascii=False), flush=True)


def _set_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class QuickLauncherOcrApp(wx.App):
    def OnInit(self):
        self.ocr_service = OCRService(Path(__file__).resolve().parent)
        self.frames = []
        self.callback_triggered = False
        self.active_display_idx = None

        threading.Thread(target=self._bg_init_ocr, daemon=True).start()

        for display_idx in range(wx.Display.GetCount()):
            frame = ScreenshotFrame(
                display_idx,
                self.on_screenshot_captured,
                active_callback=self.set_active_display,
                is_active_callback=self.is_active_display,
            )
            self.frames.append(frame)
            frame.Show()
        return True

    def _bg_init_ocr(self):
        try:
            self.ocr_service.initialize_ocr_manager()
        except Exception as exc:
            print(f"Background OCR init failed: {exc}", file=sys.stderr, flush=True)

    def set_active_display(self, display_idx):
        if self.active_display_idx == display_idx:
            return
        self.active_display_idx = display_idx
        for frame in list(self.frames):
            try:
                frame.set_interaction_active(frame.display_idx == display_idx)
            except Exception:
                pass

    def is_active_display(self, display_idx):
        return self.active_display_idx == display_idx

    def on_screenshot_captured(self, temp_path):
        if self.callback_triggered:
            return
        self.callback_triggered = True

        for frame in list(self.frames):
            try:
                frame.on_capture_callback = None
                frame.Hide()
                frame.Destroy()
            except Exception:
                pass
        self.frames = []

        if not temp_path:
            emit_result({"status": "cancelled", "message": "已取消截图 OCR"})
            self.ExitMainLoop()
            return

        try:
            results = self.ocr_service.process_ocr(temp_path, timeout=25.0)
            lines = process_ocr_result(results)
            emit_result({"status": "ok", "text": "\n".join(lines), "line_count": len(lines)})
        except Exception as exc:
            emit_result({"status": "error", "message": str(exc)})
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
            try:
                self.ocr_service.reset_ocr_manager()
            except Exception:
                pass
            self.ExitMainLoop()


def main() -> int:
    _set_dpi_awareness()
    os.makedirs(tempfile.gettempdir(), exist_ok=True)
    app = QuickLauncherOcrApp()
    app.MainLoop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
