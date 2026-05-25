"""更新检查：定时后台检查 + 手动触发。"""

import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

from commercial.api.base_client import ApiClient
from commercial.update.config import UpdateConfig, UpdateInfo

logger = logging.getLogger(__name__)

_SHA256_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


class UpdateChecker:
    """更新检查器，工作于后台线程，不阻塞 UI。"""

    def __init__(self, config: UpdateConfig = None):
        self._config = config or UpdateConfig()
        self._api = ApiClient(self._config.check_url, timeout=10, verify_ssl=self._config.verify_ssl)
        self._timer: Optional[threading.Timer] = None
        self._listeners = []
        self._running = False

    def add_listener(self, callback):
        self._listeners.append(callback)

    def _notify(self, event: str, data=None):
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception as e:
                logger.debug(f"更新通知回调异常: {e}")

    def start_auto_check(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._auto_check, daemon=True).start()

    def _auto_check(self):
        if self._should_check():
            result = self._do_check()
            if result and result.has_update:
                self._notify("update_available", result)
        self._schedule_next()

    def _should_check(self) -> bool:
        state_file = self._get_state_file()
        try:
            if os.path.isfile(state_file):
                with open(state_file, "r") as f:
                    data = json.load(f)
                last = datetime.fromisoformat(data.get("last_check", ""))
                if datetime.now() - last < timedelta(hours=self._config.check_interval_hours):
                    return False
            return True
        except Exception:
            return True

    def check_now(self) -> Optional[UpdateInfo]:
        result = self._do_check()
        if result:
            self._save_check_time()
            if result.has_update:
                self._notify("update_available", result)
            else:
                self._notify("up_to_date")
        return result

    def _do_check(self) -> Optional[UpdateInfo]:
        from core.version import APP_VERSION
        try:
            resp = self._api.get("/check", {
                "version": APP_VERSION,
                "channel": self._config.channel,
                "platform": "win64",
            })
            if resp.get("has_update"):
                changelog = resp.get("changelog", {})
                info = UpdateInfo(
                    has_update=True,
                    version=resp["version"],
                    release_date=resp.get("release_date", ""),
                    changelog_zh=changelog.get("zh", ""),
                    changelog_en=changelog.get("en", ""),
                    download_url=resp["download_url"],
                    file_hash=resp.get("file_hash", ""),
                    file_size=resp.get("file_size", 0),
                    mandatory=resp.get("mandatory", False),
                    mandatory_min_version=resp.get("mandatory_min_version", ""),
                )
                validation_error = self._validate_update_info(info)
                if validation_error:
                    raise ValueError(validation_error)
                return info
            return UpdateInfo(has_update=False)
        except Exception as e:
            self._notify("check_failed", str(e))
            return None

    def _validate_update_info(self, info: UpdateInfo) -> str:
        if not info.download_url:
            return "更新信息缺少下载地址"

        parsed = urlparse(info.download_url)
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").lower()
        if scheme != "https" and not self._config.allow_insecure_update_urls:
            return "更新包下载地址必须使用 HTTPS"
        if not host:
            return "更新包下载地址缺少域名"
        if not self._is_allowed_download_host(host):
            return f"更新包下载域名不受信任: {host}"

        if self._config.require_file_hash:
            if not _SHA256_RE.fullmatch(info.file_hash or ""):
                return "更新包缺少有效的 sha256 哈希"

        if info.file_size <= 0:
            return "更新包大小无效"
        if info.file_size > self._config.max_download_bytes:
            return "更新包大小超过安全限制"
        return ""

    def _is_allowed_download_host(self, host: str) -> bool:
        allowed_hosts = tuple(self._config.allowed_download_hosts or ())
        if not allowed_hosts:
            return True
        for allowed in allowed_hosts:
            allowed_host = (allowed or "").lower().strip()
            if not allowed_host:
                continue
            if host == allowed_host or host.endswith("." + allowed_host):
                return True
        return False

    def _get_state_file(self) -> str:
        from core.data_manager import DataManager
        dm = DataManager()
        return os.path.join(dm.app_dir, "config", ".update_state.json")

    def _save_check_time(self):
        state_file = self._get_state_file()
        try:
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, "w") as f:
                json.dump({"last_check": datetime.now().isoformat()}, f)
        except Exception:
            pass

    def _schedule_next(self):
        self._timer = threading.Timer(
            self._config.check_interval_hours * 3600, self._auto_check
        )
        self._timer.daemon = True
        self._timer.start()

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
