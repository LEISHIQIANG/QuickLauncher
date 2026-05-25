"""更新配置与数据模型。"""

from dataclasses import dataclass


@dataclass
class UpdateConfig:
    check_url: str = "https://update.quicklauncher.app/api/check"
    channel: str = "stable"
    check_interval_hours: int = 24
    auto_download: bool = False
    auto_install: bool = False
    verify_ssl: bool = True
    require_file_hash: bool = True
    allow_insecure_update_urls: bool = False
    allowed_download_hosts: tuple[str, ...] = ("update.quicklauncher.app",)
    max_download_bytes: int = 200 * 1024 * 1024


@dataclass
class UpdateInfo:
    has_update: bool = False
    version: str = ""
    release_date: str = ""
    changelog_zh: str = ""
    changelog_en: str = ""
    download_url: str = ""
    file_hash: str = ""
    file_size: int = 0
    mandatory: bool = False
    mandatory_min_version: str = ""
