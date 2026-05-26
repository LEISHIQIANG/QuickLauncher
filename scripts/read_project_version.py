#!/usr/bin/env python
"""Print QuickLauncher release metadata for shell build scripts."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


def _load_metadata() -> dict[str, str]:
    version_file = Path(__file__).resolve().parents[1] / "core" / "version.py"
    module = ast.parse(version_file.read_text(encoding="utf-8"), filename=str(version_file))
    values: dict[str, str] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not target.id.startswith("APP_"):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            values[target.id] = node.value.value
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("field", choices=("version", "publisher", "id", "name"))
    args = parser.parse_args(argv)

    key = {
        "version": "APP_VERSION",
        "publisher": "APP_PUBLISHER",
        "id": "APP_ID",
        "name": "APP_NAME",
    }[args.field]
    print(_load_metadata()[key])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
