"""Update installer launcher."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys

from core.path_security import UnsafePathError, resolve_under
from runtime_paths import app_root, is_packaged_runtime
from services.update.session import find_session_for_installer, update_session_state, utc_now_text
from services.update.trust import UpdateSignatureError, verify_update_signature

logger = logging.getLogger(__name__)

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
            except (RuntimeError, TypeError, ValueError):
                logger.debug("通知安装回调失败", exc_info=True)

    def install(
        self,
        installer_path: str,
        expected_hash: str = "",
        trusted_dir: str = "",
        data_manager=None,
        expected_signature: str = "",
        signature_payload: bytes | str = b"",
        signature_public_keys: tuple[str, ...] = (),
    ):
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
        if expected_signature:
            try:
                signature_valid = verify_update_signature(
                    signature_payload,
                    expected_signature,
                    tuple(signature_public_keys or ()),
                )
            except UpdateSignatureError as exc:
                self._fail_session(session_dir, f"安装文件签名配置无效; installer signature config invalid: {exc}")
                return
            if not signature_valid:
                self._fail_session(session_dir, "安装文件签名校验失败; installer signature mismatch")
                return

        pre_install_backup = ""
        if data_manager is not None:
            pre_install_backup = os.path.join(session_dir, "pre_install_config_backup.zip")
            backup = getattr(data_manager, "backup_full_config", None)
            if not callable(backup) or not backup(pre_install_backup):
                self._fail_session(session_dir, "failed to create pre-install configuration backup")
                return

        current_dir = str(app_root()) if is_packaged_runtime() else os.getcwd()
        log_path = os.path.join(session_dir, "update_install.log") if session_dir else ""
        if session_dir:
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
            command = [
                installer_path,
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                f"/DIR={current_dir}",
                "/TASKS=desktopicon",
                "/MERGETASKS=!associate_qlauncher",
            ]
            if log_path:
                command.append(f"/LOG={log_path}")
            _launch_independent_installer(command)
            sys.exit(0)
        except (OSError, ValueError) as exc:
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


def _launch_independent_installer(command: list[str]) -> None:
    create_new_process_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    detached_process = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    create_breakaway_from_job = 0x01000000
    creationflags = create_new_process_group | detached_process | create_breakaway_from_job
    try:
        subprocess.Popen(
            command,
            creationflags=creationflags,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        logger.debug("Installer breakaway flag unavailable; retrying detached launch", exc_info=True)
        subprocess.Popen(
            command,
            creationflags=creationflags & ~create_breakaway_from_job,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
