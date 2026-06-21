"""Audit ``border: none`` declarations that lack a ``border-radius: 0``.

Per §1.1 and §4.5 of ``UI_OPTIMIZATION_PLAN.md`` every ``border: none``
in a QSS string must be paired with ``border-radius: 0``; otherwise the
runtime border radius set in the corresponding ``paintEvent`` clashes
with the cascade and produces a fuzzy edge on 125%+ DPI displays.

The audit scans the whole project (QSS files + ``*.py`` string
literals containing ``border: none``) and reports each line that does
not have ``border-radius: 0`` somewhere on the same rule.

Usage
-----

::

    python scripts/audit_qss_radius.py
    python scripts/audit_qss_radius.py --max=120
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("ui",)

# File extensions we look at
EXTENSIONS = (".py", ".qss", ".css")

BORDER_NONE_RE = re.compile(r"border\s*:\s*none\s*;?", re.IGNORECASE)
BORDER_RADIUS_RE = re.compile(r"border-radius\s*:\s*0", re.IGNORECASE)

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
}


def _iter_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix in EXTENSIONS:
                yield path


def _scan_file(path: Path) -> Iterable[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not BORDER_NONE_RE.search(line):
            continue
        # The line should contain border-radius: 0 in the same declaration.
        # We only inspect the *same line* to keep the heuristic simple.
        if BORDER_RADIUS_RE.search(line):
            continue
        yield lineno, line.strip()


def audit(roots: Iterable[Path], max_violations: int) -> int:
    violations = 0
    per_file: list[tuple[Path, int]] = []
    for path in _iter_files(roots):
        rel = path.relative_to(PROJECT_ROOT)
        rel_str = str(rel).replace("\\", "/")
        if rel_str in WHITELIST_FILES:
            continue
        hits = list(_scan_file(path))
        if not hits:
            continue
        per_file.append((rel, len(hits)))
        violations += len(hits)
        for lineno, snippet in hits:
            print(f"{rel_str}:{lineno}: {snippet}")

    print("---")
    print(f"Files flagged: {len(per_file)} | total violations: {violations}")
    for rel, count in sorted(per_file, key=lambda t: -t[1])[:20]:
        print(f"  {rel}: {count}")

    if violations > max_violations:
        print(f"FAIL: {violations} > max {max_violations}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max", type=int, default=120, help="Maximum allowed violations")
    parser.add_argument("--strict", action="store_true", help="Alias for --max=0 (CI blocking)")
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args(argv)
    if args.strict:
        args.max = 0

    roots = [PROJECT_ROOT / r for r in args.roots]
    return audit(roots, args.max)


if __name__ == "__main__":
    sys.exit(main())
