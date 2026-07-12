from pathlib import Path

MOJIBAKE_MARKERS = (
    "\u935b\u6212\u62a4",
    "\u6fb6\u8fab\u89e6",
    "\u95bf\u6b12",
    "\u93c8\ue046\u7161",
    "\u9365\u6a40\u567a",
    "\u9365\u70ac\u7223",
    "\u7490\ue21a\u7dde",
    "\u7039\u592c\u53e1",
    "\u6768\u64b3\u58ca",
    "\u93bc\u6ec5\u50a8",
    "\u93c3\u72b3\u6665",
    "\u7ef1\u8bf2\u7037",
)


def test_python_sources_do_not_contain_common_mojibake_markers():
    root = Path(__file__).resolve().parents[1]
    excluded_parts = {".git", ".pytest_cache", ".ruff_cache", "dist", "__pycache__"}
    offenders = []

    for path in root.rglob("*.py"):
        if excluded_parts.intersection(path.relative_to(root).parts):
            continue
        text = path.read_text(encoding="utf-8")
        found = [marker for marker in MOJIBAKE_MARKERS if marker in text]
        if found:
            offenders.append(f"{path.relative_to(root)}: {', '.join(found)}")

    assert offenders == []
