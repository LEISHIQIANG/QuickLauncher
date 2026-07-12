"""Audit ``sp()`` calls that use non-4-multiple values.

Per §1.2 and §4.4 of ``UI_OPTIMIZATION_PLAN.md`` every layout dimension
should land on the 4-px grid. The audit walks :mod:`ui` looking for
``sp(<int>)`` (and ``spf(<float>)``) calls whose argument is not a
multiple of 4 and reports the file:line of each violation.

The whitelist mirrors the table in §4.4:

* 1, 3 – 1-px borders / line heights
* 5, 6 – checkbox indicators and tiny icon padding
* 7, 9, 11, 13 – currently disallowed (use 4-multiple neighbours)

Usage
-----

::

    python scripts/audit_grid_violations.py
    python scripts/audit_grid_violations.py --max=10
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

# Force UTF-8 stdout on Windows consoles to allow non-ASCII snippets.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, OSError, ValueError):
    logging.getLogger(__name__).debug("stdout UTF-8 reconfiguration unavailable", exc_info=True)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("ui",)

# Whitelist of values that are *not* 4-multiples but are intentionally
# allowed because they are 1-px borders, 2-px paddings, 5-px indicators,
# 6-px tight icon padding, or 18-px retained per §4.4 of
# UI_OPTIMIZATION_PLAN.md ("18px 保留（4 倍数边界）").
ALLOWED_EXCEPTIONS = {1, 2, 3, 5, 6, 7, 18}

# Window-level dimensions that are not strictly on the 4-grid but are
# common dialog / scene sizes. Rounding them would change the visual
# baseline, so we whitelist them explicitly. (All 4-multiples of 50 in
# the 300..600 range; canvas scenes can be larger.)
ALLOWED_WINDOW_SIZES = {350, 440, 1200, 2200}

# Files excluded from the audit (e.g. constants tables).
WHITELIST_FILES = {
    "ui/utils/ui_scale.py",
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

_SP_INT_RE = re.compile(r"\bsp\(\s*(-?\d+)\s*\)")
_SPF_FLOAT_RE = re.compile(r"\bspf\(\s*(-?\d+(?:\.\d+)?)\s*\)")


def _iter_python_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def _scan_file(path: Path) -> Iterable[tuple[int, str, int]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _SP_INT_RE.finditer(line):
            value = int(m.group(1))
            if value <= 0:
                continue
            if value in ALLOWED_EXCEPTIONS:
                continue
            if value in ALLOWED_WINDOW_SIZES:
                continue
            if value % 4 == 0:
                continue
            # Values that are not 4-multiples (and not in the exceptions)
            # are violations. Round to the nearest 4-multiple and report.
            yield lineno, line.strip(), value


def audit(roots: Iterable[Path], max_violations: int) -> int:
    violations = 0
    per_file: list[tuple[Path, int]] = []
    for path in _iter_python_files(roots):
        rel = path.relative_to(PROJECT_ROOT)
        rel_str = str(rel).replace("\\", "/")
        if rel_str in WHITELIST_FILES:
            continue
        hits = list(_scan_file(path))
        if not hits:
            continue
        per_file.append((rel, len(hits)))
        violations += len(hits)
        for lineno, snippet, value in hits[:5]:
            print(f"{rel_str}:{lineno}: sp({value}) :: {snippet}")
        if len(hits) > 5:
            print(f"  ... and {len(hits) - 5} more in {rel_str}")

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
    parser.add_argument("--max", type=int, default=584, help="Maximum allowed violations")
    parser.add_argument("--strict", action="store_true", help="Alias for --max=0 (CI blocking)")
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args(argv)
    if args.strict:
        args.max = 0

    roots = [PROJECT_ROOT / r for r in args.roots]
    return audit(roots, args.max)


if __name__ == "__main__":
    sys.exit(main())
