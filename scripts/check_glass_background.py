"""Verify the pure-Python glass renderer is importable and reports its ABI."""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "ui" / "launcher_popup" / "glass_background.py"


def _expected_metadata() -> tuple[int, int]:
    text = WRAPPER_PATH.read_text(encoding="utf-8")
    abi_match = re.search(r"GLASS_ABI_VERSION\s*=\s*(\d+)", text)
    if not abi_match:
        raise RuntimeError("glass wrapper does not declare GLASS_ABI_VERSION")
    return int(abi_match.group(1)), 1


def main() -> int:
    expected_abi, _ = _expected_metadata()
    sys.path.insert(0, str(REPO_ROOT))
    try:
        module = importlib.import_module("ui.launcher_popup.glass_background")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: cannot import the pure-Python glass renderer: {exc}")
        return 1
    actual_abi = int(getattr(module, "GLASS_ABI_VERSION", -1))
    if actual_abi != expected_abi:
        print(f"FAIL: glass renderer ABI mismatch: expected {expected_abi}, got {actual_abi}")
        return 1
    if not getattr(module, "is_glass_renderer_available", lambda: False)():
        print("FAIL: Pillow is not available; the pure-Python glass renderer cannot run.")
        return 1
    print(f"OK: pure-Python glass renderer ABI={actual_abi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
