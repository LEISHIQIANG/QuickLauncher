"""Audit hard-coded ``QColor(...)`` calls in the UI layer.

Per §1.3 and §4.1 of ``UI_OPTIMIZATION_PLAN.md`` the codebase should
resolve every theme colour through :mod:`ui.styles.design_tokens`
instead of inlining ``QColor(r, g, b, a)`` literals.

This script:

* walks the project tree under :mod:`ui`,
* flags every ``QColor(`` instance whose arguments are *all* integer /
  hex literals (i.e. not bound to a variable name),
* whitelists the design token module itself, audit helpers and palette
  tables,
* reports per-file line numbers and exits with a non-zero status when
  the violation count exceeds ``--max``.

Exit code policy (Sprint 8 hardening):
* ``--max=N``: pass when violations ≤ N, fail otherwise.
* ``--strict``: alias for ``--max=0``.

Usage
-----

::

    python scripts/audit_hardcoded_colors.py
    python scripts/audit_hardcoded_colors.py --max=2
    python scripts/audit_hardcoded_colors.py --strict
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("ui",)
WHITELIST_FILES = {
    "ui/styles/design_tokens.py",
    "ui/styles/themed_messagebox.py",
    "ui/launcher_popup/glass_background.py",
    "ui/styles/color_filter_overlay.py",
    "ui/command_icon_renderer.py",
    "ui/utils/default_icon_renderer.py",
    "ui/launcher_popup/popup_renderer.py",
    "ui/utils/lru_cache.py",
    "ui/utils/pixel_snap.py",
    "ui/utils/animations.py",
    "ui/utils/motion.py",
    "ui/utils/font_manager.py",
    "ui/utils/interruptible_animation.py",
    "ui/styles/standard_widgets.py",
    # Per §4.1 plan: icon palette files (categorical icon colours) and
    # glass-pipeline palette tables stay as literals. Token derivation
    # is not appropriate for these.
    "ui/config_window/action_button_icons.py",
    "ui/config_window/command_dialog_icon.py",
    "ui/config_window/icon_grid_palette.py",
    "ui/config_window/macro_palette.py",
    "ui/config_window/settings_group_icon_palette.py",
    "ui/config_window/settings_helpers_palette.py",
    "ui/config_window/settings_nav_palette.py",
    "ui/config_window/theme_helper_palette.py",
    "ui/launcher_popup/popup_icons.py",
    "ui/styles/focus_ring.py",
}

_QCOLOR_RE = re.compile(r"QColor\s*\(")
_INT_ARG_RE = re.compile(r"^-?\d+$")
_HEX_ARG_RE = re.compile(r"^0x[0-9A-Fa-f]+$")


def _iter_python_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def _is_literal_args(arg_segment: str) -> bool:
    parts = [p.strip() for p in arg_segment.split(",") if p.strip()]
    if not parts:
        return False
    for p in parts:
        if _INT_ARG_RE.match(p) or _HEX_ARG_RE.match(p):
            continue
        # Allow short variable names that look like ints (e.g. ``alpha=128``)
        if "=" in p and _INT_ARG_RE.match(p.split("=", 1)[1].strip()):
            continue
        return False
    return True


def _scan_file(path: Path) -> Iterable[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not _QCOLOR_RE.search(line):
            continue
        # Extract argument text
        idx = line.find("QColor(")
        after = line[idx + len("QColor(") :]
        depth = 1
        end = -1
        for i, ch in enumerate(after):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            continue
        args = after[:end]
        if _is_literal_args(args):
            yield lineno, line.strip()


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
