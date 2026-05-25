"""Unified command registry and data models for command center 2.0."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

COMMAND_INTERACTION_DIRECT = "direct"
COMMAND_INTERACTION_PANEL = "panel"
MAX_COMMAND_RESULT_ACTIONS = 2


# ============================================================
# Data models
# ============================================================


@dataclass
class CommandParam:
    name: str
    type: str = "text"
    required: bool = False
    default: str = ""
    choices: list[str] = field(default_factory=list)
    sensitive: bool = False


@dataclass
class CommandAction:
    type: str = "copy"
    label: str = ""
    value: str = ""


@dataclass
class CommandContext:
    raw_input: str = ""
    args_text: str = ""
    args: dict[str, str] = field(default_factory=dict)
    clipboard_text: str = ""
    selected_files: list[str] = field(default_factory=list)
    update_callback: Callable[[CommandResult], None] | None = None


@dataclass
class CommandResult:
    success: bool = True
    message: str = ""
    display_type: str = "text"
    payload: dict[str, Any] = field(default_factory=dict)
    actions: list[CommandAction] = field(default_factory=list)
    error: str = ""
    is_async: bool = False
    progress: float = 0.0
    cancellable: bool = False


def limit_command_result_actions(result: CommandResult) -> CommandResult:
    """Keep the compact result panel from overflowing with action buttons."""
    if result.actions and len(result.actions) > MAX_COMMAND_RESULT_ACTIONS:
        result.actions = result.actions[:MAX_COMMAND_RESULT_ACTIONS]
    return result


@dataclass
class CommandDefinition:
    id: str
    title: str
    aliases: list[str]
    description: str
    category: str
    handler: Callable[[CommandContext], CommandResult]
    icon_path: str = ""
    permission_level: str = "user"
    params: list[CommandParam] = field(default_factory=list)
    source: str = "builtin"
    sensitive: bool = False
    interaction_mode: str = COMMAND_INTERACTION_PANEL
    search_terms: list[str] = field(default_factory=list)


# ============================================================
# Phase 2 result pipe — a thread-safe single-slot for passing
# CommandResult from _execute_builtin_command back to the popup.
# ============================================================

_pending_command_result: CommandResult | None = None

# Search sources registered by plugins via PluginAPI.register_search_source
_search_sources: dict[str, dict] = {}


def take_pending_command_result() -> CommandResult | None:
    global _pending_command_result
    val = _pending_command_result
    _pending_command_result = None
    return val


def set_pending_command_result(result: CommandResult) -> None:
    global _pending_command_result
    _pending_command_result = result


# ============================================================
# Old callback bridge — wraps a string callback name into a
# Callable[[CommandContext], CommandResult] so old-style
# callbacks (registered via register_callback / call_callback)
# can live inside CommandDefinition during the migration phase.
# ============================================================


class _CallbackHandler:
    def __init__(self, callback_name: str):
        self._callback_name = callback_name

    def __call__(self, context: CommandContext) -> CommandResult:
        from core import call_callback

        try:
            result = call_callback(self._callback_name)
            if result is False:
                return CommandResult(
                    success=False,
                    message=f"命令执行失败: {self._callback_name}",
                    error="回调返回 False",
                )
            return CommandResult(success=True, message="执行成功")
        except Exception as e:
            logger.error("回调执行异常 (%s): %s", self._callback_name, e)
            return CommandResult(
                success=False,
                message=f"执行异常: {e}",
                error=str(e),
            )


# ============================================================
# CommandRegistry
# ============================================================


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, CommandDefinition] = {}
        self._alias_map: dict[str, str] = {}
        self._category_index: dict[str, list[str]] = {}
        self._owner_index: dict[str, list[str]] = {}

    # ---- registration ----

    def register(self, cmd: CommandDefinition) -> bool:
        if cmd.id in self._commands:
            logger.warning("重复命令 ID，拒绝注册: %s", cmd.id)
            return False
        self._commands[cmd.id] = cmd
        self._category_index.setdefault(cmd.category, []).append(cmd.id)
        self._merge_aliases(cmd, cmd.aliases)
        if cmd.source and cmd.source.startswith("plugin:"):
            owner = cmd.source
            self._owner_index.setdefault(owner, []).append(cmd.id)
        logger.debug("命令已注册: %s (类别: %s, 来源: %s)", cmd.id, cmd.category, cmd.source)
        return True

    def _merge_aliases(self, cmd: CommandDefinition, aliases: list[str]) -> None:
        """Merge aliases into an existing command without overwriting other commands."""
        if cmd.aliases is None:
            cmd.aliases = []
        for alias in aliases or []:
            key = alias.lower().strip()
            if not key:
                continue
            if alias not in cmd.aliases:
                cmd.aliases.append(alias)
            if key not in self._alias_map:
                self._alias_map[key] = cmd.id

    # ---- lookup ----

    def get(self, command_id: str) -> CommandDefinition | None:
        return self._commands.get(command_id)

    def get_canonical(self, alias: str) -> str:
        return self._alias_map.get(alias.lower().strip(), "")

    def find(self, query: str) -> list[CommandDefinition]:
        if not query:
            return list(self._commands.values())
        q = query.lower().strip()

        exact: list[CommandDefinition] = []
        prefix: list[CommandDefinition] = []
        substr: list[CommandDefinition] = []

        for cmd in self._commands.values():
            searchable = self._searchable_terms(cmd)
            if any(term == q for term in searchable):
                exact.append(cmd)
            elif any(term.startswith(q) for term in searchable):
                prefix.append(cmd)
            elif any(q in term for term in searchable):
                substr.append(cmd)

        seen: set[str] = set()
        out: list[CommandDefinition] = []
        for cmd in exact + prefix + substr:
            if cmd.id not in seen:
                seen.add(cmd.id)
                out.append(cmd)
        return out

    @staticmethod
    def _searchable_terms(cmd: CommandDefinition) -> list[str]:
        raw_terms = [
            cmd.id,
            cmd.id.replace(".", " "),
            cmd.id.replace("_", " "),
            cmd.title,
            cmd.description,
            cmd.category,
            cmd.source,
            cmd.source.replace("plugin:", ""),
            cmd.source.replace("plugin:", "").replace("_", " "),
            *list(cmd.aliases or []),
            *list(cmd.search_terms or []),
        ]

        terms: list[str] = []
        seen: set[str] = set()
        for term in raw_terms:
            text = str(term or "").lower().strip()
            if not text:
                continue
            variants = {
                text,
                text.replace("_", " "),
                text.replace("-", " "),
                text.replace(".", " "),
            }
            for variant in variants:
                compact = " ".join(variant.split())
                if compact and compact not in seen:
                    seen.add(compact)
                    terms.append(compact)
        return terms

    # ---- enumeration ----

    def list(self) -> list[CommandDefinition]:
        return list(self._commands.values())

    def list_by_category(self) -> dict[str, list[CommandDefinition]]:
        result: dict[str, list[CommandDefinition]] = {}
        for cat, ids in self._category_index.items():
            result[cat] = [self._commands[cid] for cid in ids if cid in self._commands]
        return result

    def count(self) -> int:
        return len(self._commands)

    # ---- removal ----

    def remove(self, command_id: str) -> bool:
        cmd = self._commands.pop(command_id, None)
        if cmd is None:
            return False
        cat_list = self._category_index.get(cmd.category, [])
        if command_id in cat_list:
            cat_list.remove(command_id)
        for alias in cmd.aliases or []:
            key = alias.lower().strip()
            if self._alias_map.get(key) == command_id:
                del self._alias_map[key]
        # Clean up owner_index
        for owner, cmd_ids in list(self._owner_index.items()):
            if command_id in cmd_ids:
                cmd_ids.remove(command_id)
                if not cmd_ids:
                    del self._owner_index[owner]
                break
        return True

    def remove_by_owner(self, owner_id: str) -> int:
        """Remove all commands registered by a given owner (e.g. 'plugin:text_tools')."""
        removed = 0
        cmd_ids = list(self._owner_index.get(owner_id, []))
        for cid in cmd_ids:
            if self.remove(cid):
                removed += 1
        self._owner_index.pop(owner_id, None)
        return removed

    def list_by_owner(self, owner_id: str) -> list[CommandDefinition]:
        """List all commands registered by a given owner."""
        return [self._commands[cid] for cid in self._owner_index.get(owner_id, []) if cid in self._commands]

    # ---- migration helpers (Phase 1) ----

    def migrate_slash_commands(self) -> int:
        from core.slash_commands import SLASH_COMMANDS

        count = 0
        for old in SLASH_COMMANDS:
            existing = self._commands.get(old.canonical)
            if existing is not None:
                self._merge_aliases(existing, old.aliases)
                if not existing.icon_path and old.icon_path:
                    existing.icon_path = old.icon_path
                if not existing.description and old.description:
                    existing.description = old.description
                continue

            handler = _CallbackHandler(old.handler)
            cmd = CommandDefinition(
                id=old.canonical,
                title=old.display_name or old.canonical,
                aliases=old.aliases,
                description=old.description,
                category=old.category,
                handler=handler,
                icon_path=old.icon_path,
                source="builtin",
                interaction_mode=getattr(old, "interaction_mode", COMMAND_INTERACTION_DIRECT),
            )
            if self.register(cmd):
                count += 1
        if count:
            logger.info("已从 SLASH_COMMANDS 迁移 %d 条命令", count)
        return count

    def migrate_builtin_aliases(self) -> int:
        from core.builtin_commands import BUILTIN_COMMAND_ALIASES

        # Collect callback names already covered by SLASH_COMMANDS migration
        # so we don't create duplicate entries (e.g. both id="services"
        # and id="open_services" pointing to the same callback).
        covered_callbacks: set[str] = set()
        for cmd in self._commands.values():
            if isinstance(cmd.handler, _CallbackHandler):
                covered_callbacks.add(cmd.handler._callback_name)

        count = 0
        for alias, canonical in BUILTIN_COMMAND_ALIASES.items():
            if canonical not in self._commands and canonical not in covered_callbacks:
                handler = _CallbackHandler(canonical)
                cmd = CommandDefinition(
                    id=canonical,
                    title=canonical.replace("_", " ").title(),
                    aliases=[alias, canonical],
                    description="",
                    category="system",
                    handler=handler,
                    source="builtin",
                    interaction_mode=COMMAND_INTERACTION_DIRECT,
                )
                if self.register(cmd):
                    count += 1
        if count:
            logger.info("已从 BUILTIN_COMMAND_ALIASES 迁移 %d 个额外命令", count)
        return count
