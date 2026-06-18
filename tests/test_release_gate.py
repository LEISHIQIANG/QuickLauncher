from types import SimpleNamespace

import pytest

from scripts import release_gate


@pytest.fixture(autouse=True)
def _no_real_cleanup(monkeypatch):
    monkeypatch.setattr(release_gate, "_clean_stale_caches", lambda root: None)


def test_release_gate_dry_run_skips_execution(capsys):
    assert release_gate.main(["--python", "py-test", "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "ruff: py-test -m ruff check --no-cache core ui hooks services tests" in output
    assert f"pytest: py-test -m pytest --basetemp {release_gate.PYTEST_BASETEMP}" in output
    assert "compileall: py-test -m compileall core ui hooks services bootstrap plugins" in output
    assert "mypy zero errors: py-test scripts/check_mypy_progress.py" in output
    assert "py-test scripts/check_release_artifacts.py --source-only --allow-source-runtime-plugins" in output
    assert "py-test scripts/post_package_smoke.py" in output


def test_release_gate_skip_tests_and_returns_failure(monkeypatch):
    calls = []

    def fake_run(command, cwd, check, env):
        calls.append((command, env))
        return SimpleNamespace(returncode=7 if command[1:3] == ["-m", "ruff"] else 0)

    monkeypatch.setattr(release_gate.subprocess, "run", fake_run)

    assert release_gate.main(["--python", "py-test", "--skip-tests"]) == 7
    assert all(command[1:3] != ["-m", "pytest"] for command, _env in calls)
    assert calls[0][0][1:3] == ["-m", "ruff"]


def test_release_gate_uses_isolated_commands_and_env(monkeypatch):
    calls = []
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)

    def fake_run(command, cwd, check, env):
        calls.append((command, env))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(release_gate.subprocess, "run", fake_run)

    assert release_gate.main(["--python", "py-test"]) == 0

    commands = [command for command, _env in calls]
    envs = [env for _command, env in calls]

    assert commands[0][:5] == ["py-test", "-m", "ruff", "check", "--no-cache"]
    assert envs[0]["RUFF_NO_CACHE"] == "1"
    assert envs[0]["PYTHONDONTWRITEBYTECODE"] == "1"

    assert commands[1] == [
        "py-test",
        "-m",
        "pytest",
        "--basetemp",
        str(release_gate.PYTEST_BASETEMP),
        "--cov=core",
        "--cov=services",
        "--cov=hooks",
        "--cov-report=term-missing",
        f"--cov-fail-under={release_gate.COVERAGE_FAIL_UNDER}",
    ]
    assert envs[1]["PYTHONDONTWRITEBYTECODE"] == "1"

    assert commands[2] == [
        "py-test",
        "scripts/audit_broad_exceptions.py",
        "--exclude-dir",
        "plugins",
        "--exclude-dir",
        "tools",
        "--max-total",
        "1420",
        "--max-unlogged",
        "300",
    ]
    assert envs[2]["PYTHONDONTWRITEBYTECODE"] == "1"

    assert commands[3] == [
        "py-test",
        "scripts/check_i18n_coverage.py",
        "--max-untranslated-pct",
        "3",
    ]
    assert envs[3]["PYTHONDONTWRITEBYTECODE"] == "1"

    assert commands[4] == ["py-test", "scripts/check_mypy_progress.py"]
    assert envs[4]["PYTHONDONTWRITEBYTECODE"] == "1"

    assert commands[5][:3] == ["py-test", "-m", "compileall"]
    assert envs[5]["PYTHONPYCACHEPREFIX"] == str(release_gate.COMPILE_PYCACHE_PREFIX)

    assert commands[6] == [
        "py-test",
        "scripts/check_release_artifacts.py",
        "--source-only",
        "--allow-source-runtime-plugins",
    ]
    assert envs[6]["PYTHONDONTWRITEBYTECODE"] == "1"

    assert commands[7] == ["py-test", "scripts/post_package_smoke.py"]
    assert envs[7]["PYTHONDONTWRITEBYTECODE"] == "1"


def test_release_gate_step_order_matches_spec():
    steps = release_gate._default_steps("python")
    assert [step.name for step in steps] == [
        "ruff",
        "pytest",
        "broad exception audit",
        "i18n coverage",
        "mypy zero errors",
        "compileall",
        "release metadata",
        "post-package smoke",
    ]


def test_release_gate_pytest_basetemp_is_outside_project_root():
    assert release_gate.ROOT.resolve(strict=False) not in release_gate.PYTEST_BASETEMP.resolve(strict=False).parents


def test_release_gate_coverage_baseline_matches_current_project_floor():
    assert release_gate.COVERAGE_FAIL_UNDER == 67


def test_release_gate_cleans_stale_caches_before_running(monkeypatch):
    clean_calls = []
    monkeypatch.setattr(release_gate, "_clean_stale_caches", lambda root: clean_calls.append(root))
    monkeypatch.setattr(release_gate.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))

    release_gate.main(["--python", "py-test"])
    assert clean_calls == [release_gate.ROOT]


def test_release_gate_env_isolation_excludes_stale_vars(monkeypatch):
    monkeypatch.setenv("STALE_PYCACHE_PREFIX", "/some/old/path")
    monkeypatch.setenv("PYTHONFAULTHANDLER", "1")
    calls = []

    def fake_run(command, cwd, check, env):
        calls.append(env)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(release_gate.subprocess, "run", fake_run)

    release_gate.main(["--python", "py-test"])

    for env in calls:
        assert "STALE_PYCACHE_PREFIX" not in env
        assert "PYTHONFAULTHANDLER" not in env
        assert "PATH" in env


def test_release_gate_env_isolation_preserves_essential_vars(monkeypatch):
    monkeypatch.setenv("SYSTEMROOT", r"C:\WINDOWS")
    monkeypatch.setenv("SystemDrive", "C:")
    monkeypatch.setenv("ProgramData", r"C:\ProgramData")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_OS", "Windows")
    calls = []

    def fake_run(command, cwd, check, env):
        calls.append(env)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(release_gate.subprocess, "run", fake_run)

    release_gate.main(["--python", "py-test"])

    for env in calls:
        assert env.get("SYSTEMROOT") == r"C:\WINDOWS"
        normalized_env = {key.upper(): value for key, value in env.items()}
        assert normalized_env.get("SYSTEMDRIVE") == "C:"
        assert normalized_env.get("PROGRAMDATA") == r"C:\ProgramData"
        assert env.get("CI") == "true"
        assert env.get("GITHUB_ACTIONS") == "true"
        assert env.get("RUNNER_OS") == "Windows"


def test_release_gate_help_exits_zero():
    with pytest.raises(SystemExit) as exc_info:
        release_gate.main(["--help"])
    assert exc_info.value.code == 0
