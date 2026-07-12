from extensions.sdk import (
    API_VERSION,
    Capability,
    CommandAction,
    CommandParam,
    CommandResult,
    SDKErrorCode,
    negotiate_api,
)


def test_sdk_dtos_are_host_neutral_serializable_values():
    result = CommandResult(
        success=True,
        message="ok",
        actions=[CommandAction(type="copy", value="value")],
    )

    assert API_VERSION == "1.0"
    assert result.to_dict()["actions"] == [
        {
            "type": "copy",
            "label": "",
            "value": "value",
            "enabled": True,
            "danger": False,
            "primary": False,
            "payload": {},
        }
    ]
    assert CommandParam(name="query").to_dict()["name"] == "query"


def test_sdk_compatibility_matrix_covers_current_previous_newer_and_missing_capability():
    assert negotiate_api("1.0", {Capability.COMMANDS}, {Capability.COMMANDS}).compatible
    assert negotiate_api("0.9", {Capability.COMMANDS}, {Capability.COMMANDS}).compatible
    assert negotiate_api("2.0", set()).error_code == SDKErrorCode.INCOMPATIBLE_VERSION
    missing = negotiate_api("1.0", set(), {Capability.CANCELLATION})
    assert missing.error_code == SDKErrorCode.MISSING_CAPABILITY
    assert missing.missing_capabilities == {Capability.CANCELLATION}
