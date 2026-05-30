"""Persistent configuration history snapshots."""

from __future__ import annotations

import gzip
import json
import logging
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ConfigSnapshot:
    """Metadata for one persisted configuration snapshot."""

    id: str
    timestamp: float
    action: str
    summary: str
    version: str
    path: str
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "action": self.action,
            "summary": self.summary,
            "version": self.version,
            "path": self.path,
            "size_bytes": self.size_bytes,
        }


class ConfigHistoryManager:
    """Stores recent AppData snapshots as compressed JSON files."""

    def __init__(self, history_dir: Path | str, max_snapshots: int = 20):
        self.history_dir = Path(history_dir)
        val = 20 if max_snapshots is None else max_snapshots
        self.max_snapshots = int(max(1, val))

    def record_snapshot(self, data_dict: dict, action: str = "change", summary: str = "") -> ConfigSnapshot | None:
        """Persist a compressed snapshot and prune old entries."""
        if not isinstance(data_dict, dict) or not data_dict:
            return None

        try:
            self.history_dir.mkdir(parents=True, exist_ok=True)
            snapshot_id = uuid.uuid4().hex
            timestamp = time.time()
            filename_time = datetime.fromtimestamp(timestamp).strftime("%Y%m%d_%H%M%S_%f")
            path = self.history_dir / f"{filename_time}_{snapshot_id}.json.gz"
            metadata = {
                "id": snapshot_id,
                "timestamp": timestamp,
                "action": action or "change",
                "summary": summary or "",
                "version": str(data_dict.get("version", "")),
            }
            payload = {"metadata": metadata, "data": data_dict}
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            with gzip.open(path, "wb") as f:
                f.write(raw)

            snapshot = ConfigSnapshot(path=str(path), size_bytes=path.stat().st_size, **metadata)
            self.prune()
            return snapshot
        except Exception as exc:
            logger.debug("record config history snapshot failed: %s", exc, exc_info=True)
            return None

    def list_snapshots(self) -> list[ConfigSnapshot]:
        """Return newest snapshots first."""
        snapshots: list[ConfigSnapshot] = []
        for path in self._snapshot_paths():
            try:
                payload = self._read_payload(path)
                meta = payload.get("metadata", {}) if isinstance(payload, dict) else {}
                snapshots.append(
                    ConfigSnapshot(
                        id=str(meta.get("id") or path.stem),
                        timestamp=float(meta.get("timestamp") or path.stat().st_mtime),
                        action=str(meta.get("action") or "change"),
                        summary=str(meta.get("summary") or ""),
                        version=str(meta.get("version") or ""),
                        path=str(path),
                        size_bytes=path.stat().st_size,
                    )
                )
            except Exception as exc:
                logger.debug("read config history metadata failed %s: %s", path, exc)
        snapshots.sort(key=lambda s: s.timestamp, reverse=True)
        return snapshots

    def load_snapshot_data(self, snapshot_id: str) -> dict:
        """Load AppData dict for a snapshot id or path."""
        target = self._find_snapshot_path(snapshot_id)
        if target is None:
            raise FileNotFoundError(snapshot_id)
        payload = self._read_payload(target)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ValueError("snapshot data is invalid")
        return data

    def prune(self):
        """Keep only the newest configured number of snapshots."""
        paths = list(self._snapshot_paths())
        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in paths[self.max_snapshots :]:
            try:
                old.unlink()
            except Exception as exc:
                logger.debug("delete old config history snapshot failed %s: %s", old, exc)

    def _snapshot_paths(self) -> Iterable[Path]:
        if not self.history_dir.exists():
            return []
        return self.history_dir.glob("*.json.gz")

    def _find_snapshot_path(self, snapshot_id: str) -> Path | None:
        raw = str(snapshot_id or "").strip()
        if not raw:
            return None
        direct = Path(raw)
        if direct.exists():
            history_root = self.history_dir.resolve(strict=False)
            resolved_direct = direct.resolve(strict=False)
            if resolved_direct.name.endswith(".json.gz") and (
                resolved_direct == history_root or history_root in resolved_direct.parents
            ):
                return resolved_direct
            return None
        for path in self._snapshot_paths():
            try:
                payload = self._read_payload(path)
                meta = payload.get("metadata", {}) if isinstance(payload, dict) else {}
                if meta.get("id") == raw:
                    return path
            except Exception:
                continue
        return None

    @staticmethod
    def _read_payload(path: Path) -> dict:
        with gzip.open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
