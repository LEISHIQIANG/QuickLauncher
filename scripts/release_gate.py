"""Run the local release gate for QuickLauncher source changes."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPILE_PYCACHE_PREFIX = ROOT / "dist" / "release-gate-pycache"
PYTEST_BASETEMP = Path(tempfile.gettempdir()) / "QuickLauncher" / "pytest-tmp" / "release-gate"
COVERAGE_FAIL_UNDER = 67

_ESSENTIAL_ENV_KEYS = frozenset(
    {
        "appdata",
        "ci",
        "comspec",
        "github_actions",
        "home",
        "homepath",
        "localappdata",
        "number_of_processors",
        "os",
        "path",
        "pathext",
        "processor_architecture",
        "programfiles",
        "programfiles(x86)",
        "qt_qpa_platform",
        "runner_os",
        "pythonhome",
        "pythonpath",
        "systemroot",
        "temp",
        "tmp",
        "userdomain",
        "userhome",
        "username",
        "userprofile",
        "windir",
    }
)


@dataclass(frozen=True)
class GateStep:
    name: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)


def _default_steps(python: str) -> list[GateStep]:
    return [
        GateStep(
            "ruff",
            [python, "-m", "ruff", "check", "--no-cache", "core", "ui", "hooks", "services", "tests"],
            {"RUFF_NO_CACHE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        ),
        GateStep(
            "pytest",
            [
                python,
                "-m",
                "pytest",
                "--basetemp",
                str(PYTEST_BASETEMP),
                "--cov=core",
                "--cov=services",
                "--cov=hooks",
                "--cov-report=term-missing",
                f"--cov-fail-under={COVERAGE_FAIL_UNDER}",
            ],
            {"PYTHONDONTWRITEBYTECODE": "1"},
        ),
        GateStep(
            "broad exception audit",
            [
                python,
                "scripts/audit_broad_exceptions.py",
                "--exclude-dir",
                "plugins",
                "--exclude-dir",
                "tools",
                "--max-total",
                "1366",
                "--max-unlogged",
                "300",
            ],
            {"PYTHONDONTWRITEBYTECODE": "1"},
        ),
        GateStep(
            "compileall",
            [python, "-m", "compileall", "core", "ui", "hooks", "services", "bootstrap", "plugins"],
            {"PYTHONPYCACHEPREFIX": str(COMPILE_PYCACHE_PREFIX)},
        ),
        GateStep(
            "release metadata",
            [python, "scripts/check_release_artifacts.py", "--source-only", "--allow-source-runtime-plugins"],
            {"PYTHONDONTWRITEBYTECODE": "1"},
        ),
        GateStep(
            "post-package smoke",
            [python, "scripts/post_package_smoke.py"],
            {"PYTHONDONTWRITEBYTECODE": "1"},
        ),
    ]


def _clean_stale_caches(root: Path) -> None:
    for pycache_dir in root.rglob("__pycache__"):
        shutil.rmtree(pycache_dir, ignore_errors=True)
    for stale_dir in (root / ".ruff_cache", PYTEST_BASETEMP, COMPILE_PYCACHE_PREFIX):
        if stale_dir.is_dir():
            shutil.rmtree(stale_dir, ignore_errors=True)


def _isolated_env(step_env: dict[str, str]) -> dict[str, str]:
    essential_upper = {k.upper() for k in _ESSENTIAL_ENV_KEYS}
    env = {key: value for key, value in os.environ.items() if key.upper() in essential_upper}
    env.update(step_env)
    return env


def _step_env(step: GateStep) -> dict[str, str]:
    return _isolated_env(step.env)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="Python executable to use for every gate step.")
    parser.add_argument(
        "--skip-tests", action="store_true", help="Skip pytest while keeping compile, ruff, and metadata checks."
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip post-package smoke test (useful when no packaged build is available).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the commands without running them.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    _clean_stale_caches(ROOT)
    steps = _default_steps(args.python)
    if args.skip_tests:
        steps = [step for step in steps if step.name != "pytest"]
    if args.skip_smoke:
        steps = [step for step in steps if step.name != "post-package smoke"]

    for index, step in enumerate(steps, start=1):
        command = step.command
        rendered = " ".join(command)
        print(f"[{index}/{len(steps)}] {step.name}: {rendered}", flush=True)
        if args.dry_run:
            continue
        result = subprocess.run(command, cwd=ROOT, check=False, env=_step_env(step))
        if result.returncode:
            print(f"[release gate failed] exit code {result.returncode}: {rendered}", file=sys.stderr)
            return result.returncode

    print("release gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
