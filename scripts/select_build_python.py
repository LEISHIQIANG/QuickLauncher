#!/usr/bin/env python
"""Select the best local Python interpreter for QuickLauncher builds."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable


PROBE_CODE = r"""
import json
import platform
import struct
import sys

print(json.dumps({
    "executable": sys.executable,
    "version": list(sys.version_info[:3]),
    "bits": struct.calcsize("P") * 8,
    "implementation": platform.python_implementation(),
}, ensure_ascii=True))
"""


@dataclass(frozen=True)
class Candidate:
    command: tuple[str, ...]
    executable: str
    version: tuple[int, int, int]
    bits: int
    implementation: str
    source: str

    @property
    def major_minor(self) -> tuple[int, int]:
        return self.version[:2]

    def command_line(self) -> str:
        return " ".join(_quote_arg(arg) for arg in self.command)

    def label(self) -> str:
        ver = ".".join(str(part) for part in self.version)
        return f"Python {ver} {self.bits}-bit {self.implementation}"


def _quote_arg(arg: str) -> str:
    if not arg:
        return '""'
    if any(ch.isspace() for ch in arg) or any(ch in arg for ch in '()&^=;!,+"'):
        return '"' + arg.replace('"', r'\"') + '"'
    return arg


def _parse_version(text: str) -> tuple[int, int]:
    parts = text.split(".")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("version must be MAJOR.MINOR")
    try:
        major, minor = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("version must be MAJOR.MINOR") from exc
    return major, minor


def _parse_prefer(text: str) -> list[tuple[int, int]]:
    result = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        result.append(_parse_version(part))
    if not result:
        raise argparse.ArgumentTypeError("prefer must contain at least one MAJOR.MINOR version")
    return result


def _version_range(min_version: tuple[int, int], max_version: tuple[int, int]) -> Iterable[tuple[int, int]]:
    min_major, min_minor = min_version
    max_major, max_minor = max_version
    versions = []
    for major in range(min_major, max_major + 1):
        start = min_minor if major == min_major else 0
        end = max_minor if major == max_major else 20
        for minor in range(start, end + 1):
            versions.append((major, minor))
    return reversed(versions)


def _run_probe(command: tuple[str, ...], source: str) -> Candidate | None:
    try:
        proc = subprocess.run(
            [*command, "-c", PROBE_CODE],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if proc.returncode != 0:
        return None

    try:
        info = json.loads(proc.stdout.strip().splitlines()[-1])
        version = tuple(int(part) for part in info["version"])
        executable = os.path.abspath(info["executable"])
        bits = int(info["bits"])
        implementation = str(info["implementation"])
    except Exception:
        return None

    return Candidate(
        command=command,
        executable=executable,
        version=version,  # type: ignore[arg-type]
        bits=bits,
        implementation=implementation,
        source=source,
    )


def _where_all(executable: str) -> list[str]:
    found: list[str] = []
    path = shutil.which(executable)
    if path:
        found.append(path)

    try:
        proc = subprocess.run(
            ["where", executable],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=4,
        )
        if proc.returncode == 0:
            found.extend(line.strip() for line in proc.stdout.splitlines() if line.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass

    result = []
    seen = set()
    for item in found:
        norm = os.path.normcase(os.path.abspath(item))
        if norm not in seen:
            seen.add(norm)
            result.append(item)
    return result


def _py_launcher_versions() -> list[tuple[int, int]]:
    try:
        proc = subprocess.run(
            ["py", "-0p"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=4,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if proc.returncode != 0:
        return []

    versions = []
    seen = set()
    for line in proc.stdout.splitlines():
        match = re.search(r"-V:(\d+)\.(\d+)", line)
        if not match:
            continue
        version = (int(match.group(1)), int(match.group(2)))
        if version in seen:
            continue
        seen.add(version)
        versions.append(version)
    return sorted(versions, reverse=True)


def discover_candidates(min_version: tuple[int, int], max_version: tuple[int, int]) -> list[Candidate]:
    probes: list[tuple[tuple[str, ...], str]] = []

    if shutil.which("py"):
        for major, minor in _py_launcher_versions():
            probes.append((("py", f"-{major}.{minor}"), "py launcher"))
        for major, minor in _version_range(min_version, max_version):
            probes.append((("py", f"-{major}.{minor}"), "py launcher"))

    env_python = os.environ.get("PYTHON")
    if env_python:
        probes.append(((env_python,), "PYTHON env"))

    for name in ("python", "python3"):
        for path in _where_all(name):
            probes.append(((path,), f"PATH {name}"))

    candidates: list[Candidate] = []
    seen_executables = set()
    for command, source in probes:
        candidate = _run_probe(command, source)
        if candidate is None:
            continue
        key = os.path.normcase(os.path.abspath(candidate.executable))
        if key in seen_executables:
            continue
        seen_executables.add(key)
        candidates.append(candidate)

    return candidates


def _is_supported(candidate: Candidate, min_version: tuple[int, int], max_version: tuple[int, int]) -> bool:
    return (
        min_version <= candidate.major_minor <= max_version
        and candidate.bits == 64
        and candidate.implementation.lower() == "cpython"
    )


def select_best(
    candidates: list[Candidate],
    min_version: tuple[int, int],
    max_version: tuple[int, int],
    preferred_versions: list[tuple[int, int]] | None = None,
) -> Candidate | None:
    supported = [item for item in candidates if _is_supported(item, min_version, max_version)]
    if not supported:
        return None
    if preferred_versions:
        for preferred in preferred_versions:
            preferred_supported = [item for item in supported if item.major_minor == preferred]
            if preferred_supported:
                return max(
                    preferred_supported,
                    key=lambda item: (
                        item.version,
                        item.bits,
                        1 if item.source == "py launcher" else 0,
                        item.executable.lower(),
                    ),
                )
    return max(
        supported,
        key=lambda item: (
            item.version,
            item.bits,
            1 if item.source == "py launcher" else 0,
            item.executable.lower(),
        ),
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min", default="3.9", type=_parse_version)
    parser.add_argument("--max", default="3.12", type=_parse_version)
    parser.add_argument("--prefer", type=_parse_prefer, help="comma-separated preferred versions, e.g. 3.12,3.11")
    parser.add_argument("--cmd", action="store_true", help="print only the selected command line")
    parser.add_argument("--explain", action="store_true", help="print selected interpreter and candidates")
    args = parser.parse_args(argv)

    if args.min > args.max:
        parser.error("--min cannot be greater than --max")

    candidates = discover_candidates(args.min, args.max)
    selected = select_best(candidates, args.min, args.max, args.prefer)

    if selected is None:
        if args.cmd:
            return 1
        print(f"  [X] No supported 64-bit CPython {args.min[0]}.{args.min[1]}-{args.max[0]}.{args.max[1]} found")
        if candidates:
            print("  Detected candidates:")
            for item in sorted(candidates, key=lambda c: c.version, reverse=True):
                print(f"    - {item.label()} [{item.source}] {item.executable}")
        return 1

    if args.cmd:
        print(selected.command_line())
        return 0

    print(f"  [OK] Selected {selected.label()} ({selected.source})")
    print(f"       Command: {selected.command_line()}")
    print(f"       Path: {selected.executable}")
    if args.explain:
        print("  Candidates:")
        for item in sorted(candidates, key=lambda c: (c.version, c.bits), reverse=True):
            status = "OK" if _is_supported(item, args.min, args.max) else "skip"
            print(f"    - [{status}] {item.label()} ({item.source}) {item.executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
