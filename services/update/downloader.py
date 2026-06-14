"""Update package downloader with progress, size, host, hash, and session checks."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request

from core.background_tasks import start_background_thread
from core.network_security import safe_urlopen
from core.version import APP_VERSION
from services.update.session import create_update_session, update_session_state, utc_now_text

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
            except (RuntimeError, TypeError, ValueError) as exc:
                logger.debug("Downloader listener failed: %s", exc)

    def download(
        self,
        url: str,
        target_dir: str | None = None,
        expected_hash: str | None = None,
        expected_size: int = 0,
        max_bytes: int = 0,
        allowed_hosts: tuple[str, ...] | None = None,
        version: str = "",
        verify_ssl: bool = True,
    ):
        self._cancel_flag = False
        self._download_thread = start_background_thread(
            name="UpdateDownloader",
            target=self._do_download,
            args=(url, target_dir, expected_hash, expected_size, max_bytes, allowed_hosts, version, verify_ssl),
            owner=self,
        )

    def cancel(self):
        self._cancel_flag = True

    def wait(self, timeout: float = 5.0) -> bool:
        """Wait for the download thread to finish. Returns True if done."""
        thread = getattr(self, "_download_thread", None)
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def _do_download(
        self,
        url: str,
        target_dir: str | None,
        expected_hash: str | None,
        expected_size: int = 0,
        max_bytes: int = 0,
        allowed_hosts: tuple[str, ...] | None = None,
        version: str = "",
        verify_ssl: bool = True,
    ):
        tmp_path = None
        session_dir = ""
        try:
            parsed = urlparse(url)
            scheme = (parsed.scheme or "").lower()
            host = (parsed.hostname or "").lower()
            if scheme not in ("http", "https"):
                raise ValueError("invalid download URL scheme")
            if allowed_hosts and not _is_allowed_host(host, allowed_hosts):
                raise ValueError(f"untrusted download host: {host}")

            target_dir = target_dir or tempfile.gettempdir()
            os.makedirs(target_dir, exist_ok=True)
            _session_id, session_dir = create_update_session(
                target_dir,
                version=version,
                download_url=url,
                file_hash=expected_hash or "",
                expected_size=expected_size,
            )
            update_session_state(
                session_dir,
                status="downloading",
                download={"status": "started", "started_at": utc_now_text()},
            )

            from services.api.base_client import _make_unverified_ssl_context, _make_verified_ssl_context

            ssl_context = _make_verified_ssl_context() if verify_ssl else _make_unverified_ssl_context()

            req = Request(url, headers={"User-Agent": f"QuickLauncher/{APP_VERSION}"})
            with safe_urlopen(req, timeout=30, context=ssl_context) as resp:
                self._validate_final_url(resp, allowed_hosts)
                total = int(resp.headers.get("Content-Length", 0) or 0)
                if max_bytes and total > max_bytes:
                    raise ValueError("download exceeds maximum allowed size")

                file_name = _safe_file_name(parsed.path)
                tmp_path = os.path.join(session_dir, f".{file_name}.{os.getpid()}.part")
                final_path = os.path.join(session_dir, file_name)
                sha256 = hashlib.sha256()
                downloaded = 0
                with open(tmp_path, "wb") as handle:
                    while True:
                        if self._cancel_flag:
                            self._remove_file(tmp_path)
                            update_session_state(
                                session_dir,
                                status="cancelled",
                                download={"status": "cancelled", "bytes": downloaded},
                            )
                            self._notify("cancelled")
                            return
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        handle.write(chunk)
                        sha256.update(chunk)
                        downloaded += len(chunk)
                        if max_bytes and downloaded > max_bytes:
                            raise ValueError("download exceeds maximum allowed size")
                        self._notify("progress", (downloaded, total))

            if expected_size and downloaded != int(expected_size):
                self._remove_file(tmp_path)
                self._fail_session(session_dir, downloaded, "size mismatch")
                self._notify("failed", f"file size mismatch; expected {expected_size}, got {downloaded}")
                return

            if expected_hash:
                match = _SHA256_RE.fullmatch(expected_hash or "")
                if not match:
                    self._remove_file(tmp_path)
                    self._fail_session(session_dir, downloaded, "invalid hash format")
                    self._notify("failed", "invalid file hash format")
                    return
                actual_hash = sha256.hexdigest()
                expected_value = match.group(1).lower()
                if actual_hash != expected_value:
                    self._remove_file(tmp_path)
                    self._fail_session(session_dir, downloaded, "hash mismatch")
                    self._notify(
                        "failed", f"哈希校验失败; file hash mismatch; expected {expected_value}, got {actual_hash}"
                    )
                    return

            os.replace(tmp_path, final_path)
            update_session_state(
                session_dir,
                status="downloaded",
                download={
                    "status": "finished",
                    "finished_at": utc_now_text(),
                    "installer_path": final_path,
                    "bytes": downloaded,
                    "error": "",
                },
            )
            self._notify("finished", final_path)
        except URLError as exc:
            if session_dir:
                self._fail_session(session_dir, 0, str(exc.reason))
            self._notify("failed", f"download failed: {exc.reason}")
        except (OSError, TypeError, ValueError) as exc:
            if session_dir:
                self._fail_session(session_dir, 0, str(exc))
            self._notify("failed", f"download error: {exc}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                self._remove_file(tmp_path)

    def _validate_final_url(self, resp, allowed_hosts: tuple[str, ...] | None) -> None:
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
                raise ValueError("invalid final download URL scheme")
            if allowed_hosts and not _is_allowed_host(final_host, allowed_hosts):
                raise ValueError(f"最终下载域名不受信任: {final_host}; untrusted final download host")

    def _fail_session(self, session_dir: str, downloaded: int, error: str) -> None:
        update_session_state(
            session_dir,
            status="failed",
            download={"status": "failed", "bytes": downloaded, "error": error},
        )

    def _remove_file(self, path: str):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            logger.debug("删除下载文件失败", exc_info=True)


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
