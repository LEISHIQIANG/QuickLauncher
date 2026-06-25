"""Audit inline ``font-size: N px`` declarations in QSS strings.

Per §1.4 and §4.3 of ``UI_OPTIMIZATION_PLAN.md`` every QSS string in
the project should use :func:`ui.utils.font_manager.get_font_css_with_size`
to construct ``font-size:`` declarations so the global UI scale and
font fallback stack stay consistent.

The audit walks the project tree, extracts every ``font-size: Npx``
occurrence from Python string literals / QSS files and reports the
file:line. Whitelisted files include the font manager itself and the
core design tokens module.

Usage
-----

::

    python scripts/audit_font_consistency.py
    python scripts/audit_font_consistency.py --max=220
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("ui",)

# Whitelisted size ladder (§1.4: 10/11/12/13/14/15/16/18/20/24/28/32/40).
# 9 px is allowed for tiny badge / status-pill labels (icon-grid folder
# badges, command profile toggles) where the standard ladder's 10 px
# minimum would crowd the surrounding layout. 26 px and 48 px are
# used for the support page "click burst" animation and the welcome
# guide hero icon respectively — both one-off special effects, not
# part of the standard type ladder.
ALLOWED_SIZES = {9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 24, 26, 28, 32, 40, 48}

# Whitelisted files (these contain intentional hard-coded values)
WHITELIST_FILES = {
    "ui/utils/font_manager.py",
    "ui/styles/design_tokens.py",
    "ui/utils/lru_cache.py",
    "ui/utils/pixel_snap.py",
    "ui/utils/animations.py",
    "ui/utils/motion.py",
    "ui/utils/interruptible_animation.py",
    "ui/styles/standard_widgets.py",
    "ui/styles/focus_ring.py",
}

FONT_SIZE_RE = re.compile(r"font-size\s*:\s*(\d+)\s*px", re.IGNORECASE)
SET_PIXEL_SIZE_RE = re.compile(r"setPixelSize\s*\(\s*(\d+)\s*\)")
QFONT_SIZE_RE = re.compile(r"QFont\s*\(\s*['\"][^'\"]+['\"]\s*,\s*(\d+)\s*\)")


def _iter_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix in (".py", ".qss", ".css"):
                yield path


def _scan_file(path: Path) -> Iterable[tuple[int, str, int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in FONT_SIZE_RE.finditer(line):
            value = int(m.group(1))
            if value in ALLOWED_SIZES:
                continue
            yield lineno, line.strip(), value, "qss"
        for m in SET_PIXEL_SIZE_RE.finditer(line):
            value = int(m.group(1))
            if value in ALLOWED_SIZES:
                continue
            yield lineno, line.strip(), value, "setPixelSize"
        for m in QFONT_SIZE_RE.finditer(line):
            value = int(m.group(1))
            if value in ALLOWED_SIZES:
                continue
            yield lineno, line.strip(), value, "QFont"


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
        for lineno, snippet, value, kind in hits[:3]:
            print(f"{rel_str}:{lineno}: {kind} {value}px :: {snippet[:100]}")
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
    parser.add_argument("--max", type=int, default=220, help="Maximum allowed violations")
    parser.add_argument("--strict", action="store_true", help="Alias for --max=0 (CI blocking)")
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args(argv)
    if args.strict:
        args.max = 0

    roots = [PROJECT_ROOT / r for r in args.roots]
    return audit(roots, args.max)


if __name__ == "__main__":
    sys.exit(main())
