"""Auto-fix QSS border-radius violations: add ``border-radius: 0;`` after ``border: none;``."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXTENSIONS = (".py", ".qss", ".css")

WHITELIST_FILES = {
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

BORDER_NONE_RE = re.compile(r"border\s*:\s*none\s*;?", re.IGNORECASE)
BORDER_RADIUS_0_RE = re.compile(r"border-radius\s*:\s*0", re.IGNORECASE)


def fix_file(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0

    lines = text.splitlines(keepends=True)
    changes = 0

    for i, line in enumerate(lines):
        if not BORDER_NONE_RE.search(line):
            continue
        if BORDER_RADIUS_0_RE.search(line):
            continue

        # Add border-radius: 0; before the border: none declaration
        # Find the position of "border: none" and insert before it
        new_line = BORDER_NONE_RE.sub(
            lambda m: (
                f"border-radius: 0; {m.group(0)}" if m.group(0).endswith(";") else f"border-radius: 0; {m.group(0)};"
            ),
            line,
        )
        if new_line != line:
            lines[i] = new_line
            changes += 1
            rel = path.relative_to(PROJECT_ROOT)
            print(f"  {rel}:L{i+1}: {line.strip()}")
            print(f"       -> {new_line.strip()}")

    if changes:
        path.write_text("".join(lines), encoding="utf-8")
    return changes


def main() -> int:
    roots = [PROJECT_ROOT / "ui"]
    total_changes = 0
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix not in EXTENSIONS:
                continue
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
