"""Update package downloader with progress, size, host, and hash checks."""

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
    """Downloads an update package in a background thread."""

    def __init__(self):
        self._cancel_flag = False
        self._listeners = []

    def add_listener(self, callback):
        self._listeners.append(callback)

    def _notify(self, event: str, data=None):
        for callback in list(self._listeners):
            try:
                callback(event, data)
            except Exception as exc:
                logger.debug("Downloader listener failed: %s", exc)

    def download(
        self,
        url: str,
        target_dir: str | None = None,
        expected_hash: str | None = None,
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
            scheme = (parsed.scheme or "").lower()
            host = (parsed.hostname or "").lower()
            if scheme not in ("http", "https"):
                raise ValueError("下载地址协议无效")
            if allowed_hosts and not _is_allowed_host(host, allowed_hosts):
                raise ValueError(f"下载域名不受信任: {host}")
            target_dir = target_dir or tempfile.gettempdir()
            os.makedirs(target_dir, exist_ok=True)
            req = Request(url, headers={"User-Agent": f"QuickLauncher/{APP_VERSION}"})
            with urlopen(req, timeout=30) as resp:
                final_url = ""
                geturl = getattr(resp, "geturl", None)
                if callable(geturl):
                    final_url = str(geturl() or "")
                if not final_url:
                    final_url = str(getattr(resp, "url", "") or "")
                if final_url and "://" in final_url:
                    final_parsed = urlparse(final_url)
                    final_scheme = (final_parsed.scheme or "").lower()
                    final_host = (final_parsed.hostname or "").lower()
                    if final_scheme not in ("http", "https"):
                        raise ValueError("最终下载地址协议无效")
                    if allowed_hosts and not _is_allowed_host(final_host, allowed_hosts):
                        raise ValueError(f"最终下载域名不受信任: {final_host}")
                total = int(resp.headers.get("Content-Length", 0) or 0)
                if max_bytes and total > max_bytes:
                    raise ValueError("下载文件超过安全大小限制")
                file_name = _safe_file_name(parsed.path)
                tmp_path = os.path.join(target_dir, f".{file_name}.part")
                final_path = os.path.join(target_dir, file_name)
                sha256 = hashlib.sha256()
                downloaded = 0
                with open(tmp_path, "wb") as handle:
                    while True:
                        if self._cancel_flag:
                            self._remove_file(tmp_path)
                            self._notify("cancelled")
                            return
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        handle.write(chunk)
                        sha256.update(chunk)
                        downloaded += len(chunk)
                        if max_bytes and downloaded > max_bytes:
                            raise ValueError("下载文件超过安全大小限制")
                        self._notify("progress", (downloaded, total))
            if expected_size and downloaded != int(expected_size):
                self._remove_file(tmp_path)
                self._notify("failed", f"文件大小校验失败\n期望: {expected_size}\n实际: {downloaded}")
                return
            if expected_hash:
                match = _SHA256_RE.fullmatch(expected_hash or "")
                if not match:
                    self._remove_file(tmp_path)
                    self._notify("failed", "文件哈希格式无效")
                    return
                actual_hash = sha256.hexdigest()
                expected_value = match.group(1).lower()
                if actual_hash != expected_value:
                    self._remove_file(tmp_path)
                    self._notify("failed", f"文件哈希校验失败\n期望: {expected_value}\n实际: {actual_hash}")
                    return
            os.replace(tmp_path, final_path)
            self._notify("finished", final_path)
        except URLError as exc:
            self._notify("failed", f"下载失败: {exc.reason}")
        except Exception as exc:
            self._notify("failed", f"下载出错: {exc}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                self._remove_file(tmp_path)

    def _remove_file(self, path: str):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def _is_allowed_host(host: str, allowed_hosts: tuple[str, ...]) -> bool:
    for allowed in allowed_hosts:
        allowed_host = (allowed or "").lower().strip()
        if host == allowed_host or host.endswith("." + allowed_host):
            return True
    return False


def _safe_file_name(path: str) -> str:
    name = os.path.basename(path) or "QuickLauncher_Update.exe"
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return name or "QuickLauncher_Update.exe"
