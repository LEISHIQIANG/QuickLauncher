from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

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


@pytest.mark.skip(reason="Project still has historical migration debt")
def test_final_baseline_has_no_migration_debt():
    baseline = json.loads(architecture.BASELINE_PATH.read_text(encoding="utf-8"))["debt"]
    assert baseline
    assert all(items == [] for items in baseline.values())
