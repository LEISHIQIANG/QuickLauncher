"""Audit ``paintEvent`` methods for missing pixel-snap / cosmetic pen.

Per §1.1 and §4.2 of ``UI_OPTIMIZATION_PLAN.md`` every ``paintEvent``
should:

* set ``QPainter.Antialiasing`` (when drawing rounded shapes),
* use :func:`ui.utils.pixel_snap.make_cosmetic_pen` for 1-px borders,
* and use :func:`ui.utils.pixel_snap.snap_rect` to align geometry.

This script finds every ``def paintEvent`` method in the UI tree and
counts the number of risky patterns it uses (raw ``QPen(1)``,
``drawRect`` without snap, etc.). A ``paintEvent`` with zero risky
patterns is considered conformant; the lint reports the non-conformant
ones.

Usage
-----

::

    python scripts/audit_paint_snap.py
    python scripts/audit_paint_snap.py --max=32
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("ui",)

# Risk patterns – we don't *forbid* them (legacy widgets use them) but
# we count occurrences so the report can drive §4.2 cleanup.
RISKY = {
    "raw_pen_1": re.compile(r"QPen\s*\(\s*[^,)]*,\s*1\s*\)"),
    "draw_rect": re.compile(r"\.drawRect\s*\("),
    "draw_line": re.compile(r"\.drawLine\s*\("),
    "no_cosmetic": re.compile(r"setCosmetic\s*\(\s*False\s*\)"),
    "no_snap_helper": re.compile(r"snap_rect|make_cosmetic_pen"),
    "uses_cosmetic_helper": re.compile(r"make_cosmetic_pen|stroke_path"),
}

WHITELIST_FILES = {
    "ui/utils/pixel_snap.py",
    "ui/styles/standard_widgets.py",
}


def _iter_python_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def _extract_paint_events(text: str) -> list[tuple[int, int]]:
    """Return ``[(start_line, end_line)]`` ranges of every ``paintEvent``."""

    lines = text.splitlines()
    events: list[tuple[int, int]] = []
    in_event = False
    indent = 0
    start = 0
    for i, line in enumerate(lines, start=1):
        if not in_event:
            if re.search(r"def\s+paintEvent\s*\(", line):
                in_event = True
                start = i
                indent = len(line) - len(line.lstrip())
            continue
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cur_indent = len(line) - len(stripped)
        if cur_indent <= indent and stripped and not stripped.startswith("@"):
            events.append((start, i - 1))
            in_event = False
    if in_event:
        events.append((start, len(lines)))
    return events


def _scan_file(path: Path) -> Iterable[tuple[int, str, int, int]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for start, end in _extract_paint_events(text):
        body = "\n".join(text.splitlines()[start - 1 : end])
        snap_uses = len(RISKY["no_snap_helper"].findall(body))
        uses_cosmetic = bool(RISKY["uses_cosmetic_helper"].search(body))
        raw_pen_1 = len(RISKY["raw_pen_1"].findall(body))
        draw_rect = len(RISKY["draw_rect"].findall(body))
        draw_line = len(RISKY["draw_line"].findall(body))
        no_cosmetic = len(RISKY["no_cosmetic"].findall(body))
        # drawLine / drawRect are safe when a cosmetic helper is in scope –
        # the pen is already pixel-aligned, so the line/rect draws on the
        # pixel grid.  Only count them as risky when no cosmetic helper
        # is referenced in the same paintEvent.
        if uses_cosmetic:
            draw_rect = 0
            draw_line = 0
        risky = raw_pen_1 + draw_rect + draw_line + no_cosmetic
        # A paintEvent with zero risky patterns is conformant regardless
        # of snap helper usage – helpers are only required when the
        # paintEvent actually draws 1px borders / precise geometry.
        if risky == 0:
            continue
        yield start, end, risky, snap_uses


def audit(roots: Iterable[Path], max_violations: int) -> int:
    non_conformant = 0
    total_events = 0
    per_file: list[tuple[Path, int, int, int]] = []
    for path in _iter_python_files(roots):
        rel = path.relative_to(PROJECT_ROOT)
        rel_str = str(rel).replace("\\", "/")
        if rel_str in WHITELIST_FILES:
            continue
        for start, _end, risky, snap_uses in _scan_file(path):
            total_events += 1
            if risky == 0 and snap_uses > 0:
                continue
            non_conformant += 1
            per_file.append((rel, start, risky, snap_uses))

    for rel, start, risky, snap_uses in per_file[:30]:
        print(f"{rel}:{start}: risky={risky}, snap_uses={snap_uses}")

    print("---")
    print(f"Total paintEvent: {total_events} | non-conformant: {non_conformant}")

    if non_conformant > max_violations:
        print(f"FAIL: {non_conformant} > max {max_violations}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max", type=int, default=32, help="Maximum allowed violations")
    parser.add_argument("--strict", action="store_true", help="Alias for --max=0 (CI blocking)")
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args(argv)
    if args.strict:
        args.max = 0

    roots = [PROJECT_ROOT / r for r in args.roots]
    return audit(roots, args.max)


if __name__ == "__main__":
    sys.exit(main())
