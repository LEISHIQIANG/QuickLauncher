import hashlib

from scripts.generate_build_info import build_info


def test_build_info_contains_contracts_toolchain_and_binary_hash(tmp_path):
    binary = tmp_path / "QuickLauncher.exe"
    binary.write_bytes(b"runtime")

    info = build_info(binary)

    assert info["schema_version"] == 1
    assert info["contracts"]["config_schema"] == 1
    assert info["contracts"]["plugin_sdk"] == "1.0"
    assert info["toolchain"]["python"]
    assert info["dependency_lock_sha256"]
    assert info["binary_sha256"]["QuickLauncher.exe"] == hashlib.sha256(b"runtime").hexdigest()
