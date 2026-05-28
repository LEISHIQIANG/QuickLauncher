import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from core.version import APP_ID, APP_PUBLISHER, APP_VERSION
from scripts.check_release_artifacts import check_release_artifacts, check_source_metadata

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


def test_win11_build_defaults_to_performance_profile_and_includes_plugins():
    script = (ROOT / "scripts" / "build_win11_setup.bat").read_text(encoding="utf-8")

    assert 'if not defined QL_BUILD_PROFILE set "QL_BUILD_PROFILE=smooth"' in script
    assert "--include-data-dir=plugins=plugins" in script
    assert "--include-data-files=PLUGIN_DEV.md=PLUGIN_DEV.md" in script
    assert 'xcopy "plugins" "dist\\QuickLauncher\\plugins\\" /E /I /Y' in script
    assert 'copy /Y "PLUGIN_DEV.md" "dist\\QuickLauncher\\"' in script
    assert 'if not defined QL_UPX_EXE set "QL_UPX_EXE=0"' in script
    assert 'if not defined QL_KEEP_DIRECT2D set "QL_KEEP_DIRECT2D=1"' in script
    assert "scripts\\check_release_artifacts.py" in script
    assert "QuickLauncher_Setup_%APP_VERSION%.sha256" in script


def test_installer_preserves_user_plugins_on_upgrade():
    installer = (ROOT / "scripts" / "installer.iss").read_text(encoding="utf-8")

    assert "(FindRec.Name <> 'plugins')" in installer


def test_release_source_gate_passes_current_tree():
    result = check_source_metadata(ROOT, APP_VERSION)

    assert result.ok, result.errors


def test_release_artifact_checker_validates_dist_tree(tmp_path):
    dist = tmp_path / "QuickLauncher"
    (dist / "hooks").mkdir(parents=True)
    (dist / "assets").mkdir()
    (dist / "plugins" / "sample").mkdir(parents=True)
    (dist / "QuickLauncher.exe").write_bytes(b"x" * 32)
    (dist / "hooks" / "hooks.dll").write_bytes(b"dll")
    (dist / "assets" / "app.ico").write_bytes(b"ico")
    (dist / "plugins" / "sample" / "plugin.json").write_text("{}", encoding="utf-8")
    (dist / "plugins" / "sample" / "main.py").write_text("pass\n", encoding="utf-8")
    installer = tmp_path / f"QuickLauncher_Setup_{APP_VERSION}.exe"
    installer.write_bytes(b"setup")

    result = check_release_artifacts(ROOT, dist_dir=dist, installer=installer, version=APP_VERSION, min_exe_bytes=1)

    assert result.ok, result.errors
    assert result.manifest["artifacts"]["exe"]["sha256"]
    assert result.manifest["artifacts"]["installer"]["sha256"]


def test_release_artifact_checker_fails_missing_hooks(tmp_path):
    dist = tmp_path / "QuickLauncher"
    (dist / "assets").mkdir(parents=True)
    (dist / "plugins").mkdir()
    (dist / "QuickLauncher.exe").write_bytes(b"x" * 32)
    (dist / "assets" / "app.ico").write_bytes(b"ico")
    installer = tmp_path / f"QuickLauncher_Setup_{APP_VERSION}.exe"
    installer.write_bytes(b"setup")

    result = check_release_artifacts(ROOT, dist_dir=dist, installer=installer, version=APP_VERSION, min_exe_bytes=1)

    assert not result.ok
    assert any("hooks.dll" in error for error in result.errors)
