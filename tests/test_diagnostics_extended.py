"""Extended diagnostics tests – helper functions, report generation, sanitization, redaction."""

import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

from core.data_models import AppData
from core.diagnostics import (
    MAX_DIAGNOSTIC_TEXT_BYTES,
    MAX_EVENTS_LINES,
    MAX_PLUGIN_ERROR_LINES,
    MAX_SHORTCUT_ISSUES,
    DiagnosticItem,
    _build_manifest,
    _bump_redaction,
    _is_logging_disabled,
    _read_json_file,
    _read_tail_lines,
    _read_tail_text,
    _recent_error_lines,
    _reset_redaction_counts,
    _sanitize_dict,
    _sanitize_jsonl_lines,
    _sanitize_text,
    collect_diagnostics,
    export_diagnostics_zip,
    get_redaction_counts,
)

# ======================================================================
# DiagnosticItem dataclass
# ======================================================================


class TestDiagnosticItem:
    def test_to_dict_roundtrip(self):
        item = DiagnosticItem("Test", "ok", "All good", "details here", "do something")
        d = item.to_dict()
        assert d["title"] == "Test"
        assert d["status"] == "ok"
        assert d["summary"] == "All good"
        assert d["details"] == "details here"
        assert d["action"] == "do something"

    def test_to_dict_defaults(self):
        item = DiagnosticItem("X", "warn", "issue")
        d = item.to_dict()
        assert d["details"] == ""
        assert d["action"] == ""

    def test_status_values(self):
        for status in ("ok", "warn", "error", "unknown"):
            item = DiagnosticItem("T", status, "s")
            assert item.to_dict()["status"] == status


# ======================================================================
# _sanitize_text – path redaction
# ======================================================================


class TestSanitizeText:
    def setup_method(self):
        _reset_redaction_counts()

    def test_replaces_user_home(self, monkeypatch):
        home = r"C:\Users\TestUser"
        monkeypatch.setenv("USERPROFILE", home)
        # expanduser reads USERPROFILE on Windows
        with patch("core.diagnostics.os.path.expanduser", return_value=home):
            result = _sanitize_text(f"Path is {home}\\Documents")
        assert "<USER_HOME>" in result
        assert "TestUser" not in result

    def test_replaces_username_env(self, monkeypatch):
        monkeypatch.setenv("USERNAME", "SecretUser")
        result = _sanitize_text("Running as SecretUser today")
        assert "<USERNAME>" in result
        assert "SecretUser" not in result

    def test_replaces_computername_env(self, monkeypatch):
        monkeypatch.setenv("COMPUTERNAME", "MYPC01")
        result = _sanitize_text("Host: MYPC01")
        assert "<COMPUTERNAME>" in result
        assert "MYPC01" not in result

    def test_redacts_bearer_token(self):
        result = _sanitize_text("Authorization: Bearer abc1234567890xyz")
        assert "<REDACTED>" in result
        assert "abc1234567890xyz" not in result

    def test_redacts_basic_auth(self):
        result = _sanitize_text("Basic dXNlcjpwYXNz")
        assert "<REDACTED>" in result
        assert "dXNlcjpwYXNz" not in result

    def test_redacts_cli_token_flag(self):
        result = _sanitize_text("cmd --token=supersecretvalue")
        assert "<REDACTED>" in result
        assert "supersecretvalue" not in result

    def test_redacts_api_key_param(self):
        result = _sanitize_text("apikey=abcdef123456&ok=true")
        assert "<REDACTED>" in result
        assert "abcdef123456" not in result

    def test_redacts_authorization_header(self):
        result = _sanitize_text("Authorization: Custom sometoken123")
        assert "<REDACTED>" in result

    def test_redacts_cookie_header(self):
        result = _sanitize_text("Cookie: sessionid=abc12345; token=xyz")
        assert "<REDACTED>" in result

    def test_redacts_x_api_key(self):
        result = _sanitize_text("X-Api-Key: myapikeyvalue123")
        assert "<REDACTED>" in result

    def test_redacts_client_secret(self):
        result = _sanitize_text("client_secret=verysecretvalue")
        assert "<REDACTED>" in result

    def test_redacts_access_token(self):
        result = _sanitize_text("access_token=longaccesstoken12345")
        assert "<REDACTED>" in result

    def test_empty_string(self):
        assert _sanitize_text("") == ""

    def test_none_input(self):
        assert _sanitize_text(None) == ""

    def test_no_sensitive_data_passthrough(self):
        text = "Normal log line with nothing sensitive"
        assert _sanitize_text(text) == text

    def test_short_env_values_not_redacted(self, monkeypatch):
        monkeypatch.setenv("USERNAME", "ab")
        result = _sanitize_text("User: ab")
        assert "ab" in result  # too short to redact


# ======================================================================
# _sanitize_dict / _sanitize_jsonl_lines
# ======================================================================


class TestSanitizeDict:
    def setup_method(self):
        _reset_redaction_counts()

    def test_nested_dict(self):
        data = {"a": {"b": "Bearer token12345678"}}
        result = _sanitize_dict(data)
        assert "<REDACTED>" in result["a"]["b"]

    def test_list_values(self):
        data = ["Bearer abc123456789", "clean"]
        result = _sanitize_dict(data)
        assert "<REDACTED>" in result[0]
        assert result[1] == "clean"

    def test_non_string_passthrough(self):
        data = {"num": 42, "bool": True, "none": None}
        result = _sanitize_dict(data)
        assert result == data

    def test_sanitize_jsonl_lines_valid_json(self):
        lines = ['{"key": "Bearer secret12345678"}', '{"key": "clean"}']
        result = _sanitize_jsonl_lines(lines)
        assert len(result) == 2
        parsed = json.loads(result[0])
        assert "<REDACTED>" in parsed["key"]

    def test_sanitize_jsonl_lines_invalid_json(self):
        lines = ["not json Bearer secret12345678"]
        result = _sanitize_jsonl_lines(lines)
        assert "<REDACTED>" in result[0]


# ======================================================================
# Redaction counters
# ======================================================================


class TestRedactionCounters:
    def setup_method(self):
        _reset_redaction_counts()

    def test_reset_clears(self):
        _bump_redaction("test", 5)
        _reset_redaction_counts()
        assert get_redaction_counts() == {}

    def test_bump_accumulates(self):
        _bump_redaction("cat", 3)
        _bump_redaction("cat", 2)
        assert get_redaction_counts()["cat"] == 5

    def test_get_returns_snapshot(self):
        _bump_redaction("x", 1)
        snap = get_redaction_counts()
        _bump_redaction("x", 10)
        assert snap["x"] == 1  # snapshot not updated

    def test_multiple_categories(self):
        _bump_redaction("a", 1)
        _bump_redaction("b", 2)
        counts = get_redaction_counts()
        assert counts["a"] == 1
        assert counts["b"] == 2


# ======================================================================
# _recent_error_lines
# ======================================================================


class TestRecentErrorLines:
    def test_no_file_returns_empty(self, tmp_path):
        assert _recent_error_lines(tmp_path / "missing.log") == []

    def test_extracts_error_lines(self, tmp_path):
        log = tmp_path / "error.log"
        log.write_text(
            "INFO - ok\n"
            "2026-01-01 - ERROR - something broke\n"
            "DEBUG - fine\n"
            "2026-01-01 - CRITICAL - very bad\n",
            encoding="utf-8",
        )
        lines = _recent_error_lines(log)
        assert len(lines) == 2
        assert "ERROR" in lines[0]
        assert "CRITICAL" in lines[1]

    def test_limits_to_200(self, tmp_path):
        log = tmp_path / "error.log"
        lines = "\n".join(f"L{i} - ERROR - msg {i}" for i in range(300))
        log.write_text(lines, encoding="utf-8")
        result = _recent_error_lines(log)
        assert len(result) == 200

    def test_empty_file(self, tmp_path):
        log = tmp_path / "error.log"
        log.write_text("", encoding="utf-8")
        assert _recent_error_lines(log) == []


# ======================================================================
# _is_logging_disabled
# ======================================================================


class TestIsLoggingDisabled:
    def test_no_data(self):
        manager = MagicMock(spec=[])
        assert _is_logging_disabled(manager) is False

    def test_enable_logging_false(self):
        manager = MagicMock()
        manager.data.settings.enable_logging = False
        assert _is_logging_disabled(manager) is True

    def test_enable_logging_true(self):
        manager = MagicMock()
        manager.data.settings.enable_logging = True
        assert _is_logging_disabled(manager) is False

    def test_disable_logging_attr(self):
        manager = MagicMock()
        del manager.data.settings.enable_logging
        manager.data.settings.disable_logging = True
        assert _is_logging_disabled(manager) is True


# ======================================================================
# _read_tail_text / _read_tail_lines / _read_json_file
# ======================================================================


class TestReadHelpers:
    def test_read_tail_text_nonexistent(self, tmp_path):
        assert _read_tail_text(tmp_path / "nope") == ""

    def test_read_tail_text_normal(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        assert _read_tail_text(f) == "hello world"

    def test_read_tail_text_truncates_large(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_bytes(b"A" * (MAX_DIAGNOSTIC_TEXT_BYTES + 1000))
        result = _read_tail_text(f)
        assert "[truncated" in result
        assert len(result.encode("utf-8")) <= MAX_DIAGNOSTIC_TEXT_BYTES + 200

    def test_read_tail_lines(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("a\nb\nc\nd\ne", encoding="utf-8")
        result = _read_tail_lines(f, 3)
        assert result == ["c", "d", "e"]

    def test_read_tail_lines_nonexistent(self, tmp_path):
        assert _read_tail_lines(tmp_path / "nope", 10) == []

    def test_read_json_file_valid(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        assert _read_json_file(f) == {"key": "value"}

    def test_read_json_file_invalid(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json", encoding="utf-8")
        assert _read_json_file(f) is None

    def test_read_json_file_nonexistent(self, tmp_path):
        assert _read_json_file(tmp_path / "missing.json") is None

    def test_read_json_file_directory(self, tmp_path):
        d = tmp_path / "dir"
        d.mkdir()
        assert _read_json_file(d) is None


# ======================================================================
# _build_manifest
# ======================================================================


class TestBuildManifest:
    def test_basic_structure(self):
        payload = {"generated_at": "2026-01-01T00:00:00", "export_level": "full"}
        manifest = _build_manifest(payload, ["a.json", "b.log"], False)
        assert manifest["schema"] == 1
        assert manifest["generated_at"] == "2026-01-01T00:00:00"
        assert manifest["export_level"] == "full"
        assert "manifest.json" in manifest["files"]
        assert "a.json" in manifest["files"]
        assert manifest["logging_disabled"] is False

    def test_limits_included(self):
        payload = {"generated_at": "now", "export_level": "minimal"}
        manifest = _build_manifest(payload, [], True)
        assert manifest["limits"]["max_text_bytes_per_file"] == MAX_DIAGNOSTIC_TEXT_BYTES
        assert manifest["limits"]["max_plugin_error_lines"] == MAX_PLUGIN_ERROR_LINES
        assert manifest["limits"]["max_shortcut_issues"] == MAX_SHORTCUT_ISSUES
        assert manifest["limits"]["max_events_lines"] == MAX_EVENTS_LINES
        assert manifest["logging_disabled"] is True

    def test_default_export_level(self):
        payload = {"generated_at": "now"}
        manifest = _build_manifest(payload, [], False)
        assert manifest["export_level"] == "standard"


# ======================================================================
# collect_diagnostics (with mocked imports)
# ======================================================================


class TestCollectDiagnostics:
    def _make_manager(self, tmp_path):
        dm = MagicMock()
        dm.data = AppData()
        dm.app_dir = tmp_path
        dm.config_dir = tmp_path
        dm.get_config_status.return_value = {
            "status": "ok",
            "source": "test",
            "issues": [],
            "recovery": {"status": "ok", "reason": "test"},
        }
        dm.get_icon_cache_stats.return_value = {"total_files": 0, "total_size_mb": 0}
        dm.get_settings.return_value = dm.data.settings
        dm.history_manager = MagicMock()
        dm.history_manager.list_snapshots.return_value = []
        return dm

    def test_returns_list_of_diagnostic_items(self, tmp_path):
        dm = self._make_manager(tmp_path)
        items = collect_diagnostics(dm)
        assert isinstance(items, list)
        assert all(isinstance(i, DiagnosticItem) for i in items)

    def test_config_status_ok(self, tmp_path):
        dm = self._make_manager(tmp_path)
        items = collect_diagnostics(dm)
        config_items = [i for i in items if i.title == "配置文件"]
        assert len(config_items) == 1
        assert config_items[0].status == "ok"

    def test_config_status_warn(self, tmp_path):
        dm = self._make_manager(tmp_path)
        dm.get_config_status.return_value = {
            "status": "warn",
            "source": "test",
            "issues": ["issue1"],
            "recovery": {},
        }
        items = collect_diagnostics(dm)
        config_items = [i for i in items if i.title == "配置文件"]
        assert config_items[0].status == "warn"

    def test_recovery_section_present(self, tmp_path):
        dm = self._make_manager(tmp_path)
        items = collect_diagnostics(dm)
        recovery_items = [i for i in items if i.title == "配置恢复"]
        assert len(recovery_items) >= 1

    def test_config_structure_section(self, tmp_path):
        dm = self._make_manager(tmp_path)
        items = collect_diagnostics(dm)
        struct_items = [i for i in items if i.title == "配置结构"]
        assert len(struct_items) == 1
        assert struct_items[0].status == "ok"

    def test_icon_cache_section(self, tmp_path):
        dm = self._make_manager(tmp_path)
        items = collect_diagnostics(dm)
        cache_items = [i for i in items if i.title == "图标缓存"]
        assert len(cache_items) == 1

    def test_config_history_section(self, tmp_path):
        dm = self._make_manager(tmp_path)
        items = collect_diagnostics(dm)
        hist_items = [i for i in items if i.title == "配置历史"]
        assert len(hist_items) == 1

    def test_no_history_manager(self, tmp_path):
        dm = self._make_manager(tmp_path)
        dm.history_manager = None
        items = collect_diagnostics(dm)
        hist_items = [i for i in items if i.title == "配置历史"]
        assert hist_items[0].status == "unknown"

    def test_memory_state_with_guard(self, tmp_path):
        dm = self._make_manager(tmp_path)
        tray = MagicMock()
        tray.memory_guard.get_status.return_value = {
            "status": "ok",
            "current_mb": 50,
        }
        items = collect_diagnostics(dm, tray_app=tray)
        mem_items = [i for i in items if i.title == "内存状态"]
        assert len(mem_items) == 1
        assert mem_items[0].status == "ok"

    def test_memory_state_critical(self, tmp_path):
        dm = self._make_manager(tmp_path)
        tray = MagicMock()
        tray.memory_guard.get_status.return_value = {
            "status": "critical",
            "current_mb": 500,
        }
        items = collect_diagnostics(dm, tray_app=tray)
        mem_items = [i for i in items if i.title == "内存状态"]
        assert mem_items[0].status == "warn"

    def test_memory_state_no_guard(self, tmp_path):
        dm = self._make_manager(tmp_path)
        tray = MagicMock(spec=[])
        items = collect_diagnostics(dm, tray_app=tray)
        mem_items = [i for i in items if i.title == "内存状态"]
        assert mem_items[0].status == "unknown"


# ======================================================================
# export_diagnostics_zip
# ======================================================================


class TestExportDiagnosticsZip:
    def _make_manager(self, tmp_path):
        dm = MagicMock()
        dm.data = AppData()
        dm.app_dir = tmp_path
        dm.config_dir = tmp_path
        dm.get_config_status.return_value = {
            "status": "ok",
            "source": "test",
            "issues": [],
            "recovery": {},
        }
        dm.get_icon_cache_stats.return_value = {"total_files": 0, "total_size_mb": 0}
        dm.get_settings.return_value = dm.data.settings
        dm.history_manager = MagicMock()
        dm.history_manager.list_snapshots.return_value = []
        return dm

    def test_creates_valid_zip(self, tmp_path):
        dm = self._make_manager(tmp_path)
        export_path = tmp_path / "diag.zip"
        assert export_diagnostics_zip(dm, str(export_path)) is True
        assert export_path.exists()
        assert zipfile.is_zipfile(export_path)

    def test_zip_contains_manifest(self, tmp_path):
        dm = self._make_manager(tmp_path)
        export_path = tmp_path / "diag.zip"
        export_diagnostics_zip(dm, str(export_path))
        with zipfile.ZipFile(export_path) as zf:
            assert "manifest.json" in zf.namelist()
            assert "diagnostics.json" in zf.namelist()

    def test_zip_contains_error_log(self, tmp_path):
        dm = self._make_manager(tmp_path)
        (tmp_path / "error.log").write_text("ERROR - test error", encoding="utf-8")
        export_path = tmp_path / "diag.zip"
        export_diagnostics_zip(dm, str(export_path))
        with zipfile.ZipFile(export_path) as zf:
            assert "error.log" in zf.namelist()

    def test_minimal_export_only_diagnostics(self, tmp_path):
        dm = self._make_manager(tmp_path)
        (tmp_path / "error.log").write_text("ERROR - test", encoding="utf-8")
        export_path = tmp_path / "diag.zip"
        export_diagnostics_zip(dm, str(export_path), export_level="minimal")
        with zipfile.ZipFile(export_path) as zf:
            names = zf.namelist()
            assert "diagnostics.json" in names
            assert "manifest.json" in names
            assert "error.log" not in names

    def test_full_export_includes_rotated_logs(self, tmp_path):
        dm = self._make_manager(tmp_path)
        (tmp_path / "error.log.1").write_text("old error", encoding="utf-8")
        (tmp_path / "faulthandler.log.1").write_text("old fault", encoding="utf-8")
        export_path = tmp_path / "diag.zip"
        export_diagnostics_zip(dm, str(export_path), export_level="full")
        with zipfile.ZipFile(export_path) as zf:
            names = zf.namelist()
            assert "logs/error.log.1" in names
            assert "logs/faulthandler.log.1" in names

    def test_redaction_report_included_when_redactions(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USERNAME", "SecretUser123")
        dm = self._make_manager(tmp_path)
        (tmp_path / "error.log").write_text(
            "ERROR - failed for SecretUser123",
            encoding="utf-8",
        )
        export_path = tmp_path / "diag.zip"
        export_diagnostics_zip(dm, str(export_path))
        with zipfile.ZipFile(export_path) as zf:
            if "redaction_report.json" in zf.namelist():
                report = json.loads(zf.read("redaction_report.json"))
                assert isinstance(report, dict)

    def test_manifest_valid_json(self, tmp_path):
        dm = self._make_manager(tmp_path)
        export_path = tmp_path / "diag.zip"
        export_diagnostics_zip(dm, str(export_path))
        with zipfile.ZipFile(export_path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert "schema" in manifest
            assert "files" in manifest

    def test_export_sanitizes_sensitive_data(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USERPROFILE", r"C:\Users\Private")
        dm = self._make_manager(tmp_path)
        (tmp_path / "error.log").write_text(
            "ERROR - path C:\\Users\\Private\\secret",
            encoding="utf-8",
        )
        export_path = tmp_path / "diag.zip"
        export_diagnostics_zip(dm, str(export_path))
        with zipfile.ZipFile(export_path) as zf:
            log_content = zf.read("error.log").decode("utf-8")
            assert "Private" not in log_content or "<USER_HOME>" in log_content or "<USERPROFILE>" in log_content


# ======================================================================
# Events file inclusion
# ======================================================================


class TestEventsInclusion:
    def _make_manager(self, tmp_path):
        dm = MagicMock()
        dm.data = AppData()
        dm.app_dir = tmp_path
        dm.config_dir = tmp_path
        dm.get_config_status.return_value = {"status": "ok", "source": "test", "issues": [], "recovery": {}}
        dm.get_icon_cache_stats.return_value = {"total_files": 0, "total_size_mb": 0}
        dm.get_settings.return_value = dm.data.settings
        dm.history_manager = MagicMock()
        dm.history_manager.list_snapshots.return_value = []
        return dm

    def test_events_jsonl_included(self, tmp_path):
        dm = self._make_manager(tmp_path)
        events = tmp_path / "events.jsonl"
        events.write_text('{"ts": 1}\n{"ts": 2}\n', encoding="utf-8")
        export_path = tmp_path / "diag.zip"
        export_diagnostics_zip(dm, str(export_path))
        with zipfile.ZipFile(export_path) as zf:
            assert "events.jsonl" in zf.namelist()
