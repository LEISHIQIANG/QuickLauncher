"""Run a non-interactive smoke test against a packaged QuickLauncher build."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class PostPackageSmokeResult:
    ok: bool
    errors: list[str]
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    elapsed_seconds: float
    smoke_payload: dict | None

    def to_manifest(self) -> dict:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "command": self.command,
            "returncode": self.returncode,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "smoke_payload": self.smoke_payload,
        }


def _extract_smoke_payload(stdout: str) -> dict | None:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "status" in payload:
            return payload
    return None


def run_packaged_smoke(
    dist_dir: Path,
    *,
    exe: Path | None = None,
    timeout: float = 30.0,
    smoke_args: list[str] | None = None,
) -> PostPackageSmokeResult:
    dist_dir = Path(dist_dir)
    exe_path = Path(exe) if exe is not None else dist_dir / "QuickLauncher.exe"
    command = [str(exe_path), *(smoke_args or ["--safe-mode", "--smoke-test"])]
    errors: list[str] = []
    started = time.monotonic()

    if not dist_dir.is_dir():
        errors.append(f"missing dist directory: {dist_dir}")
    if not exe_path.is_file():
        errors.append(f"missing executable: {exe_path}")
    if errors:
        return PostPackageSmokeResult(
            ok=False,
            errors=errors,
            command=command,
            returncode=None,
            stdout="",
            stderr="",
            elapsed_seconds=time.monotonic() - started,
            smoke_payload=None,
        )

    env = os.environ.copy()
    env["QL_SAFE_MODE"] = "1"
    env.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.warning=false")

    try:
        completed = subprocess.run(
            command,
            cwd=str(dist_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return PostPackageSmokeResult(
            ok=False,
            errors=[f"smoke test timed out after {timeout:g}s"],
            command=command,
            returncode=None,
            stdout=stdout,
            stderr=stderr,
            elapsed_seconds=time.monotonic() - started,
            smoke_payload=None,
        )
    except OSError as exc:
        return PostPackageSmokeResult(
            ok=False,
            errors=[f"failed to start smoke test: {exc}"],
            command=command,
            returncode=None,
            stdout="",
            stderr="",
            elapsed_seconds=time.monotonic() - started,
            smoke_payload=None,
        )

    payload = _extract_smoke_payload(completed.stdout)
    if completed.returncode != 0:
        errors.append(f"smoke test exited with code {completed.returncode}")
    if payload is None:
        errors.append("smoke test did not emit a JSON status payload")
    elif payload.get("status") != "ok":
        payload_errors = payload.get("errors")
        if isinstance(payload_errors, list) and payload_errors:
            errors.extend(str(error) for error in payload_errors)
        else:
            errors.append(f"smoke test status is {payload.get('status')!r}")

    return PostPackageSmokeResult(
        ok=not errors,
        errors=errors,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        elapsed_seconds=time.monotonic() - started,
        smoke_payload=payload,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist" / "QuickLauncher")
    parser.add_argument("--exe", type=Path, default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    result = run_packaged_smoke(args.dist_dir, exe=args.exe, timeout=args.timeout)
    print(json.dumps(result.to_manifest(), ensure_ascii=False, indent=2))
    if result.ok:
        print("post-package smoke passed")
        return 0
    for error in result.errors:
        print(f"post-package smoke failed: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
