from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_glass_background.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("check_glass_background", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_expected_metadata_matches_python_wrapper():
    module = _load_script()
    abi, _ = module._expected_metadata()

    assert abi == 1
