"""Deterministic checks for the visual-regression baseline and diff gate."""

from pathlib import Path

import pytest

from qt_compat import QColor, QImage
from scripts import visual_diff

pytestmark = pytest.mark.ui


def _write_image(path: Path, color: str) -> None:
    image = QImage(8, 8, QImage.Format_ARGB32)
    image.fill(QColor(color))
    assert image.save(str(path))


def test_visual_baseline_inventory_has_dark_and_light_pairs():
    baseline_dir = Path(__file__).resolve().parents[1] / "docs" / "visual_baseline"
    names = {path.name for path in baseline_dir.glob("*.png")}
    components = {name.removesuffix("_dark_200.png") for name in names if name.endswith("_dark_200.png")}

    if not components:
        pytest.skip("no visual baselines available (directory empty or removed)")
    assert len(components) >= 18
    for component in components:
        assert f"{component}_light_200.png" in names


def test_visual_diff_passes_equal_images_and_blocks_missing_or_changed(tmp_path):
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    baseline.mkdir()
    candidate.mkdir()
    baseline_file = baseline / "sample_dark_200.png"
    candidate_file = candidate / baseline_file.name

    _write_image(baseline_file, "#112233")
    _write_image(candidate_file, "#112233")
    assert visual_diff.main(["--baseline", str(baseline), "--candidate", str(candidate)]) == 0

    _write_image(candidate_file, "#FFFFFF")
    assert visual_diff.main(["--baseline", str(baseline), "--candidate", str(candidate)]) == 1

    candidate_file.unlink()
    assert visual_diff.main(["--baseline", str(baseline), "--candidate", str(candidate)]) == 1
