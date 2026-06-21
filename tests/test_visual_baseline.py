"""CI test for visual baseline regression detection."""

from pathlib import Path

import pytest

from tools import dump_visual_baseline, visual_diff

pytestmark = pytest.mark.ui


def test_visual_baseline_matches_current(tmp_path):
    # Set up candidate output directory
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()

    # Generate candidate screenshots for current codebase
    dump_args = ["--out", str(candidate_dir), "--theme", "both", "--dpi", "200"]
    ret = dump_visual_baseline.main(dump_args)
    assert ret == 0, "Failed to generate visual candidate screenshots"

    # Locate baseline directory
    baseline_dir = Path(__file__).resolve().parents[1] / "docs" / "visual_baseline"

    # Check that baseline exists
    assert baseline_dir.exists(), f"Baseline directory {baseline_dir} does not exist"
    baseline_pngs = list(baseline_dir.glob("*.png"))
    assert len(baseline_pngs) > 0, "No visual baseline PNGs found"

    # Compare candidate against baseline using visual_diff
    diff_args = ["--baseline", str(baseline_dir), "--candidate", str(candidate_dir), "--threshold", "0.5"]
    diff_ret = visual_diff.main(diff_args)
    assert diff_ret == 0, "Visual diff failed: current UI deviates from the reference baseline by > 0.5% pixels"
