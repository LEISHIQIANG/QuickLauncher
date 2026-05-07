"""Memory guard with tiered cleanup."""

import gc
import logging
from typing import Callable

import psutil

logger = logging.getLogger(__name__)


class MemoryGuard:
    """Monitor process memory and run cleanup callbacks when needed."""

    def __init__(self, critical_mb: int = 200, moderate_mb: int = 150, light_mb: int = 100):
        self.light_mb = light_mb
        self.moderate_mb = moderate_mb
        self.critical_mb = critical_mb
        try:
            self.process = psutil.Process()
        except Exception as e:
            logger.debug("failed to create psutil process handle: %s", e)
            self.process = None
        self._cleanup_callbacks = []

    def get_memory_mb(self) -> float:
        """Return current process USS memory in MB."""
        if not self.process:
            return 0.0
        try:
            return self.process.memory_full_info().uss / 1024 / 1024
        except Exception as e:
            logger.debug("failed to read memory info: %s", e)
            return 0.0

    def register_cleanup_callback(self, callback: Callable):
        """Register a cleanup callback.

        Callbacks may optionally accept one positional argument: the cleanup
        level ("light", "moderate", or "critical").
        """
        self._cleanup_callbacks.append(callback)

    def check_and_optimize(self) -> bool:
        """Run tiered cleanup if memory crosses a threshold."""
        mem = self.get_memory_mb()

        if mem > self.critical_mb:
            self._force_cleanup("critical")
            return True
        if mem > self.moderate_mb:
            self._force_cleanup("moderate")
            return True
        if mem > self.light_mb:
            self._force_cleanup("light")
            return True

        return False

    def _force_cleanup(self, level: str = "critical"):
        """Run cleanup callbacks and garbage collection for the requested level."""
        self._cleanup_icon_cache(level)

        for callback in self._cleanup_callbacks:
            try:
                try:
                    callback(level)
                except TypeError:
                    callback()
            except Exception as e:
                logger.debug("cleanup callback failed at %s level: %s", level, e)

        if level == "light":
            gc.collect(0)
        elif level == "moderate":
            gc.collect(1)
        else:
            gc.collect()

    def _cleanup_icon_cache(self, level: str):
        try:
            from core.icon_extractor import IconExtractor

            if level == "light":
                IconExtractor.clear_expired_cache()
            elif level == "moderate":
                IconExtractor.clear_expired_cache()
            else:
                IconExtractor.clear_cache()
        except Exception as e:
            logger.debug("icon cache cleanup failed: %s", e)

    def get_status(self) -> dict:
        """Return memory status."""
        mem = self.get_memory_mb()
        if mem > self.critical_mb:
            status = "critical"
        elif mem > self.moderate_mb:
            status = "moderate"
        elif mem > self.light_mb:
            status = "light"
        else:
            status = "normal"

        return {
            "current_mb": round(mem, 1),
            "light_mb": self.light_mb,
            "moderate_mb": self.moderate_mb,
            "critical_mb": self.critical_mb,
            "status": status,
        }
