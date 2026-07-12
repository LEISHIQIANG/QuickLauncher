#!/usr/bin/env python3
"""Audit broad exception handlers and summarize the cleanup surface."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

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
    }
)

LOG_METHODS = frozenset(
    {
        "critical",
        "debug",
        "error",
        "exception",
        "info",
        "log",
        "warn",
        "warning",
    }
)


@dataclass(frozen=True)
class BroadException:
    path: str
    line: int
    kind: str
    has_logging: bool
    reraises: bool
    returns: bool


def _is_broad_exception(node: ast.ExceptHandler) -> tuple[bool, str]:
    if node.type is None:
        return True, "bare"
    if isinstance(node.type, ast.Name) and node.type.id in {"BaseException", "Exception"}:
        return True, node.type.id
    if isinstance(node.type, ast.Tuple):
        names = [elt.id for elt in node.type.elts if isinstance(elt, ast.Name)]
        if "BaseException" in names:
            return True, "tuple:BaseException"
        if "Exception" in names:
            return True, "tuple:Exception"
    return False, ""


def _has_logging(node: ast.ExceptHandler) -> bool:
    return any(
        isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr in LOG_METHODS
        for statement in node.body
        for child in ast.walk(statement)
    )


def _has_reraise(node: ast.ExceptHandler) -> bool:
    return any(isinstance(child, ast.Raise) for statement in node.body for child in ast.walk(statement))


def _has_return(node: ast.ExceptHandler) -> bool:
    return any(isinstance(child, ast.Return) for statement in node.body for child in ast.walk(statement))


def _iter_python_files(root: Path, excluded_dirs: set[str]) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if excluded_dirs.intersection(path.relative_to(root).parts):
            continue
        yield path


def collect_broad_exceptions(root: Path, excluded_dirs: set[str]) -> list[BroadException]:
    findings: list[BroadException] = []
    for path in _iter_python_files(root, excluded_dirs):
        try:
            source = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            rel = path.relative_to(root).as_posix()
            findings.append(BroadException(rel, 0, f"parse-error:{type(exc).__name__}", False, False, False))
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            broad, kind = _is_broad_exception(node)
            if not broad:
                continue
            findings.append(
                BroadException(
                    path=path.relative_to(root).as_posix(),
                    line=node.lineno,
                    kind=kind,
                    has_logging=_has_logging(node),
                    reraises=_has_reraise(node),
                    returns=_has_return(node),
                )
            )
    return findings


def _print_summary(findings: list[BroadException], top: int) -> None:
    total = len(findings)
    with_logging = sum(item.has_logging for item in findings)
    reraises = sum(item.reraises for item in findings)
    returns = sum(item.returns for item in findings)
    unlogged = [item for item in findings if not item.has_logging and not item.reraises]

    print(f"broad exception handlers: {total}")
    print(f"with direct logging: {with_logging}")
    print(f"with re-raise: {reraises}")
    print(f"with return fallback: {returns}")
    print(f"without direct logging or re-raise: {len(unlogged)}")
    print()

    print("by top-level directory:")
    for name, count in Counter(item.path.split("/", 1)[0] for item in findings).most_common():
        print(f"  {name}: {count}")
    print()

    print(f"top {top} files:")
    for path, count in Counter(item.path for item in findings).most_common(top):
        print(f"  {count:>4}  {path}")
    print()

    print(f"top {top} unlogged/no-reraise locations:")
    for item in unlogged[:top]:
        print(f"  {item.path}:{item.line} ({item.kind})")


def _count_unlogged(findings: list[BroadException]) -> int:
    return sum(not item.has_logging and not item.reraises for item in findings)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root to scan.")
    parser.add_argument("--top", type=int, default=20, help="Number of top files and samples to print.")
    parser.add_argument("--json", action="store_true", help="Emit JSON findings instead of a text summary.")
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Additional directory name to exclude. Can be passed multiple times.",
    )
    parser.add_argument(
        "--fail-on-unlogged",
        action="store_true",
        help="Return non-zero when broad handlers lack direct logging or re-raise.",
    )
    parser.add_argument("--max-total", type=int, help="Fail when total broad handlers exceed this baseline.")
    parser.add_argument(
        "--max-unlogged",
        type=int,
        help="Fail when unlogged/no-reraise broad handlers exceed this baseline.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
    excluded_dirs.update(args.exclude_dir)

    findings = collect_broad_exceptions(root, excluded_dirs)
    if args.json:
        print(json.dumps([asdict(item) for item in findings], ensure_ascii=False, indent=2))
    else:
        _print_summary(findings, args.top)

    failed = False
    if args.max_total is not None and len(findings) > args.max_total:
        print(
            f"broad exception count exceeded baseline: {len(findings)} > {args.max_total}",
            file=sys.stderr,
        )
        failed = True

    unlogged = _count_unlogged(findings)
    if args.max_unlogged is not None and unlogged > args.max_unlogged:
        print(
            f"unlogged/no-reraise broad exception count exceeded baseline: {unlogged} > {args.max_unlogged}",
            file=sys.stderr,
        )
        failed = True

    if args.fail_on_unlogged and unlogged:
        failed = True

    if failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
