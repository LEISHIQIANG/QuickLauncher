"""Audit ``QPixmap`` constructions that miss ``setDevicePixelRatio``.

Per §4.10.8 of ``UI_OPTIMIZATION_PLAN.md`` every ``QPixmap`` that is
displayed at high DPI must call ``setDevicePixelRatio`` on the pixmap
or on the painter that draws it. Otherwise icons and thumbnails look
blurry on 150%+ DPI displays.

The audit is *warning* by default and flags any line that constructs
a ``QPixmap`` (or uses a helper that does) without a corresponding
``setDevicePixelRatio`` call.

Usage
-----

::

    python scripts/audit_pixmap_no_dpi.py
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("ui",)

PIXMAP_RE = re.compile(r"QPixmap\s*\(")
DPI_RE = re.compile(r"setDevicePixelRatio\s*\(")
CREATE_PIXMAP_RE = re.compile(r"create_pixmap\s*\(")

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
    "ui/launcher_popup/glass_background.py",  # handles its own DPR
    "scripts/audit_pixmap_no_dpi.py",
}


def _iter_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def _scan_file(path: Path) -> tuple[int, int, bool, bool]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0, 0, False, False
    pixmap = len(PIXMAP_RE.findall(text))
    dpi = len(DPI_RE.findall(text))
    # The audit also considers a file "DPI-aware" if it routes QPixmap
    # construction through :func:`ui.utils.pixel_snap.create_pixmap`
    # (which sets ``setDevicePixelRatio`` internally).
    uses_helper = bool(CREATE_PIXMAP_RE.search(text))
    # Honour an explicit ``# noqa: pixmap_dpi`` marker inside the file.
    has_noqa = "noqa: pixmap_dpi" in text
    return pixmap, dpi, uses_helper, has_noqa


def audit(roots: Iterable[Path], max_violations: int) -> int:
    total_pixmap = 0
    total_dpi = 0
    per_file: list[tuple[Path, int, int]] = []
    for path in _iter_files(roots):
        rel = path.relative_to(PROJECT_ROOT)
        rel_str = str(rel).replace("\\", "/")
        if rel_str in WHITELIST_FILES:
            continue
        pixmap, dpi, uses_helper, has_noqa = _scan_file(path)
        if pixmap == 0:
            continue
        total_pixmap += pixmap
        total_dpi += dpi
        if dpi == 0 and not uses_helper and not has_noqa:
            per_file.append((rel, pixmap, dpi))
            print(f"{rel_str}: QPixmap {pixmap}x, setDevicePixelRatio 0x")

    print("---")
    print(f"Total QPixmap constructions: {total_pixmap} (with DPR: {total_dpi})")
    print(f"Files with no DPR handling: {len(per_file)}")
    if len(per_file) > max_violations:
        print(f"FAIL: {len(per_file)} > max {max_violations}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max", type=int, default=20, help="Maximum allowed files with no DPR handling")
    parser.add_argument("--strict", action="store_true", help="Alias for --max=0 (CI blocking)")
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args(argv)
    if args.strict:
        args.max = 0

    roots = [PROJECT_ROOT / r for r in args.roots]
    return audit(roots, args.max)


if __name__ == "__main__":
    sys.exit(main())
