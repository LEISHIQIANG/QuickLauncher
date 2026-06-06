from __future__ import annotations

from core.action_executor import ActionExecutionContext, execute_command_action
from core.command_action_safety import sanitize_command_actions
from core.command_registry import CommandAction, CommandResult
from core.command_result_actions import enrich_result_actions


def test_enrich_result_actions_keeps_manual_actions_and_adds_log_actions():
    result = CommandResult(
        success=True,
        message="ok",
        display_type="log",
        payload={"stdout": "out", "stderr": "err", "command": "echo ok"},
        actions=[CommandAction(type="copy", label="复制自定义", value="manual", primary=True)],
    )

    enriched = enrich_result_actions(result)
    labels = [action.label for action in enriched.actions]
    assert labels[0] == "复制自定义"
    assert "复制 stdout" in labels
    assert "复制 stderr" in labels
    assert "复制命令" in labels


def test_enrich_result_actions_adds_table_and_json_save_actions():
    table = enrich_result_actions(
        CommandResult(
            success=True,
            message="",
            display_type="table",
            payload={"columns": ["a"], "rows": [['b,c "d"']]},
        )
    )
    save_csv = next(action for action in table.actions if action.type == "save_csv")
    assert save_csv.value == 'a\r\n"b,c ""d"""\r\n'
    assert any(action.label == "复制 TSV" for action in table.actions)

    json_result = enrich_result_actions(
        CommandResult(
            success=True,
            message="",
            display_type="json",
            payload={"data": {"b": 2, "a": 1}},
        )
    )
    assert any(action.type == "save_json" for action in json_result.actions)
    assert any(action.label == "复制压缩 JSON" for action in json_result.actions)


def test_action_sanitizer_filters_unsafe_urls_and_paths(tmp_path):
    file_path = tmp_path / "out.txt"
    file_path.write_text("ok", encoding="utf-8")
    folder_path = tmp_path / "folder"
    folder_path.mkdir()

    actions = sanitize_command_actions(
        [
            CommandAction(type="open_url", label="Bad", value="javascript:alert(1)"),
            CommandAction(type="open_url", label="Good", value="https://example.com"),
            CommandAction(type="open_file", label="Missing", value=str(tmp_path / "missing.txt")),
            CommandAction(type="open_file", label="File", value=str(file_path)),
            CommandAction(type="open_folder", label="Folder", value=str(folder_path)),
            CommandAction(type="unknown", label="Unknown", value="x"),
        ]
    )

    assert [(action.type, action.label) for action in actions] == [
        ("open_url", "Good"),
        ("open_file", "File"),
        ("open_folder", "Folder"),
    ]


def test_enrich_result_actions_does_not_mutate_original_and_filters_missing_files(tmp_path):
    result = CommandResult(message="ok", payload={"files": [str(tmp_path / "missing.txt")]})

    enriched = enrich_result_actions(result)

    assert result.actions == []
    assert any(action.label == "复制全部" for action in enriched.actions)
    assert not any(action.type == "open_file" for action in enriched.actions)


def test_action_executor_copies_and_audits(monkeypatch):
    copied = {}
    events = []
    monkeypatch.setattr("core.event_log.log_event", lambda event, message, payload: events.append((event, payload)))

    ok = execute_command_action(
        CommandAction(type="copy", label="Copy", value="hello"),
        ActionExecutionContext(source="test", set_clipboard_text=lambda text: copied.setdefault("text", text)),
    )

    assert ok
    assert copied["text"] == "hello"
    assert events[-1][0] == "command.action"
    assert events[-1][1]["source"] == "test"
    assert events[-1][1]["ok"] is True


def test_action_executor_open_url_uses_single_core_path(monkeypatch):
    opened = {}
    monkeypatch.setattr("core.action_executor.webbrowser.open", lambda url: opened.setdefault("url", url))

    ok = execute_command_action(CommandAction(type="open_url", label="Open", value="https://example.com"))

    assert ok
    assert opened["url"] == "https://example.com"


def test_action_executor_saves_text_and_files(tmp_path):
    saved_text = tmp_path / "result.txt"
    source_file = tmp_path / "source.txt"
    copied_file = tmp_path / "copied.txt"
    source_file.write_text("source", encoding="utf-8")
    paths = iter([str(saved_text), str(copied_file)])

    context = ActionExecutionContext(save_file_dialog=lambda *_args: (next(paths), ""))

    assert execute_command_action(CommandAction(type="save_text", label="Save", value="hello"), context)
    assert saved_text.read_text(encoding="utf-8") == "hello"
    assert execute_command_action(CommandAction(type="save_file", label="Save file", value=str(source_file)), context)
    assert copied_file.read_text(encoding="utf-8") == "source"
