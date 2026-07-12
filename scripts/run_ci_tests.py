"""Run the full pytest suite in stable Windows-friendly chunks."""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
COVERAGE_TARGETS = ("core", "services", "hooks", "bootstrap")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="Python executable to use.")
    parser.add_argument("--chunks", type=int, default=20, help="Number of pytest processes to split the suite into.")
    parser.add_argument("--basetemp", default="", help="Optional pytest basetemp root; one child is used per chunk.")
    parser.add_argument("--cov-fail-under", type=int, default=None, help="Optional combined coverage minimum.")
    parser.add_argument("--verbose", action="store_true", help="Use verbose pytest output.")
    return parser.parse_args()


def _test_files() -> list[Path]:
    files = [path for path in TESTS_DIR.rglob("test_*.py") if path.is_file() and "__pycache__" not in path.parts]
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix().lower())


def _chunks(items: list[Path], count: int) -> list[list[Path]]:
    count = max(1, int(count))
    size = max(1, math.ceil(len(items) / count))
    return [items[index : index + size] for index in range(0, len(items), size)]


def _run(command: list[str]) -> int:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def main() -> int:
    args = _parse_args()
    files = _test_files()
    if not files:
        print("No test files found.", file=sys.stderr)
        return 1

    _run([args.python, "-m", "coverage", "erase"])

    pytest_flags = ["-v" if args.verbose else "-q", "--tb=short", "--timeout=120", "--timeout-method=thread"]
    for index, chunk in enumerate(_chunks(files, args.chunks), start=1):
        command = [args.python, "-m", "pytest", *[str(path.relative_to(ROOT)) for path in chunk], *pytest_flags]
        if args.basetemp:
            command.extend(["--basetemp", str(Path(args.basetemp) / f"chunk-{index}")])
        for target in COVERAGE_TARGETS:
            command.append(f"--cov={target}")
        command.extend(["--cov-append", "--cov-report="])
        print(f"[pytest chunk {index}] {len(chunk)} files", flush=True)
        result = _run(command)
        if result:
            return result

    result = _run([args.python, "-m", "coverage", "xml"])
    if result:
        return result

    report_command = [args.python, "-m", "coverage", "report", "-m"]
    if args.cov_fail_under is not None:
        report_command.append(f"--fail-under={args.cov_fail_under}")
    return _run(report_command)


if __name__ == "__main__":
    raise SystemExit(main())
