"""Run the canonical mypy scope and require zero errors."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCOPE: tuple[str, ...] = ("core", "ui", "hooks", "services", "bootstrap", "main.py")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="Python interpreter used to run mypy.")
    parser.add_argument("--scope", nargs="+", default=None, help="Override the canonical source scope.")
    parser.add_argument("--report-only", action="store_true", help="Print errors without failing.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    scope = list(args.scope or DEFAULT_SCOPE)
    command = [args.python, "-m", "mypy", "--no-incremental", "--no-error-summary", *scope]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    error_lines = [line for line in output.splitlines() if " error:" in line]

    print(f"mypy scope: {' '.join(scope)}")
    print(f"current error count: {len(error_lines)}")
    if output:
        print(output)
    if args.report_only:
        return 0
    if result.returncode != 0 or error_lines:
        print("mypy must pass with zero errors", file=sys.stderr)
        return result.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
