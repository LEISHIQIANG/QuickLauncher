"""Update session state helpers."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

SESSION_SCHEMA_VERSION = 1
SESSION_FILE_NAME = "update_session.json"


def utc_now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_update_session(
    target_dir: str,
    *,
    version: str = "",
    download_url: str = "",
    file_hash: str = "",
    expected_size: int = 0,
) -> tuple[str, str]:
    session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    session_dir = os.path.join(target_dir, session_id)
    os.makedirs(session_dir, exist_ok=True)
    write_session_state(
        session_dir,
        {
            "schema": SESSION_SCHEMA_VERSION,
            "session_id": session_id,
            "version": version or "",
            "download_url": download_url or "",
            "file_hash": file_hash or "",
            "expected_size": int(expected_size or 0),
            "status": "created",
            "created_at": utc_now_text(),
            "download": {
                "status": "pending",
                "started_at": "",
                "finished_at": "",
                "installer_path": "",
                "bytes": 0,
                "error": "",
            },
            "install": {
                "status": "pending",
                "started_at": "",
                "installer_path": "",
                "pre_install_backup": "",
                "log_path": "",
                "error": "",
            },
            "first_start": {
                "confirmed": False,
                "confirmed_at": "",
            },
        },
    )
    return session_id, session_dir


def read_session_state(session_dir_or_file: str | os.PathLike) -> dict:
    path = Path(session_dir_or_file)
    if path.is_dir():
        path = path / SESSION_FILE_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_session_state(session_dir: str | os.PathLike, state: dict) -> None:
    path = Path(session_dir) / SESSION_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def update_session_state(session_dir_or_file: str | os.PathLike, **updates) -> dict:
    path = Path(session_dir_or_file)
    session_dir = path if path.is_dir() else path.parent
    state = read_session_state(session_dir)
    if not state:
        state = {"schema": SESSION_SCHEMA_VERSION, "session_id": session_dir.name}
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(state.get(key), dict):
            merged = dict(state[key])
            merged.update(value)
            state[key] = merged
        else:
            state[key] = value
    write_session_state(session_dir, state)
    return state


def find_session_for_installer(installer_path: str) -> tuple[str, dict]:
    session_dir = Path(installer_path).resolve(strict=False).parent
    state = read_session_state(session_dir)
    if not state:
        return "", {}
    return str(session_dir), state


def latest_session_state(base_dir: str | os.PathLike) -> dict:
    root = Path(base_dir)
    if not root.exists():
        return {}
    candidates = sorted(root.glob(f"*/{SESSION_FILE_NAME}"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        state = read_session_state(path)
        if state:
            return state
    return {}


def mark_latest_session_first_start_confirmed(base_dir: str | os.PathLike) -> dict:
    root = Path(base_dir)
    if not root.exists():
        return {}
    candidates = sorted(root.glob(f"*/{SESSION_FILE_NAME}"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        state = read_session_state(path)
        if not state:
            continue
        first_start_value = state.get("first_start")
        install_value = state.get("install")
        first_start = first_start_value if isinstance(first_start_value, dict) else {}
        install = install_value if isinstance(install_value, dict) else {}
        if install.get("status") == "started" and not first_start.get("confirmed"):
            return update_session_state(
                path,
                status="first_start_confirmed",
                first_start={"confirmed": True, "confirmed_at": utc_now_text()},
            )
    return {}
