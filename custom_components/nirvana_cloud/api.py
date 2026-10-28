"""Async cloud client. No requests to the heat pump's local network."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

import aiohttp
from pycognito.aws_srp import generate_hash_device

from .const import API_URL, CLIENT_ID, COGNITO_URL, PARAMETERS

_LOGGER = logging.getLogger(__name__)


class NirvanaError(Exception):
    """Sanitized error safe to display in Home Assistant."""


class CannotConnect(NirvanaError):
    """Transport error or temporary server failure."""


class InvalidAuth(NirvanaError):
    """Sign-in or session expired."""


class CognitoAuthError(InvalidAuth):
    """Authentication failure with only allowlisted diagnostic information."""

    def __init__(self, operation: str, code: str, status: int) -> None:
        self.operation = operation
        self.code = code
        self.status = status
        super().__init__(f"{operation}: {code} (HTTP {status})")


class ApiError(NirvanaError):
    """Unexpected or rejected API request."""


class NoDeviceData(NirvanaError):
    """Device does not yet report supported data."""


class UnsupportedChallenge(InvalidAuth):
    """Complete account activation/password reset in the official app."""


class MfaRequired(NirvanaError):
    """Continue the login with a one-time code."""


MFA_FIELDS = {
    "SMS_MFA": "SMS_MFA_CODE",
    "SOFTWARE_TOKEN_MFA": "SOFTWARE_TOKEN_MFA_CODE",
    "EMAIL_OTP": "EMAIL_OTP_CODE",
    "SMS_OTP": "SMS_OTP_CODE",
}


class NirvanaClient:
    """Use the app's Cognito public client and access-token API contract."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        executor: Callable,
        *,
        refresh_token: str | None = None,
        device_key: str | None = None,
        credentials_changed: Callable[[str, str | None], None] | None = None,
    ) -> None:
        self._session = session
        self._executor = executor
        self.refresh_token = refresh_token
        self.device_key = device_key
        self._credentials_changed = credentials_changed
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._token_lock = asyncio.Lock()
        self._challenge: dict[str, Any] | None = None
        self._challenge_username: str | None = None

    async def _json_request(self, method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        try:
            async with self._session.request(
                method,
                url,
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=False,
                **kwargs,
            ) as response:
                try:
                    body = await response.json(content_type=None)
                except (ValueError, UnicodeDecodeError):
                    body = None
                return response.status, body
        except (aiohttp.ClientError, TimeoutError) as err:
            # Never expose response bodies, passwords, bearer tokens or device IDs.
            raise CannotConnect("Unable to reach Nirvana") from err

    async def _cognito(self, operation: str, payload: dict) -> dict:
        status, body = await self._json_request(
            "POST",
            COGNITO_URL,
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": f"AWSCognitoIdentityProviderService.{operation}",
            },
            json=payload,
        )
        if not isinstance(body, dict):
            raise CannotConnect("Invalid authentication response")
        code = str(body.get("__type", "")).split("#")[-1]
        if status == 429 or status >= 500 or code == "TooManyRequestsException":
            raise CannotConnect("Authentication service temporarily unavailable")
        if status >= 400 or code:
            allowed_codes = {
                "NotAuthorizedException",
                "UserNotFoundException",
                "UserNotConfirmedException",
                "PasswordResetRequiredException",
                "InvalidParameterException",
                "ForbiddenException",
                "CodeMismatchException",
                "ExpiredCodeException",
                "ResourceNotFoundException",
                "InvalidUserPoolConfigurationException",
                "InvalidPasswordException",
                "DeviceKeyExistsException",
                "OperationNotEnabledException",
                "RefreshTokenReuseException",
                "UserLambdaValidationException",
                "UnexpectedLambdaException",
                "InvalidLambdaResponseException",
                "InvalidSmsRoleAccessPolicyException",
                "InvalidSmsRoleTrustRelationshipException",
                "CodeDeliveryFailureException",
                "UnsupportedOperationException",
            }
            safe_code = code if code in allowed_codes else "UnknownError"
            _LOGGER.warning(
                "Nirvana authentication request failed: operation=%s code=%s HTTP=%s",
                operation,
                safe_code,
                status,
            )
            if safe_code in {"UserNotConfirmedException", "PasswordResetRequiredException"}:
                raise UnsupportedChallenge(
                    "Complete account activation or password reset in the Nirvana app"
                )
            raise CognitoAuthError(operation, safe_code, status)
        return body

    async def async_login(self, username: str, password: str) -> None:
        # Zf in the shipped Android 4.0.7 bundle explicitly selects this flow.
        # Credentials go only to Cognito over verified HTTPS and are not retained.
        response = await self._cognito(
            "InitiateAuth",
            {
                "AuthFlow": "USER_PASSWORD_AUTH",
                "ClientId": CLIENT_ID,
                "AuthParameters": {"USERNAME": username, "PASSWORD": password},
            },
        )
        parameters = response.get("ChallengeParameters", {})
        self._challenge_username = (
            parameters.get("USER_ID_FOR_SRP") or parameters.get("USERNAME") or username
        )
        await self._finish_login(response)

    async def _finish_login(self, response: dict) -> None:
        challenge = response.get("ChallengeName")
        if challenge in MFA_FIELDS:
            self._challenge = response
            raise MfaRequired("Verification code required")
        if challenge:
            raise UnsupportedChallenge("Complete this account challenge in the Nirvana app")
        self._store_tokens(response)
        metadata = response["AuthenticationResult"].get("NewDeviceMetadata")
        if metadata:
            # Confirm a new Cognito device so refresh works with device tracking.
            # Follow the existing user-pool device/MFA policy without changing it.
            _, verifier = await self._executor(
                generate_hash_device,
                metadata["DeviceGroupKey"],
                metadata["DeviceKey"],
            )
            try:
                await self._cognito(
                    "ConfirmDevice",
                    {
                        "AccessToken": self._access_token,
                        "DeviceKey": metadata["DeviceKey"],
                        "DeviceName": "Home Assistant",
                        "DeviceSecretVerifierConfig": verifier,
                    },
                )
            except NirvanaError:
                # The app's sl helper also treats device confirmation as optional.
                # Failure to remember a device does not mean wrong credentials.
                self.device_key = None
                _LOGGER.warning("Cognito device confirmation skipped; account sign-in continues")
            else:
                self.device_key = metadata["DeviceKey"]
        if not self.refresh_token:
            raise InvalidAuth("No refresh token received")
        self._challenge = None

    async def async_submit_mfa(self, code: str) -> None:
        if not self._challenge:
            raise InvalidAuth("Restart sign-in")
        challenge = self._challenge
        response = await self._cognito(
            "RespondToAuthChallenge",
            {
                "ClientId": CLIENT_ID,
                "ChallengeName": challenge["ChallengeName"],
                "Session": challenge["Session"],
                "ChallengeResponses": {
                    "USERNAME": self._challenge_username,
                    MFA_FIELDS[challenge["ChallengeName"]]: code,
                },
            },
        )
        await self._finish_login(response)

    def _store_tokens(self, response: dict) -> None:
        result = response.get("AuthenticationResult", {})
        token = result.get("AccessToken")
        if not isinstance(token, str) or not token:
            raise InvalidAuth("No access token received")
        self._access_token = token
        self._expires_at = time.monotonic() + float(result.get("ExpiresIn", 3600)) - 60
        self.refresh_token = result.get("RefreshToken", self.refresh_token)

    async def async_access_token(self, rejected_token: str | None = None) -> str:
        async with self._token_lock:
            if self._access_token and self._expires_at > time.monotonic():
                if rejected_token is None or rejected_token != self._access_token:
                    return self._access_token
            if not self.refresh_token:
                raise InvalidAuth("Sign in to Nirvana")
            response = await self._cognito(
                "GetTokensFromRefreshToken",
                {
                    "ClientId": CLIENT_ID,
                    "RefreshToken": self.refresh_token,
                    **({"DeviceKey": self.device_key} if self.device_key else {}),
                },
            )
            self._store_tokens(response)
            if self._credentials_changed:
                self._credentials_changed(self.refresh_token, self.device_key)
            return self._access_token

    async def async_account_id(self) -> str:
        token = await self.async_access_token()
        response = await self._cognito("GetUser", {"AccessToken": token})
        for attr in response.get("UserAttributes", []):
            if attr.get("Name") == "sub" and isinstance(attr.get("Value"), str):
                return attr["Value"]
        raise ApiError("Account has no stable identifier")

    async def _request(self, method: str, path: str, payload: dict | None = None) -> Any:
        token = await self.async_access_token()
        for attempt in range(2):
            status, body = await self._json_request(
                method,
                API_URL + path,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                **({"json": payload} if payload is not None else {}),
            )
            if status == 401:
                if attempt:
                    raise InvalidAuth("Nirvana session rejected")
                token = await self.async_access_token(rejected_token=token)
                continue
            if status >= 500 or status == 429:
                raise CannotConnect("Nirvana service temporarily unavailable")
            if status >= 400 or 300 <= status < 400:
                detail = body.get("detail", "") if isinstance(body, dict) else ""
                if isinstance(detail, str) and any(
                    x in detail for x in ("NO_DATA", "NOT_SUPPORTED")
                ):
                    raise NoDeviceData("No supported device data")
                raise ApiError(f"Nirvana rejected the request (HTTP {status})")
            return body
        raise InvalidAuth("Nirvana session rejected")

    async def async_devices(self) -> list[dict]:
        data = await self._request("GET", "/customer/devices")
        if not isinstance(data, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("CARD_ID"), str) for item in data
        ):
            raise ApiError("Unexpected device list format")
        return [
            item
            for item in data
            if item["CARD_ID"]
            and str(item.get("TYPE", "")).upper() not in {"EXT_PUMP", "PUMP", "VARIABLE_PUMP"}
        ]

    async def async_parameters(self, card_id: str) -> dict:
        data = await self._request(
            "POST",
            "/pump/parameter",
            {
                "card_id": card_id,
                "params": PARAMETERS,
            },
        )
        if not isinstance(data, dict) or not any(key in data for key in ("desired", "reported")):
            raise ApiError("Unexpected device parameter format")
        for key in ("desired", "reported"):
            if data.get(key) is None:
                data[key] = {}
            elif not isinstance(data[key], dict):
                raise ApiError("Invalid device parameter sections")
        return data

    async def async_command(self, path: str, payload: dict) -> None:
        await self._request("POST", path, payload)
