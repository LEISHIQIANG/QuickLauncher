"""Audit i18n translation coverage and gate the release on missing keys.

QuickLauncher stores Chinese source strings in code and translates them at
runtime via :func:`core.i18n.tr`.  When the active language is ``en_US`` and
no English translation is registered for a key, :func:`tr` silently falls
back to the Chinese source — which is a translation defect.

This script:

1. Walks the production source tree (``core/`` + ``ui/`` + ``hooks/`` +
   ``services/`` + ``bootstrap/``) and collects every literal first argument
   to a ``tr(...)`` call.  Any literal that contains a non-ASCII character is
   treated as a Chinese source string (the project's convention; see
   :mod:`core.i18n`).
2. Loads :data:`core.i18n._EN_US` and reports which source strings are
   missing an English translation.
3. Returns non-zero when the missing-translation rate exceeds
   ``--max-untranslated-pct`` (default: 5%).

Run as a release-gate step:

    python scripts/check_i18n_coverage.py
    python scripts/check_i18n_coverage.py --max-untranslated-pct 50
    python scripts/check_i18n_coverage.py --json
    python scripts/check_i18n_coverage.py --include-tests
    python scripts/check_i18n_coverage.py --report-only  # never fails
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger(__name__)

# Force UTF-8 stdout/stderr on Windows to avoid GBK encoding errors when
# printing Chinese source strings. Without this, ``print()`` raises
# ``UnicodeEncodeError`` on the Windows release-gate runner.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError, ValueError) as exc:
        logger.debug("unable to reconfigure stdout/stderr to utf-8: %s", exc)

DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "temp_icons",
        ".claude",
        ".mimocode",
        ".reasonix",
        ".plugins",
        ".vscode",
    }
)

# Production source directories. Tests are excluded by default; opt-in via
# ``--include-tests``.
DEFAULT_INCLUDED_DIRS: tuple[str, ...] = (
    "core",
    "ui",
    "hooks",
    "hooks_dll",
    "services",
    "bootstrap",
    "modules",
    "plugins",
    "tools",
)


def _iter_python_files(
    root: Path,
    included: Iterable[str],
    excluded_dirs: set[str],
    include_tests: bool,
) -> Iterable[Path]:
    seen: set[Path] = set()
    for sub in included:
        base = root / sub
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if excluded_dirs.intersection(path.relative_to(root).parts):
                continue
            if not include_tests and "tests" in path.relative_to(root).parts:
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path


def _string_literal(node: ast.AST) -> str | None:
    """Return a concatenated string literal value, or ``None`` if not one."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        # f-strings are not pure literals, but we only care about literal
        # parts here; bail out.
        return None
    return None


def _is_chinese_source(text: str) -> bool:
    """A string counts as a Chinese source if it contains any CJK character."""
    for ch in text:
        code = ord(ch)
        # CJK Unified Ideographs (basic + ext A/B/C/D/E/F) and compatibility.
        if (
            0x3400 <= code <= 0x4DBF  # Extension A
            or 0x4E00 <= code <= 0x9FFF  # CJK Unified
            or 0x20000 <= code <= 0x2A6DF  # Extension B
            or 0x2A700 <= code <= 0x2B73F  # Extension C
            or 0x2B740 <= code <= 0x2B81F  # Extension D
            or 0x2B820 <= code <= 0x2CEAF  # Extension E
            or 0x2CEB0 <= code <= 0x2EBEF  # Extension F
            or 0xF900 <= code <= 0xFAFF  # Compatibility Ideographs
        ):
            return True
    return False


def collect_tr_sources(
    root: Path,
    included: Iterable[str],
    excluded_dirs: set[str],
    include_tests: bool,
) -> list[tuple[Path, int, str]]:
    """Collect every literal first argument to ``tr(...)`` calls."""
    sources: list[tuple[Path, int, str]] = []
    for path in _iter_python_files(root, included, excluded_dirs, include_tests):
        try:
            source = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "tr" and node.args:
                literal = _string_literal(node.args[0])
                if literal is not None:
                    sources.append((path, node.lineno, literal))
            elif isinstance(func, ast.Attribute) and func.attr == "tr" and node.args:
                # ``module.tr(...)`` style — accept the same literal rule.
                literal = _string_literal(node.args[0])
                if literal is not None:
                    sources.append((path, node.lineno, literal))
    return sources


def _extract_string_dict(value: ast.AST) -> dict[str, str]:
    """Extract string→string mappings from an AST Dict node."""
    if not isinstance(value, ast.Dict):
        return {}
    result: dict[str, str] = {}
    for k, v in zip(value.keys, value.values):
        if not isinstance(k, ast.Constant) or not isinstance(v, ast.Constant):
            continue
        if not isinstance(k.value, str) or not isinstance(v.value, str):
            continue
        result[k.value] = v.value
    return result


def load_translation_dict(repo_root: Path) -> dict[str, str]:
    """Return the ``_EN_US`` mapping from :mod:`core.i18n` without importing Qt.

    Handles both the main ``_EN_US = {...}`` dictionary and any
    ``_EN_US.update({...})`` calls that follow it.
    """
    i18n_path = repo_root / "core" / "i18n.py"
    try:
        source = i18n_path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(i18n_path))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        print(f"failed to parse {i18n_path}: {exc}", file=sys.stderr)
        return {}

    result: dict[str, str] = {}
    for node in tree.body:
        # Main assignment: _EN_US = {...} or _EN_US: dict = {...}
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "_EN_US":
            result.update(_extract_string_dict(node.value))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_EN_US":
                    result.update(_extract_string_dict(node.value))
                    break
        # _EN_US.update({...}) call
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "update"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "_EN_US"
                and call.args
            ):
                result.update(_extract_string_dict(call.args[0]))
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root to scan.")
    parser.add_argument(
        "--max-untranslated-pct",
        type=float,
        default=3.0,
        help=(
            "Maximum allowed percentage of Chinese tr() keys without an en_US "
            "translation. The default of 3% matches the 1.6.3.9 baseline "
            "(2.16% untranslated, 11 missing keys, mostly the dynamic "
            "``步骤 {n}: ...`` formatter strings)."
        ),
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include ``tests/`` in the scan. Off by default.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON report instead of a human summary.",
    )
    parser.add_argument(
        "--fail-on-untranslated",
        action="store_true",
        help="Always fail when any key is missing an en_US translation (overrides --max-untranslated-pct).",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Print a report and never return non-zero. Useful for first-run audits.",
    )
    return parser.parse_args()


def _print_summary(
    chinese_keys: list[tuple[Path, int, str]],
    translated: dict[str, str],
    missing: list[tuple[Path, int, str]],
    by_file: Counter,
) -> None:
    total = len(chinese_keys)
    unique = len({text for _, _, text in chinese_keys})
    unique_missing = len({text for _, _, text in missing})

    print(f"tr() calls with literal source: {total}")
    print(f"unique Chinese source keys: {unique}")
    print(f"unique en_US translations registered: {len(translated)}")
    print(f"unique missing en_US keys: {unique_missing}")
    if unique:
        pct = (unique_missing / unique) * 100.0
        print(f"missing percentage: {pct:.2f}%")
    print()
    if missing:
        print("top files with untranslated keys:")
        for path, count in by_file.most_common(10):
            print(f"  {count:>4}  {path}")
        print()
        print(f"top {min(20, len(missing))} untranslated keys:")
        for path, lineno, text in missing[:20]:
            preview = text if len(text) <= 60 else text[:57] + "..."
            print(f"  {path}:{lineno}  {preview}")


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
    sources = collect_tr_sources(
        root,
        DEFAULT_INCLUDED_DIRS,
        excluded_dirs,
        args.include_tests,
    )
    translated = load_translation_dict(root)

    chinese_keys = [(path, line, text) for path, line, text in sources if _is_chinese_source(text)]
    missing = [(path, line, text) for path, line, text in chinese_keys if text not in translated]
    by_file: Counter = Counter(str(path) for path, _, _ in missing)

    unique_total = len({text for _, _, text in chinese_keys})
    unique_missing = len({text for _, _, text in missing})
    pct = (unique_missing / unique_total * 100.0) if unique_total else 0.0

    if args.json:
        report = {
            "tr_calls_total": len(sources),
            "chinese_keys_unique": unique_total,
            "en_us_translations": len(translated),
            "missing_keys_unique": unique_missing,
            "missing_pct": round(pct, 2),
            "missing_samples": [{"path": str(p), "line": line, "text": text} for p, line, text in missing[:50]],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_summary(chinese_keys, translated, missing, by_file)

    if args.report_only:
        return 0

    if args.fail_on_untranslated and unique_missing:
        print(
            f"fail-on-untranslated: {unique_missing} Chinese key(s) without en_US translation",
            file=sys.stderr,
        )
        return 1

    if pct > args.max_untranslated_pct:
        print(
            f"missing percentage {pct:.2f}% exceeds {args.max_untranslated_pct:.2f}%",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
