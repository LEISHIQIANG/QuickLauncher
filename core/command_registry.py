"""Unified command registry and data models for command center 2.0."""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .command_metadata import CommandMetadata
from .command_metadata import builtin_command_metadata as _builtin_command_metadata

logger = logging.getLogger(__name__)

COMMAND_INTERACTION_DIRECT = "direct"
COMMAND_INTERACTION_PANEL = "panel"
MAX_COMMAND_RESULT_ACTIONS = 2
MAX_SEARCH_SOURCE_RESULTS = 50
SEARCH_SOURCE_RESULT_KEYS = {"id", "title", "name", "command", "folder", "icon_path"}
SEARCH_SOURCE_TIMEOUT_SECONDS = 1.0
SEARCH_SOURCE_TOTAL_TIMEOUT_SECONDS = 1.5


def builtin_command_metadata(command_id: str, category: str = "") -> CommandMetadata:
    """Compatibility facade for older imports from command_registry."""
    return _builtin_command_metadata(command_id, category)


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
    label: str = ""
    placeholder: str = ""
    help: str = ""
    multiline: bool = False
    remember: bool = True
    source: str = ""
    validator: str = ""
    pattern: str = ""
    min_value: str = ""
    max_value: str = ""
    advanced: bool = False


@dataclass
class CommandAction:
    type: str = "copy"
    label: str = ""
    value: str = ""
    enabled: bool = True
    danger: bool = False
    primary: bool = False
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandContext:
    raw_input: str = ""
    args_text: str = ""
    args: dict[str, str] = field(default_factory=dict)
    clipboard_text: str = ""
    clipboard_kind: str = ""
    clipboard_files: list[str] = field(default_factory=list)
    clipboard_html: str = ""
    selected_text: str = ""
    selected_text_method: str = ""
    selected_files: list[str] = field(default_factory=list)
    context_meta: dict = field(default_factory=dict)
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
    """Compatibility hook retained for old callers.

    Compact legacy surfaces decide how many actions to render; the model keeps
    the full action list for the independent command panel.
    """
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
    result_window_size: str = ""
    metadata: CommandMetadata | dict = field(default_factory=CommandMetadata)

    def __post_init__(self):
        self.metadata = CommandMetadata.from_value(self.metadata, category=self.category)
        if self.permission_level and self.permission_level != "user":
            self.metadata.requires_admin = True
        if self.metadata.requires_confirmation and self.metadata.risk_level == "low":
            self.metadata.risk_level = "high"


# ============================================================
# Phase 2 result pipe — a thread-safe single-slot for passing
# CommandResult from _execute_builtin_command back to the popup.
# ============================================================

_pending_command_result: CommandResult | None = None
_pending_command_result_lock = threading.Lock()

# Search sources registered by plugins via PluginAPI.register_search_source
_search_sources: dict[str, dict] = {}
_search_sources_lock = threading.RLock()


def register_search_source(source_id: str, source_info: dict) -> bool:
    """Register a plugin search source without overwriting another owner."""
    with _search_sources_lock:
        if source_id in _search_sources:
            return False
        _search_sources[source_id] = dict(source_info)
        return True


def remove_search_source(source_id: str, plugin_id: str | None = None) -> bool:
    """Remove a search source, optionally only when it still belongs to plugin_id."""
    with _search_sources_lock:
        current = _search_sources.get(source_id)
        if current is None:
            return False
        if plugin_id is not None and current.get("plugin_id") != plugin_id:
            return False
        _search_sources.pop(source_id, None)
        return True


def snapshot_search_sources() -> list[tuple[str, dict]]:
    """Return a stable copy for callers that iterate while plugins may change."""
    with _search_sources_lock:
        return [(source_id, dict(source_info)) for source_id, source_info in _search_sources.items()]


def execute_search_source(source_id: str, query: str) -> list[dict]:
    """Execute one plugin search source with validation, timeout, and failure reporting."""
    with _search_sources_lock:
        source_info = dict(_search_sources.get(source_id) or {})
    handler = source_info.get("handler")
    if handler is None:
        return []
    plugin_id = str(source_info.get("plugin_id") or "")
    pool = None
    try:
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(handler, query)
        try:
            raw_results = future.result(timeout=SEARCH_SOURCE_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            logger.warning("plugin search source timed out: %s", source_id)
            callback = source_info.get("error_callback")
            if callable(callback):
                callback(plugin_id, "search", source_id, TimeoutError("search source timed out"), "")
            return []
        if not isinstance(raw_results, list):
            return []
        results = []
        for item in raw_results[:MAX_SEARCH_SOURCE_RESULTS]:
            if not isinstance(item, dict):
                continue
            results.append({key: value for key, value in item.items() if key in SEARCH_SOURCE_RESULT_KEYS})
        return results
    except Exception as exc:
        callback = source_info.get("error_callback")
        if callable(callback):
            callback(plugin_id, "search", source_id, exc, traceback.format_exc())
        logger.exception("plugin search source failed: %s", source_id)
        return []
    finally:
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)


def execute_search_sources(
    query: str, timeout: float = SEARCH_SOURCE_TOTAL_TIMEOUT_SECONDS
) -> list[tuple[str, dict, list[dict]]]:
    """Execute plugin search sources concurrently within a bounded total timeout."""
    sources = snapshot_search_sources()
    if not sources:
        return []
    results: list[tuple[str, dict, list[dict]]] = []
    max_workers = max(1, min(len(sources), 8))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(execute_search_source, source_id, query): (source_id, source_info)
            for source_id, source_info in sources
        }
        done, pending = concurrent.futures.wait(future_map, timeout=max(0.01, float(timeout or 0)))
        for future in done:
            source_id, source_info = future_map[future]
            try:
                source_results = future.result()
            except Exception:
                logger.exception("plugin search source future failed: %s", source_id)
                source_results = []
            if source_results:
                results.append((source_id, source_info, source_results))
        for future in pending:
            source_id, source_info = future_map[future]
            plugin_id = str(source_info.get("plugin_id") or "")
            logger.warning("plugin search source skipped by total timeout: %s", source_id)
            callback = source_info.get("error_callback")
            if callable(callback):
                callback(plugin_id, "search", source_id, TimeoutError("search sources total timeout"), "")
            future.cancel()
    return results


def take_pending_command_result() -> CommandResult | None:
    global _pending_command_result
    with _pending_command_result_lock:
        val = _pending_command_result
        _pending_command_result = None
        return val


def set_pending_command_result(result: CommandResult) -> None:
    global _pending_command_result
    with _pending_command_result_lock:
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
            if not result:
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
