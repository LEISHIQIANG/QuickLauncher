"""Application ports for Windows-owned capabilities."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol


class GlobalHotkeyPort(Protocol):
    def register(self, hotkey: str, callback: Callable[[], None]) -> object: ...

    def unregister(self, handle: object) -> None: ...

    def close(self) -> None: ...


class WindowPort(Protocol):
    def open_path(self, path: str | Path) -> None: ...

    def focus(self, native_handle: int) -> bool: ...


class IconProvider(Protocol):
    def extract(self, source: str | Path, *, size: int = 32) -> Any: ...

    def invalidate(self, source: str | Path) -> None: ...


class AutoStartPort(Protocol):
    def status(self) -> tuple[bool, str]: ...

    def enable(self) -> tuple[bool, str]: ...

    def disable(self) -> tuple[bool, str]: ...
