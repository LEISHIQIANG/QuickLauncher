"""Repack all .qlzip plugin files with trust metadata and code fixes.

Adds "trust_level": "builtin" and "install_source": "builtin" to plugin.json
in all .qlzip files. Also updates screenshot_ocr and qr_code_scanner main.py.
"""

import json
import shutil
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = PROJECT_ROOT / ".plugins"
EXTRACTED_PLUGINS = PROJECT_ROOT / "plugins"


def fix_manifest(data: dict) -> dict:
    """Add trust_level and install_source if missing."""
    modified = False
    if "trust_level" not in data:
        data["trust_level"] = "builtin"
        modified = True
    if "install_source" not in data:
        data["install_source"] = "builtin"
        modified = True
    return modified


def read_fixed_main_py(plugin_id: str) -> str | None:
    """Read the fixed main.py from the extracted plugins directory."""
    path = EXTRACTED_PLUGINS / plugin_id / "main.py"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return None


def repack_qlzip(qlzip_path: Path) -> bool:
    """Repack a single .qlzip with fixes."""
    plugin_id = qlzip_path.stem  # e.g. "screenshot_ocr"
    fixed_main = read_fixed_main_py(plugin_id)

    # Read the original ZIP
    with zipfile.ZipFile(str(qlzip_path), "r") as zf:
        entries = {}
        for info in zf.infolist():
            entries[info.filename] = zf.read(info.filename)

    modified = False

    # Fix plugin.json
    plugin_json_names = [n for n in entries if n.endswith("plugin.json") or n == "plugin.json"]
    for name in plugin_json_names:
        data = json.loads(entries[name].decode("utf-8"))
        if fix_manifest(data):
            modified = True
            print(f"  [+] {name}: added trust_level/install_source")
            entries[name] = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")

    # Fix main.py for screenshot_ocr and qr_code_scanner
    if fixed_main is not None:
        main_py_names = [n for n in entries if n.endswith("main.py") or n == "main.py"]
        for name in main_py_names:
            old_content = entries[name].decode("utf-8")
            if "from core.command_registry" in old_content or "import subprocess" in old_content:
                modified = True
                print(f"  [+] {name}: updated to latest version")
                entries[name] = fixed_main.encode("utf-8")

    if not modified:
        print("  [-] No changes needed")
        return False

    # Write new .qlzip
    backup_path = qlzip_path.with_suffix(".qlzip.bak")
    shutil.copy2(str(qlzip_path), str(backup_path))

    with zipfile.ZipFile(str(qlzip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)

    print(f"  [*] Repacked: {qlzip_path.name}")
    return True


def main():
    qlzip_files = sorted(PLUGINS_DIR.glob("*.qlzip"))
    print(f"Found {len(qlzip_files)} .qlzip files\n")

    fixed_count = 0
    for qlzip in qlzip_files:
        print(f"--- {qlzip.name} ---")
        if repack_qlzip(qlzip):
            fixed_count += 1

    print(f"\nFixed {fixed_count}/{len(qlzip_files)} .qlzip files")

    # Also fix extracted plugins/qr_code_scanner/plugin.json
    qr_json = EXTRACTED_PLUGINS / "qr_code_scanner" / "plugin.json"
    if qr_json.is_file():
        data = json.loads(qr_json.read_text(encoding="utf-8"))
        if fix_manifest(data):
            qr_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print("\nFixed extracted: plugins/qr_code_scanner/plugin.json")


if __name__ == "__main__":
    main()
