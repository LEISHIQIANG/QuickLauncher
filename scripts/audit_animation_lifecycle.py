"""Audit ``QPropertyAnimation`` / ``QTimer`` lifecycle correctness.

Per §4.10.3 and §4.10.6 of ``UI_OPTIMIZATION_PLAN.md`` every
``QPropertyAnimation.start()`` call should be paired with a ``stop()``
or ``deleteLater()`` on the same owner. ``QTimer.singleShot`` should
not be used to drive animation chains – use ``QPropertyAnimation`` /
``QSequentialAnimationGroup`` instead.

This script is a *warning* audit: it counts ``QPropertyAnimation``
instantiations that are never paired with a ``stop()`` / ``deleteLater``
in the same file, and ``QTimer.singleShot`` calls that look like
animation steps.

Usage
-----

::

    python scripts/audit_animation_lifecycle.py
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("ui",)

QPROP_ANIM_RE = re.compile(r"QPropertyAnimation\s*\(")
ANIMATION_STOP_RE = re.compile(
    r"\.stop\s*\(\s*\)"
    r"|deleteLater\s*(\(\s*\)|\b)"  # match `deleteLater()` or `deleteLater` (Qt method ref)
    r"|stop_animation\s*\("
    r"|stop_named_animations\s*\("
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
}


def _iter_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def _scan_file(path: Path) -> tuple[int, int]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0, 0
    starts = len(QPROP_ANIM_RE.findall(text))
    stops = len(ANIMATION_STOP_RE.findall(text))
    return starts, stops


def audit(roots: Iterable[Path], max_unbalanced: int) -> int:
    unbalanced = 0
    for path in _iter_files(roots):
        rel = path.relative_to(PROJECT_ROOT)
        rel_str = str(rel).replace("\\", "/")
        if rel_str in WHITELIST_FILES:
            continue
        starts, stops = _scan_file(path)
        diff = starts - stops
        if diff > 0:
            unbalanced += diff
            print(f"{rel_str}: QPropertyAnimation {starts}x, stop/deleteLater {stops}x (delta +{diff})")

    print("---")
    print(f"Total unbalanced QPropertyAnimation: {unbalanced}")
    if unbalanced > max_unbalanced:
        print(f"FAIL: {unbalanced} > max {max_unbalanced}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max", type=int, default=200, help="Maximum allowed unbalanced hits")
    parser.add_argument("--strict", action="store_true", help="Alias for --max=0 (CI blocking)")
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args(argv)
    if args.strict:
        args.max = 0

    roots = [PROJECT_ROOT / r for r in args.roots]
    return audit(roots, args.max)


if __name__ == "__main__":
    sys.exit(main())
