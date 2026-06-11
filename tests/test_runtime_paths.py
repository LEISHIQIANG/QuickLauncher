from pathlib import Path

import runtime_paths


def test_quicklauncher_exe_without_sys_frozen_is_packaged(monkeypatch, tmp_path):
    exe = tmp_path / "QuickLauncher.exe"
    exe.write_bytes(b"exe")
    monkeypatch.delattr(runtime_paths.sys, "frozen", raising=False)
    monkeypatch.setattr(runtime_paths.sys, "executable", str(exe))
    monkeypatch.setattr(runtime_paths.sys, "argv", ["main.py"])

    assert runtime_paths.is_packaged_runtime() is True
    assert runtime_paths.app_executable() == exe
    assert runtime_paths.app_root() == tmp_path
    assert runtime_paths.config_dir() == tmp_path / "config"


def test_source_runtime_uses_project_root(monkeypatch):
    monkeypatch.delattr(runtime_paths.sys, "frozen", raising=False)
    monkeypatch.setattr(runtime_paths.sys, "executable", r"C:\Python312\python.exe")
    monkeypatch.setattr(runtime_paths.sys, "argv", ["main.py"])

    assert runtime_paths.is_packaged_runtime() is False
    assert runtime_paths.app_root() == Path(runtime_paths.__file__).resolve().parent


def test_smoke_config_dir_override(monkeypatch, tmp_path):
    target = tmp_path / "smoke-config"
    monkeypatch.setenv("QL_SMOKE_CONFIG_DIR", str(target))

    assert runtime_paths.config_dir() == target.resolve()
