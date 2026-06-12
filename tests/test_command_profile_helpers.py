from ui.config_window.command_profile_helpers import (
    format_command_env,
    format_command_params,
    parse_command_env_text,
    parse_command_params_text,
)


def test_parse_command_params_text_normalizes_rows():
    params = parse_command_params_text(
        """
        # comment
        host,choice,required,prod,prod|stage|
        flag,bool,yes,true,
        ignored,
        path,unknown,false,,
        """
    )

    assert [
        (param["name"], param["type"], param["required"], param["default"], param["choices"]) for param in params
    ] == [
        ("host", "choice", True, "prod", ["prod", "stage"]),
        ("flag", "bool", True, "true", []),
        ("ignored", "text", False, "", []),
        ("path", "text", False, "", []),
    ]


def test_parse_command_params_text_skips_empty_names_and_supports_chinese_required():
    params = parse_command_params_text(
        """
        ,text,true,,
        user,text,必填,guest,
        """
    )

    assert [(param["name"], param["type"], param["required"], param["default"]) for param in params] == [
        ("user", "text", True, "guest")
    ]


def test_format_command_params_round_trips_normalized_shape():
    text = format_command_params(
        [
            {
                "name": "host",
                "type": "choice",
                "required": True,
                "default": "prod",
                "choices": ["prod", "stage"],
            },
            {"name": "flag", "type": "bool", "required": False, "default": "false"},
        ]
    )

    assert text == "host,choice,true,prod,prod|stage\nflag,bool,false,false,"


def test_parse_and_format_command_env_text():
    assert (
        parse_command_env_text(
            """
        # ignored
        API_KEY = secret
        BAD_LINE
        EMPTY=
        """
        )
        == {"API_KEY": "secret", "EMPTY": ""}
    )
    assert format_command_env({"A": 1, " B ": "two", "": "skip", "C": None}) == "A=1\n B =two\nC=None"
    assert format_command_env(["not", "dict"]) == ""


def test_parse_and_format_command_params_json_lines():
    text = format_command_params(
        [
            {
                "name": "body",
                "type": "textarea",
                "label": "Body",
                "source": "clipboard",
                "validator": "json",
                "multiline": True,
            }
        ]
    )

    assert text.startswith("{")
    parsed = parse_command_params_text(text)
    assert parsed[0]["name"] == "body"
    assert parsed[0]["type"] == "textarea"
    assert parsed[0]["label"] == "Body"
    assert parsed[0]["source"] == "clipboard"
    assert parsed[0]["validator"] == "json"
    assert parsed[0]["multiline"] is True


def test_command_dialog_static_helpers_delegate_to_profile_helpers():
    from ui.config_window.command_dialog import CommandDialog

    params = [{"name": "host", "type": "text", "required": True}]

    assert CommandDialog._format_command_params(params) == format_command_params(params)
    assert CommandDialog._parse_env_text("A=1") == {"A": "1"}
    assert CommandDialog._format_env({"A": "1"}) == "A=1"
