"""Auto-fix sp() grid violations: round non-4-multiple values to nearest 4-multiple."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

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

ALLOWED_EXCEPTIONS = {1, 2, 3, 5, 6, 7, 18}
ALLOWED_WINDOW_SIZES = {350, 440, 1200, 2200}

SP_INT_RE = re.compile(r"\bsp\(\s*(-?\d+)\s*\)")


def nearest_grid(value: int) -> int:
    if value <= 0:
        return value
    if value in ALLOWED_EXCEPTIONS:
        return value
    if value in ALLOWED_WINDOW_SIZES:
        return value
    if value % 4 == 0:
        return value
    lower = (value // 4) * 4
    upper = lower + 4
    if value - lower <= upper - value:
        return lower if lower > 0 else upper
    return upper


def is_violation(value: int) -> bool:
    if value <= 0:
        return False
    if value in ALLOWED_EXCEPTIONS:
        return False
    if value in ALLOWED_WINDOW_SIZES:
        return False
    return value % 4 != 0


def fix_file(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0

    changes = 0

    def replace_sp(m: re.Match) -> str:
        nonlocal changes
        value = int(m.group(1))
        if not is_violation(value):
            return m.group(0)
        new_val = nearest_grid(value)
        if new_val == value:
            return m.group(0)
        changes += 1
        rel = path.relative_to(PROJECT_ROOT)
        print(f"  {rel}:{m.group(0)} -> sp({new_val})")
        return f"sp({new_val})"

    new_text = SP_INT_RE.sub(replace_sp, text)
    if changes:
        path.write_text(new_text, encoding="utf-8")
    return changes


def main() -> int:
    roots = [PROJECT_ROOT / "ui"]
    total_changes = 0
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(PROJECT_ROOT)
            rel_str = str(rel).replace("\\", "/")
            if rel_str in WHITELIST_FILES:
                continue
            changes = fix_file(path)
            if changes:
                total_changes += changes
                print(f"  -> {changes} changes in {rel_str}")
                print()

    print(f"\nTotal changes: {total_changes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
