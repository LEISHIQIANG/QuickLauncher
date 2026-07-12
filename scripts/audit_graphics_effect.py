"""Audit ``QGraphicsEffect`` usage.

Per §1.6 and §4.10.1 of ``UI_OPTIMIZATION_PLAN.md``:

* :class:`QGraphicsOpacityEffect` should be replaced by
  ``widget.setWindowOpacity()`` (17 → 0 in the S6 plan).
* :class:`QGraphicsDropShadowEffect` may stay, but its arguments must
  come from :mod:`ui.styles.design_tokens.elevation` (2 → 2, parameters
  only).

This script counts both flavours and flags any new opacity effect that
doesn't reference :func:`setWindowOpacity` (warning, not blocking).

Usage
-----

::

    python scripts/audit_graphics_effect.py
    python scripts/audit_graphics_effect.py --max-opacity=0
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("ui",)

OPACITY_EFFECT_RE = re.compile(r"QGraphicsOpacityEffect\s*\(")
DROP_SHADOW_RE = re.compile(r"QGraphicsDropShadowEffect\s*\(")
ELEVATION_TOKEN_RE = re.compile(r"\belevation\(|elevation\(\s*[0-3]")

WHITELIST_FILES = {
    "ui/utils/animations.py",
    "ui/utils/motion.py",
    "ui/utils/pixel_snap.py",
    "ui/utils/lru_cache.py",
    "ui/utils/font_manager.py",
    "ui/utils/interruptible_animation.py",
    "ui/utils/widget_opacity.py",
    "ui/styles/standard_widgets.py",
    "ui/styles/focus_ring.py",
    "ui/styles/design_tokens.py",
}


def _iter_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def audit(roots: Iterable[Path], max_opacity: int, max_shadow_untokenized: int) -> int:
    opacity = 0
    shadow = 0
    shadow_untokenized = 0
    per_file_opacity: list[tuple[Path, int]] = []
    for path in _iter_files(roots):
        rel = path.relative_to(PROJECT_ROOT)
        rel_str = str(rel).replace("\\", "/")
        if rel_str in WHITELIST_FILES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        op_hits = OPACITY_EFFECT_RE.findall(text)
        sh_hits = DROP_SHADOW_RE.findall(text)
        if op_hits:
            opacity += len(op_hits)
            per_file_opacity.append((rel, len(op_hits)))
        if sh_hits:
            shadow += len(sh_hits)
            token_uses = ELEVATION_TOKEN_RE.findall(text)
            if not token_uses:
                shadow_untokenized += len(sh_hits)
                print(f"{rel_str}: drop-shadow without elevation() token ({len(sh_hits)}x)")

    for rel, count in sorted(per_file_opacity, key=lambda t: -t[1])[:20]:
        print(f"{rel}: {count} QGraphicsOpacityEffect")

    print("---")
    print(f"Opacity effects: {opacity} (max {max_opacity})")
    print(f"Drop-shadow effects: {shadow} (untokenized {shadow_untokenized}, max {max_shadow_untokenized})")

    failures = []
    if opacity > max_opacity:
        failures.append(f"opacity={opacity} > {max_opacity}")
    if shadow_untokenized > max_shadow_untokenized:
        failures.append(f"shadow_untokenized={shadow_untokenized} > {max_shadow_untokenized}")
    if failures:
        print("FAIL: " + ", ".join(failures))
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-opacity", type=int, default=0)
    parser.add_argument("--max-shadow-untokenized", type=int, default=0)
    parser.add_argument("--strict", action="store_true", help="Alias for max values to be 0 (CI blocking)")
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args(argv)
    if args.strict:
        args.max_opacity = 0
        args.max_shadow_untokenized = 0

    roots = [PROJECT_ROOT / r for r in args.roots]
    return audit(roots, args.max_opacity, args.max_shadow_untokenized)


if __name__ == "__main__":
    sys.exit(main())
