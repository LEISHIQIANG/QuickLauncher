from __future__ import annotations

import json
from pathlib import Path


def test_performance_baseline_has_reference_and_hard_budgets():
    path = Path(__file__).parents[1] / "docs" / "quality" / "performance_baseline.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["reference_version"] == "1.6.3.5"
    assert payload["reference"]
    assert payload["current_at_capture"]
    assert payload["budgets"]["command_dispatch_p95_ms"] == 20.0
    assert set(payload["budgets"]) >= {"cold_import_ms", "resident_memory_mb", "search_1000_p95_ms"}
