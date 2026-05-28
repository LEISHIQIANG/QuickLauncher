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

    assert params == [
        {
            "name": "host",
            "type": "choice",
            "required": True,
            "default": "prod",
            "choices": ["prod", "stage"],
            "sensitive": False,
        },
        {
            "name": "flag",
            "type": "bool",
            "required": True,
            "default": "true",
            "choices": [],
            "sensitive": False,
        },
        {
            "name": "ignored",
            "type": "text",
            "required": False,
            "default": "",
            "choices": [],
            "sensitive": False,
        },
        {
            "name": "path",
            "type": "text",
            "required": False,
            "default": "",
            "choices": [],
            "sensitive": False,
        },
    ]


def test_parse_command_params_text_skips_empty_names_and_supports_chinese_required():
    params = parse_command_params_text(
        """
        ,text,true,,
        user,text,必填,guest,
        """
    )

    assert params == [
        {
            "name": "user",
            "type": "text",
            "required": True,
            "default": "guest",
            "choices": [],
            "sensitive": False,
        }
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
    assert parse_command_env_text(
        """
        # ignored
        API_KEY = secret
        BAD_LINE
        EMPTY=
        """
    ) == {"API_KEY": "secret", "EMPTY": ""}
    assert format_command_env({"A": 1, " B ": "two", "": "skip", "C": None}) == "A=1\n B =two\nC=None"
    assert format_command_env(["not", "dict"]) == ""


def test_command_dialog_static_helpers_delegate_to_profile_helpers():
    from ui.config_window.command_dialog import CommandDialog

    params = [{"name": "host", "type": "text", "required": True}]

    assert CommandDialog._format_command_params(params) == format_command_params(params)
    assert CommandDialog._parse_env_text("A=1") == {"A": "1"}
    assert CommandDialog._format_env({"A": "1"}) == "A=1"
