"""Configuration recovery reports and damaged config quarantine helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

RECOVERY_STATE_FILE = "recovery_state.json"
MAX_QUARANTINED_FILES = 10
MAX_QUARANTINED_BYTES = 10 * 1024 * 1024


@dataclass
class ConfigRecoveryReport:
    status: str = "ok"
    reason: str = ""
    source_path: str = ""
    recovered_from: str = ""
    quarantined_path: str = ""
    issues: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: object) -> ConfigRecoveryReport:
        if not isinstance(data, dict):
            return cls(status="unknown", reason="invalid recovery report")
        return cls(
            status=str(data.get("status") or "unknown"),
            reason=str(data.get("reason") or ""),
            source_path=str(data.get("source_path") or ""),
            recovered_from=str(data.get("recovered_from") or ""),
            quarantined_path=str(data.get("quarantined_path") or ""),
            issues=(
                [str(item) for item in data.get("issues", []) if item is not None]
                if isinstance(data.get("issues", []), list)
                else []
            ),
            created_at=str(data.get("created_at") or datetime.now().isoformat(timespec="seconds")),
        )


def recovery_state_path(recovery_dir: Path | str) -> Path:
    return Path(recovery_dir) / RECOVERY_STATE_FILE


def write_recovery_report(recovery_dir: Path | str, report: ConfigRecoveryReport) -> bool:
    try:
        recovery_root = Path(recovery_dir)
        recovery_root.mkdir(parents=True, exist_ok=True)
        recovery_state_path(recovery_root).write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception as exc:
        logger.debug("write config recovery report failed: %s", exc)
        return False


def read_recovery_report(recovery_dir: Path | str) -> ConfigRecoveryReport | None:
    try:
        path = recovery_state_path(recovery_dir)
        if not path.exists():
            return None
        return ConfigRecoveryReport.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        logger.debug("read config recovery report failed: %s", exc)
        return None


def quarantine_bad_config(data_file: Path | str, recovery_dir: Path | str) -> Path | None:
    """Copy a damaged data.json into recovery storage and prune old copies."""
    try:
        source = Path(data_file)
        if not source.exists() or not source.is_file():
            return None

        recovery_root = Path(recovery_dir)
        recovery_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = recovery_root / f"bad_data_{timestamp}.json"

        size = source.stat().st_size
        if size <= MAX_QUARANTINED_BYTES:
            shutil.copy2(source, target)
        else:
            target = recovery_root / f"bad_data_{timestamp}.summary.json"
            digest = hashlib.sha256()
            with source.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            summary = {
                "original_path": str(source),
                "size_bytes": size,
                "sha256": digest.hexdigest(),
                "note": "Original damaged config exceeded quarantine size limit.",
            }
            target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        prune_quarantine(recovery_root)
        return target
    except Exception as exc:
        logger.debug("quarantine damaged config failed: %s", exc)
        return None


def prune_quarantine(recovery_dir: Path | str, keep: int = MAX_QUARANTINED_FILES) -> None:
    try:
        recovery_root = Path(recovery_dir)
        paths = sorted(set(recovery_root.glob("bad_data_*.json")) | set(recovery_root.glob("bad_data_*.summary.json")))
        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in paths[max(1, int(keep)) :]:
            try:
                old.unlink()
            except Exception as exc:
                logger.debug("delete old quarantined config failed %s: %s", old, exc)
    except Exception as exc:
        logger.debug("prune quarantined configs failed: %s", exc)
