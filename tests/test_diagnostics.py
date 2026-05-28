import json
import zipfile

from core.config_recovery import ConfigRecoveryReport, write_recovery_report
from core.data_models import AppData, Folder, ShortcutItem
from core.diagnostics import collect_diagnostics, export_diagnostics_zip


class _Manager:
    def __init__(self, tmp_path):
        self.data = AppData(folders=[Folder(id="default", name="Default", items=[ShortcutItem(id="bad", name="Bad")])])
        self.app_dir = tmp_path
        self.icons_dir = tmp_path / "icons"
        self.icons_dir.mkdir()

    def get_config_status(self):
        return {"status": "ok", "source": "test", "issues": [], "recovery": self.get_recovery_report()}

    def get_recovery_report(self):
        report_path = self.app_dir / "recovery" / "recovery_state.json"
        if not report_path.exists():
            return {}
        return json.loads(report_path.read_text(encoding="utf-8"))

    def get_settings(self):
        return self.data.settings

    def get_icon_cache_stats(self):
        return {"total_files": 0, "total_size_mb": 0}


def test_collect_diagnostics_returns_core_sections(tmp_path):
    write_recovery_report(tmp_path / "recovery", ConfigRecoveryReport(status="ok", reason="test"))

    items = collect_diagnostics(_Manager(tmp_path))

    assert any(item.title == "Hook DLL" for item in items)
    assert any(item.title == "命令执行审计" for item in items)
    assert any(_json_details(item).get("status") == "ok" for item in items)


def test_export_diagnostics_zip_sanitizes_logs_and_includes_structured_state(tmp_path, monkeypatch):
    manager = _Manager(tmp_path)
    recovery_dir = tmp_path / "recovery"
    write_recovery_report(
        recovery_dir,
        ConfigRecoveryReport(status="recovered", reason="bad json", source_path=str(tmp_path / "data.json")),
    )
    home = tmp_path / "home"
    monkeypatch.setenv("USERPROFILE", str(home))
    (tmp_path / ".update_state.json").write_text('{"last_check": "2026-05-27T00:00:00"}', encoding="utf-8")
    update_session_dir = tmp_path / "downloads" / "updates" / "session-1"
    update_session_dir.mkdir(parents=True)
    (update_session_dir / "update_session.json").write_text(
        '{"session_id": "session-1", "status": "downloaded"}',
        encoding="utf-8",
    )
    (tmp_path / "plugin_errors.jsonl").write_text(
        "\n".join(json.dumps({"plugin_id": f"p{i}", "error": str(home)}) for i in range(250)),
        encoding="utf-8",
    )
    (tmp_path / "error.log").write_text(
        "\n".join(
            [
                f"ERROR path={home}\\secret",
                "Cookie: sessionid=abc123456; token=secret-token",
                "Authorization: Custom abc123456789",
                "GET https://example.test/callback?client_secret=supersecret&ok=1",
            ]
        ),
        encoding="utf-8",
    )
    export_path = tmp_path / "diag.zip"

    assert export_diagnostics_zip(manager, str(export_path))

    with zipfile.ZipFile(export_path) as zf:
        names = set(zf.namelist())
        assert {
            "manifest.json",
            "diagnostics.json",
            "recovery_state.json",
            "update_state.json",
            "update_session.json",
            "plugin_errors_tail.jsonl",
            "shortcut_health_summary.json",
            "error.log",
        } <= names
        error_log = zf.read("error.log").decode("utf-8")
        assert "<USER_HOME>" in error_log
        assert "abc123456" not in error_log
        assert "supersecret" not in error_log
        assert "Cookie: <REDACTED>" in error_log
        assert "Authorization: <REDACTED>" in error_log
        plugin_lines = zf.read("plugin_errors_tail.jsonl").decode("utf-8").splitlines()
        assert len(plugin_lines) == 200
        assert "p50" in plugin_lines[0]
        assert "<USER_HOME>" in plugin_lines[-1]
        diagnostics = json.loads(zf.read("diagnostics.json").decode("utf-8"))
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        shortcut_summary = json.loads(zf.read("shortcut_health_summary.json").decode("utf-8"))
        update_session = json.loads(zf.read("update_session.json").decode("utf-8"))
        redaction = json.loads(zf.read("redaction_report.json").decode("utf-8"))
        assert diagnostics["config_status"]["recovery"]["status"] == "recovered"
        assert manifest["limits"]["max_plugin_error_lines"] == 200
        assert shortcut_summary["total"] >= 1
        assert update_session["session_id"] == "session-1"
        assert redaction["cookie_header"] >= 1
        assert redaction["auth_header"] >= 1
        assert redaction["secret_param"] >= 1


def _json_details(item) -> dict:
    try:
        return json.loads(item.details)
    except Exception:
        return {}
