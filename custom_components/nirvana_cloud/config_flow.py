"""UI sign-in, MFA, reauthentication and polling options."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    ApiError,
    CannotConnect,
    CognitoAuthError,
    InvalidAuth,
    MfaRequired,
    NirvanaClient,
    UnsupportedChallenge,
)
from .const import CONF_DEVICE_KEY, CONF_REFRESH_TOKEN, DEFAULT_SCAN_INTERVAL, DOMAIN


class NirvanaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._client: NirvanaClient | None = None
        self._username = ""
        self._reauth_entry = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors = {}
        auth_error = ""
        if user_input is not None:
            self._username = user_input[CONF_USERNAME].strip()
            self._client = NirvanaClient(
                async_get_clientsession(self.hass), self.hass.async_add_executor_job
            )
            try:
                await self._client.async_login(self._username, user_input[CONF_PASSWORD])
                return await self._async_finish()
            except MfaRequired:
                return await self.async_step_mfa()
            except UnsupportedChallenge:
                errors["base"] = "unsupported_challenge"
            except CognitoAuthError as err:
                errors["base"] = "cognito_error"
                auth_error = str(err)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except ApiError:
                errors["base"] = "unexpected_response"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=self._username): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders={"auth_error": auth_error},
        )

    async def async_step_mfa(self, user_input: dict[str, Any] | None = None):
        errors = {}
        auth_error = ""
        if user_input is not None:
            try:
                await self._client.async_submit_mfa(user_input["code"].strip())
                return await self._async_finish()
            except MfaRequired:
                errors["base"] = "invalid_auth"
            except UnsupportedChallenge:
                return self.async_abort(reason="unsupported_challenge")
            except CognitoAuthError as err:
                errors["base"] = "cognito_error"
                auth_error = str(err)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except ApiError:
                errors["base"] = "unexpected_response"
        return self.async_show_form(
            step_id="mfa",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
            description_placeholders={"auth_error": auth_error},
        )

    async def _async_finish(self):
        account_id = await self._client.async_account_id()
        await self._client.async_devices()
        data = {
            CONF_USERNAME: self._username,
            CONF_REFRESH_TOKEN: self._client.refresh_token,
            CONF_DEVICE_KEY: self._client.device_key,
        }
        if self._reauth_entry:
            if account_id != self._reauth_entry.unique_id:
                return self.async_abort(reason="wrong_account")
            self.hass.config_entries.async_update_entry(self._reauth_entry, data=data)
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
            return self.async_abort(reason="reauth_successful")
        await self.async_set_unique_id(account_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=f"Nirvana ({self._username})", data=data)

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        self._username = entry_data.get(CONF_USERNAME, "")
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NirvanaOptionsFlow(config_entry)


class NirvanaOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry):
        self._entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "scan_interval",
                        default=self._entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=300)),
                }
            ),
        )
