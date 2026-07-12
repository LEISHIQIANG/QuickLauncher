"""Filesystem plugin catalog discovery."""

from __future__ import annotations

import logging
from pathlib import Path

from .manifest import PluginManifestParser
from .models import PluginInfo
from .state_store import PluginStateStore

logger = logging.getLogger(__name__)


class PluginCatalog:
    def __init__(
        self,
        plugins_dir: str | Path,
        *,
        parser: PluginManifestParser,
        state_store: PluginStateStore,
    ) -> None:
        self.plugins_dir = Path(plugins_dir).resolve(strict=False)
        self.parser = parser
        self.state_store = state_store

    def scan(self) -> dict[str, PluginInfo]:
        discovered: dict[str, PluginInfo] = {}
        if not self.plugins_dir.is_dir():
            logger.info("插件目录不存在: %s", self.plugins_dir)
            return discovered
        for directory in sorted(self.plugins_dir.iterdir()):
            if not directory.is_dir():
                continue
            manifest_path = directory / "plugin.json"
            if not manifest_path.is_file():
                continue
            info = self.parser.parse(directory, manifest_path)
            if info.status == "loaded":
                info = self.state_store.apply(info)
            discovered[info.manifest.id] = info
        return discovered
