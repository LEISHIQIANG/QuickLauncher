"""Rate limiting for command execution."""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class CommandRateLimiter:
    """Token bucket rate limiter for command execution."""

    def __init__(
        self,
        global_limit: int = 100,
        per_shortcut_limit: int = 10,
        admin_limit: int = 5,
        window_seconds: int = 60,
    ):
        self.global_limit = global_limit
        self.per_shortcut_limit = per_shortcut_limit
        self.admin_limit = admin_limit
        self.window_seconds = window_seconds

        self._global_tokens: list[float] = []
        self._shortcut_tokens: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check_rate_limit(self, shortcut_id: str = "", is_admin: bool = False) -> tuple[bool, str]:
        """Check if command execution is allowed.

        Returns:
            (allowed, reason) - True if allowed, False with reason if blocked
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            self._global_tokens = [t for t in self._global_tokens if t > cutoff]

            if len(self._global_tokens) >= self.global_limit:
                return False, f"全局速率限制: {self.global_limit} 命令/分钟"

            if shortcut_id:
                self._shortcut_tokens[shortcut_id] = [t for t in self._shortcut_tokens[shortcut_id] if t > cutoff]

                limit = self.admin_limit if is_admin else self.per_shortcut_limit
                if len(self._shortcut_tokens[shortcut_id]) >= limit:
                    return False, f"快捷方式速率限制: {limit} 命令/分钟"

            return True, ""

    def record_execution(self, shortcut_id: str = "") -> None:
        """Record a command execution."""
        now = time.time()
        with self._lock:
            self._global_tokens.append(now)
            if shortcut_id:
                self._shortcut_tokens[shortcut_id].append(now)

    def get_remaining_quota(self, shortcut_id: str = "", is_admin: bool = False) -> int:
        """Get remaining quota for shortcut."""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            if shortcut_id:
                tokens = [t for t in self._shortcut_tokens.get(shortcut_id, []) if t > cutoff]
                limit = self.admin_limit if is_admin else self.per_shortcut_limit
                return max(0, limit - len(tokens))
            return max(0, self.global_limit - len([t for t in self._global_tokens if t > cutoff]))


_default_limiter: CommandRateLimiter | None = None
_limiter_lock = threading.Lock()


def get_rate_limiter() -> CommandRateLimiter:
    """Get or create default rate limiter."""
    global _default_limiter
    if _default_limiter is None:
        with _limiter_lock:
            if _default_limiter is None:
                _default_limiter = CommandRateLimiter()
    return _default_limiter
