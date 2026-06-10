"""Background update checker."""

import json
import logging
import os
import re
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from core.background_tasks import start_background_thread
from services.api.base_client import ApiClient, ApiError
from services.update.config import UpdateConfig, UpdateInfo
from services.update.trust import UpdateSignatureError, update_signature_payload, verify_update_signature

logger = logging.getLogger(__name__)
_SHA256_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_SHA256_ANYWHERE_RE = re.compile(r"sha256:[0-9a-fA-F]{64}", re.IGNORECASE)
_ED25519_SIGNATURE_RE = re.compile(r"ed25519:[A-Za-z0-9+/=_-]{43,128}|ed25519:[0-9a-fA-F]{128}", re.IGNORECASE)


class UpdateCheckError(Exception):
    event = "check_failed"


class UpdateNetworkError(UpdateCheckError):
    event = "check_network_error"


class UpdateParseError(UpdateCheckError):
    event = "check_parse_error"


class UpdateValidationError(UpdateCheckError):
    event = "check_validation_error"


class UpdateChecker:
    """Checks for updates in a background thread and reports events to listeners."""

    def __init__(self, config: UpdateConfig | None = None):
        self._config = config or UpdateConfig()
        self._api = ApiClient(self._config.check_url, timeout=10, verify_ssl=self._config.verify_ssl)
        self._timer: threading.Thread | None = None
        self._timer_cancel_event: threading.Event | None = None
        self._timer_lock = threading.Lock()
        self._listeners: list[Callable[[str, Any], None]] = []
        self._running = False
        self._last_check_status = ""
        self._last_check_error = ""

    def add_listener(self, callback: Callable[[str, Any], None]) -> None:
        self._listeners.append(callback)

    def _notify(self, event: str, data: Any = None) -> None:
        for callback in list(self._listeners):
            try:
                callback(event, data)
            except Exception as exc:
                logger.debug("Update listener failed: %s", exc)

    def start_auto_check(self):
        if self._running:
            return
        self._running = True
        if self._config.check_on_startup:
            self._auto_check_thread = start_background_thread(
                name="UpdateAutoCheck",
                target=self._auto_check,
                owner=self,
            )
        else:
            self._schedule_next()

    def check_now(self) -> UpdateInfo | None:
        result = self._do_check()
        self._save_check_time()
        if result is None:
            return None
        if result.has_update:
            self._notify("update_available", result)
        else:
            self._notify("up_to_date")
        return result

    def skip_version(self, version: str):
        if not version:
            return
        state = self._load_state()
        skipped = list(state.get("skipped_versions", []))
        if version not in skipped:
            skipped.append(version)
        state["skipped_versions"] = skipped
        self._save_state(state)

    def is_version_skipped(self, version: str) -> bool:
        return bool(version and version in self._load_state().get("skipped_versions", []))

    def _auto_check(self):
        try:
            if self._running and self._should_check():
                result = self._do_check()
                self._save_check_time()
                if result and result.has_update:
                    if self.is_version_skipped(result.version) and not result.mandatory:
                        self._notify("update_skipped", result)
                    elif self._config.auto_download:
                        self._notify("auto_download_requested", result)
                    else:
                        self._notify("update_available", result)
        finally:
            if self._config.repeat_auto_check:
                self._schedule_next()

    def _should_check(self) -> bool:
        try:
            last_check = self._load_state().get("last_check", "")
            if not last_check:
                return True
            last = datetime.fromisoformat(last_check)
            return datetime.now() - last >= timedelta(hours=self._config.check_interval_hours)
        except (OSError, TypeError, ValueError):
            return True

    def _do_check(self) -> UpdateInfo | None:
        from core.version import APP_VERSION

        try:
            if self._config.update_source == "github":
                try:
                    result = self._do_github_release_check(APP_VERSION)
                except ApiError as exc:
                    raise UpdateNetworkError(str(exc)) from exc
                except (KeyError, TypeError, ValueError) as exc:
                    raise UpdateValidationError(str(exc)) from exc
                self._last_check_status = "ok"
                self._last_check_error = ""
                return result

            try:
                resp = self._api.get(
                    "/check",
                    {
                        "version": APP_VERSION,
                        "channel": self._config.channel,
                        "platform": "win64",
                    },
                )
            except ApiError as exc:
                raise UpdateNetworkError(str(exc)) from exc
            if not isinstance(resp, dict):
                raise UpdateParseError("更新接口返回内容不是 JSON 对象")
            if not resp.get("has_update"):
                self._last_check_status = "ok"
                self._last_check_error = ""
                return UpdateInfo(has_update=False)
            try:
                changelog = resp.get("changelog", {})
                if not isinstance(changelog, dict):
                    raise TypeError("changelog must be an object")
                info = UpdateInfo(
                    has_update=True,
                    version=resp["version"],
                    release_date=resp.get("release_date", ""),
                    changelog_zh=changelog.get("zh", ""),
                    changelog_en=changelog.get("en", ""),
                    download_url=resp["download_url"],
                    file_hash=resp.get("file_hash", ""),
                    file_signature=resp.get("file_signature", "") or resp.get("signature", ""),
                    file_size=int(resp.get("file_size", 0) or 0),
                    mandatory=bool(resp.get("mandatory", False)),
                    mandatory_min_version=resp.get("mandatory_min_version", ""),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise UpdateParseError(f"更新接口响应解析失败: {exc}") from exc
            validation_error = self._validate_update_info(info)
            if validation_error:
                raise UpdateValidationError(validation_error)
            self._last_check_status = "ok"
            self._last_check_error = ""
            return info
        except UpdateCheckError as exc:
            self._fail_check(exc.event, str(exc))
            return None
        except (ApiError, OSError, RuntimeError, TypeError, ValueError) as exc:
            self._fail_check("check_failed", str(exc))
            return None

    def _fail_check(self, event: str, message: str) -> None:
        self._last_check_status = "failed"
        self._last_check_error = message
        if event != "check_failed":
            self._notify(event, message)
        self._notify("check_failed", message)

    def _do_github_release_check(self, current_version: str) -> UpdateInfo:
        resp = self._api.get()
        if resp.get("draft") or (resp.get("prerelease") and self._config.channel == "stable"):
            return UpdateInfo(has_update=False)

        version = _normalize_version(resp.get("tag_name") or resp.get("name") or "")
        if not version:
            raise ValueError("GitHub Release 缺少版本号")
        if _compare_versions(version, current_version) <= 0:
            return UpdateInfo(has_update=False)

        asset = self._select_release_asset(resp.get("assets", []))
        if not asset:
            raise ValueError("GitHub Release 未找到 Windows 安装包 asset")

        file_hash = self._extract_release_hash(resp, asset)
        file_signature = self._extract_release_signature(resp, asset)
        info = UpdateInfo(
            has_update=True,
            version=version,
            release_date=resp.get("published_at") or resp.get("created_at") or "",
            changelog_zh=resp.get("body") or "",
            download_url=asset.get("browser_download_url", ""),
            file_hash=file_hash,
            file_signature=file_signature,
            file_size=int(asset.get("size", 0) or 0),
            mandatory=False,
        )
        validation_error = self._validate_update_info(info)
        if validation_error:
            raise ValueError(validation_error)
        return info

    def _select_release_asset(self, assets: list[dict]) -> dict | None:
        pattern = re.compile(self._config.asset_name_pattern)
        for asset in assets:
            name = asset.get("name", "")
            if pattern.search(name):
                return asset
        return None

    def _extract_release_hash(self, release: dict, asset: dict) -> str:
        digest = str(asset.get("digest") or "")
        if _SHA256_RE.fullmatch(digest):
            return digest
        body_match = _SHA256_ANYWHERE_RE.search(str(release.get("body") or ""))
        if body_match:
            return body_match.group(0)
        return ""

    def _extract_release_signature(self, release: dict, asset: dict) -> str:
        for value in (asset.get("signature"), asset.get("ed25519"), release.get("body")):
            match = _ED25519_SIGNATURE_RE.search(str(value or ""))
            if match:
                return match.group(0)
        return ""

    def _validate_update_info(self, info: UpdateInfo) -> str:
        if not info.version:
            return "更新信息缺少版本号"
        if not info.download_url:
            return "更新信息缺少下载地址"
        parsed = urlparse(info.download_url)
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").lower()
        if scheme not in ("http", "https"):
            return "更新包下载地址协议无效"
        if scheme != "https" and not self._config.allow_insecure_update_urls:
            return "更新包下载地址必须使用 HTTPS"
        if not host:
            return "更新包下载地址缺少域名"
        if not self._is_allowed_download_host(host):
            return f"更新包下载域名不受信任: {host}"
        if self._config.require_file_hash and not _SHA256_RE.fullmatch(info.file_hash or ""):
            return "更新包缺少有效的 sha256 哈希"
        if self._config.require_signature:
            if not info.file_signature:
                return "更新包缺少发布签名"
            try:
                valid_signature = verify_update_signature(
                    update_signature_payload(info),
                    info.file_signature,
                    tuple(self._config.signature_public_keys or ()),
                )
            except UpdateSignatureError as exc:
                return f"更新签名配置无效: {exc}"
            if not valid_signature:
                return "更新包发布签名校验失败"
        if info.file_size <= 0:
            return "更新包大小无效"
        if info.file_size > self._config.max_download_bytes:
            return "更新包大小超过安全限制"
        return ""

    def _is_allowed_download_host(self, host: str) -> bool:
        allowed_hosts = self._config.allowed_download_hosts or ()
        if not allowed_hosts:
            return True
        for allowed in allowed_hosts:
            allowed_host = (allowed or "").lower().strip()
            if host == allowed_host or host.endswith("." + allowed_host):
                return True
        return False

    def _get_state_file(self) -> str:
        # Lazy: avoids circular import via core.__init__.
        from core.data_manager import DataManager

        dm = DataManager()
        return os.path.join(dm.app_dir, ".update_state.json")

    def _get_legacy_state_file(self) -> str:
        # Lazy: avoids circular import via core.__init__.
        from core.data_manager import DataManager

        dm = DataManager()
        return os.path.join(dm.app_dir, "config", ".update_state.json")

    def _load_state(self) -> dict:
        state_file = self._get_state_file()
        try:
            if os.path.isfile(state_file):
                with open(state_file, encoding="utf-8") as handle:
                    data = json.load(handle)
                    return data if isinstance(data, dict) else {}
            legacy_state_file = self._get_legacy_state_file()
            if os.path.isfile(legacy_state_file):
                with open(legacy_state_file, encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    self._save_state(data)
                    return data
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.debug("Failed to load update state: %s", exc)
        return {}

    def _save_state(self, state: dict):
        state_file = self._get_state_file()
        try:
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.debug("Failed to save update state: %s", exc)

    def _save_check_time(self):
        state = self._load_state()
        state["last_check"] = datetime.now().isoformat()
        if self._last_check_status:
            state["last_check_status"] = self._last_check_status
            state["last_check_error"] = self._last_check_error
        self._save_state(state)

    def _schedule_next(self):
        with self._timer_lock:
            if not self._running:
                return
            interval = max(3600, int(self._config.check_interval_hours * 3600))
            cancel_event = threading.Event()
            self._timer_cancel_event = cancel_event
            self._timer = start_background_thread(
                name="UpdateAutoCheckTimer",
                target=self._wait_then_auto_check,
                args=(interval, cancel_event),
                owner=self,
            )

    def _wait_then_auto_check(self, interval: int, cancel_event: threading.Event) -> None:
        if cancel_event.wait(max(0, int(interval))):
            return
        self._auto_check()

    def stop(self):
        with self._timer_lock:
            self._running = False
            cancel_event = self._timer_cancel_event
            self._timer = None
            self._timer_cancel_event = None
        if cancel_event:
            cancel_event.set()


def _normalize_version(value: str) -> str:
    value = (value or "").strip()
    if value.lower().startswith("v"):
        value = value[1:]
    match = re.search(r"\d+(?:\.\d+){0,3}", value)
    return match.group(0) if match else ""


def _compare_versions(left: str, right: str) -> int:
    def parts(value: str) -> list[int]:
        nums = [int(part) for part in _normalize_version(value).split(".") if part.isdigit()]
        return nums + [0] * (4 - len(nums))

    left_parts = parts(left)
    right_parts = parts(right)
    if left_parts > right_parts:
        return 1
    if left_parts < right_parts:
        return -1
    return 0
