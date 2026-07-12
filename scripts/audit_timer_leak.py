"""Audit ``QTimer.singleShot`` calls that should be animations.

Per §4.10.3 of ``UI_OPTIMIZATION_PLAN.md`` ``QTimer.singleShot`` should
not be used as a poor man's animation primitive – use
``QPropertyAnimation`` or :mod:`ui.utils.animations` instead. This
script flags every ``QTimer.singleShot`` call whose callback performs a
visible widget mutation (``setX`` / ``setY`` / ``setGeometry`` /
``setWindowOpacity`` / ``setProperty`` / ``show`` / ``hide``).

The audit is *warning* by default (S1-S6) and becomes blocking during
the S8 hardening window.

Usage
-----

::

    python scripts/audit_timer_leak.py
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("ui",)

SINGLE_SHOT_RE = re.compile(r"QTimer\.singleShot\s*\(\s*(\d+)\s*,")
SETTER_RE = re.compile(
    r"\.set(?:WindowOpacity|Property|Geometry|Pos|Value|Text|Visible|Enabled|Size|MaximumWidth|MaximumHeight|MinimumWidth|MinimumHeight)\s*\("
)

WHITELIST_FILES = {
    "ui/utils/animations.py",
    "ui/utils/motion.py",
    "ui/utils/pixel_snap.py",
    "ui/utils/lru_cache.py",
    "ui/utils/font_manager.py",
    "ui/utils/interruptible_animation.py",
    "ui/styles/standard_widgets.py",
    "ui/styles/focus_ring.py",
    "ui/styles/design_tokens.py",
    "scripts/audit_timer_leak.py",
}


def _iter_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def _scan_file(path: Path) -> Iterable[tuple[int, str, int]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    lines = text.splitlines()
    for lineno, line in enumerate(lines, start=1):
        m = SINGLE_SHOT_RE.search(line)
        if not m:
            continue
        duration = int(m.group(1))
        snippet = line
        if ")" not in snippet[line.index("QTimer.singleShot") :]:
            end = lineno
            depth = line.count("(") - line.count(")")
            while depth > 0 and end < len(lines):
                end += 1
                depth += lines[end - 1].count("(") - lines[end - 1].count(")")
                snippet += " " + lines[end - 1]
        if SETTER_RE.search(snippet):
            yield lineno, line.strip(), duration


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
        for lineno, snippet, duration in hits[:3]:
            print(f"{rel_str}:{lineno}: {duration}ms :: {snippet[:100]}")
        if len(hits) > 3:
            print(f"  ... and {len(hits) - 3} more in {rel_str}")

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
    parser.add_argument("--max", type=int, default=200, help="Maximum allowed violations")
    parser.add_argument("--strict", action="store_true", help="Alias for --max=0 (CI blocking)")
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args(argv)
    if args.strict:
        args.max = 0

    roots = [PROJECT_ROOT / r for r in args.roots]
    return audit(roots, args.max)


if __name__ == "__main__":
    sys.exit(main())
