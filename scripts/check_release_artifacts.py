"""Validate QuickLauncher release metadata and built artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_PLUGIN_PACKAGE_IDS = (
    "api_tester",
    "disk_cleaner",
    "event_inspector",
    "file_tools",
    "network_tools",
    "process_tools",
    "screenshot_ocr",
    "startup_tools",
    "text_tools",
)


@dataclass
class ReleaseCheckResult:
    ok: bool
    errors: list[str]
    manifest: dict


def _default_version(root: Path) -> str:
    import ast

    tree = ast.parse((root / "core" / "version.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "APP_VERSION":
                    return str(ast.literal_eval(node.value))
    return "0.0.0.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_file(errors: list[str], path: Path, *, min_bytes: int = 1) -> None:
    if not path.is_file():
        errors.append(f"missing file: {path}")
        return
    size = path.stat().st_size
    if size < min_bytes:
        errors.append(f"file too small: {path} ({size} bytes, expected >= {min_bytes})")


def _require_dir(errors: list[str], path: Path) -> None:
    if not path.is_dir():
        errors.append(f"missing directory: {path}")


def check_source_metadata(root: Path = ROOT, version: str | None = None) -> ReleaseCheckResult:
    root = Path(root)
    version = version or _default_version(root)
    errors: list[str] = []
    manifest: dict = {"version": version, "source": {}, "artifacts": {}}

    installer = (root / "scripts" / "installer.iss").read_text(encoding="utf-8")
    for define_name in ("MyAppVersion", "MyAppFileVersion"):
        expected = f'#define {define_name} "{version}"'
        if expected not in installer:
            errors.append(f"installer.iss missing {expected}")
    if 'OutputBaseFilename "QuickLauncher_Setup_" + MyAppVersion' not in installer:
        errors.append("installer.iss output filename must include MyAppVersion")

    manifest_path = root / "QuickLauncher.manifest"
    _require_file(errors, manifest_path)
    if manifest_path.is_file():
        xml_root = ET.fromstring(manifest_path.read_text(encoding="utf-8"))
        identity = xml_root.find("{urn:schemas-microsoft-com:asm.v1}assemblyIdentity")
        actual = identity.attrib.get("version", "") if identity is not None else ""
        if actual != version:
            errors.append(f"QuickLauncher.manifest version {actual!r} != {version!r}")

    required_source_files = [
        root / "assets" / "app.ico",
        root / "hooks" / "hooks.dll",
        root / "QuickLauncher.manifest",
        root / "plugins" / "PLUGIN_DEV.md",
        root / "scripts" / "installer.iss",
        root / "scripts" / "build_win11_setup.bat",
    ]
    for path in required_source_files:
        _require_file(errors, path)

    plugins_dir = root / "plugins"
    _require_dir(errors, plugins_dir)
    if plugins_dir.is_dir():
        plugin_dirs = [p for p in plugins_dir.iterdir() if p.is_dir()]
        for plugin_dir in plugin_dirs:
            if (plugin_dir / "plugin.json").is_file():
                errors.append(f"source plugins directory must not bundle runtime plugin: {plugin_dir}")

    plugin_package_dir = root / ".plugins"
    _require_dir(errors, plugin_package_dir)
    if plugin_package_dir.is_dir():
        for plugin_id in OFFICIAL_PLUGIN_PACKAGE_IDS:
            _require_file(errors, plugin_package_dir / f"{plugin_id}.qlzip")

    return ReleaseCheckResult(ok=not errors, errors=errors, manifest=manifest)


_FORBIDDEN_PATTERNS = (
    "__pycache__",
    ".pyc",
)

_UPLOAD_ARTIFACT_PATTERNS = (
    ".upload-config",
    ".credentials",
)


def _scan_debris(dist_dir: Path) -> list[str]:
    """Return human-readable descriptions of forbidden files found under *dist_dir*."""
    debris: list[str] = []
    if not dist_dir.is_dir():
        return debris
    for path in dist_dir.rglob("*"):
        name = path.name
        if name in _FORBIDDEN_PATTERNS:
            debris.append(f"forbidden directory: {path.relative_to(dist_dir)}")
        elif any(name.endswith(ext) for ext in (".pyc",)):
            debris.append(f"forbidden bytecode: {path.relative_to(dist_dir)}")
        elif any(name.startswith(prefix) for prefix in _UPLOAD_ARTIFACT_PATTERNS):
            debris.append(f"forbidden upload artifact: {path.relative_to(dist_dir)}")
    return debris


def check_release_artifacts(
    root: Path = ROOT,
    *,
    dist_dir: Path | None = None,
    installer: Path | None = None,
    version: str | None = None,
    min_exe_bytes: int = 1024 * 1024,
) -> ReleaseCheckResult:
    root = Path(root)
    version = version or _default_version(root)
    source_result = check_source_metadata(root, version)
    errors = list(source_result.errors)
    release_manifest = source_result.manifest

    dist_dir = Path(dist_dir or root / "dist" / "QuickLauncher")
    installer = Path(installer or root / "dist" / f"QuickLauncher_Setup_{version}.exe")

    # Scan for forbidden debris (pycache, bytecode, temp uploads)
    debris = _scan_debris(dist_dir)
    errors.extend(debris)
    release_manifest["debris_found"] = len(debris)

    required_artifacts = [
        (dist_dir / "QuickLauncher.exe", min_exe_bytes),
        (dist_dir / "hooks" / "hooks.dll", 1),
        (dist_dir / "assets" / "app.ico", 1),
        (dist_dir / "plugins", 0),
        (installer, min_exe_bytes),
    ]
    for path, min_bytes in required_artifacts:
        if min_bytes == 0:
            _require_dir(errors, path)
        else:
            _require_file(errors, path, min_bytes=min_bytes)

    expected_name = f"QuickLauncher_Setup_{version}.exe"
    if installer.name != expected_name:
        errors.append(f"installer filename {installer.name!r} must be {expected_name!r}")

    if (dist_dir / "plugins").is_dir():
        for plugin_json in sorted((dist_dir / "plugins").glob("*/plugin.json")):
            errors.append(f"release must not contain bundled plugin source: {plugin_json.parent}")

    for key, path in {
        "exe": dist_dir / "QuickLauncher.exe",
        "hooks_dll": dist_dir / "hooks" / "hooks.dll",
        "installer": installer,
    }.items():
        if path.is_file():
            release_manifest["artifacts"][key] = {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }

    return ReleaseCheckResult(ok=not errors, errors=errors, manifest=release_manifest)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--version", default=None)
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--dist-dir", type=Path, default=None)
    parser.add_argument("--installer", type=Path, default=None)
    parser.add_argument("--min-exe-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--write-manifest", type=Path, default=None)
    parser.add_argument("--write-installer-sha256", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    result = (
        check_source_metadata(args.root, args.version)
        if args.source_only
        else check_release_artifacts(
            args.root,
            dist_dir=args.dist_dir,
            installer=args.installer,
            version=args.version,
            min_exe_bytes=args.min_exe_bytes,
        )
    )
    if args.write_manifest:
        args.write_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.write_manifest.write_text(json.dumps(result.manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    installer_info = result.manifest.get("artifacts", {}).get("installer", {})
    if args.write_installer_sha256 and installer_info.get("sha256"):
        args.write_installer_sha256.parent.mkdir(parents=True, exist_ok=True)
        args.write_installer_sha256.write_text(
            f"{installer_info['sha256']}  {Path(installer_info['path']).name}\n",
            encoding="utf-8",
        )
    if result.ok:
        print("release artifact check passed")
        return 0
    for error in result.errors:
        print(f"release artifact check failed: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
