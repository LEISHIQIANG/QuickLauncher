"""Measure architecture-sensitive performance and compare it with 1.6.3.5.

The probe runs in a fresh child interpreter so imports, RSS and executor state
cannot be contaminated by the measurement controller.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT.parent / "QuickLauncher_V1.6.3.5"
DEFAULT_BASELINE = ROOT / "docs" / "quality" / "performance_baseline.json"
logger = logging.getLogger(__name__)


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _timed_samples(callback, *, warmups: int, iterations: int) -> list[float]:
    for _ in range(warmups):
        callback()
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        callback()
        samples.append((time.perf_counter() - started) * 1000.0)
    return samples


def _probe(source_root: Path) -> dict[str, Any]:
    os.chdir(source_root)
    sys.path.insert(0, str(source_root))
    import_started = time.perf_counter()
    __import__("main")
    cold_import_ms = (time.perf_counter() - import_started) * 1000.0

    import psutil

    from core.fuzzy_search import search_shortcuts

    items = [
        SimpleNamespace(
            id=f"item-{index}",
            name=f"Visual Studio Code {index}",
            alias=f"vscode{index}",
            tags=["editor", "development"],
            target_path=f"C:/Apps/Editor{index}.exe",
            enabled=True,
            order=index,
        )
        for index in range(1000)
    ]
    pages = [SimpleNamespace(id="apps", name="Applications", items=items)]
    search_samples = _timed_samples(
        lambda: search_shortcuts(pages, "visual code", limit=20),
        warmups=3,
        iterations=15,
    )

    metrics: dict[str, float] = {
        "cold_import_ms": cold_import_ms,
        "resident_memory_mb": psutil.Process().memory_info().rss / (1024 * 1024),
        "search_1000_p95_ms": _p95(search_samples),
    }

    try:
        from core.command_execution_service import CommandExecutionService

        service = CommandExecutionService()
        sequence = iter(range(10000))

        def submit_once() -> None:
            request_id = f"perf-{next(sequence)}"
            future = service._submit_worker(lambda: None, "perf", request_id)
            future.result(timeout=2.0)

        dispatch_samples = _timed_samples(submit_once, warmups=10, iterations=100)
        metrics["command_dispatch_p95_ms"] = _p95(dispatch_samples)
        shutdown = getattr(service, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown(timeout=2.0, shutdown_executor=True)
            except TypeError:
                shutdown()
    except (ImportError, AttributeError, RuntimeError, TypeError):
        logger.debug("command execution performance probe unavailable", exc_info=True)

    try:
        from application.state import StateStore

        store = StateStore({"counter": 0})

        def mutate() -> None:
            snapshot = store.snapshot()
            store.submit(
                lambda state: {**state, "counter": int(state["counter"]) + 1},
                expected_revision=snapshot.revision,
            )

        state_samples = _timed_samples(mutate, warmups=10, iterations=200)
        metrics["state_command_p95_ms"] = _p95(state_samples)
    except (ImportError, AttributeError, RuntimeError, TypeError):
        logger.debug("state performance probe unavailable", exc_info=True)

    return {key: round(value, 3) for key, value in metrics.items()}


def _run_probe(source_root: Path) -> dict[str, float]:
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--probe", str(source_root)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    return {str(key): float(value) for key, value in payload.items()}


def _build_baseline(reference: Path, current: Path) -> dict[str, Any]:
    reference_runs = [_run_probe(reference) for _ in range(5)]
    current_runs = [_run_probe(current) for _ in range(5)]

    def median_metrics(runs: list[dict[str, float]]) -> dict[str, float]:
        keys = set.intersection(*(set(run) for run in runs))
        return {key: round(statistics.median(run[key] for run in runs), 3) for key in sorted(keys)}

    reference_metrics = median_metrics(reference_runs)
    current_metrics = median_metrics(current_runs)
    budgets = {
        key: round(value * 1.05, 3)
        for key, value in reference_metrics.items()
        if key in {"cold_import_ms", "resident_memory_mb", "search_1000_p95_ms"}
    }
    budgets["command_dispatch_p95_ms"] = 20.0
    return {
        "schema_version": 1,
        "reference_version": "1.6.3.5",
        "reference_root": str(reference.resolve()),
        "measurement": "median of 5 isolated process probes; operation metrics report p95",
        "reference": reference_metrics,
        "current_at_capture": current_metrics,
        "budgets": budgets,
    }


def _check(current: dict[str, float], baseline: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for name, limit in dict(baseline.get("budgets") or {}).items():
        value = current.get(name)
        if value is None:
            failures.append(f"missing metric: {name}")
        elif value > float(limit):
            failures.append(f"{name}: {value:.3f} > {float(limit):.3f}")
    return failures


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.probe is not None:
        print(json.dumps(_probe(args.probe), sort_keys=True))
        return 0
    if args.write_baseline:
        if not args.reference.is_dir():
            print(f"reference checkout missing: {args.reference}", file=sys.stderr)
            return 2
        payload = _build_baseline(args.reference, ROOT)
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"performance baseline written: {args.baseline}")
        return 0
    if args.check:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        current = _run_probe(ROOT)
        failures = _check(current, baseline)
        print(json.dumps({"current": current, "failures": failures}, ensure_ascii=False, indent=2))
        return 1 if failures else 0
    print(json.dumps(_run_probe(ROOT), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
