"""Track mypy error count against a tracked baseline.

The repo has a long-standing mypy backlog (over 1000 errors mostly from
dynamic Qt/mixin typing) that we are cleaning up incrementally. This
script reads a baseline JSON file and compares it against a fresh mypy
run. It returns non-zero when the current error count exceeds the
``max_error_count`` field in the baseline, which allows the release gate
to fail on **regressions** rather than on the absolute count.

Typical use:

    python scripts/check_mypy_progress.py
    python scripts/check_mypy_progress.py --scope core ui services
    python scripts/check_mypy_progress.py --update-baseline
    python scripts/check_mypy_progress.py --max-error-count 2000

The baseline file lives at ``docs/quality/mypy_baseline.json`` and uses
this schema:

    {
      "version": 1,
      "scope": ["core", "ui", "hooks", "services", "bootstrap"],
      "max_error_count": 2050,
      "last_count": 2042,
      "recorded_at": "2026-06-16",
      "notes": "..."
    }
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = REPO_ROOT / "docs" / "quality" / "mypy_baseline.json"
DEFAULT_SCOPE: tuple[str, ...] = ("core", "ui", "hooks", "services", "bootstrap")


def _run_mypy(scope: list[str], python: str) -> tuple[int, list[str]]:
    """Run mypy once and return ``(error_count, error_lines)``."""
    cmd = [python, "-m", "mypy", "--no-incremental", "--no-error-summary", *scope]
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    error_lines = [line for line in output.splitlines() if " error:" in line]
    return len(error_lines), error_lines


def _load_baseline(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 1, "scope": list(DEFAULT_SCOPE), "max_error_count": None, "last_count": None}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"failed to read baseline {path}: {exc}", file=sys.stderr)
        return {"version": 1, "scope": list(DEFAULT_SCOPE), "max_error_count": None, "last_count": None}


def _save_baseline(path: Path, scope: list[str], count: int, max_error_count: int, notes: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "scope": scope,
        "max_error_count": max_error_count,
        "last_count": count,
        "recorded_at": date.today().isoformat(),
    }
    if notes:
        data["notes"] = notes
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="Python interpreter to use for mypy.")
    parser.add_argument(
        "--scope",
        nargs="+",
        default=None,
        help=f"Directories to scan (default: {' '.join(DEFAULT_SCOPE)}).",
    )
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help="Path to the mypy baseline JSON file.",
    )
    parser.add_argument(
        "--max-error-count",
        type=int,
        default=None,
        help="Override the max-error-count gate (default: from baseline).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the baseline file with the current count (max-error-count preserved or set to count+8).",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help="Optional notes to store when --update-baseline is used.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Print the report and always return 0. Useful for first-run audits.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    baseline_path = Path(args.baseline)
    scope = args.scope or list(DEFAULT_SCOPE)
    baseline = _load_baseline(baseline_path)

    if shutil.which("python") is None and not Path(args.python).exists():
        print(f"python executable not found: {args.python}", file=sys.stderr)
        return 1

    count, _ = _run_mypy(scope, args.python)

    max_error_count = args.max_error_count
    if max_error_count is None:
        max_error_count = baseline.get("max_error_count")
    if max_error_count is None:
        max_error_count = count + 8

    last_count = baseline.get("last_count")
    delta = count - last_count if isinstance(last_count, int) else None

    print(f"mypy scope: {' '.join(scope)}")
    print(f"current error count: {count}")
    if isinstance(last_count, int):
        print(f"baseline last_count: {last_count} (delta: {delta:+d})")
    print(f"max error count: {max_error_count}")

    if args.update_baseline:
        # When updating, set the new max to count+8 unless the user passed one.
        new_max = max_error_count if args.max_error_count is not None else count + 8
        _save_baseline(baseline_path, scope, count, new_max, args.notes)
        print(f"updated baseline: max_error_count={new_max}, last_count={count}")
        return 0

    if args.report_only:
        return 0

    if count > max_error_count:
        print(
            f"mypy error count {count} exceeds baseline max {max_error_count} "
            f"(regression of {count - max_error_count})",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
