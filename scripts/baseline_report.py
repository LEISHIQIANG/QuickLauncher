"""Generate a comprehensive baseline report for the 1.7.0 UI plan.

Runs all the audit scripts and collects the per-script summary into a
single JSON / Markdown report under ``docs/quality/``.

Usage
-----

::

    python scripts/baseline_report.py --out docs/quality/audit_baseline.md
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "docs" / "quality" / "audit_baseline.md"

AUDIT_SCRIPTS = [
    ("audit_hardcoded_colors.py", "Hard-coded QColor (theme colours)"),
    ("audit_grid_violations.py", "Non-4-multiple sp() values"),
    ("audit_paint_snap.py", "paintEvent without snap/cosmetic"),
    ("audit_qss_radius.py", "border:none missing border-radius:0"),
    ("audit_motion_consistency.py", "QTimer.singleShot animation chains"),
    ("audit_font_consistency.py", "Inline font-size:Npx"),
    ("audit_graphics_effect.py", "QGraphicsEffect usage"),
    ("audit_paint_perf.py", "paintEvent performance anti-patterns"),
    ("audit_animation_lifecycle.py", "QPropertyAnimation lifecycle"),
    ("audit_timer_leak.py", "QTimer.singleShot animation leaks"),
    ("audit_pixmap_no_dpi.py", "QPixmap without setDevicePixelRatio"),
]


def _run_audit(script: str) -> dict:
    cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / script), "--max=10000"]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(PROJECT_ROOT)
    )
    out = result.stdout + result.stderr
    summary = {"script": script, "exit": result.returncode}
    m = re.search(r"Files flagged:\s+(\d+)\s*\|\s*total violations:\s+(\d+)", out)
    if m:
        summary["files_flagged"] = int(m.group(1))
        summary["total_violations"] = int(m.group(2))
    else:
        m2 = re.search(r"Total paintEvent:\s+(\d+)\s*\|\s*non-conformant:\s+(\d+)", out)
        if m2:
            summary["total_paintEvent"] = int(m2.group(1))
            summary["non_conformant"] = int(m2.group(2))
        else:
            m3 = re.search(r"Total anti-pattern hits:\s+(\d+)", out)
            if m3:
                summary["anti_pattern_hits"] = int(m3.group(1))
            else:
                summary["raw_excerpt"] = out[-500:]
    return summary


def _format_markdown(summaries: list[dict], now: str) -> str:
    lines = [
        "# QuickLauncher UI 优化基线报告",
        "",
        f"> 生成时间：{now}",
        "> 基线版本：1.6.3.6（目标 1.7.0）",
        "",
        "## 1. 总体概览",
        "",
        "| 脚本 | 检查项 | 状态 |",
        "|------|--------|------|",
    ]
    for s in summaries:
        script = s["script"]
        label = next((lbl for sname, lbl in AUDIT_SCRIPTS if sname == script), script)
        status = "✅" if s["exit"] == 0 else "❌"
        lines.append(f"| `{script}` | {label} | {status} |")
    lines.append("")
    lines.append("## 2. 详细计数")
    lines.append("")
    lines.append("| 脚本 | 违规数 | 文件数 |")
    lines.append("|------|------:|------:|")
    for s in summaries:
        v = s.get("total_violations") or s.get("non_conformant") or s.get("anti_pattern_hits") or "—"
        f = s.get("files_flagged") or s.get("total_paintEvent") or "—"
        lines.append(f"| `{s['script']}` | {v} | {f} |")
    lines.append("")
    lines.append("## 3. 行动计划")
    lines.append("")
    lines.append(
        "本报告对应 `UI_OPTIMIZATION_PLAN.md` S0 阶段产物，作为后续 S1-S8 Sprint "
        "执行的基线。Sprint 期间每次跑 `audit_*` 脚本对当前状态做差异，目标是："
    )
    lines.append("")
    lines.append("- `audit_hardcoded_colors.py` 由 120 → 0")
    lines.append("- `audit_grid_violations.py` 由 584 → 0（白名单除外）")
    lines.append("- `audit_paint_snap.py` 由 32 → 0")
    lines.append("- `audit_qss_radius.py` 由 120 → 0")
    lines.append("- `audit_graphics_effect.py` Opacity 17 → 0；Drop-shadow 2 → 2（参数 token 化）")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", type=Path, default=None, help="Optional path to also write the raw JSON report")
    args = parser.parse_args(argv)

    summaries = [_run_audit(s) for s, _ in AUDIT_SCRIPTS]
    now = datetime.now().isoformat(timespec="seconds")
    md = _format_markdown(summaries, now)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    print(f"Wrote {args.out}")

    if args.json:
        args.json.write_text(
            json.dumps({"generated_at": now, "summaries": summaries}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
