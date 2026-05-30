#!/usr/bin/env python3
"""Pre-commit hook: reject new silent except Exception: pass patterns."""

import re
import sys

SILENT_PATTERN = re.compile(r"^\s*except\s+\w+(\s*,\s*\w+)*\s*:\s*pass\s*$")
ALLOWED_PREFIX = "# noqa: S110"


def check_file(filepath: str) -> list[str]:
    errors = []
    try:
        with open(filepath, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if SILENT_PATTERN.search(line) and ALLOWED_PREFIX not in line:
                    errors.append(f"{filepath}:{lineno}: 静默异常被捕获，请至少添加日志记录")
    except (OSError, UnicodeDecodeError):
        pass
    return errors


def main() -> int:
    if len(sys.argv) < 2:
        return 0
    all_errors = []
    for filepath in sys.argv[1:]:
        if filepath.endswith(".py"):
            all_errors.extend(check_file(filepath))
    for err in all_errors:
        print(err)
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
