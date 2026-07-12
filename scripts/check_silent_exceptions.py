#!/usr/bin/env python3
"""Pre-commit hook: reject new silent except Exception: pass patterns."""

import re
import sys

# 单行形式: except Exception: pass
SILENT_PATTERN_SINGLE = re.compile(r"^\s*except\b.*:\s*pass\s*$")
# 两行形式起始: except Exception:
SILENT_EXCEPT_LINE = re.compile(r"^\s*except\b.*:\s*$")
ALLOWED_PREFIX = "# noqa: S110"


def check_file(filepath: str) -> list[str]:
    errors = []
    try:
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return errors
    for i, line in enumerate(lines):
        # 单行形式: except Exception: pass
        if SILENT_PATTERN_SINGLE.search(line) and ALLOWED_PREFIX not in line:
            errors.append(f"{filepath}:{i + 1}: 静默异常被捕获，请至少添加日志记录")
        # 两行形式: except Exception:\n    pass
        elif SILENT_EXCEPT_LINE.match(line):
            for j in range(i + 1, min(i + 3, len(lines))):
                stripped = lines[j].strip()
                if stripped == "pass":
                    if ALLOWED_PREFIX not in line:
                        errors.append(f"{filepath}:{i + 1}: 静默异常被捕获，请至少添加日志记录")
                    break
                elif stripped:
                    break
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
