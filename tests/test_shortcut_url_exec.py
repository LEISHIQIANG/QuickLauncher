from urllib.error import URLError

import core.shortcut_url_exec as url_exec
from core.data_models import ShortcutItem, ShortcutType
from core.shortcut_url_exec import UrlExecutionMixin


def test_url_normalizes_missing_scheme():
    url, error = UrlExecutionMixin._prepare_url("example.com", {})

    assert error == ""
    assert url == "https://example.com"


def test_url_variables_are_url_encoded():
    url, error = UrlExecutionMixin._prepare_url(
        "https://google.com/search?q={{input}}",
        {"input": "中文 space"},
    )

    assert error == ""
    assert "中文" not in url
    assert "%E4%B8%AD%E6%96%87%20space" in url


def test_url_resolves_ip_variables(monkeypatch):
    monkeypatch.setattr(url_exec, "get_default_lan_ipv4", lambda: "192.168.1.20")
    monkeypatch.setattr(url_exec, "fetch_public_wan_ipv4", lambda: "203.0.113.9")

    url, error = UrlExecutionMixin._prepare_url("http://{{LAN_IP}}/wan/{{wan_ip}}", {})

    assert error == ""
    assert url == "http://192.168.1.20/wan/203.0.113.9"


def test_url_unknown_double_brace_variable_is_rejected():
    _, error = UrlExecutionMixin._prepare_url("https://example.com/{{unknown}}", {})

    assert error
    assert "{{unknown}}" in error


def test_url_escaped_double_braces_are_literal():
    url, error = UrlExecutionMixin._prepare_url("https://example.com/{{{{input}}}}", {"input": "abc"})

    assert error == ""
    assert url == "https://example.com/{{input}}"


def test_url_keeps_custom_deeplink_scheme():
    url, error = UrlExecutionMixin._prepare_url("obsidian://open?vault=Work", {})

    assert error == ""
    assert url.startswith("obsidian://")


def test_url_rejects_dangerous_scheme():
    _, error = UrlExecutionMixin._prepare_url("javascript:alert(1)", {})

    assert "不支持" in error


def test_url_uses_preferred_browser(monkeypatch, tmp_path):
    captured = {}
    browser = tmp_path / "browser.exe"
    browser.write_text("", encoding="utf-8")

    class FakeExecutor(UrlExecutionMixin):
        @staticmethod
        def _safe_split_args(args):
            return args.split()

        @staticmethod
        def _launch_with_privilege(target, parameters=None, directory=None, show_cmd=1, run_as_admin=False):
            captured["target"] = target
            captured["parameters"] = parameters
            captured["directory"] = directory
            return True, ""

    monkeypatch.setattr(url_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.URL)
    item.url = "example.com"
    item.preferred_browser_path = str(browser)
    item.preferred_browser_args = "--profile Default {{url}}"

    success, error = UrlExecutionMixin._execute_url(item)

    assert success
    assert error == ""
    assert captured["target"] == str(browser)
    assert "https://example.com" in captured["parameters"]
    assert "Default" in captured["parameters"]


def test_preferred_browser_args_resolve_ip_variables(monkeypatch, tmp_path):
    captured = {}
    browser = tmp_path / "browser.exe"
    browser.write_text("", encoding="utf-8")
    monkeypatch.setattr(url_exec, "get_default_lan_ipv4", lambda: "192.168.1.20")

    class FakeExecutor(UrlExecutionMixin):
        @staticmethod
        def _safe_split_args(args):
            return args.split()

        @staticmethod
        def _launch_with_privilege(target, parameters=None, directory=None, show_cmd=1, run_as_admin=False):
            captured["parameters"] = parameters
            return True, ""

    monkeypatch.setattr(url_exec, "ShortcutExecutor", FakeExecutor)

    item = ShortcutItem(type=ShortcutType.URL)
    item.url = "example.com"
    item.preferred_browser_path = str(browser)
    item.preferred_browser_args = "--host {{LAN_IP}} {{url}}"

    success, error = UrlExecutionMixin._execute_url(item)

    assert success
    assert error == ""
    assert "192.168.1.20" in captured["parameters"]


def test_elevated_normal_url_does_not_fallback_to_current_token(monkeypatch):
    class FakeExecutor(UrlExecutionMixin):
        @staticmethod
        def _launch_with_privilege(target, parameters=None, directory=None, show_cmd=1, run_as_admin=False):
            return False, ""

        @staticmethod
        def _is_launch_context_elevated():
            return True

    monkeypatch.setattr(url_exec, "ShortcutExecutor", FakeExecutor)
    monkeypatch.setattr(
        url_exec.webbrowser, "open", lambda url: (_ for _ in ()).throw(AssertionError("must not fallback"))
    )

    item = ShortcutItem(type=ShortcutType.URL)
    item.url = "example.com"
    item.run_as_admin = False

    success, error = UrlExecutionMixin._execute_url(item)

    assert success is False
    assert "privilege boundary" in error


def test_url_latency_fast_success_is_green(monkeypatch):
    class FakeResponse:
        def read(self, size=-1):
            return b""

        def close(self):
            pass

    monkeypatch.setattr(url_exec, "urlopen", lambda request, timeout=0: FakeResponse())
    values = iter([100.0, 100.12])
    monkeypatch.setattr(url_exec.time, "perf_counter", lambda: next(values))

    result = UrlExecutionMixin.test_url_latency("example.com")

    assert result["success"] is True
    assert result["latency_ms"] == 120
    assert result["color"] == "green"


def test_url_latency_slow_success_is_yellow(monkeypatch):
    class FakeResponse:
        def read(self, size=-1):
            return b""

        def close(self):
            pass

    monkeypatch.setattr(url_exec, "urlopen", lambda request, timeout=0: FakeResponse())
    values = iter([100.0, 101.2])
    monkeypatch.setattr(url_exec.time, "perf_counter", lambda: next(values))

    result = UrlExecutionMixin.test_url_latency("https://example.com")

    assert result["success"] is True
    assert result["latency_ms"] == 1200
    assert result["color"] == "yellow"


def test_url_latency_network_error_is_red_minus_one(monkeypatch):
    def fail(request, timeout=0):
        raise URLError("network unreachable")

    monkeypatch.setattr(url_exec, "urlopen", fail)

    result = UrlExecutionMixin.test_url_latency("https://example.com")

    assert result["success"] is False
    assert result["latency_ms"] == -1
    assert result["color"] == "red"
    assert result["error"]


def test_url_latency_non_http_scheme_is_red_minus_one():
    result = UrlExecutionMixin.test_url_latency("obsidian://open?vault=Work")

    assert result["success"] is False
    assert result["latency_ms"] == -1
    assert result["color"] == "red"
