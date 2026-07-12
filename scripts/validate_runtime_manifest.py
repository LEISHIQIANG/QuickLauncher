"""Validate the authoritative runtime graph against active build scripts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "runtime_manifest.json"


def _load(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("runtime manifest schema_version must be 1")
    return raw


def validate(path: Path = DEFAULT_MANIFEST) -> list[str]:
    manifest = _load(path)
    errors: list[str] = []
    targets = [ROOT / value for value in manifest.get("build_targets", [])]
    target_text = {}
    for target in targets:
        if not target.is_file():
            errors.append(f"missing build target: {target.relative_to(ROOT)}")
            continue
        target_text[target] = target.read_text(encoding="utf-8", errors="replace")

    for package in manifest.get("required_packages", []):
        if not (ROOT / package).is_dir():
            errors.append(f"missing required package directory: {package}")
        token = f"--include-package={package}"
        for target, text in target_text.items():
            if token not in text:
                errors.append(f"{target.relative_to(ROOT)} missing {token}")

    declared_packages = set(manifest.get("required_packages", [])) | set(manifest.get("external_packages", []))
    for target, text in target_text.items():
        actual_packages = set(re.findall(r"--include-package=([^\s^]+)", text))
        for package in sorted(actual_packages - declared_packages):
            errors.append(f"{target.relative_to(ROOT)} has undeclared include package {package}")

    for module in manifest.get("hidden_imports", []):
        token = f"--include-module={module}"
        for target, text in target_text.items():
            if token not in text:
                errors.append(f"{target.relative_to(ROOT)} missing {token}")

    declared_modules = set(manifest.get("hidden_imports", []))
    for target, text in target_text.items():
        actual_modules = set(re.findall(r"--include-module=([^\s^]+)", text))
        for module in sorted(actual_modules - declared_modules):
            errors.append(f"{target.relative_to(ROOT)} has undeclared hidden import {module}")

    for entry in manifest.get("data_files", []):
        source = str(entry.get("source") or "")
        if not source or not (ROOT / source).exists():
            errors.append(f"missing runtime data source: {source or '<empty>'}")
            continue
        normalized = source.replace("/", "\\")
        for target, text in target_text.items():
            if normalized not in text:
                errors.append(f"{target.relative_to(ROOT)} missing data source {source}")

    storage = manifest.get("plugin_storage", {})
    if storage.get("bundle_source_plugins") is not False:
        errors.append("plugin_storage.bundle_source_plugins must be false")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    errors = validate(args.manifest.resolve())
    if errors:
        print("runtime manifest validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("runtime manifest validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
