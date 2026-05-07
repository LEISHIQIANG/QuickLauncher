"""
应用扫描器
扫描开始菜单和桌面快捷方式，为快速搜索列表提供候选项。
"""

import os
import logging
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Set

from .data_models import ShortcutItem, ShortcutType
from .shortcut_parser import ShortcutParser


logger = logging.getLogger(__name__)


class AppScanner:
    """扫描 Windows 常见入口目录中的应用快捷方式。"""

    SUPPORTED_EXTENSIONS = {".lnk", ".exe", ".url"}
    EXCLUDE_PATTERNS = {
        "卸载", "unins", "uninst", "uninstall",
        "安装", "setup", "install", "update",
        "帮助", "help", "readme",
    }

    @classmethod
    def scan_apps(cls, include_uwp: bool = True, progress_callback: Optional[Callable[[int, int, str], None]] = None) -> List[ShortcutItem]:
        """扫描开始菜单和桌面应用。

        Args:
            include_uwp: 为保持兼容而保留，当前主要依赖开始菜单入口。
            progress_callback: 进度回调 (current, total, message)
        """
        candidates = cls._collect_candidates()
        total = max(1, len(candidates))
        seen_targets: Set[str] = set()
        items: List[ShortcutItem] = []

        for index, path in enumerate(candidates, start=1):
            if progress_callback:
                try:
                    progress_callback(index, total, f"正在扫描 {path.name}")
                except Exception:
                    pass

            item = cls._build_item(path, include_uwp=include_uwp)
            if item is None:
                continue

            target_key = cls._make_dedupe_key(item)
            if target_key in seen_targets:
                continue
            seen_targets.add(target_key)
            items.append(item)

        items.sort(key=lambda item: ((item.alias or "").lower(), item.name.lower(), item.target_path.lower()))
        return items

    @classmethod
    def _collect_candidates(cls) -> List[Path]:
        roots = cls._scan_roots()
        results: List[Path] = []
        seen_paths: Set[str] = set()

        for root in roots:
            if not root.exists():
                continue

            try:
                iterator = root.rglob("*")
            except Exception as exc:
                logger.debug(f"无法遍历扫描目录 {root}: {exc}")
                continue

            for path in iterator:
                if not path.is_file():
                    continue
                if path.suffix.lower() not in cls.SUPPORTED_EXTENSIONS:
                    continue
                if cls._should_exclude(path):
                    continue

                normalized = os.path.normcase(str(path))
                if normalized in seen_paths:
                    continue
                seen_paths.add(normalized)
                results.append(path)

        return results

    @staticmethod
    def _scan_roots() -> List[Path]:
        roots = []
        env_paths = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("USERPROFILE", "")) / "Desktop",
            Path(os.environ.get("PUBLIC", "")) / "Desktop",
        ]
        for path in env_paths:
            try:
                if str(path):
                    roots.append(path)
            except Exception:
                continue
        return roots

    @classmethod
    def _should_exclude(cls, path: Path) -> bool:
        lowered = path.stem.lower()
        return any(pattern in lowered for pattern in cls.EXCLUDE_PATTERNS)

    @classmethod
    def _build_item(cls, path: Path, include_uwp: bool = True) -> Optional[ShortcutItem]:
        suffix = path.suffix.lower()
        parsed = ShortcutParser.parse(str(path))
        name = path.stem.strip()
        if not name:
            return None

        item = ShortcutItem()
        item.name = name
        item.alias = ""

        if suffix == ".url":
            target = (parsed.get("target") or "").strip()
            if not target:
                return None
            item.type = ShortcutType.URL
            item.url = target
            item.target_path = target
            item.icon_path = (parsed.get("icon_location") or "").strip()
            return item

        if suffix == ".lnk":
            target = (parsed.get("target") or "").strip()
            if not target:
                return None
            if target.lower().startswith("shell:") and not include_uwp:
                return None
            item.type = ShortcutType.FILE
            item.target_path = target
            item.target_args = (parsed.get("args") or "").strip()
            item.working_dir = (parsed.get("working_dir") or "").strip()
            icon_location = (parsed.get("icon_location") or "").strip()
            if icon_location:
                item.icon_path = icon_location
            return item

        if suffix == ".exe":
            item.type = ShortcutType.FILE
            item.target_path = str(path)
            item.working_dir = str(path.parent)
            return item

        return None

    @staticmethod
    def _make_dedupe_key(item: ShortcutItem) -> str:
        if item.type == ShortcutType.URL:
            return f"url:{(item.url or item.target_path).strip().lower()}"
        return f"path:{os.path.normcase(item.target_path or item.url or item.name)}"
