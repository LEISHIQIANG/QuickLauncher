"""Application settings service.

Extracted from :class:`core.data_manager.DataManager` in 1.6.3.7 to isolate:

* :py:meth:`SettingsService.update` — diff-and-apply key/value updates onto
  :class:`AppSettings`, with trigger-settings normalization.
* :py:meth:`SettingsService.get` — defensive deep-copy of mutable list
  fields so callers cannot accidentally mutate the live settings.
* :py:meth:`SettingsService.set_language` — convenience wrapper that
  keeps the in-memory :func:`set_language` singleton in sync with the
  persisted setting.

Public API stays on :class:`DataManager`; this class is internal and may be
called directly by tests.
"""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any

from .data_models import AppSettings
from .i18n import normalize_language, set_language
from .trigger_config import normalize_trigger_settings

if TYPE_CHECKING:
    from .data_manager import DataManager

logger = logging.getLogger(__name__)

_HISTORY_DEFAULT = "\u914d\u7f6e\u53d8\u66f4"


class SettingsService:
    """High-level settings mutation and snapshot access."""

    def __init__(self, dm: DataManager) -> None:
        self._dm = dm

    def update(self, *, immediate: bool = True, **kwargs: Any) -> None:
        dm = self._dm
        with dm._save_lock:
            changed = False

            if any(key.startswith("popup_trigger_") or key.startswith("popup_special_trigger_") for key in kwargs):
                preview = copy.copy(dm.data.settings)
                for key, value in kwargs.items():
                    if hasattr(preview, key):
                        setattr(preview, key, value)
                kwargs = {**kwargs, **normalize_trigger_settings(preview)}

            for key, value in kwargs.items():
                if hasattr(dm.data.settings, key):
                    current_value = getattr(dm.data.settings, key)

                    if current_value is value:
                        if isinstance(value, list | dict | set):
                            changed = True
                        continue

                    if current_value == value:
                        continue

                    setattr(dm.data.settings, key, value)
                    changed = True

            if changed:
                dm._mark_history(_HISTORY_DEFAULT)
                dm.save(immediate=immediate)

    def get(self) -> AppSettings:
        """Return a defensive snapshot of :class:`AppSettings`."""
        dm = self._dm
        with dm._save_lock:
            set_language(getattr(dm.data.settings, "language", "zh_CN"))
            snapshot = copy.copy(dm.data.settings)
            # 深拷贝可变列表字段，防止调用者修改列表污染原始数据
            snapshot.enabled_plugins = list(snapshot.enabled_plugins)
            snapshot.favorite_commands = list(snapshot.favorite_commands)
            snapshot.disabled_builtin_commands = list(snapshot.disabled_builtin_commands)
            return snapshot

    def set_language(self, language: str, immediate: bool = True) -> str:
        """Set the application language without requiring a UI switch control."""
        dm = self._dm
        normalized = normalize_language(language)
        with dm._save_lock:
            if getattr(dm.data.settings, "language", "zh_CN") != normalized:
                dm.data.settings.language = normalized
                dm._mark_history(_HISTORY_DEFAULT)
                dm.save(immediate=immediate)
        set_language(normalized)
        return normalized


__all__ = ["SettingsService"]
