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
    "qr_code_scanner",
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


def _version_metadata(root: Path) -> tuple[str, str]:
    import ast

    version = "0.0.0.0"
    status = ""
    tree = ast.parse((root / "core" / "version.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        targets = []
        value = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        if value is None:
            continue
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "APP_VERSION":
                version = str(ast.literal_eval(value))
            elif target.id == "RELEASE_STATUS":
                status = str(ast.literal_eval(value))
    return version, status


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


def check_source_metadata(
    root: Path = ROOT,
    version: str | None = None,
    *,
    allow_source_runtime_plugins: bool = False,
) -> ReleaseCheckResult:
    root = Path(root)
    metadata_version, release_status = _version_metadata(root)
    version = version or metadata_version
    errors: list[str] = []
    manifest: dict = {"version": version, "release_status": release_status, "source": {}, "artifacts": {}}
    if release_status not in {"unreleased", "rc", "stable"}:
        errors.append(f"core/version.py RELEASE_STATUS is invalid: {release_status!r}")

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
        root / "modules" / "action_chain" / "module.json",
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
        ignored_runtime_plugins: list[str] = []
        plugin_dirs = [p for p in plugins_dir.iterdir() if p.is_dir()]
        for plugin_dir in plugin_dirs:
            if (plugin_dir / "plugin.json").is_file():
                if allow_source_runtime_plugins:
                    ignored_runtime_plugins.append(plugin_dir.name)
                else:
                    errors.append(f"source plugins directory must not bundle runtime plugin: {plugin_dir}")
        if ignored_runtime_plugins:
            manifest["source"]["runtime_plugin_dirs_ignored"] = sorted(ignored_runtime_plugins)

    plugin_package_dir = root / ".plugins"
    _require_dir(errors, plugin_package_dir)
    if plugin_package_dir.is_dir():
        for plugin_id in OFFICIAL_PLUGIN_PACKAGE_IDS:
            _require_file(errors, plugin_package_dir / f"{plugin_id}.qlzip")
        actual_packages = {path.stem for path in plugin_package_dir.glob("*.qlzip")}
        expected_packages = set(OFFICIAL_PLUGIN_PACKAGE_IDS)
        extra_packages = sorted(actual_packages - expected_packages)
        missing_packages = sorted(expected_packages - actual_packages)
        if extra_packages:
            errors.append(f"unexpected official plugin packages: {', '.join(extra_packages)}")
        if missing_packages:
            errors.append(f"missing official plugin packages: {', '.join(missing_packages)}")

    changelog_path = root / "CHANGELOG.md"
    if changelog_path.is_file():
        changelog = changelog_path.read_text(encoding="utf-8")
        if release_status == "stable" and f"## [{version}] - Unreleased" in changelog:
            errors.append(f"CHANGELOG.md marks stable version {version} as Unreleased")

    dist_root = root / "dist"
    version_artifacts = [
        dist_root / f"QuickLauncher_Setup_{version}.exe",
        dist_root / f"QuickLauncher_Portable_{version}.zip",
        dist_root / f"QuickLauncher_release_{version}.json",
    ]
    if release_status == "unreleased" and any(path.exists() for path in version_artifacts):
        errors.append(f"dist contains artifacts for unreleased version {version}")

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
    portable_zip: Path | None = None,
    version: str | None = None,
    min_exe_bytes: int = 1024 * 1024,
    run_smoke: bool = False,
    smoke_timeout: float = 30.0,
    smoke_exe: Path | None = None,
    smoke_args: list[str] | None = None,
    allow_source_runtime_plugins: bool = False,
) -> ReleaseCheckResult:
    root = Path(root)
    version = version or _default_version(root)
    source_result = check_source_metadata(
        root,
        version,
        allow_source_runtime_plugins=allow_source_runtime_plugins,
    )
    errors = list(source_result.errors)
    release_manifest = source_result.manifest

    dist_dir = Path(dist_dir or root / "dist" / "QuickLauncher")
    installer = Path(installer or root / "dist" / f"QuickLauncher_Setup_{version}.exe")
    portable_zip = Path(portable_zip) if portable_zip is not None else None

    # Scan for forbidden debris (pycache, bytecode, temp uploads)
    debris = _scan_debris(dist_dir)
    errors.extend(debris)
    release_manifest["debris_found"] = len(debris)

    required_artifacts = [
        (dist_dir / "QuickLauncher.exe", min_exe_bytes),
        (dist_dir / "hooks" / "hooks.dll", 1),
        (dist_dir / "modules" / "action_chain" / "module.json", 1),
        (dist_dir / "assets" / "app.ico", 1),
        (dist_dir / "plugins", 0),
        (installer, min_exe_bytes),
    ]
    if portable_zip is not None:
        required_artifacts.append((portable_zip, min_exe_bytes))
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

    unused_runtime_components = [
        dist_dir / "PIL" / "_avif.pyd",
        dist_dir / "PIL" / "_imagingtk.pyd",
    ]
    for path in unused_runtime_components:
        if path.exists():
            errors.append(f"unused runtime component must be removed: {path.relative_to(dist_dir)}")

    artifact_paths = {
        "exe": dist_dir / "QuickLauncher.exe",
        "hooks_dll": dist_dir / "hooks" / "hooks.dll",
        "installer": installer,
    }
    if portable_zip is not None:
        artifact_paths["portable_zip"] = portable_zip
    for key, path in artifact_paths.items():
        if path.is_file():
            release_manifest["artifacts"][key] = {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }

    if run_smoke and not errors:
        try:
            from scripts.post_package_smoke import run_packaged_smoke
        except ModuleNotFoundError:
            from post_package_smoke import run_packaged_smoke

        smoke_result = run_packaged_smoke(
            dist_dir,
            exe=smoke_exe,
            timeout=smoke_timeout,
            smoke_args=smoke_args,
        )
        release_manifest["post_package_smoke"] = smoke_result.to_manifest()
        if not smoke_result.ok:
            errors.extend(f"post-package smoke: {error}" for error in smoke_result.errors)
    elif run_smoke:
        release_manifest["post_package_smoke"] = {"ok": False, "skipped": "artifact validation failed"}

    return ReleaseCheckResult(ok=not errors, errors=errors, manifest=release_manifest)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--version", default=None)
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--dist-dir", type=Path, default=None)
    parser.add_argument("--installer", type=Path, default=None)
    parser.add_argument("--portable-zip", type=Path, default=None)
    parser.add_argument("--min-exe-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--run-smoke", action="store_true")
    parser.add_argument("--smoke-timeout", type=float, default=30.0)
    parser.add_argument(
        "--allow-source-runtime-plugins",
        action="store_true",
        help="Ignore local runtime plugin directories under source plugins/ while validating packaged artifacts.",
    )
    parser.add_argument("--write-manifest", type=Path, default=None)
    parser.add_argument("--write-installer-sha256", type=Path, default=None)
    parser.add_argument("--write-portable-sha256", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    result = (
        check_source_metadata(
            args.root,
            args.version,
            allow_source_runtime_plugins=args.allow_source_runtime_plugins,
        )
        if args.source_only
        else check_release_artifacts(
            args.root,
            dist_dir=args.dist_dir,
            installer=args.installer,
            portable_zip=args.portable_zip,
            version=args.version,
            min_exe_bytes=args.min_exe_bytes,
            run_smoke=args.run_smoke,
            smoke_timeout=args.smoke_timeout,
            allow_source_runtime_plugins=args.allow_source_runtime_plugins,
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
    portable_info = result.manifest.get("artifacts", {}).get("portable_zip", {})
    if args.write_portable_sha256 and portable_info.get("sha256"):
        args.write_portable_sha256.parent.mkdir(parents=True, exist_ok=True)
        args.write_portable_sha256.write_text(
            f"{portable_info['sha256']}  {Path(portable_info['path']).name}\n",
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
