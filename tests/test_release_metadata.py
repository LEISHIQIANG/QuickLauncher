import subprocess
import sys
from pathlib import Path

from core.version import APP_ID, APP_PUBLISHER, APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_script_matches_core_version():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "read_project_version.py"), "version"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == APP_VERSION


def test_installer_metadata_has_no_commercial_placeholders():
    installer = (ROOT / "scripts" / "installer.iss").read_text(encoding="utf-8")

    assert "Your Name" not in installer
    assert "A1B2C3D4-E5F6-7890-ABCD-EF1234567890" not in installer
    assert APP_PUBLISHER in installer
    assert APP_ID in installer


def test_win11_build_defaults_to_performance_profile_and_includes_plugins():
    script = (ROOT / "scripts" / "build_win11_setup.bat").read_text(encoding="utf-8")

    assert 'if not defined QL_BUILD_PROFILE set "QL_BUILD_PROFILE=smooth"' in script
    assert "--include-data-dir=plugins=plugins" in script
    assert "--include-data-files=PLUGIN_DEV.md=PLUGIN_DEV.md" in script
    assert 'xcopy "plugins" "dist\\QuickLauncher\\plugins\\" /E /I /Y' in script
    assert 'copy /Y "PLUGIN_DEV.md" "dist\\QuickLauncher\\"' in script
    assert 'if not defined QL_UPX_EXE set "QL_UPX_EXE=0"' in script
    assert 'if not defined QL_KEEP_DIRECT2D set "QL_KEEP_DIRECT2D=1"' in script


def test_installer_preserves_user_plugins_on_upgrade():
    installer = (ROOT / "scripts" / "installer.iss").read_text(encoding="utf-8")

    assert "(FindRec.Name <> 'plugins')" in installer
