from types import SimpleNamespace

from bootstrap import startup_tasks


class _Logger:
    def __init__(self):
        self.messages = []

    def debug(self, message, *args, **_kwargs):
        self.messages.append(("debug", message % args if args else message))

    def info(self, message, *args, **_kwargs):
        self.messages.append(("info", message % args if args else message))

    def warning(self, message, *args, **_kwargs):
        self.messages.append(("warning", message % args if args else message))


def test_sync_frozen_autostart_logs_bad_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "data.json").write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr(startup_tasks, "is_packaged_runtime", lambda: True)
    logger = _Logger()

    startup_tasks.sync_frozen_autostart_from_config(str(tmp_path), logger)

    assert ("warning", f"读取自启动配置失败: {config_dir / 'data.json'}") in logger.messages


def test_sync_frozen_autostart_uses_config_value(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "data.json").write_text('{"settings": {"auto_start": true}}', encoding="utf-8")
    monkeypatch.setattr(startup_tasks, "is_packaged_runtime", lambda: True)
    calls = []

    import core.auto_start_manager as auto_start_manager

    monkeypatch.setattr(auto_start_manager, "_ensure_auto_start", lambda enabled: calls.append(enabled))

    startup_tasks.sync_frozen_autostart_from_config(str(tmp_path), _Logger())

    assert calls == [True]


def test_merge_default_special_apps_updates_and_writes_marker(tmp_path, monkeypatch):
    import core
    import core.data_models as data_models

    monkeypatch.setattr(core, "APP_VERSION", "9.9.9-test")
    monkeypatch.setattr(data_models, "DEFAULT_SPECIAL_APPS", ["a.exe", "b.exe"])
    updates = []
    data_manager = SimpleNamespace(
        app_dir=tmp_path,
        get_settings=lambda: SimpleNamespace(special_apps=["a.exe"]),
        update_settings=lambda **kwargs: updates.append(kwargs),
    )
    tray = SimpleNamespace(data_manager=data_manager)

    startup_tasks.merge_default_special_apps(tray, _Logger())

    assert updates == [{"special_apps": ["a.exe", "b.exe"]}]
    assert (tmp_path / ".special_apps_merged_version").read_text(encoding="utf-8") == "9.9.9-test"


def test_cleanup_stale_command_cache_logs_os_error(monkeypatch):
    from core.shortcut_command_exec import CommandExecutionMixin

    monkeypatch.setattr(CommandExecutionMixin, "_cleanup_cmd_cache", classmethod(lambda cls: (_ for _ in ()).throw(OSError("denied"))))
    logger = _Logger()

    startup_tasks.cleanup_stale_command_cache(logger)

    assert ("warning", "清理命令缓存目录失败") in logger.messages


def test_process_startup_events_ignores_qt_runtime_error():
    app = SimpleNamespace(processEvents=lambda: (_ for _ in ()).throw(RuntimeError("deleted")))
    logger = _Logger()

    startup_tasks.process_startup_events(app, logger)

    assert ("debug", "启动事件处理失败: deleted") in logger.messages


def test_sync_autostart_setting_from_task_enables_config(monkeypatch):
    import core.auto_start_manager as auto_start_manager

    monkeypatch.setattr(startup_tasks, "is_packaged_runtime", lambda: True)
    monkeypatch.setattr(auto_start_manager, "get_auto_start_check_result", lambda: (True, "ok"))
    updates = []
    tray = SimpleNamespace(
        data_manager=SimpleNamespace(
            get_settings=lambda: SimpleNamespace(auto_start=False),
            update_settings=lambda **kwargs: updates.append(kwargs),
        )
    )

    startup_tasks.sync_autostart_setting_from_task(tray, _Logger())

    assert updates == [{"auto_start": True}]


def test_sync_autostart_setting_from_task_disables_stale_config(monkeypatch):
    import core.auto_start_manager as auto_start_manager

    monkeypatch.setattr(startup_tasks, "is_packaged_runtime", lambda: True)
    monkeypatch.setattr(auto_start_manager, "get_auto_start_check_result", lambda: (False, "missing"))
    updates = []
    tray = SimpleNamespace(
        data_manager=SimpleNamespace(
            get_settings=lambda: SimpleNamespace(auto_start=True),
            update_settings=lambda **kwargs: updates.append(kwargs),
        )
    )

    startup_tasks.sync_autostart_setting_from_task(tray, _Logger())

    assert updates == [{"auto_start": False}]
