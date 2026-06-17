"""Tests for the P1-07 ``scripts/check_hooks_dll.py`` helper.

The script is a release-time gate that ensures the committed
``hooks/hooks.dll`` matches the metadata declared in the runtime
wrapper.  These tests exercise the two main code paths:

* a passing check when the DLL hash matches the wrapper metadata;
* a failing check when the script is asked to validate a different
  path or detect a missing DLL.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_hooks_dll.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("check_hooks_dll", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_expected_metadata_is_parsed_from_wrapper():
    module = _load_script_module()
    version, sha = module._expected_metadata()
    assert version == 15
    assert len(sha) == 64
    int(sha, 16)  # parses without raising


def test_main_passes_against_committed_dll():
    module = _load_script_module()
    assert module.main() == 0


def test_main_reports_missing_dll(tmp_path, monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(module, "DLL_PATH", tmp_path / "missing.dll")
    assert module.main() == 1


def test_main_reports_hash_mismatch(tmp_path, monkeypatch):
    module = _load_script_module()
    fake_dll = tmp_path / "hooks.dll"
    fake_dll.write_bytes(b"not the real dll")
    monkeypatch.setattr(module, "DLL_PATH", fake_dll)
    # The expected SHA-256 of the real DLL is non-zero; the fake
    # bytes should never match.
    assert module.main() == 1


def test_cli_invocation_matches_imported_main():
    """``python scripts/check_hooks_dll.py`` exits 0 in this checkout."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "OK: hooks.dll matches" in result.stdout
