"""Capture a screen rectangle and decode QR codes."""

from __future__ import annotations

import ctypes
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)
PLUGIN_DIR = Path(__file__).resolve().parent
RUNTIME_SITE = PLUGIN_DIR / "runtime" / "site-packages"
APP_ROOT = Path(sys.executable or "").resolve().parent
for import_path in (RUNTIME_SITE, APP_ROOT):
    import_str = str(import_path)
    if import_path.is_dir() and import_str not in sys.path:
        sys.path.insert(0, import_str)
for dll_path in (RUNTIME_SITE, APP_ROOT, APP_ROOT / "PyQt5"):
    dll_str = str(dll_path)
    if not dll_path.is_dir():
        continue
    os.environ["PATH"] = dll_str + os.pathsep + os.environ.get("PATH", "")
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory:
        try:
            add_dll_directory(dll_str)
        except OSError:
            logger.debug("Failed to register DLL directory: %s", dll_str, exc_info=True)

from PIL import Image, ImageOps  # noqa: E402, I001

from capture_qt import capture_region  # noqa: E402

SENTINEL = "QL_SCREENSHOT_QR_RESULT="


def emit_result(payload: dict) -> None:
    print(SENTINEL + json.dumps(payload, ensure_ascii=False), flush=True)


def _set_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        logger.debug("Per-monitor DPI awareness is unavailable", exc_info=True)
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            logger.debug("System DPI awareness is unavailable", exc_info=True)


def _candidate_images(image: Image.Image) -> list[Image.Image]:
    rgb = image.convert("RGB")
    gray = ImageOps.grayscale(rgb)
    candidates = [rgb, gray, ImageOps.autocontrast(gray)]
    width, height = gray.size
    if max(width, height) < 1200:
        candidates.append(gray.resize((width * 2, height * 2), Image.Resampling.NEAREST))
    for threshold in (96, 128, 160, 192):
        candidates.append(gray.point(lambda p, t=threshold: 255 if p >= t else 0))
    return candidates


def _decode_qr(image_path: Path) -> str:
    try:
        import zxingcpp
    except Exception as exc:
        raise RuntimeError(f"二维码解码组件不可用: {exc}") from exc

    seen: set[str] = set()
    with Image.open(image_path) as img:
        for candidate in _candidate_images(img):
            try:
                barcodes = zxingcpp.read_barcodes(candidate)
            except Exception:
                continue
            for barcode in barcodes:
                text = str(getattr(barcode, "text", "") or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                return text
    return ""


def main() -> int:
    _set_dpi_awareness()
    Path(tempfile.gettempdir()).mkdir(parents=True, exist_ok=True)
    image_path = capture_region()
    if not image_path:
        emit_result({"status": "cancelled", "message": "已取消二维码截图"})
        return 0

    path = Path(image_path)
    try:
        text = _decode_qr(path)
        if not text:
            emit_result({"status": "no_qr", "message": "未识别到二维码"})
            return 0
        emit_result({"status": "ok", "text": text})
        return 0
    except Exception as exc:
        emit_result({"status": "error", "message": str(exc)})
        return 1
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.debug("Failed to remove temporary QR image: %s", path, exc_info=True)


if __name__ == "__main__":
    raise SystemExit(main())
