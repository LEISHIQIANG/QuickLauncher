"""Durable plugin lifecycle state and bounded diagnostic log storage."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import (
    PLUGIN_ERROR_LOG_BACKUPS,
    PLUGIN_ERROR_LOG_MAX_BYTES,
    PLUGIN_STATE_SCHEMA,
)

logger = logging.getLogger(__name__)


class PluginStateStore:
    def __init__(self, config_dir: Path) -> None:
        self.config_dir = Path(config_dir)
        self.state_file = self.config_dir / "plugin_state.json"
        self.error_log_file = self.config_dir / "plugin_errors.jsonl"
        self._state = self._load()

    def _empty(self) -> dict[str, Any]:
        return {"schema": PLUGIN_STATE_SCHEMA, "plugins": {}}

    def _load(self) -> dict[str, Any]:
        try:
            if not self.state_file.exists():
                return self._empty()
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return self._empty()
            plugins = data.get("plugins", {})
            return {"schema": PLUGIN_STATE_SCHEMA, "plugins": plugins if isinstance(plugins, dict) else {}}
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("plugin state is unreadable; using empty state: %s", exc)
            return self._empty()

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.state_file)

    def apply(self, info: Any) -> Any:
        plugins = self._state.get("plugins", {})
        if info.manifest.id not in plugins:
            return info
        state = plugins.get(info.manifest.id, {})
        if not isinstance(state, dict):
            return info
        info.failure_count = int(state.get("failure_count") or 0)
        info.last_error_stage = str(state.get("last_error_stage") or "")
        info.disabled_reason = str(state.get("disabled_reason") or "")
        info.last_error_at = float(state.get("last_error_at") or 0)
        if state.get("status") == "quarantined":
            info.status = "quarantined"
            info.quarantined = True
            info.error = info.disabled_reason or "plugin quarantined"
        return info

    def persist(self, info: Any) -> None:
        plugins = self._state.setdefault("plugins", {})
        plugins[info.manifest.id] = {
            "status": "quarantined" if info.quarantined else info.status,
            "failure_count": info.failure_count,
            "last_error_stage": info.last_error_stage,
            "last_error_at": info.last_error_at,
            "disabled_reason": info.disabled_reason,
        }
        self.save()

    def append_error(
        self,
        plugin_id: str,
        stage: str,
        operation_id: str,
        error: BaseException,
        trace: str,
        action: str,
    ) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._rotate_error_log()
        payload = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "plugin_id": plugin_id,
            "stage": stage,
            "operation_id": operation_id,
            "error": str(error),
            "trace": trace,
            "action": action,
        }
        with self.error_log_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

    def _rotate_error_log(self) -> None:
        if not self.error_log_file.exists() or self.error_log_file.stat().st_size < PLUGIN_ERROR_LOG_MAX_BYTES:
            return
        for index in range(PLUGIN_ERROR_LOG_BACKUPS - 1, 0, -1):
            source = self.error_log_file.with_name(f"{self.error_log_file.name}.{index}")
            target = self.error_log_file.with_name(f"{self.error_log_file.name}.{index + 1}")
            if source.exists():
                target.unlink(missing_ok=True)
                source.replace(target)
        first = self.error_log_file.with_name(f"{self.error_log_file.name}.1")
        first.unlink(missing_ok=True)
        self.error_log_file.replace(first)
