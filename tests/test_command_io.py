from __future__ import annotations

from dataclasses import dataclass, field

from core.command_io import (
    CommandInvocationSnapshot,
    build_invocation_snapshot,
    build_output_artifact,
    chain_values_from_artifact,
    discover_input_variables,
    prepare_runtime_shortcut,
    remembered_args,
    resolve_param_default,
)
from core.command_registry import CommandDefinition, CommandParam, CommandResult
from core.data_models import ShortcutItem


def _handler(_context):
    return CommandResult()


@dataclass
class Request:
    command_id: str = "cmd"
    args_text: str = ""
    raw_input: str = "/cmd"
    context_meta: dict = field(default_factory=dict)
    source: str = "test"
    args: dict = field(default_factory=dict)


def test_invocation_masks_sensitive_and_sanitizes_context():
    command = CommandDefinition(
        id="cmd",
        title="Command",
        aliases=[],
        description="",
        category="test",
        handler=_handler,
        params=[
            CommandParam(name="token", sensitive=True),
            CommandParam(name="host"),
        ],
    )
    request = Request(
        args={"token": "secret", "host": "example.com"},
        context_meta={
            "clipboard_text": "secret clipboard",
            "clipboard_kind": "file_list",
            "clipboard_files": ["C:/clip/a.txt"],
            "clipboard_html": "<b>secret</b>",
            "selected_text": "secret selected",
            "selected_text_method": "uia",
            "selected_files": ["C:/tmp/a.txt"],
            "summary": "ok",
            "destructive_confirmed": True,
        },
    )
    snapshot = build_invocation_snapshot(request, command, None)
    assert snapshot.args["token"] == "secret"
    assert snapshot.masked_args["token"] == "******"
    assert snapshot.clipboard_kind == "file_list"
    assert snapshot.clipboard_files == ["C:/clip/a.txt"]
    assert snapshot.clipboard_html == "<b>secret</b>"
    assert snapshot.selected_text == "secret selected"
    assert snapshot.selected_text_method == "uia"
    assert snapshot.context_meta == {
        "clipboard_kind": "file_list",
        "clipboard_files": ["C:/clip/a.txt"],
        "selected_text_method": "uia",
        "selected_files": ["C:/tmp/a.txt"],
        "summary": "ok",
    }
    assert remembered_args(snapshot.args, command.params) == {"host": "example.com"}


def test_prepare_runtime_shortcut_clears_old_runtime_values():
    shortcut = ShortcutItem(name="Run")
    shortcut._runtime_param_values = {"old": "value"}
    shortcut._runtime_input_values = {"input": "old"}
    shortcut._destructive_command_confirmed = True
    snapshot = CommandInvocationSnapshot(
        args={"new": "value"},
        input_values={"input": "fresh"},
        selected_files=["C:/tmp/new.txt"],
        chain_values={"prev.output": "ok"},
    )

    runtime = prepare_runtime_shortcut(shortcut, snapshot)

    assert runtime is not shortcut
    assert runtime._runtime_param_values == {"new": "value"}
    assert runtime._runtime_input_values == {"input": "fresh"}
    assert runtime._runtime_selected_files == ["C:/tmp/new.txt"]
    assert runtime._chain_values == {"prev.output": "ok"}
    assert not hasattr(runtime, "_destructive_command_confirmed")
    assert shortcut._runtime_param_values == {"old": "value"}


def test_build_output_artifact_normalizes_outputs_and_table_values():
    result = CommandResult(
        success=True,
        message="done",
        display_type="table",
        payload={
            "columns": ["name", "value"],
            "rows": [["host", "example.com"], ["quoted", 'a,b "c"']],
            "outputs": {"host": "example.com", "nested": {"b": 2, "a": 1}},
        },
    )

    artifact = build_output_artifact(result)
    assert artifact.outputs["success"] == "true"
    assert artifact.outputs["host"] == "example.com"
    assert artifact.outputs["nested"] == '{"a":1,"b":2}'
    assert artifact.outputs["table.tsv"] == 'name\tvalue\nhost\texample.com\nquoted\ta,b "c"'
    assert artifact.outputs["table.csv"] == 'name,value\r\nhost,example.com\r\nquoted,"a,b ""c"""\r\n'


def test_chain_values_include_named_outputs_and_arrays():
    artifact = build_output_artifact(
        CommandResult(
            success=False,
            message="failed",
            error="boom",
            payload={"outputs": {"host": "example.com"}, "files": ["C:/a.txt"], "urls": ["https://example.com"]},
        )
    )
    values = chain_values_from_artifact(2, artifact)
    assert values["2.success"] == "false"
    assert values["prev.outputs.host"] == "example.com"
    assert values["prev.files.count"] == "1"
    assert values["prev.files.0"] == "C:/a.txt"
    assert values["prev.urls.0"] == "https://example.com"


def test_param_defaults_and_input_discovery():
    context = {
        "clipboard_text": "clip",
        "selected_text": "sel",
        "selected_files": ["C:/folder/file.txt"],
    }
    assert resolve_param_default(CommandParam(name="a", source="clipboard"), context_meta=context) == "clip"
    assert resolve_param_default(CommandParam(name="a", source="selected_text"), context_meta=context) == "sel"
    assert resolve_param_default(CommandParam(name="a", source="selected_file"), context_meta=context) == "C:/folder/file.txt"
    assert resolve_param_default(CommandParam(name="a", source="last"), last_args={"a": "last"}) == "last"
    assert discover_input_variables("echo {{input}} {{input:提示}} {{input:提示}}") == [
        ("input", ""),
        ("提示", "提示"),
    ]
