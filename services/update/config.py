"""Update configuration and response models."""

from dataclasses import dataclass


@dataclass
class UpdateConfig:
    update_source: str = "github"
    check_url: str = "https://api.github.com/repos/LEISHIQIANG/QuickLauncher/releases/latest"
    github_repo: str = "LEISHIQIANG/QuickLauncher"
    asset_name_pattern: str = r"(?i)(quicklauncher|setup).*\.(exe|msi)$"
    channel: str = "stable"
    check_interval_hours: int = 24
    check_on_startup: bool = True
    repeat_auto_check: bool = False
    auto_download: bool = False
    auto_install: bool = False
    verify_ssl: bool = True
    require_file_hash: bool = True
    allow_insecure_update_urls: bool = False
    allowed_download_hosts: tuple[str, ...] = ("github.com", "githubusercontent.com")
    max_download_bytes: int = 200 * 1024 * 1024
    download_dir_name: str = "updates"


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
