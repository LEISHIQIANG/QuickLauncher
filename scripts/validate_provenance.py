"""Validate dependency licenses and native binary provenance coverage."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _requirement_name(line: str) -> str:
    return re.split(r"[<>=!~\[]", line, maxsplit=1)[0].strip().lower().replace("_", "-")


def validate() -> list[str]:
    payload = json.loads((ROOT / "third_party_licenses.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("third-party provenance schema_version must be 1")
    entries = payload.get("python_dependencies") or []
    covered = {str(item.get("name") or "").lower().replace("_", "-") for item in entries}
    requirements = {
        _requirement_name(line)
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    for missing in sorted(requirements - covered):
        errors.append(f"missing dependency provenance: {missing}")
    for item in entries:
        if not item.get("license") or not item.get("source") or not item.get("requirement"):
            errors.append(f"incomplete dependency provenance: {item.get('name') or '<unnamed>'}")
    for item in payload.get("native_binaries") or []:
        path = ROOT / str(item.get("path") or "")
        source = ROOT / str(item.get("source") or "")
        if not path.is_file():
            errors.append(f"missing native binary: {path.relative_to(ROOT)}")
        if not source.is_file():
            errors.append(f"missing native source: {source.relative_to(ROOT)}")
        if not item.get("owner") or item.get("hash_algorithm") != "sha256":
            errors.append(f"incomplete native provenance: {item.get('path') or '<unnamed>'}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("provenance validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("provenance validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
