"""Audit ``paintEvent`` performance anti-patterns.

Per §4.10.2 of ``UI_OPTIMIZATION_PLAN.md`` a paint handler should:

* not call ``self.update()`` without arguments (full repaint),
* not call ``self.repaint()`` (synchronous repaint blocks the GUI thread),
* not construct :class:`QPainterPath` on every paint (cache it),
* not call ``setRenderHint`` repeatedly (set it once in ``__init__``),
* avoid ``QGraphicsEffect`` when the same visual is achievable with
  a token-driven border / shadow.

This script walks the UI tree and counts the number of risky patterns
per ``paintEvent``. The default threshold of 0 turns it into a
warning-only lint.

Usage
-----

::

    python scripts/audit_paint_perf.py
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("ui",)

# Match the unguarded ``self.update()`` or ``update()`` with no args
UPDATE_NO_ARG_RE = re.compile(r"(?:^|[^.\w])update\s*\(\s*\)")
REP_NO_ARG_RE = re.compile(r"(?:^|[^.\w])repaint\s*\(\s*\)")
PATH_CONSTRUCT_RE = re.compile(r"QPainterPath\s*\(")
RENDER_HINT_RE = re.compile(r"setRenderHint\s*\(")
GRAPHICS_EFFECT_RE = re.compile(r"setGraphicsEffect\s*\(")

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
    "scripts/audit_paint_perf.py",
}


def _iter_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def _extract_paint_event_ranges(text: str) -> list[tuple[int, int]]:
    lines = text.splitlines()
    ranges: list[tuple[int, int]] = []
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
            ranges.append((start, i - 1))
            in_event = False
    if in_event:
        ranges.append((start, len(lines)))
    return ranges


def _scan_file(path: Path) -> Iterable[tuple[int, int, int]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for start, end in _extract_paint_event_ranges(text):
        body = "\n".join(text.splitlines()[start - 1 : end])
        # Honour an explicit ``# noqa: paint_perf`` marker inside the body.
        if "noqa: paint_perf" in body:
            continue
        bad = (
            len(UPDATE_NO_ARG_RE.findall(body))
            + len(REP_NO_ARG_RE.findall(body))
            + len(PATH_CONSTRUCT_RE.findall(body))
            + len(RENDER_HINT_RE.findall(body))
            + len(GRAPHICS_EFFECT_RE.findall(body))
        )
        if bad:
            yield start, end, bad


def audit(roots: Iterable[Path], max_per_event: int) -> int:
    bad = 0
    for path in _iter_files(roots):
        rel = path.relative_to(PROJECT_ROOT)
        rel_str = str(rel).replace("\\", "/")
        if rel_str in WHITELIST_FILES:
            continue
        for start, end, count in _scan_file(path):
            bad += count
            print(f"{rel_str}:{start}-{end}: {count} anti-pattern hits")

    print("---")
    print(f"Total anti-pattern hits: {bad}")
    if bad > max_per_event:
        print(f"FAIL: {bad} > max {max_per_event}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max", type=int, default=0, help="Maximum allowed anti-pattern hits")
    parser.add_argument("--strict", action="store_true", help="Alias for --max=0 (CI blocking)")
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args(argv)
    if args.strict:
        args.max = 0

    roots = [PROJECT_ROOT / r for r in args.roots]
    return audit(roots, args.max)


if __name__ == "__main__":
    sys.exit(main())
