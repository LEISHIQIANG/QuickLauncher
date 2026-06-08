import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from core.version import APP_ID, APP_PUBLISHER, APP_VERSION, RELEASE_STATUS
from scripts.check_release_artifacts import check_release_artifacts, check_source_metadata
from scripts.post_package_smoke import default_dist_dir, run_packaged_smoke

ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_script_matches_core_version():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "read_project_version.py"), "version"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == APP_VERSION


def test_installer_metadata_has_no_placeholder_metadata():
    installer = (ROOT / "scripts" / "installer.iss").read_text(encoding="utf-8")

    assert "Your Name" not in installer
    assert "A1B2C3D4-E5F6-7890-ABCD-EF1234567890" not in installer
    assert "AppVerName={#MyAppName} {#MyAppVersion}" in installer
    assert 'OutputBaseFilename "QuickLauncher_Setup_" + MyAppVersion' in installer
    assert APP_PUBLISHER in installer
    assert APP_ID in installer
    assert f'#define MyAppVersion "{APP_VERSION}"' in installer
    assert f'#define MyAppFileVersion "{APP_VERSION}"' in installer


def test_manifest_version_matches_core_version():
    root = ET.fromstring((ROOT / "QuickLauncher.manifest").read_text(encoding="utf-8"))
    identity = root.find("{urn:schemas-microsoft-com:asm.v1}assemblyIdentity")

    assert identity is not None
    assert identity.attrib["version"] == APP_VERSION


def test_win11_build_defaults_to_performance_profile_and_externalizes_plugins():
    script = (ROOT / "scripts" / "build_win11_setup.bat").read_text(encoding="utf-8")

    assert 'if not defined QL_BUILD_PROFILE set "QL_BUILD_PROFILE=smooth"' in script
    assert '--min 3.12 --max 3.12 --prefer "3.12"' in script
    assert "plugin-bundled wxPython is cp312" in script
    assert "--include-data-dir=plugins=plugins" not in script
    assert "--include-data-files=plugins\\PLUGIN_DEV.md=PLUGIN_DEV.md" in script
    assert "wxPython==" not in script
    assert "--include-module=wx" not in script
    assert "--include-package=wx" not in script
    assert "wechat-ocr" not in script
    assert "wechat_ocr" not in script
    assert "google.protobuf" not in script
    assert 'xcopy "plugins" "dist\\QuickLauncher\\plugins\\" /E /I /Y' not in script
    assert 'mkdir "dist\\QuickLauncher\\plugins"' in script
    assert 'dist\\QuickLauncher\\.plugins' not in script
    assert 'copy /Y "plugins\\PLUGIN_DEV.md" "dist\\QuickLauncher\\"' in script
    assert "Failed to remove old dist\\QuickLauncher" in script
    assert 'robocopy "dist\\main.dist" "dist\\QuickLauncher" /MIR' in script
    assert "Start-Sleep -Seconds 2" in script
    assert 'cd /d "%~dp0.."' in script
    assert "Failed to stage dist\\main.dist into dist\\QuickLauncher" in script
    assert 'if exist "dist\\QuickLauncher\\QuickLauncher.exe"' in script
    assert 'if not defined QL_UPX_EXE set "QL_UPX_EXE=0"' in script
    assert 'if not defined QL_KEEP_DIRECT2D set "QL_KEEP_DIRECT2D=1"' in script
    assert "scripts\\check_release_artifacts.py" in script
    assert "--allow-source-runtime-plugins" in script
    assert "--run-smoke" in script
    assert "QuickLauncher_Setup_%APP_VERSION%.sha256" in script


def test_installer_preserves_user_plugins_on_upgrade():
    installer = (ROOT / "scripts" / "installer.iss").read_text(encoding="utf-8")

    assert "(FindRec.Name <> 'plugins')" in installer


def test_release_source_gate_passes_current_tree():
    result = check_source_metadata(ROOT, APP_VERSION, allow_source_runtime_plugins=True)

    assert result.ok, result.errors
    assert result.manifest["release_status"] == RELEASE_STATUS


def test_changelog_release_state_matches_core_version():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    if RELEASE_STATUS == "stable":
        assert f"## [{APP_VERSION}] - Unreleased" not in changelog
        assert f"## [{APP_VERSION}] -" in changelog


def test_release_artifact_checker_validates_dist_tree(tmp_path):
    dist = tmp_path / "QuickLauncher"
    (dist / "hooks").mkdir(parents=True)
    (dist / "assets").mkdir()
    (dist / "plugins").mkdir()
    (dist / "QuickLauncher.exe").write_bytes(b"x" * 32)
    (dist / "hooks" / "hooks.dll").write_bytes(b"dll")
    (dist / "assets" / "app.ico").write_bytes(b"ico")
    installer = tmp_path / f"QuickLauncher_Setup_{APP_VERSION}.exe"
    installer.write_bytes(b"setup")

    result = check_release_artifacts(
        ROOT,
        dist_dir=dist,
        installer=installer,
        version=APP_VERSION,
        min_exe_bytes=1,
        allow_source_runtime_plugins=True,
    )

    assert result.ok, result.errors
    assert result.manifest["artifacts"]["exe"]["sha256"]
    assert result.manifest["artifacts"]["installer"]["sha256"]


def test_release_artifact_checker_can_ignore_local_source_runtime_plugins(tmp_path):
    root = tmp_path / "release-root"
    (root / "core").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "assets").mkdir()
    (root / "hooks").mkdir()
    (root / "plugins" / "screenshot_ocr").mkdir(parents=True)
    (root / ".plugins").mkdir()

    (root / "core" / "version.py").write_text(
        f'APP_VERSION = "{APP_VERSION}"\nRELEASE_STATUS = "stable"\n',
        encoding="utf-8",
    )
    (root / "scripts" / "installer.iss").write_text(
        f'#define MyAppVersion "{APP_VERSION}"\n'
        f'#define MyAppFileVersion "{APP_VERSION}"\n'
        'OutputBaseFilename "QuickLauncher_Setup_" + MyAppVersion\n',
        encoding="utf-8",
    )
    (root / "scripts" / "build_win11_setup.bat").write_text("@echo off\n", encoding="utf-8")
    (root / "QuickLauncher.manifest").write_text(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">\n'
        f'  <assemblyIdentity version="{APP_VERSION}" name="QuickLauncher" type="win32"/>\n'
        "</assembly>\n",
        encoding="utf-8",
    )
    (root / "assets" / "app.ico").write_bytes(b"ico")
    (root / "hooks" / "hooks.dll").write_bytes(b"dll")
    (root / "plugins" / "PLUGIN_DEV.md").write_text("plugin docs\n", encoding="utf-8")
    (root / "plugins" / "screenshot_ocr" / "plugin.json").write_text(
        '{"id": "screenshot_ocr"}\n',
        encoding="utf-8",
    )
    for plugin_id in (
        "api_tester",
        "disk_cleaner",
        "event_inspector",
        "file_tools",
        "network_tools",
        "process_tools",
        "qr_code_scanner",
        "screenshot_ocr",
        "startup_tools",
        "text_tools",
    ):
        (root / ".plugins" / f"{plugin_id}.qlzip").write_bytes(b"pkg")

    dist = tmp_path / "QuickLauncher"
    (dist / "hooks").mkdir(parents=True)
    (dist / "assets").mkdir()
    (dist / "plugins").mkdir()
    (dist / "QuickLauncher.exe").write_bytes(b"x" * 32)
    (dist / "hooks" / "hooks.dll").write_bytes(b"dll")
    (dist / "assets" / "app.ico").write_bytes(b"ico")
    installer = tmp_path / f"QuickLauncher_Setup_{APP_VERSION}.exe"
    installer.write_bytes(b"setup")

    strict_result = check_release_artifacts(root, dist_dir=dist, installer=installer, version=APP_VERSION, min_exe_bytes=1)
    allowed_result = check_release_artifacts(
        root,
        dist_dir=dist,
        installer=installer,
        version=APP_VERSION,
        min_exe_bytes=1,
        allow_source_runtime_plugins=True,
    )

    assert not strict_result.ok
    assert any("source plugins directory" in error for error in strict_result.errors)
    assert allowed_result.ok, allowed_result.errors
    assert allowed_result.manifest["source"]["runtime_plugin_dirs_ignored"] == ["screenshot_ocr"]


def test_release_artifact_checker_runs_post_package_smoke(tmp_path):
    dist = tmp_path / "QuickLauncher"
    (dist / "hooks").mkdir(parents=True)
    (dist / "assets").mkdir()
    (dist / "plugins").mkdir()
    (dist / "QuickLauncher.exe").write_bytes(b"x" * 32)
    (dist / "hooks" / "hooks.dll").write_bytes(b"dll")
    (dist / "assets" / "app.ico").write_bytes(b"ico")
    installer = tmp_path / f"QuickLauncher_Setup_{APP_VERSION}.exe"
    installer.write_bytes(b"setup")
    fake_smoke = tmp_path / "fake_smoke.py"
    fake_smoke.write_text(
        "import json\n"
        "print('starting fake smoke')\n"
        "print(json.dumps({'status': 'ok', 'checks': {'fake': True, 'network_runtime': {}}, 'errors': []}))\n",
        encoding="utf-8",
    )

    result = check_release_artifacts(
        ROOT,
        dist_dir=dist,
        installer=installer,
        version=APP_VERSION,
        min_exe_bytes=1,
        allow_source_runtime_plugins=True,
        run_smoke=True,
        smoke_exe=Path(sys.executable),
        smoke_args=[str(fake_smoke)],
    )

    assert result.ok, result.errors
    assert result.manifest["post_package_smoke"]["ok"] is True
    assert result.manifest["post_package_smoke"]["smoke_payload"]["checks"]["fake"] is True


def test_post_package_smoke_default_dist_dir_uses_versioned_portable(tmp_path):
    root = tmp_path / "root"
    (root / "core").mkdir(parents=True)
    (root / "dist" / f"QuickLauncher_Portable_{APP_VERSION}").mkdir(parents=True)
    (root / "core" / "version.py").write_text(f'APP_VERSION = "{APP_VERSION}"\n', encoding="utf-8")
    exe = root / "dist" / f"QuickLauncher_Portable_{APP_VERSION}" / "QuickLauncher.exe"
    exe.write_bytes(b"exe")

    assert default_dist_dir(root) == exe.parent


def test_post_package_smoke_default_dist_dir_prefers_staged_dist(tmp_path):
    root = tmp_path / "root"
    staged = root / "dist" / "QuickLauncher"
    portable = root / "dist" / f"QuickLauncher_Portable_{APP_VERSION}"
    staged.mkdir(parents=True)
    portable.mkdir(parents=True)
    (staged / "QuickLauncher.exe").write_bytes(b"exe")
    (portable / "QuickLauncher.exe").write_bytes(b"exe")

    assert default_dist_dir(root) == staged


def test_post_package_smoke_rejects_failed_payload(tmp_path):
    dist = tmp_path / "QuickLauncher"
    dist.mkdir()
    fake_smoke = tmp_path / "fake_smoke.py"
    fake_smoke.write_text(
        "import json\nprint(json.dumps({'status': 'failed', 'errors': ['boom']}))\n",
        encoding="utf-8",
    )

    result = run_packaged_smoke(dist, exe=Path(sys.executable), smoke_args=[str(fake_smoke)])

    assert not result.ok
    assert "boom" in result.errors
    assert result.smoke_payload == {"status": "failed", "errors": ["boom"]}


def test_post_package_smoke_requires_network_runtime_check(tmp_path):
    dist = tmp_path / "QuickLauncher"
    dist.mkdir()
    fake_smoke = tmp_path / "fake_smoke.py"
    fake_smoke.write_text(
        "import json\nprint(json.dumps({'status': 'ok', 'checks': {}, 'errors': []}))\n",
        encoding="utf-8",
    )

    result = run_packaged_smoke(dist, exe=Path(sys.executable), smoke_args=[str(fake_smoke)])

    assert not result.ok
    assert any("network_runtime" in error for error in result.errors)


def test_release_artifact_checker_fails_missing_hooks(tmp_path):
    dist = tmp_path / "QuickLauncher"
    (dist / "assets").mkdir(parents=True)
    (dist / "plugins").mkdir()
    (dist / "QuickLauncher.exe").write_bytes(b"x" * 32)
    (dist / "assets" / "app.ico").write_bytes(b"ico")
    installer = tmp_path / f"QuickLauncher_Setup_{APP_VERSION}.exe"
    installer.write_bytes(b"setup")

    result = check_release_artifacts(
        ROOT,
        dist_dir=dist,
        installer=installer,
        version=APP_VERSION,
        min_exe_bytes=1,
        allow_source_runtime_plugins=True,
    )

    assert not result.ok
    assert any("hooks.dll" in error for error in result.errors)


def test_release_artifact_checker_rejects_pycache(tmp_path):
    dist = tmp_path / "QuickLauncher"
    (dist / "hooks").mkdir(parents=True)
    (dist / "assets").mkdir()
    (dist / "plugins" / "sample").mkdir(parents=True)
    (dist / "QuickLauncher.exe").write_bytes(b"x" * 32)
    (dist / "hooks" / "hooks.dll").write_bytes(b"dll")
    (dist / "assets" / "app.ico").write_bytes(b"ico")
    # Simulate __pycache__ debris that should be caught
    pycache = dist / "plugins" / "sample" / "__pycache__"
    pycache.mkdir()
    (pycache / "main.cpython-312.pyc").write_bytes(b"")
    installer = tmp_path / f"QuickLauncher_Setup_{APP_VERSION}.exe"
    installer.write_bytes(b"setup")

    result = check_release_artifacts(
        ROOT,
        dist_dir=dist,
        installer=installer,
        version=APP_VERSION,
        min_exe_bytes=1,
        allow_source_runtime_plugins=True,
    )

    assert not result.ok
    debris_errors = [e for e in result.errors if "pycache" in e.lower() or ".pyc" in e.lower()]
    assert len(debris_errors) >= 1, f"Expected debris errors, got: {result.errors}"


def test_build_script_cleans_pycache_from_plugins():
    script = (ROOT / "scripts" / "build_win11_setup.bat").read_text(encoding="utf-8")
    assert "rmdir /s /q" in script
    assert "__pycache__" in script
    assert "*.pyc" in script
