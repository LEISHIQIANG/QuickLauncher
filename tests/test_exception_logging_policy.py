import ast
from pathlib import Path

SKIP_PARTS = {"build", "dist", ".git", ".pytest_cache", ".venv", "venv", "__pycache__", "tests"}


def test_no_exception_pass_handlers_in_production_code():
    offenders = []
    for path in _production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body = [stmt for stmt in node.body if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Constant)]
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                offenders.append(f"{path}:{body[0].lineno}")

    assert offenders == []


def _production_python_files():
    for path in Path(".").rglob("*.py"):
        if set(path.parts) & SKIP_PARTS:
            continue
        yield path
