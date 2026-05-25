"""更新包下载器，支持进度回调与哈希校验。"""

import hashlib
import logging
import os
import re
import tempfile
import threading
from typing import Optional
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from core.version import APP_VERSION

logger = logging.getLogger(__name__)
_SHA256_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$")


class UpdateDownloader:
    """后台下载更新包。"""

    def __init__(self):
        self._cancel_flag = False
        self._listeners = []

    def add_listener(self, callback):
        self._listeners.append(callback)

    def _notify(self, event: str, data=None):
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception as e:
                logger.debug(f"下载器通知回调异常: {e}")

    def download(
        self,
        url: str,
        target_dir: str = None,
        expected_hash: str = None,
        expected_size: int = 0,
        max_bytes: int = 0,
        allowed_hosts: tuple[str, ...] | None = None,
    ):
        self._cancel_flag = False
        threading.Thread(
            target=self._do_download,
            args=(url, target_dir, expected_hash, expected_size, max_bytes, allowed_hosts),
            daemon=True,
        ).start()

    def cancel(self):
        self._cancel_flag = True

    def _do_download(
        self,
        url: str,
        target_dir: Optional[str],
        expected_hash: Optional[str],
        expected_size: int = 0,
        max_bytes: int = 0,
        allowed_hosts: tuple[str, ...] | None = None,
    ):
        tmp_path = None
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            if allowed_hosts and not _is_allowed_host(host, allowed_hosts):
                raise ValueError(f"下载域名不受信任: {host}")

            target_dir = target_dir or tempfile.gettempdir()
            os.makedirs(target_dir, exist_ok=True)

            req = Request(url, headers={"User-Agent": f"QuickLauncher/{APP_VERSION}"})
            resp = urlopen(req, timeout=30)
            total = int(resp.headers.get("Content-Length", 0))
            if max_bytes and total > max_bytes:
                raise ValueError("下载文件超过安全大小限制")
            file_name = os.path.basename(url.split("?")[0]) or "QuickLauncher_Update.exe"
            tmp_path = os.path.join(target_dir, f".{file_name}.part")
            final_path = os.path.join(target_dir, file_name)

            sha256 = hashlib.sha256()
            downloaded = 0
            chunk_size = 65536

            with open(tmp_path, "wb") as f:
                while True:
                    if self._cancel_flag:
                        f.close()
                        os.remove(tmp_path)
                        self._notify("cancelled")
                        return
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    sha256.update(chunk)
                    downloaded += len(chunk)
                    if max_bytes and downloaded > max_bytes:
                        raise ValueError("下载文件超过安全大小限制")
                    if total > 0:
                        self._notify("progress", (downloaded, total))

            if expected_size and downloaded != int(expected_size):
                os.remove(tmp_path)
                self._notify("failed", f"文件大小校验失败\n期望: {expected_size}\n实际: {downloaded}")
                return

            if expected_hash:
                actual_hash = sha256.hexdigest()
                match = _SHA256_RE.fullmatch(expected_hash or "")
                if not match:
                    os.remove(tmp_path)
                    self._notify("failed", "文件哈希格式无效")
                    return
                expected_value = match.group(1).lower()
                if actual_hash != expected_value:
                    os.remove(tmp_path)
                    self._notify("failed", f"文件哈希校验失败\n期望: {expected_value}\n实际: {actual_hash}")
                    return

            os.replace(tmp_path, final_path)
            self._notify("finished", final_path)

        except URLError as e:
            self._notify("failed", f"下载失败: {e.reason}")
        except Exception as e:
            self._notify("failed", f"下载出错: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass


def _is_allowed_host(host: str, allowed_hosts: tuple[str, ...]) -> bool:
    for allowed in allowed_hosts:
        allowed_host = (allowed or "").lower().strip()
        if not allowed_host:
            continue
        if host == allowed_host or host.endswith("." + allowed_host):
            return True
    return False
