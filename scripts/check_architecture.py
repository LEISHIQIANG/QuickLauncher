"""Enforce QuickLauncher package boundaries and architecture debt budgets.

The baseline is deliberately an itemized debt ledger, not a count-only waiver.
Existing entries may be removed during migration; new entries always fail.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "docs" / "quality" / "architecture_baseline.json"
PRODUCTION_ROOTS = (
    "application",
    "bootstrap",
    "core",
    "domain",
    "extensions",
    "hooks",
    "infrastructure",
    "modules",
    "platform",
    "services",
    "ui",
)

FORBIDDEN_PREFIXES: dict[str, tuple[str, ...]] = {
    "domain": (
        "PyQt5",
        "bootstrap",
        "infrastructure",
        "platform",
        "requests",
        "subprocess",
        "ui",
        "urllib",
        "win32",
    ),
    "application": ("PyQt5", "bootstrap", "infrastructure", "platform", "ui", "win32"),
    "services": ("ui",),
    "modules": ("ui",),
}

SENSITIVE_CALLS = {
    "os.startfile": "process",
    "subprocess.call": "process",
    "subprocess.check_call": "process",
    "subprocess.check_output": "process",
    "subprocess.Popen": "process",
    "subprocess.run": "process",
    "requests.delete": "network",
    "requests.get": "network",
    "requests.patch": "network",
    "requests.post": "network",
    "requests.put": "network",
    "urllib.request.urlopen": "network",
}

# These modules own the corresponding native capability.  Calls elsewhere are
# reported as migration debt and must eventually enter one of these adapters.
SENSITIVE_ADAPTERS: dict[str, str] = {
    "infrastructure.process.runtime": "process capability owner",
    "infrastructure.shell_opener_adapter": "shell open / relaunch owner",
}

DYNAMIC_IMPORT_ADAPTERS = frozenset(
    {
        "bootstrap.deps",
        "core",  # __getattr__ is the lazy-export adapter for the package
        "core.module_registry",
        "core.plugin.runtime",
        "ui.config_window",
        "ui.tray_app",  # deferred heavy-module loading for memory-guard callback
        "ui.tray_mixins.popup_mixin",  # TrayApp mixin: deferred import to break cycle
        "ui.tray_mixins.shutdown_mixin",  # TrayApp mixin: deferred import to break cycle
    }
)

SERVICE_CONSTRUCTORS = frozenset({"DataManager", "PluginManager"})

IMPORT_TIME_CONSTRUCTORS = {
    "CommandRegistry",
    "ExecutorManager",
    "ModuleRegistry",
    "PluginManager",
    "QApplication",
    "QTimer",
    "Thread",
    "ThreadPoolExecutor",
}


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    path: Path
    tree: ast.Module


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _production_modules() -> dict[str, ModuleInfo]:
    modules: dict[str, ModuleInfo] = {}
    for package in PRODUCTION_ROOTS:
        root = ROOT / package
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            except (OSError, SyntaxError) as exc:
                raise RuntimeError(f"cannot parse {path.relative_to(ROOT)}: {exc}") from exc
            name = _module_name(path)
            modules[name] = ModuleInfo(name=name, path=path, tree=tree)
    main_path = ROOT / "main.py"
    if main_path.is_file():
        modules["main"] = ModuleInfo(
            name="main",
            path=main_path,
            tree=ast.parse(main_path.read_text(encoding="utf-8-sig"), filename=str(main_path)),
        )
    return modules


def _resolve_from(module: str, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    package = module.split(".")
    if module != "main" and not (ROOT / Path(*package)).is_dir():
        package = package[:-1]
    trim = max(node.level - 1, 0)
    if trim:
        package = package[:-trim]
    if node.module:
        package.extend(node.module.split("."))
    return ".".join(package)


def _imports(info: ModuleInfo) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(info.tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from(info.name, node)
            if base:
                result.add(base)
                for alias in node.names:
                    if alias.name != "*":
                        result.add(f"{base}.{alias.name}")
    return result


def _internal_target(name: str, modules: dict[str, ModuleInfo]) -> str | None:
    candidate = name
    while candidate:
        if candidate in modules:
            return candidate
        candidate = candidate.rpartition(".")[0]
    return None


def _strongly_connected(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indexes[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(graph[node]):
            if target not in indexes:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[target])
        if lowlinks[node] != indexes[node]:
            return
        component: list[str] = []
        while stack:
            item = stack.pop()
            on_stack.remove(item)
            component.append(item)
            if item == node:
                break
        if len(component) > 1 or node in graph[node]:
            components.append(sorted(component))

    for node in sorted(graph):
        if node not in indexes:
            visit(node)
    return sorted(components)


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _location(info: ModuleInfo, node: ast.AST, detail: str) -> str:
    return f"{info.path.relative_to(ROOT).as_posix()}:{getattr(node, 'lineno', 1)}:{detail}"


def _top_level_calls(info: ModuleInfo) -> list[str]:
    findings: list[str] = []
    for node in info.tree.body:
        value: ast.AST | None = None
        if isinstance(node, ast.Expr):
            value = node.value
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            value = node.value
        if not isinstance(value, ast.Call):
            continue
        name = _dotted_name(value.func)
        leaf = name.rpartition(".")[2]
        if leaf in IMPORT_TIME_CONSTRUCTORS:
            findings.append(_location(info, value, name))
    return findings


def _sensitive_calls(info: ModuleInfo) -> list[str]:
    if info.name in SENSITIVE_ADAPTERS:
        return []
    aliases: dict[str, str] = {}
    for node in info.tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    findings: list[str] = []
    for node in ast.walk(info.tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_name(node.func)
        head, dot, tail = name.partition(".")
        resolved = f"{aliases.get(head, head)}{dot}{tail}" if head else name
        if resolved in SENSITIVE_CALLS:
            findings.append(_location(info, node, f"{SENSITIVE_CALLS[resolved]}:{resolved}"))
    return findings


def _dynamic_imports(info: ModuleInfo) -> list[str]:
    if info.name in DYNAMIC_IMPORT_ADAPTERS:
        return []
    findings: list[str] = []
    for node in ast.walk(info.tree):
        if isinstance(node, ast.Call) and _dotted_name(node.func) in {"__import__", "importlib.import_module"}:
            findings.append(_location(info, node, _dotted_name(node.func)))
    return findings


def _service_locators(info: ModuleInfo) -> list[str]:
    # core is exempt: its ensure_plugin_manager_initialized() is a bootstrap
    # helper that must construct PluginManager before the composition root
    # finishes wiring (see rationale in core/__init__.py docstring).
    if info.name in {"bootstrap.composition_root", "bootstrap.gui_application", "bootstrap.plugin_factory", "core"}:
        return []
    findings: list[str] = []
    for node in ast.walk(info.tree):
        if isinstance(node, ast.Call):
            leaf = _dotted_name(node.func).rpartition(".")[2]
            if leaf in SERVICE_CONSTRUCTORS:
                findings.append(_location(info, node, leaf))
    return findings


def scan() -> dict[str, list[Any]]:
    modules = _production_modules()
    imports_by_module = {name: _imports(info) for name, info in modules.items()}
    graph: dict[str, set[str]] = {name: set() for name in modules}
    boundary_violations: list[str] = []
    plugin_internal_imports: list[str] = []
    import_time_side_effects: list[str] = []
    sensitive_calls: list[str] = []
    dynamic_imports: list[str] = []
    service_locators: list[str] = []

    for name, info in modules.items():
        source_root = name.split(".", 1)[0]
        for imported in sorted(imports_by_module[name]):
            target = _internal_target(imported, modules)
            if target and target != name:
                graph[name].add(target)
            for forbidden in FORBIDDEN_PREFIXES.get(source_root, ()):
                if imported == forbidden or imported.startswith(f"{forbidden}."):
                    boundary_violations.append(f"{info.path.relative_to(ROOT).as_posix()}:{source_root}->{imported}")
        import_time_side_effects.extend(_top_level_calls(info))
        sensitive_calls.extend(_sensitive_calls(info))
        dynamic_imports.extend(_dynamic_imports(info))
        service_locators.extend(_service_locators(info))

    plugin_root = ROOT / "plugins"
    if plugin_root.is_dir():
        for path in sorted(plugin_root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            info = ModuleInfo(_module_name(path), path, tree)
            for imported in sorted(_imports(info)):
                if imported in {"core", "ui"} or imported.startswith(("core.", "ui.")):
                    plugin_internal_imports.append(f"{path.relative_to(ROOT).as_posix()}->{imported}")

    cycles = ["|".join(component) for component in _strongly_connected(graph)]
    return {
        "boundary_violations": sorted(set(boundary_violations)),
        "cycles": cycles,
        "import_time_side_effects": sorted(set(import_time_side_effects)),
        "plugin_internal_imports": sorted(set(plugin_internal_imports)),
        "sensitive_calls": sorted(set(sensitive_calls)),
        "dynamic_imports": sorted(set(dynamic_imports)),
        "service_locators": sorted(set(service_locators)),
    }


def _load_baseline(path: Path) -> dict[str, list[Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {key: list(value) for key, value in raw["debt"].items()}


def _write_baseline(path: Path, findings: dict[str, list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "policy": "Itemized migration debt. New entries fail; remove entries as debt is fixed; final debt must be empty.",
        "debt": findings,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument(
        "--require-clean", action="store_true", help="Require every architecture debt list to be empty."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    findings = scan()
    if args.write_baseline:
        _write_baseline(args.baseline, findings)
        print(f"architecture baseline written: {args.baseline}")
        return 0
    if not args.baseline.is_file():
        print(f"architecture baseline missing: {args.baseline}", file=sys.stderr)
        return 2
    baseline = _load_baseline(args.baseline)
    failed = False
    for category, current_items in findings.items():
        current = set(current_items)
        allowed = set(baseline.get(category, []))
        new_items = sorted(current - allowed)
        stale_items = sorted(allowed - current)
        print(f"{category}: {len(current)} current / {len(allowed)} baseline")
        if new_items:
            failed = True
            print(f"  new {category}:", file=sys.stderr)
            for item in new_items:
                print(f"    {item}", file=sys.stderr)
        if stale_items:
            failed = True
            print("  fixed entries still present in baseline; remove them:", file=sys.stderr)
            for item in stale_items:
                print(f"    {item}", file=sys.stderr)
        if args.require_clean and current:
            failed = True
    if failed:
        return 1
    print("architecture gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
