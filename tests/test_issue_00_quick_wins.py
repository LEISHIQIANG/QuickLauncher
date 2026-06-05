import json

from core.chain_processors import execute_chain_processor
from ui.tray_mixins.sleep_mixin import SleepMixin


class _Settings:
    sleep_mode_enabled = True
    sleep_timeout_seconds = 10
    hardware_acceleration = False


class _DataManager:
    def get_settings(self):
        return _Settings()


class _Timer:
    def __init__(self):
        self.started = []
        self.stopped = False

    def isActive(self):
        return False

    def start(self, interval=None):
        self.started.append(interval)

    def stop(self):
        self.stopped = True


class _SleepHarness(SleepMixin):
    def __init__(self):
        self.data_manager = _DataManager()
        self._sleep_timer = _Timer()
        self._sleeping = False
        self.popup_window = None
        self._extra_popup_windows = []
        self.config_window = None
        self.log_window = None
        self.command_panel_window = None
        self._mouse_paused_state = False
        self.cleanup_calls = 0

    def _perform_sleep_cleanup(self):
        self.cleanup_calls += 1

    def _stop_timer_if_active(self, timer_name):
        return None


def test_mark_activity_does_not_run_sleep_cleanup():
    harness = _SleepHarness()

    harness._mark_activity("test")

    assert harness.cleanup_calls == 0
    assert harness._sleep_timer.started == [10000]


def test_enter_light_sleep_runs_cleanup_once():
    harness = _SleepHarness()

    harness._enter_light_sleep()

    assert harness._sleeping is True
    assert harness.cleanup_calls == 1


def test_chain_http_get_blocks_private_ip(monkeypatch):
    def fail_urlopen(*args, **kwargs):
        raise AssertionError("blocked URL must not reach urlopen")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)

    result = execute_chain_processor("http_get", {"url": "http://127.0.0.1/latest/meta-data/"})

    assert result.success is False
    assert "blocked" in result.message


def test_chain_http_post_blocks_sensitive_headers(monkeypatch):
    def fail_urlopen(*args, **kwargs):
        raise AssertionError("blocked headers must not reach urlopen")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)

    result = execute_chain_processor(
        "http_post",
        {
            "url": "https://example.com",
            "headers": json.dumps({"Host": "169.254.169.254"}),
            "data": "{}",
        },
    )

    assert result.success is False
    assert "blocked sensitive request header" in result.message


def test_chain_all_merges_legacy_and_extra_exports():
    import core.chain as chain

    assert "definitions" in chain.__all__
    assert "execute_extended_processor" in chain.__all__
    assert len(chain.__all__) == len(set(chain.__all__))


def test_enhanced_file_processors_dispatch_through_file_module(tmp_path):
    src = tmp_path / "src.txt"
    dst = tmp_path / "nested" / "dst.txt"
    src.write_text("hello", encoding="utf-8")

    copy_result = execute_chain_processor(
        "file_copy",
        {"src": str(src), "dst": str(dst), "overwrite": "true"},
    )
    assert copy_result.success is True
    assert dst.read_text(encoding="utf-8") == "hello"

    size_result = execute_chain_processor("file_size", {"path": str(dst)})
    assert size_result.success is True
    assert size_result.payload["outputs"]["output"] == "5"

    list_result = execute_chain_processor("file_list_dir", {"path": str(dst.parent), "pattern": "*.txt"})
    assert list_result.success is True
    assert list_result.payload["raw_outputs"]["output"] == ["dst.txt"]

    delete_result = execute_chain_processor("file_delete", {"path": str(dst)})
    assert delete_result.success is True
    assert delete_result.payload["outputs"]["output"] == "true"
    assert not dst.exists()


def test_enhanced_json_processors_dispatch_through_structured_module():
    merge_result = execute_chain_processor("json_merge", {"a": '{"a":1}', "b": '{"b":2}'})
    assert merge_result.success is True
    assert merge_result.payload["outputs"]["output"] == '{"a":1,"b":2}'

    flatten_result = execute_chain_processor("json_flatten", {"json": '{"a":{"b":2}}', "separator": "."})
    assert flatten_result.success is True
    assert flatten_result.payload["outputs"]["output"] == '{"a.b":2}'

    keys_result = execute_chain_processor("json_keys", {"json": '{"a":1,"b":2}'})
    assert keys_result.success is True
    assert keys_result.payload["raw_outputs"]["output"] == ["a", "b"]

    values_result = execute_chain_processor("json_values", {"json": '{"a":1,"b":2}'})
    assert values_result.success is True
    assert values_result.payload["raw_outputs"]["output"] == ["1", "2"]

    length_result = execute_chain_processor("json_length", {"json": "[1,2,3]"})
    assert length_result.success is True
    assert length_result.payload["outputs"]["output"] == "3"


def test_hooks_reset_uninstalls_native_hooks():
    from hooks.hooks_wrapper import HooksDLL

    calls = []

    class FakeDLL:
        def UninstallMouseHook(self):
            calls.append("mouse")

        def UninstallKeyboardHook(self):
            calls.append("keyboard")

        def ClearGlobalHotkey(self):
            calls.append("hotkey")

    instance = object.__new__(HooksDLL)
    instance.dll = FakeDLL()
    instance.loaded = True
    instance.compatible = True

    HooksDLL._instance = instance
    HooksDLL._load_attempted = True
    HooksDLL.reset()

    assert calls == ["mouse", "keyboard", "hotkey"]
    assert HooksDLL._instance is None
    assert HooksDLL._load_attempted is False
