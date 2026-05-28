"""Maintenance built-in command handlers."""

from __future__ import annotations

from .command_registry import CommandAction, CommandContext, CommandResult


def cmd_clean_cache(context: CommandContext) -> CommandResult:
    from core import data_manager
    from core.project_cache_cleaner import clean_unused_project_cache

    dry_run = (context.args_text or "").strip().lower() in {"dry-run", "dryrun", "preview", "预览"}
    stats = clean_unused_project_cache(data_manager, dry_run=dry_run)
    removed = int(stats.get("total_removed", 0) or 0)
    freed = float(stats.get("total_size_freed_mb", 0) or 0)
    failed = int(stats.get("failed", 0) or 0)

    lines = ["缓存清理预览:" if dry_run else "缓存清理完成:"]
    lines.append(f"- 可清理/已清理: {removed} 个文件")
    lines.append(f"- 可释放/已释放: {freed:.2f} MB")
    if failed:
        lines.append(f"- 失败: {failed} 项")

    labels = {
        "temp_icons": "临时图标",
        "__pycache__": "Python 字节码",
        ".pytest_cache": "pytest 缓存",
        ".ruff_cache": "ruff 缓存",
        "restore_temp": "恢复临时目录",
        "empty_dirs": "空缓存目录",
    }
    for area, area_stats in sorted((stats.get("by_area") or {}).items()):
        count = int(area_stats.get("files_removed", 0) or 0)
        size = float(area_stats.get("size_freed_mb", 0) or 0)
        if count:
            lines.append(f"- {labels.get(area, area)}: {count} 项，{size:.2f} MB")

    return CommandResult(
        success=failed == 0,
        message="\n".join(lines),
        payload=stats,
        actions=[CommandAction(type="copy", label="复制报告", value="\n".join(lines))],
        error="" if failed == 0 else "部分缓存清理失败",
    )


def cmd_config_repair(context: CommandContext) -> CommandResult:
    from core import data_manager
    from core.config_repairs import apply_config_repairs, scan_config_repairs

    if data_manager is None:
        return CommandResult(success=False, message="数据管理器不可用", error="不可用")

    mode = (context.args_text or "").strip().lower()
    should_fix = mode in {"fix", "apply", "repair", "save", "修复", "应用"}
    report = apply_config_repairs(data_manager.data) if should_fix else scan_config_repairs(data_manager.data)

    if should_fix and report.changed:
        try:
            data_manager._mark_history("配置修复", f"应用 {report.repaired} 项配置修复")
        except Exception:
            pass
        if not data_manager.save(immediate=True):
            return CommandResult(
                success=False, message="配置修复已计算，但保存失败", payload=report.to_dict(), error="保存失败"
            )

    action = "已修复" if should_fix else "扫描完成"
    lines = [f"配置修复{action}: {report.repaired} 项可自动修复项"]
    if report.problem_count:
        lines.append(f"需要人工确认: {report.problem_count} 项")
    if not report.issues:
        lines.append("未发现需要修复的配置。")
    else:
        for issue in report.issues[:20]:
            status = "fixed" if issue.fixed else "warn"
            lines.append(f"- [{status}] {issue.path}: {issue.message}")
        if len(report.issues) > 20:
            lines.append(f"- ... 另有 {len(report.issues) - 20} 项")

    message = "\n".join(lines)
    return CommandResult(
        success=report.problem_count == 0 or not should_fix,
        message=message,
        display_type="list",
        payload=report.to_dict(),
        actions=[CommandAction(type="copy", label="复制报告", value=message)],
        error="" if report.problem_count == 0 else "存在未自动修复的问题",
    )
