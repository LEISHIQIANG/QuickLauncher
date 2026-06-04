"""WeChat OCR service wrapper used by the QuickLauncher plugin helper."""

from __future__ import annotations

import gc
import os
import sys
import threading
from pathlib import Path
from typing import Any

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
if VENDOR_DIR.is_dir():
    sys.path.insert(0, str(VENDOR_DIR))

from wechat_ocr.ocr_manager import OcrManager

OCR_ENGINE_DIR = "ocrTx"
OCR_LIB_DIR = "wx"

_instances: list["OCRService"] = []


def _plugin_dir() -> Path:
    return Path(__file__).resolve().parent


def ocr_result_callback(img_path: str, results: dict[str, Any]) -> None:
    abs_img_path = os.path.abspath(img_path).lower()
    for instance in list(_instances):
        matched_key = None
        for key in list(instance.active_tasks.keys()):
            if os.path.abspath(key).lower() == abs_img_path:
                matched_key = key
                break
        if matched_key:
            instance.results[matched_key] = results
            instance.active_tasks[matched_key].set()


def process_ocr_result(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return []
    result_list: list[str] = []
    for result in data.get("ocrResult", []) or []:
        text = str(result.get("text", "") or "").strip()
        if text:
            result_list.append(text)
    return result_list


class OCRService:
    def __init__(self, base_dir: str | os.PathLike[str] | None = None):
        self.base_dir = Path(base_dir) if base_dir is not None else _plugin_dir()
        self.ocr_manager: OcrManager | None = None
        self.active_tasks: dict[str, threading.Event] = {}
        self.results: dict[str, dict[str, Any]] = {}
        if self not in _instances:
            _instances.append(self)

    def initialize_ocr_manager(self) -> None:
        if self.ocr_manager is not None:
            return
        lib_dir = self.base_dir / OCR_LIB_DIR
        ocr_dir = self.base_dir / OCR_ENGINE_DIR
        if not lib_dir.is_dir():
            raise FileNotFoundError(f"OCR 依赖目录不存在: {lib_dir}")
        if not ocr_dir.is_dir():
            raise FileNotFoundError(f"OCR 程序目录不存在: {ocr_dir}")

        manager = OcrManager(str(lib_dir))
        manager.SetExePath(str(ocr_dir))
        manager.SetUsrLibDir(str(lib_dir))
        manager.SetOcrResultCallback(ocr_result_callback)
        manager.StartWeChatOCR()
        self.ocr_manager = manager

    def process_ocr(self, img_path: str, timeout: float = 25.0) -> dict[str, Any] | None:
        if self.ocr_manager is None:
            self.initialize_ocr_manager()

        event = threading.Event()
        self.active_tasks[img_path] = event
        try:
            assert self.ocr_manager is not None
            self.ocr_manager.DoOCRTask(img_path)
            if not event.wait(timeout=max(1.0, float(timeout or 0))):
                return None
            return self.results.pop(img_path, None)
        finally:
            self.active_tasks.pop(img_path, None)
            gc.collect()

    def reset_ocr_manager(self) -> None:
        if self.ocr_manager is not None:
            try:
                self.ocr_manager.KillWeChatOCR()
            finally:
                self.ocr_manager = None
        if self in _instances:
            _instances.remove(self)
        gc.collect()
