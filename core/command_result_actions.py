"""Default action enrichment for command-panel results."""

from __future__ import annotations

import os
from dataclasses import replace

from core.command_action_safety import sanitize_command_actions
from core.command_io import CommandOutputArtifact, build_output_artifact
from core.command_registry import CommandAction, CommandResult


def enrich_result_actions(result: CommandResult, artifact: CommandOutputArtifact | None = None) -> CommandResult:
    """Append useful default actions while preserving command-provided actions."""

    artifact = artifact or build_output_artifact(result)
    actions = list(result.actions or [])
    default_actions: list[CommandAction] = []
    if artifact.text or artifact.output:
        default_actions.append(CommandAction(type="copy", label="复制全部", value=artifact.text or artifact.output))

    display_type = str(result.display_type or "text").lower()
    if display_type == "log":
        _copy(default_actions, "复制 stdout", artifact.stdout)
        _copy(default_actions, "复制 stderr", artifact.stderr)
        _copy(default_actions, "复制命令", artifact.command)
    if display_type == "table":
        _copy(default_actions, "复制 TSV", artifact.table_tsv)
        table_csv = artifact.outputs.get("table.csv", "")
        if table_csv or artifact.table_tsv:
            default_actions.append(
                CommandAction(type="save_csv", label="保存 CSV", value=table_csv or artifact.table_tsv)
            )
    if display_type == "json":
        _copy(default_actions, "复制 JSON", artifact.json_text or artifact.outputs.get("json", ""))
        _copy(default_actions, "复制压缩 JSON", artifact.outputs.get("json.compact", ""))
        if artifact.json_text or artifact.outputs.get("json"):
            default_actions.append(
                CommandAction(
                    type="save_json", label="保存 JSON", value=artifact.json_text or artifact.outputs.get("json", "")
                )
            )

    for path in artifact.files:
        default_actions.append(CommandAction(type="open_file", label="打开文件", value=path))
        parent = os.path.dirname(path)
        if parent:
            default_actions.append(CommandAction(type="open_folder", label="打开所在文件夹", value=parent))
        _copy(default_actions, "复制路径", path)
    for folder in artifact.folders:
        default_actions.append(CommandAction(type="open_folder", label="打开文件夹", value=folder))
        _copy(default_actions, "复制路径", folder)
    for url in artifact.urls:
        default_actions.append(CommandAction(type="open_url", label="打开链接", value=url))
        _copy(default_actions, "复制链接", url)

    return replace(result, actions=sanitize_command_actions(_dedupe(actions + default_actions)))


def _copy(actions: list[CommandAction], label: str, value: str) -> None:
    if value:
        actions.append(CommandAction(type="copy", label=label, value=str(value)))


def _dedupe(actions: list[CommandAction]) -> list[CommandAction]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[CommandAction] = []
    for action in actions:
        key = (str(action.type or ""), str(action.label or ""), str(action.value or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped
