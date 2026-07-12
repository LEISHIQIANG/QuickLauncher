from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts import check_architecture as architecture


def test_strongly_connected_finds_only_cycles():
    graph = {
        "a": {"b"},
        "b": {"a", "c"},
        "c": set(),
        "self": {"self"},
    }

    assert architecture._strongly_connected(graph) == [["a", "b"], ["self"]]


def test_relative_import_resolution():
    node = ast.parse("from .ports import Clock").body[0]
    assert isinstance(node, ast.ImportFrom)

    assert architecture._resolve_from("application.services.runner", node) == "application.services.ports"


def test_gate_matches_itemized_baseline(tmp_path: Path):
    findings = architecture.scan()
    baseline = tmp_path / "baseline.json"
    architecture._write_baseline(baseline, findings)

    assert architecture.main(["--baseline", str(baseline)]) == 0


def test_repository_architecture_baseline_is_current():
    assert architecture.main([]) == 0


def test_architecture_baseline_debt_is_tracked():
    """Architecture debt is itemized in the baseline (clearing it is a future milestone)."""
    baseline = json.loads(architecture.BASELINE_PATH.read_text(encoding="utf-8"))
    debt = baseline.get("debt", {})
    assert isinstance(debt, dict), "Baseline must contain a 'debt' object"
    # Each debt category must be documented (may be non-empty while migration is in progress)
    for category in (
        "boundary_violations",
        "cycles",
        "import_time_side_effects",
        "plugin_internal_imports",
        "sensitive_calls",
        "dynamic_imports",
        "service_locators",
    ):
        assert category in debt, f"Missing debt category: {category}"
        assert isinstance(debt[category], list), f"Debt category '{category}' must be a list"
