"""安装更新包。"""

import logging
import hashlib
import os
import re
import subprocess
import sys

logger = logging.getLogger(__name__)
_SHA256_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$")


class UpdateInstaller:
    """安装器：执行更新包并退出当前进程。"""

    def __init__(self):
        self._listeners = []

    def add_listener(self, callback):
        self._listeners.append(callback)

    def _notify(self, event: str, data=None):
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception:
                pass

    def install(self, installer_path: str, expected_hash: str = ""):
        if not os.path.isfile(installer_path):
            self._notify("failed", f"安装文件不存在: {installer_path}")
            return
        if os.path.splitext(installer_path)[1].lower() != ".exe":
            self._notify("failed", "安装文件类型无效")
            return
        if expected_hash:
            if not _verify_sha256(installer_path, expected_hash):
                self._notify("failed", "安装文件哈希校验失败")
                return

        self._notify("started")

        try:
            current_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()

            subprocess.Popen(
                [
                    installer_path,
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    f"/DIR={current_dir}",
                    "/TASKS=desktopicon",
                    "/MERGETASKS=!associate_qlauncher",
                    "/LOG=update_install.log",
                ],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            sys.exit(0)
        except Exception as e:
            self._notify("failed", f"启动安装失败: {e}")


def _verify_sha256(path: str, expected_hash: str) -> bool:
    match = _SHA256_RE.fullmatch(expected_hash or "")
    if not match:
        return False
    expected = match.group(1).lower()
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected
