"""Pixel-level visual regression check against baseline PNGs.

Usage:
    python scripts/visual_diff.py --baseline docs/visual_baseline
    python scripts/visual_diff.py --baseline docs/visual_baseline --threshold 0.5

The script compares every {component}_{theme}_{dpi}.png in the baseline
directory against a freshly captured screenshot of the same component
(using the same dump mechanism as the local visual baseline dumper, when
available).

Exit code:
    0 – all diffs <= threshold
    1 – any diff > threshold (blocking for CI)

Threshold is the percentage of differing pixels (default 0.5 %).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _load_pixels(path: Path) -> Any:
    from qt_compat import QImage

    image = QImage(str(path))
    if image.isNull():
        raise FileNotFoundError(f"Cannot load {path}")
    return image


def pixel_diff_pct(baseline_path: Path, candidate_path: Path) -> float:
    b_img = _load_pixels(baseline_path)
    c_img = _load_pixels(candidate_path)

    if b_img.size() != c_img.size():
        logger.warning(
            "Size mismatch: %s (%dx%d) vs %s (%dx%d)",
            baseline_path.name,
            b_img.width(),
            b_img.height(),
            candidate_path.name,
            c_img.width(),
            c_img.height(),
        )
        return 100.0

    width = b_img.width()
    height = b_img.height()
    differing = 0
    total = width * height

    for y in range(height):
        for x in range(width):
            bp = b_img.pixel(x, y)
            cp = c_img.pixel(x, y)
            if bp != cp:
                differing += 1
                if differing > total * 0.02:  # early exit at 2 %
                    return 100.0 * differing / total

    return 100.0 * differing / total


def compare_all(
    baseline_dir: Path,
    candidate_dir: Path,
    threshold: float,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    baseline_files = sorted(baseline_dir.glob("*.png"))

    if not baseline_files:
        logger.error("No baseline PNGs found in %s", baseline_dir)
        sys.exit(1)

    for bf in baseline_files:
        cf = candidate_dir / bf.name
        if not cf.exists():
            results.append({"file": bf.name, "diff_pct": 100.0, "status": "MISSING"})
            continue
        try:
            diff = pixel_diff_pct(bf, cf)
        except Exception as exc:
            results.append({"file": bf.name, "diff_pct": 100.0, "status": f"ERROR: {exc}"})
            continue
        status = "PASS" if diff <= threshold else "FAIL"
        results.append({"file": bf.name, "diff_pct": diff, "status": status})

    return results


def _capture_live_candidates(baseline_dir: Path) -> Path:
    candidate_dir = baseline_dir.parent / ".candidate"
    candidate_dir.mkdir(parents=True, exist_ok=True)

    from qt_compat import QApplication
    from tools.dump_visual_baseline import COMPONENTS, dump_component

    QApplication.instance() or QApplication(sys.argv)
    dpis = [100, 125, 150, 200]
    for entry in COMPONENTS:
        dump_component(entry, candidate_dir, dpis)
    return candidate_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Visual regression check")
    parser.add_argument("--baseline", required=True, type=Path, help="Baseline PNG directory")
    parser.add_argument(
        "--candidate",
        type=Path,
        default=None,
        help="Candidate PNG directory (default: re-capture live)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Max allowed pixel diff %% (default: 0.5)",
    )
    args = parser.parse_args(argv)

    baseline_dir = args.baseline.resolve()
    if not baseline_dir.is_dir():
        logger.error("Baseline directory not found: %s", baseline_dir)
        sys.exit(1)

    candidate_dir = args.candidate.resolve() if args.candidate else _capture_live_candidates(baseline_dir)
    results = compare_all(baseline_dir, candidate_dir, args.threshold)

    failed = 0
    for result in results:
        status = str(result["status"])
        marker = "✓" if status == "PASS" else "✗"
        logger.info(
            "  %s %-50s %6.2f %%  %s",
            marker,
            result["file"],
            result["diff_pct"],
            status,
        )
        if status != "PASS":
            failed += 1

    if failed:
        logger.error("%d / %d images exceed threshold %.1f %%", failed, len(results), args.threshold)
        return 1
    logger.info("All %d images pass (Δ <= %.1f %%)", len(results), args.threshold)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
