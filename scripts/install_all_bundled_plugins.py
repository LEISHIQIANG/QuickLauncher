"""Install all bundled .qlzip plugins from .plugins/ into plugins/."""

import json
import shutil
import sys
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
QLZIP_DIR = PROJECT / ".plugins"
PLUGINS_DIR = PROJECT / "plugins"
BACKUP_DIR = PLUGINS_DIR / ".backup"

SKIP_IDS = {"screenshot_ocr", "qr_code_scanner"}  # already extracted

errors = []
installed = []

for qlzip_path in sorted(QLZIP_DIR.glob("*.qlzip")):
    pid = qlzip_path.stem
    if pid in SKIP_IDS:
        continue

    target = PLUGINS_DIR / pid
    print(f"Installing {pid}...", end=" ")

    try:
        with zipfile.ZipFile(qlzip_path) as zf:
            names = zf.namelist()
            # Find manifest to get plugin id
            manifest_name = None
            archive_root = None
            for n in names:
                if n == "plugin.json":
                    manifest_name = "plugin.json"
                    break
                if n.endswith("/plugin.json") and len(n.split("/")) == 2:
                    manifest_name = n
                    archive_root = n.split("/", 1)[0]
                    break

            if not manifest_name:
                errors.append(f"{pid}: no plugin.json found")
                print("FAIL (no manifest)")
                continue

            manifest = json.loads(zf.read(manifest_name))
            actual_id = manifest.get("id", "")
            if actual_id != pid:
                errors.append(f"{pid}: id mismatch ({actual_id} != {pid})")
                print("FAIL (id mismatch)")
                continue

            # Backup existing
            if target.exists():
                backup = BACKUP_DIR / pid
                if backup.exists():
                    shutil.rmtree(backup)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(target, backup)
                shutil.rmtree(target)

            # Extract
            if archive_root:
                # Sub-folder format: extract files inside archive_root/ to target/
                prefix = archive_root + "/"
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    name = member.filename
                    if not name.startswith(prefix):
                        continue
                    rel = name[len(prefix) :]
                    dest = target / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
            else:
                # Flat format: extract plugin.json + all files directly
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    name = member.filename
                    dest = target / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            # Verify
            if not (target / "plugin.json").is_file():
                errors.append(f"{pid}: plugin.json missing after extract")
                print("FAIL (no plugin.json)")
                continue

            # Verify trust_level in extracted plugin.json
            with open(target / "plugin.json") as f:
                data = json.load(f)
            tl = data.get("trust_level", "missing")
            ins = data.get("install_source", "missing")
            if tl != "builtin" or ins != "builtin":
                errors.append(f"{pid}: extracted trust_level={tl} install_source={ins}")
                print(f"FAIL (trust={tl})")
                continue

            installed.append(pid)
            print("OK")

    except Exception as e:
        errors.append(f"{pid}: {e}")
        print(f"FAIL: {e}")

print()
print(f"Installed: {len(installed)}")
for p in installed:
    print(f"  + {p}")
if errors:
    print(f"\nErrors ({len(errors)}):")
    for e in errors:
        print(f"  ! {e}")
    sys.exit(1)
else:
    print("\nAll good!")
