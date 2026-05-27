"""Update installer launcher."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys

from core.path_security import UnsafePathError, resolve_under
from services.update.session import find_session_for_installer, update_session_state, utc_now_text

_SHA256_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$")


class UpdateInstaller:
    """Starts the downloaded installer and exits the current process."""

    def __init__(self):
        self._listeners = []

    def add_listener(self, callback):
        self._listeners.append(callback)

    def _notify(self, event: str, data=None):
        for callback in list(self._listeners):
            try:
                callback(event, data)
            except Exception:
                pass

    def install(self, installer_path: str, expected_hash: str = "", trusted_dir: str = "", data_manager=None):
        session_dir, _session_state = find_session_for_installer(installer_path)
        if not os.path.isfile(installer_path):
            self._fail_session(session_dir, f"安装文件不存在: {installer_path}; installer file does not exist")
            return
        if os.path.islink(installer_path):
            self._fail_session(session_dir, "installer file must not be a symlink")
            return
        if trusted_dir:
            try:
                installer_path = str(resolve_under(trusted_dir, installer_path))
            except UnsafePathError:
                self._fail_session(
                    session_dir, "安装文件不在可信下载目录内; installer file is outside the trusted download directory"
                )
                return
        if os.path.splitext(installer_path)[1].lower() != ".exe":
            self._fail_session(session_dir, "安装文件类型无效; invalid installer file type")
            return
        if expected_hash and not _verify_sha256(installer_path, expected_hash):
            self._fail_session(session_dir, "安装文件哈希校验失败; installer hash mismatch")
            return

        pre_install_backup = ""
        if data_manager is not None:
            pre_install_backup = os.path.join(session_dir, "pre_install_config_backup.zip")
            backup = getattr(data_manager, "backup_full_config", None)
            if not callable(backup) or not backup(pre_install_backup):
                self._fail_session(session_dir, "failed to create pre-install configuration backup")
                return

        current_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
        log_path = os.path.join(session_dir, "update_install.log")
        update_session_state(
            session_dir,
            status="installing",
            install={
                "status": "started",
                "started_at": utc_now_text(),
                "installer_path": installer_path,
                "pre_install_backup": pre_install_backup,
                "log_path": log_path,
                "error": "",
            },
        )
        self._notify("started")
        try:
            subprocess.Popen(
                [
                    installer_path,
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    f"/DIR={current_dir}",
                    "/TASKS=desktopicon",
                    "/MERGETASKS=!associate_qlauncher",
                    f"/LOG={log_path}",
                ],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            sys.exit(0)
        except Exception as exc:
            self._fail_session(session_dir, f"failed to start installer: {exc}")

    def _fail_session(self, session_dir: str, message: str) -> None:
        if session_dir:
            update_session_state(session_dir, status="failed", install={"status": "failed", "error": message})
        self._notify("failed", message)


def _verify_sha256(path: str, expected_hash: str) -> bool:
    match = _SHA256_RE.fullmatch(expected_hash or "")
    if not match:
        return False
    expected = match.group(1).lower()
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected
