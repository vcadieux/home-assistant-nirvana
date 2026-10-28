"""Load real HA platforms and exercise the actual config flow offline."""

import inspect
import shutil
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.nirvana_cloud.const import DOMAIN


async def prepare(hass):
    dest = Path(hass.config.config_dir) / "custom_components" / DOMAIN
    shutil.copytree(Path(__file__).parents[1] / "custom_components" / DOMAIN, dest)
    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    await ar.async_load(hass)
    if hasattr(dr, "async_setup"):
        dr.async_setup(hass)
    await dr.async_load(hass)
    await er.async_load(hass)
    # Set up HA's loader/entity infrastructure, without starting servers or discovery.
    assert await async_setup_component(hass, "homeassistant", {})


def entry():
    return ConfigEntry(
        domain=DOMAIN,
        title="Nirvana",
        unique_id="account-test",
        version=1,
        minor_version=1,
        source="user",
        data={"username": "test@example.com", "refresh_token": "test-refresh"},
        options={},
        discovery_keys=MappingProxyType({}),
        **(
            {"subentries_data": []}
            if "subentries_data" in inspect.signature(ConfigEntry).parameters
            else {}
        ),
    )


async def test_load_all_platforms_and_unload(hass, fake_client):
    await prepare(hass)
    config_entry = entry()
    with patch("custom_components.nirvana_cloud.NirvanaClient", return_value=fake_client):
        await hass.config_entries.async_add(config_entry)
        await hass.async_block_till_done()
    assert config_entry.state == ConfigEntryState.LOADED
    states = hass.states.async_all()
    climates = [state for state in states if state.domain == "climate"]
    assert len(climates) == 1
    thermostat = climates[0]
    assert thermostat.state == "heat"
    assert thermostat.attributes["current_temperature"] == 25
    assert thermostat.attributes["temperature"] == 28
    assert thermostat.attributes["preset_mode"] == "pool"
    assert len([state for state in states if state.domain == "sensor"]) == 5
    assert len([state for state in states if state.domain == "binary_sensor"]) == 2
    assert len([state for state in states if state.domain == "select"]) == 1
    # Exercise real service dispatch, not only direct entity methods.
    with patch.object(
        config_entry.runtime_data, "async_control", new_callable=AsyncMock
    ) as control:
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": thermostat.entity_id, "temperature": 29},
            blocking=True,
        )
        control.assert_awaited_once_with("AA-BB-CC-DD-EE-FF", "temperature", 29)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state == ConfigEntryState.NOT_LOADED


async def test_config_flow_does_not_store_password(hass):
    await prepare(hass)
    client = AsyncMock()
    client.refresh_token = "refresh-token"
    client.device_key = "device-key"
    client.async_account_id.return_value = "account-test"
    client.async_devices.return_value = []
    with (
        patch("custom_components.nirvana_cloud.config_flow.NirvanaClient", return_value=client),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_setup",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={CONF_USERNAME: "test@example.com", CONF_PASSWORD: "password-not-stored"},
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"] == {
        "username": "test@example.com",
        "refresh_token": "refresh-token",
        "device_key": "device-key",
    }
    assert CONF_PASSWORD not in result["result"].data


async def test_refresh_token_rotation_does_not_reload_integration(hass, fake_client):
    await prepare(hass)
    config_entry = entry()
    with patch("custom_components.nirvana_cloud.NirvanaClient", return_value=fake_client):
        await hass.config_entries.async_add(config_entry)
        await hass.async_block_till_done()
    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock) as reload:
        hass.config_entries.async_update_entry(
            config_entry, data={**config_entry.data, "refresh_token": "rotated"}
        )
        await hass.async_block_till_done()
        reload.assert_not_called()
        hass.config_entries.async_update_entry(config_entry, options={"scan_interval": 60})
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(config_entry.entry_id)
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_config_flow_displays_failed_cognito_stage_without_secrets(hass):
    from custom_components.nirvana_cloud.api import CognitoAuthError

    await prepare(hass)
    client = AsyncMock()
    client.async_login.side_effect = CognitoAuthError(
        "InitiateAuth", "InvalidParameterException", 400
    )
    with patch("custom_components.nirvana_cloud.config_flow.NirvanaClient", return_value=client):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={CONF_USERNAME: "private-user", CONF_PASSWORD: "private-password"},
        )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cognito_error"}
    assert result["description_placeholders"] == {
        "auth_error": "InitiateAuth: InvalidParameterException (HTTP 400)"
    }
    assert "private-password" not in str(result)
