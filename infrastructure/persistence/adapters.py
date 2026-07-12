"""Infrastructure adapters implementing persistence ports.

These adapters bridge the existing core/config_services.py implementations
to the port interfaces defined in application/ports/persistence.py.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from application.ports.persistence import (  # noqa: F401 — port contracts, structural match
    BackupStore,
    ConfigRepository,
    HistoryStore,
)

if TYPE_CHECKING:
    from core.config_history import ConfigHistoryManager
    from core.config_services import (
        ConfigBackupService,
        ConfigDataStore,
    )

__all__ = [
    "ConfigRepositoryAdapter",
    "BackupStoreAdapter",
    "HistoryStoreAdapter",
]


class ConfigRepositoryAdapter:
    """Adapter wrapping ConfigDataStore to implement ConfigRepository."""

    def __init__(self, store: ConfigDataStore) -> None:
        self._store = store

    def load(self) -> Mapping[str, Any]:
        try:
            text = self._store.data_file.read_text(encoding="utf-8")
            return cast(Mapping[str, Any], json.loads(text))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save(self, data: Mapping[str, Any], *, expected_revision: int) -> int:
        # In the current architecture, revision tracking is handled by
        # SaveCoordinator; this adapter focuses on the I/O boundary.
        import tempfile

        serialized = self._store.serialize_data(dict(data))
        fd, tmp = tempfile.mkstemp(suffix=".json", prefix=".data_", dir=self._store.data_file.parent)
        try:
            with open(fd, "w", encoding="utf-8", closefd=True) as f:
                f.write(serialized)
            self._store.replace_data_file(Path(tmp))
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise
        return expected_revision + 1


class BackupStoreAdapter:
    """Adapter wrapping ConfigBackupService to implement BackupStore."""

    def __init__(self, backup_service: ConfigBackupService, data_file: Path | str) -> None:
        self._backup = backup_service
        self._data_file = Path(data_file)

    def create(self, data: Mapping[str, Any], *, reason: str) -> str:
        # Write data to the data file first, then trigger auto-backup.
        serialized = json.dumps(dict(data), ensure_ascii=False)
        self._data_file.write_text(serialized, encoding="utf-8")
        result = self._backup.create_auto_backup(self._data_file)
        return str(result) if result else ""

    def restore(self, backup_id: str) -> Mapping[str, Any]:
        backup_path = Path(backup_id)
        if not backup_path.is_file():
            raise FileNotFoundError(f"backup not found: {backup_id}")
        return cast(Mapping[str, Any], json.loads(backup_path.read_text(encoding="utf-8")))


class HistoryStoreAdapter:
    """Adapter wrapping ConfigHistoryManager to implement HistoryStore."""

    def __init__(self, history_manager: ConfigHistoryManager) -> None:
        self._history = history_manager

    def append(self, revision: int, data: Mapping[str, Any], *, action: str, summary: str) -> None:
        self._history.record_snapshot(dict(data), action=action or "change", summary=summary or "")
