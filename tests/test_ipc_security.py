import json

from bootstrap.ipc import _parse_ipc_command


def test_ipc_command_requires_matching_token():
    payload = json.dumps({"token": "secret", "command": "show_config"}).encode("utf-8")

    assert _parse_ipc_command(payload, "secret") == "show_config"
    assert _parse_ipc_command(payload, "other") == ""


def test_ipc_rejects_legacy_plaintext_when_token_is_required():
    assert _parse_ipc_command(b"show_config", "secret") == ""


def test_ipc_rejects_unknown_command():
    payload = json.dumps({"token": "secret", "command": "reload_plugins"}).encode("utf-8")

    assert _parse_ipc_command(payload, "secret") == ""
