"""Auto-fix ``border: none`` violations in QSS strings / Python sources.

Per §1.1 and §4.5 of ``UI_OPTIMIZATION_PLAN.md`` every ``border: none``
declaration must be paired with ``border-radius: 0`` to avoid QSS /
paintEvent rounding conflicts. This script rewrites the offending
lines in-place.

The script is conservative: it never modifies a line that already
contains ``border-radius: 0`` (case insensitive). The match is done
on the literal string ``border: none;`` (or ``border : none;`` with
optional spaces) to avoid touching other ``border`` properties.

Usage
-----

::

    python scripts/fix_border_radius.py --dry-run   # show changes
    python scripts/fix_border_radius.py             # apply changes
    python scripts/fix_border_radius.py --path ui/launcher_popup
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("ui",)

BORDER_NONE_RE = re.compile(r"border\s*:\s*none\s*;?", re.IGNORECASE)
BORDER_RADIUS_RE = re.compile(r"border-radius\s*:\s*0\b", re.IGNORECASE)

WHITELIST_FILES = {
    "ui/styles/design_tokens.py",
    "ui/utils/lru_cache.py",
    "ui/utils/pixel_snap.py",
    "ui/utils/animations.py",
    "ui/utils/motion.py",
    "ui/utils/font_manager.py",
    "ui/utils/interruptible_animation.py",
    "ui/styles/standard_widgets.py",
    "ui/styles/focus_ring.py",
    "scripts/fix_border_radius.py",
}


def _iter_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix in (".py", ".qss", ".css"):
                yield path


def _fix_line(line: str) -> str:
    if not BORDER_NONE_RE.search(line):
        return line
    if BORDER_RADIUS_RE.search(line):
        return line
    return BORDER_NONE_RE.sub(
        lambda m: f"{m.group(0)} border-radius: 0;",
        line,
        count=1,
    )


def fix_files(roots: Iterable[Path], dry_run: bool) -> int:
    fixed = 0
    files = 0
    for path in _iter_files(roots):
        rel = path.relative_to(PROJECT_ROOT)
        rel_str = str(rel).replace("\\", "/")
        if rel_str in WHITELIST_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        new_lines = []
        changed = 0
        for line in text.splitlines(keepends=False):
            new_line = _fix_line(line)
            if new_line != line:
                changed += 1
            new_lines.append(new_line)
        if changed:
            files += 1
            fixed += changed
            if dry_run:
                for orig, new in zip(text.splitlines(), new_lines):
                    if orig != new:
                        print(f"{rel_str}: {orig.strip()}")
                        print(f"      → {new.strip()}")
            else:
                new_text = "\n".join(new_lines)
                if text.endswith("\n"):
                    new_text += "\n"
                path.write_text(new_text, encoding="utf-8")
                print(f"Fixed {changed} lines in {rel_str}")
    print("---")
    print(f"Files affected: {files} | lines fixed: {fixed}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    parser.add_argument("--path", type=str, default=None, help="Restrict to a sub-path")
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args(argv)

    roots = [PROJECT_ROOT / r for r in args.roots]
    if args.path:
        roots = [r / args.path for r in roots]
    return fix_files(roots, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
