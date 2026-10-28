import copy
import inspect
from types import MappingProxyType

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import ConfigEntryAuthFailed, UpdateFailed

from custom_components.nirvana_cloud.api import CannotConnect, InvalidAuth
from custom_components.nirvana_cloud.coordinator import NirvanaCoordinator


async def make_coordinator(hass, client):
    coordinator = NirvanaCoordinator(
        hass,
        ConfigEntry(
            domain="nirvana_cloud",
            title="Test",
            unique_id="test",
            version=1,
            minor_version=1,
            source="user",
            data={},
            options={},
            discovery_keys=MappingProxyType({}),
            **(
                {"subentries_data": []}
                if "subentries_data" in inspect.signature(ConfigEntry).parameters
                else {}
            ),
        ),
        client,
    )
    await coordinator.async_refresh()
    return coordinator


async def test_command_confirms_reported_not_desired(
    hass, fake_client, pump_state_data, monkeypatch
):
    coordinator = await make_coordinator(hass, fake_client)
    initial = copy.deepcopy(pump_state_data["parameters"])
    desired_only = copy.deepcopy(initial)
    desired_only["desired"]["DESIRED_POOL_TEMPERATURE"] = 29
    confirmed = copy.deepcopy(desired_only)
    confirmed["reported"]["DESIRED_POOL_TEMPERATURE"] = 29
    fake_client.async_parameters.side_effect = [desired_only, confirmed]
    monkeypatch.setattr("custom_components.nirvana_cloud.coordinator.CONFIRM_DELAY", 0)
    await coordinator.async_control("AA-BB-CC-DD-EE-FF", "temperature", 29)
    fake_client.async_command.assert_awaited_once_with(
        "/pump/desired/setpoint", {"card_id": "AA-BB-CC-DD-EE-FF", "mode": "pool", "value": 29}
    )
    assert fake_client.async_parameters.await_count == 3
    assert coordinator.command_status["AA-BB-CC-DD-EE-FF"] == "confirmed"
    assert not coordinator.pending


async def test_unconfirmed_command_not_retried_or_optimistic(hass, fake_client, monkeypatch):
    coordinator = await make_coordinator(hass, fake_client)
    monkeypatch.setattr("custom_components.nirvana_cloud.coordinator.CONFIRM_ATTEMPTS", 2)
    monkeypatch.setattr("custom_components.nirvana_cloud.coordinator.CONFIRM_DELAY", 0)
    with pytest.raises(HomeAssistantError, match="non confirmée"):
        await coordinator.async_control("AA-BB-CC-DD-EE-FF", "temperature", 29)
    assert fake_client.async_command.await_count == 1
    assert coordinator.data["AA-BB-CC-DD-EE-FF"].value("DESIRED_POOL_TEMPERATURE") == 28
    assert coordinator.command_status["AA-BB-CC-DD-EE-FF"] == "unconfirmed"


@pytest.mark.parametrize("value", [36, 9, "NaN", True])
async def test_reject_out_of_bounds_before_network(hass, fake_client, value):
    coordinator = await make_coordinator(hass, fake_client)
    with pytest.raises(HomeAssistantError):
        await coordinator.async_control("AA-BB-CC-DD-EE-FF", "temperature", value)
    fake_client.async_command.assert_not_called()


async def test_offline_technician_and_idempotent_command(hass, fake_client):
    coordinator = await make_coordinator(hass, fake_client)
    await coordinator.async_control("AA-BB-CC-DD-EE-FF", "temperature", 28)
    fake_client.async_command.assert_not_called()
    state = coordinator.data["AA-BB-CC-DD-EE-FF"]
    state.parameters["reported"]["CTRL_MODE"] = "REMOTECTRL"
    with pytest.raises(HomeAssistantError):
        await coordinator.async_control(state.card_id, "mode", "OFF")
    state.parameters["reported"].update(CTRL_MODE="NORMAL", CARD_LAST_CONNECT="2020-01-01")
    with pytest.raises(HomeAssistantError):
        await coordinator.async_control(state.card_id, "mode", "OFF")
    fake_client.async_command.assert_not_called()


async def test_polling_auth_failure(hass, fake_client):
    coordinator = await make_coordinator(hass, fake_client)
    fake_client.async_devices.side_effect = InvalidAuth("expired")
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    fake_client.async_devices.side_effect = CannotConnect("offline")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_session_expired_during_command_starts_reauth(hass, fake_client):
    from unittest.mock import patch

    coordinator = await make_coordinator(hass, fake_client)
    fake_client.async_command.side_effect = InvalidAuth("expired")
    with patch.object(coordinator.entry, "async_start_reauth") as reauth:
        with pytest.raises(HomeAssistantError, match="expirée"):
            await coordinator.async_control("AA-BB-CC-DD-EE-FF", "temperature", 29)
        reauth.assert_called_once_with(hass)
    assert not coordinator.pending


async def test_spa_and_performance_contracts(hass, fake_client, monkeypatch):
    coordinator = await make_coordinator(hass, fake_client)
    updated = copy.deepcopy(fake_client.async_parameters.return_value)
    fake_client.async_parameters.return_value = updated
    reported = updated["reported"]
    reported.update(HEAT_MODE="SPA", DESIRED_SPA_TEMPERATURE=39)
    await coordinator.async_control("AA-BB-CC-DD-EE-FF", "mode", "SPA")
    await coordinator.async_control("AA-BB-CC-DD-EE-FF", "temperature", 39)
    # Already reported 39, so a second target write is unnecessary.
    assert fake_client.async_command.await_count == 1
    updated = copy.deepcopy(updated)
    updated["reported"]["FAN_MODE"] = "BOOST"
    fake_client.async_parameters.return_value = updated
    await coordinator.async_control("AA-BB-CC-DD-EE-FF", "performance", "BOOST")
    fake_client.async_command.assert_awaited_with(
        "/pump/desired/fan-mode", {"card_id": "AA-BB-CC-DD-EE-FF", "value": "BOOST"}
    )


async def test_fractional_native_temperature_from_ha_unit_conversion(hass, fake_client):
    coordinator = await make_coordinator(hass, fake_client)
    initial = coordinator.data["AA-BB-CC-DD-EE-FF"].parameters
    initial["reported"].update(
        TEMPERATURE_UNIT="F",
        HEATPUMP_MIN_TEMP=50,
        HEATPUMP_MAX_TEMP=104,
        DESIRED_POOL_TEMPERATURE=82,
    )
    confirmed = copy.deepcopy(initial)
    confirmed["reported"]["DESIRED_POOL_TEMPERATURE"] = 84
    fake_client.async_parameters.return_value = confirmed
    # HA converts 29 °C into 84.2 °F before calling a Fahrenheit climate entity.
    await coordinator.async_control("AA-BB-CC-DD-EE-FF", "temperature", 84.2)
    fake_client.async_command.assert_awaited_once_with(
        "/pump/desired/setpoint", {"card_id": "AA-BB-CC-DD-EE-FF", "mode": "pool", "value": 84}
    )
