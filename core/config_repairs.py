"""Configuration repair helpers.

Repairs operate on AppData objects after deserialization so model loading stays
side-effect free. The first repair pass migrates whitelisted legacy variable
syntax and reports unsupported double-brace variables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .command_variables import (
    find_unknown_variable_specs,
    migrate_legacy_variable_syntax,
)
from .data_models import AppData, ShortcutItem, ShortcutType


@dataclass
class RepairIssue:
    code: str
    path: str
    message: str
    before: str = ""
    after: str = ""
    fixed: bool = False

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "before": self.before,
            "after": self.after,
            "fixed": self.fixed,
        }


@dataclass
class RepairReport:
    issues: list[RepairIssue] = field(default_factory=list)
    repaired: int = 0

    @property
    def changed(self) -> bool:
        return self.repaired > 0

    @property
    def problem_count(self) -> int:
        return len([issue for issue in self.issues if not issue.fixed])

    def add(self, issue: RepairIssue) -> None:
        self.issues.append(issue)
        if issue.fixed:
            self.repaired += 1

    def extend(self, other: "RepairReport") -> None:
        self.issues.extend(other.issues)
        self.repaired += other.repaired

    def to_dict(self) -> dict:
        return {
            "changed": self.changed,
            "repaired": self.repaired,
            "problem_count": self.problem_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def scan_config_repairs(data: AppData | dict[str, Any]) -> RepairReport:
    return _repair_config(data, apply=False)


def apply_config_repairs(data: AppData | dict[str, Any]) -> RepairReport:
    return _repair_config(data, apply=True)


def _repair_config(data: AppData | dict[str, Any], *, apply: bool) -> RepairReport:
    if isinstance(data, AppData):
        return _repair_app_data(data, apply=apply)
    if isinstance(data, dict):
        return _repair_app_data(AppData.from_dict(data), apply=False)
    return RepairReport([RepairIssue("invalid_config", "$", "Unsupported config object")])


def _repair_app_data(data: AppData, *, apply: bool) -> RepairReport:
    report = RepairReport()
    for folder_index, folder in enumerate(getattr(data, "folders", []) or []):
        for item_index, item in enumerate(getattr(folder, "items", []) or []):
            prefix = f"folders[{folder_index}].items[{item_index}]"
            report.extend(_repair_shortcut(item, prefix, apply=apply))
    return report


def _repair_shortcut(item: ShortcutItem, prefix: str, *, apply: bool) -> RepairReport:
    report = RepairReport()

    executable_fields: list[tuple[str, bool]] = []
    item_type = getattr(item, "type", None)
    if item_type == ShortcutType.COMMAND:
        executable_fields.append(("command", False))
    elif item_type == ShortcutType.URL:
        executable_fields.append(("url", False))
        executable_fields.append(("preferred_browser_args", True))
    elif item_type == ShortcutType.FILE:
        executable_fields.append(("target_args", False))

    for field_name, include_url in executable_fields:
        value = getattr(item, field_name, "")
        if not isinstance(value, str) or not value:
            continue
        path = f"{prefix}.{field_name}"
        migrated = migrate_legacy_variable_syntax(value, include_url=include_url)
        if migrated != value:
            report.add(
                RepairIssue(
                    code="legacy_variable_syntax",
                    path=path,
                    message="Migrated legacy single-brace variable syntax",
                    before=value,
                    after=migrated,
                    fixed=apply,
                )
            )
            if apply:
                setattr(item, field_name, migrated)
                value = migrated

        for spec in find_unknown_variable_specs(value, include_url=include_url):
            report.add(
                RepairIssue(
                    code="unknown_variable",
                    path=path,
                    message="Unknown variable: {{" + spec + "}}",
                    before=value,
                    fixed=False,
                )
            )

    return report
