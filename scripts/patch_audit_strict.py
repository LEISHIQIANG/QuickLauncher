"""Apply --strict to all audit_*.py scripts in one shot.

For each ``scripts/audit_*.py`` file that does not already accept a
``--strict`` flag, inject the corresponding argparse lines + the
``if args.strict: args.max = 0`` runtime override. Idempotent: a
second run is a no-op.

Usage
-----

::

    python scripts/patch_audit_strict.py
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"


def _has_strict(text: str) -> bool:
    return '"--strict"' in text or "'--strict'" in text


def _patch(text: str) -> str:
    if _has_strict(text):
        return text
    # Add the --strict argument to the parser
    text = re.sub(
        r'(\.add_argument\("--max",[^)]+\))',
        r'\1\n    parser.add_argument("--strict", action="store_true", help="Alias for --max=0 (CI blocking)")',
        text,
        count=1,
    )
    # Add the override after `args = parser.parse_args(argv)`
    text = re.sub(
        r"(\s*args = parser\.parse_args\(argv\))",
        r"\1\n    if args.strict:\n        args.max = 0",
        text,
        count=1,
    )
    return text


def main() -> int:
    count = 0
    for path in sorted(SCRIPTS.glob("audit_*.py")):
        text = path.read_text(encoding="utf-8")
        if _has_strict(text):
            continue
        new_text = _patch(text)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            count += 1
            print(f"Patched {path.name}")
    print("---")
    print(f"Total patched: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
