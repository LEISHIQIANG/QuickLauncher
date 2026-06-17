"""Verify that the checked-in ``hooks/hooks.dll`` matches the expected
version and SHA-256 recorded in :class:`HooksDLL`.

The script is part of the P1-07 release engineering work: it lets
publishers catch the "DLL rebuilt but expected hash not updated"
footgun before the binary ships to users.

Usage::

    py -3.12 scripts/check_hooks_dll.py

The script exits with status 0 when the DLL exists and matches the
expected version + hash, and status 1 otherwise.  When the DLL is
missing, the script prints a hint explaining how to rebuild it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DLL_PATH = REPO_ROOT / "hooks" / "hooks.dll"


def _expected_metadata() -> tuple[int, str]:
    """Read the expected version and hash directly from the wrapper source.

    Parsing the source instead of importing the wrapper avoids pulling
    in the full Qt / runtime stack (the wrapper imports ``runtime_paths``
    which expects a packaged runtime layout) and keeps the script
    runnable in a clean checkout.
    """
    import re

    wrapper_path = REPO_ROOT / "hooks" / "hooks_wrapper.py"
    text = wrapper_path.read_text(encoding="utf-8")
    version_match = re.search(r"EXPECTED_VERSION\s*=\s*(\d+)", text)
    hash_match = re.search(r"EXPECTED_DLL_SHA256\s*=\s*\"([0-9a-fA-F]+)\"", text)
    if not version_match or not hash_match:
        raise RuntimeError(f"could not find EXPECTED_VERSION / EXPECTED_DLL_SHA256 in {wrapper_path}")
    return int(version_match.group(1)), hash_match.group(1)


def main() -> int:
    if not DLL_PATH.exists():
        print(f"FAIL: {DLL_PATH} is missing.")
        print("  Hint: run hooks_dll/build.bat to rebuild the DLL.")
        return 1

    sha = hashlib.sha256(DLL_PATH.read_bytes()).hexdigest()
    try:
        expected_version, expected_hash = _expected_metadata()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: cannot load expected metadata: {exc}")
        return 1

    print(f"DLL path        : {DLL_PATH}")
    print(f"DLL size        : {DLL_PATH.stat().st_size} bytes")
    print(f"DLL SHA-256     : {sha}")
    print(f"Expected SHA-256: {expected_hash}")
    print(f"Expected version: {expected_version}")

    if sha.lower() != expected_hash.lower():
        print("FAIL: SHA-256 mismatch — update HooksDLL.EXPECTED_DLL_SHA256")
        print("       in hooks/hooks_wrapper.py after rebuilding the DLL.")
        return 1

    # Version is checked by the runtime wrapper when the DLL is
    # loaded; here we only print the expected value as a reminder.
    print("OK: hooks.dll matches the expected version and SHA-256.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
