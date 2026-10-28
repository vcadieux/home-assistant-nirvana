import asyncio
from unittest.mock import Mock

import pytest

from custom_components.nirvana_cloud.api import (
    ApiError,
    CannotConnect,
    InvalidAuth,
    MfaRequired,
    NoDeviceData,
)
from custom_components.nirvana_cloud.const import API_URL, CLIENT_ID, COGNITO_URL


def auth_response(access="access-test", refresh=None):
    result = {"AccessToken": access, "ExpiresIn": 3600, "IdToken": "unused"}
    if refresh:
        result["RefreshToken"] = refresh
    return {"AuthenticationResult": result}


def test_requests(mock_http, url):
    return [
        call
        for (method, called_url), calls in mock_http.requests.items()
        if str(called_url) == url
        for call in calls
    ]


# A helper, not a pytest test.
test_requests.__test__ = False


async def test_refresh_rotation_and_concurrent_calls(http_client, mock_http):
    changed = Mock()
    http_client._credentials_changed = changed
    mock_http.post(COGNITO_URL, payload=auth_response(refresh="rotated"))
    assert (
        await asyncio.gather(*[http_client.async_access_token() for _ in range(5)])
        == ["access-test"] * 5
    )
    calls = test_requests(mock_http, COGNITO_URL)
    assert len(calls) == 1
    assert calls[0].kwargs["json"] == {"ClientId": CLIENT_ID, "RefreshToken": "refresh-test"}
    changed.assert_called_once_with("rotated", None)


async def test_password_login_and_mfa(http_client, mock_http):
    mock_http.post(
        COGNITO_URL,
        payload={
            "ChallengeName": "SOFTWARE_TOKEN_MFA",
            "Session": "mfa-session",
            "ChallengeParameters": {"USERNAME": "canonical-user"},
        },
    )
    with pytest.raises(MfaRequired):
        await http_client.async_login("email@example.com", "password-test")
    mock_http.post(COGNITO_URL, payload=auth_response(refresh="initial-refresh"))
    await http_client.async_submit_mfa("123456")
    calls = test_requests(mock_http, COGNITO_URL)
    assert calls[0].kwargs["json"]["AuthFlow"] == "USER_PASSWORD_AUTH"
    assert calls[0].kwargs["json"]["AuthParameters"] == {
        "USERNAME": "email@example.com",
        "PASSWORD": "password-test",
    }
    assert calls[1].kwargs["json"]["Session"] == "mfa-session"
    assert calls[1].kwargs["json"]["ChallengeResponses"] == {
        "USERNAME": "canonical-user",
        "SOFTWARE_TOKEN_MFA_CODE": "123456",
    }
    assert http_client.refresh_token == "initial-refresh"


async def test_device_confirmation_and_refresh_key(http_client, mock_http):
    response = auth_response(refresh="initial-refresh")
    response["AuthenticationResult"]["NewDeviceMetadata"] = {
        "DeviceKey": "device-test",
        "DeviceGroupKey": "group-test",
    }
    mock_http.post(COGNITO_URL, payload=response)
    mock_http.post(COGNITO_URL, payload={"UserConfirmationNecessary": False})
    await http_client.async_login("user", "pass")
    assert http_client.device_key == "device-test"
    http_client._expires_at = 0
    mock_http.post(COGNITO_URL, payload=auth_response())
    await http_client.async_access_token()
    assert test_requests(mock_http, COGNITO_URL)[-1].kwargs["json"]["DeviceKey"] == "device-test"


async def test_401_refresh_and_post_contract(http_client, mock_http):
    mock_http.post(COGNITO_URL, payload=auth_response())
    mock_http.post(API_URL + "/pump/desired/setpoint", status=401)
    mock_http.post(COGNITO_URL, payload=auth_response(access="new-access"))
    mock_http.post(API_URL + "/pump/desired/setpoint", payload={"ok": True})
    body = {"card_id": "test-card", "mode": "pool", "value": 29}
    await http_client.async_command("/pump/desired/setpoint", body)
    calls = test_requests(mock_http, API_URL + "/pump/desired/setpoint")
    assert calls[0].kwargs["json"] == body
    assert calls[1].kwargs["headers"]["Authorization"] == "Bearer new-access"


@pytest.mark.parametrize(
    "status,body,exception",
    [
        (403, {"detail": "private account details"}, ApiError),
        (429, {}, CannotConnect),
        (503, {}, CannotConnect),
        (400, {"detail": "NO_DATA"}, NoDeviceData),
    ],
)
async def test_sanitized_api_errors(http_client, mock_http, status, body, exception):
    mock_http.post(COGNITO_URL, payload=auth_response())
    mock_http.get(API_URL + "/customer/devices", status=status, payload=body)
    with pytest.raises(exception) as caught:
        await http_client.async_devices()
    assert "private account details" not in str(caught.value)


async def test_bad_credentials_and_malformed_devices(http_client, mock_http):
    mock_http.post(
        COGNITO_URL,
        status=400,
        payload={"__type": "NotAuthorizedException", "message": "secret details"},
    )
    with pytest.raises(InvalidAuth):
        await http_client.async_access_token()
    mock_http.post(COGNITO_URL, payload=auth_response())
    mock_http.get(API_URL + "/customer/devices", payload={"unexpected": []})
    with pytest.raises(ApiError):
        await http_client.async_devices()


async def test_device_list_excludes_external_pumps(http_client, mock_http):
    mock_http.post(COGNITO_URL, payload=auth_response())
    mock_http.get(
        API_URL + "/customer/devices",
        payload=[{"CARD_ID": "hp", "TYPE": "HP"}, {"CARD_ID": "pump", "TYPE": "EXT_PUMP"}],
    )
    assert await http_client.async_devices() == [{"CARD_ID": "hp", "TYPE": "HP"}]


async def test_null_parameter_sections(http_client, mock_http):
    mock_http.post(COGNITO_URL, payload=auth_response())
    mock_http.post(
        API_URL + "/pump/parameter",
        payload={"desired": None, "reported": {"WATER_TEMPERATURE": 25}},
    )
    assert await http_client.async_parameters("card") == {
        "desired": {},
        "reported": {"WATER_TEMPERATURE": 25},
    }


async def test_optional_device_confirmation_does_not_reject_valid_login(http_client, mock_http):
    response = auth_response(refresh="initial-refresh")
    response["AuthenticationResult"]["NewDeviceMetadata"] = {
        "DeviceKey": "device-test",
        "DeviceGroupKey": "group-test",
    }
    mock_http.post(COGNITO_URL, payload=response)
    mock_http.post(
        COGNITO_URL,
        status=400,
        payload={
            "__type": "NotAuthorizedException",
            "message": "Access Token does not have required scopes",
        },
    )
    await http_client.async_login("valid-user", "valid-password")
    assert http_client.refresh_token == "initial-refresh"
    assert http_client.device_key is None
    mock_http.post(
        COGNITO_URL, payload={"UserAttributes": [{"Name": "sub", "Value": "account-test"}]}
    )
    assert await http_client.async_account_id() == "account-test"


async def test_cognito_diagnostics_exclude_raw_message_and_unknown_type(
    http_client, mock_http, caplog
):
    from custom_components.nirvana_cloud.api import CognitoAuthError

    mock_http.post(
        COGNITO_URL,
        status=400,
        payload={
            "__type": "InvalidParameterException",
            "message": "private-user private-password private-token",
        },
    )
    with pytest.raises(CognitoAuthError) as caught:
        await http_client.async_login("private-user", "private-password")
    assert str(caught.value) == "InitiateAuth: InvalidParameterException (HTTP 400)"
    for secret in ("private-user", "private-password", "private-token"):
        assert secret not in caplog.text
        assert secret not in str(caught.value)
    assert "InitiateAuth" in caplog.text
    mock_http.post(
        COGNITO_URL, status=400, payload={"__type": "private-token", "message": "private-password"}
    )
    with pytest.raises(CognitoAuthError, match="UnknownError"):
        await http_client.async_login("private-user", "private-password")
    assert "private-token" not in caplog.text


async def test_password_flow_is_exactly_the_shipped_app_contract(http_client, mock_http):
    mock_http.post(COGNITO_URL, payload=auth_response(refresh="initial"))
    await http_client.async_login("email@example.com", "  exact-password  ")
    call = test_requests(mock_http, COGNITO_URL)[0]
    assert call.kwargs["json"] == {
        "AuthFlow": "USER_PASSWORD_AUTH",
        "ClientId": CLIENT_ID,
        "AuthParameters": {"USERNAME": "email@example.com", "PASSWORD": "  exact-password  "},
    }
    assert not hasattr(http_client, "password")
    assert not hasattr(http_client, "_password")
