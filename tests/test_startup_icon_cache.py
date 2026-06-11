from types import SimpleNamespace

import ui.tray_mixins.startup_mixin as startup_mixin
from core import APP_VERSION
from ui.tray_mixins.startup_mixin import StartupMixin


def test_startup_icon_cache_audit_does_not_delete_icons_on_version_change(monkeypatch, tmp_path):
    calls = []

    def run_now(name, target, owner):
        calls.append((name, owner))
        target()

    class Manager:
        app_dir = tmp_path

        def __init__(self):
            self.clean_calls = []

        def get_icon_cache_stats(self):
            return {"invalid_size_mb": 32.0}

        def clean_icon_cache(self, dry_run=False):
            self.clean_calls.append(dry_run)
            return {}

    manager = Manager()
    (tmp_path / ".icon_cache_cleaned").write_text("old-version", encoding="utf-8")
    tray = SimpleNamespace(_sleeping=False, data_manager=manager)

    monkeypatch.setattr(startup_mixin, "start_background_thread", run_now)

    StartupMixin._clean_icon_cache_async(tray)

    assert calls == [("IconCacheCleaner", "startup")]
    assert manager.clean_calls == []
    assert (tmp_path / ".icon_cache_cleaned").read_text(encoding="utf-8") == APP_VERSION
