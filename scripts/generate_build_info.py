"""Generate deterministic provenance metadata for a packaged runtime."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(args: list[str]) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def build_info(binary: Path | None = None) -> dict[str, Any]:
    manifest = json.loads((ROOT / "runtime_manifest.json").read_text(encoding="utf-8"))
    lock_files = [ROOT / "requirements.txt", ROOT / "requirements-dev.txt"]
    lock_digest = hashlib.sha256()
    for path in lock_files:
        lock_digest.update(path.name.encode("utf-8"))
        lock_digest.update(path.read_bytes())
    binary_hashes = {}
    if binary is not None and binary.is_file():
        binary_hashes[binary.name] = _sha256(binary)
    return {
        "schema_version": 1,
        "source": {
            "commit": _git(["rev-parse", "HEAD"]),
            "dirty": bool(_git(["status", "--porcelain"])),
        },
        "toolchain": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "nuitka": _package_version("Nuitka"),
        },
        "dependency_lock_sha256": lock_digest.hexdigest(),
        "contracts": dict(manifest["versions"]),
        "binary_sha256": binary_hashes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_info(args.binary), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"build info written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
