"""Coordinated reads and serialized, confirmed device commands."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import (
    ConfigEntryAuthFailed,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import InvalidAuth, NirvanaClient, NirvanaError, NoDeviceData
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .models import PumpState

_LOGGER = logging.getLogger(__name__)
CONFIRM_ATTEMPTS = 10
CONFIRM_DELAY = 2


class NirvanaCoordinator(DataUpdateCoordinator[dict[str, PumpState]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: NirvanaClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(
                seconds=entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.entry = entry
        self.client = client
        self.pending: dict[str, str] = {}
        self.command_status: dict[str, str] = {}
        self._command_locks: dict[str, asyncio.Lock] = {}

    async def _async_update_data(self) -> dict[str, PumpState]:
        try:
            devices = await self.client.async_devices()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NirvanaError as err:
            raise UpdateFailed(str(err)) from err
        states = {}
        temporary_failures = 0
        for device in devices:
            card_id = device["CARD_ID"]
            try:
                parameters = await self.client.async_parameters(card_id)
                states[card_id] = PumpState(device, parameters)
            except InvalidAuth as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except NoDeviceData:
                states[card_id] = PumpState(device, error=True)
            except NirvanaError:
                temporary_failures += 1
                previous = (self.data or {}).get(card_id)
                states[card_id] = PumpState(
                    device, previous.parameters if previous else {}, error=True
                )
        if devices and temporary_failures == len(devices):
            raise UpdateFailed("Unable to refresh Nirvana devices")
        return states

    def assert_control(self, card_id: str) -> PumpState:
        state = (self.data or {}).get(card_id)
        if not self.last_update_success or state is None or not state.control_available:
            raise HomeAssistantError("Thermopompe indisponible ou sous contrôle technicien")
        return state

    async def async_control(self, card_id: str, operation: str, value: Any) -> None:
        """Validate against latest state inside the device's command lock."""
        lock = self._command_locks.setdefault(card_id, asyncio.Lock())
        async with lock:
            state = self.assert_control(card_id)
            payload = {"card_id": card_id, "value": value}
            if operation == "temperature":
                if state.mode not in {"POOL", "SPA"}:
                    raise HomeAssistantError(
                        "Choisissez piscine ou spa avant de régler la température"
                    )
                from .models import number

                numeric = number(value)
                low, high = state.bounds
                if numeric is None or not low <= numeric <= high:
                    raise HomeAssistantError(
                        f"La consigne doit être entre {low} et {high} °{state.unit}"
                    )
                key, path = state.target_key, "/pump/desired/setpoint"
                payload.update(mode=state.mode.lower(), value=math.floor(numeric + 0.5))
            elif operation == "mode":
                if value not in {"POOL", "SPA", "OFF"}:
                    raise HomeAssistantError("Mode Nirvana invalide")
                key, path = "HEAT_MODE", "/pump/desired/heating-mode"
            elif operation == "performance":
                if state.mode == "OFF" or value not in state.performance_modes:
                    raise HomeAssistantError("Ce mode de performance n’est pas disponible")
                key, path = "FAN_MODE", "/pump/desired/fan-mode"
            elif operation == "hvac":
                if value not in {"HEAT", "COOL"} or not state.supports_cooling:
                    raise HomeAssistantError(
                        "Ce mode de chauffage/refroidissement n’est pas disponible"
                    )
                key, path = "PUMP_MODE", "/pump/desired/pump-mode"
            else:
                raise HomeAssistantError("Commande Nirvana inconnue")
            reported = state.parameters.get("reported", {})
            if _equal(reported.get(key), payload["value"]):
                return
            self.pending[card_id] = key
            self.command_status[card_id] = "pending"
            self.async_update_listeners()
            try:
                await self.client.async_command(path, payload)
                for attempt in range(CONFIRM_ATTEMPTS):
                    if attempt:
                        await asyncio.sleep(CONFIRM_DELAY)
                    parameters = await self.client.async_parameters(card_id)
                    # Only a reported value confirms a command, never desired alone.
                    self.async_set_updated_data(
                        {
                            **self.data,
                            card_id: PumpState(state.device, parameters),
                        }
                    )
                    if _equal(parameters.get("reported", {}).get(key), payload["value"]):
                        self.command_status[card_id] = "confirmed"
                        return
                self.command_status[card_id] = "unconfirmed"
                raise HomeAssistantError(
                    "Commande envoyée, mais non confirmée par la thermopompe; vérifiez son état avant de réessayer"
                )
            except InvalidAuth as err:
                self.command_status[card_id] = "failed"
                self.entry.async_start_reauth(self.hass)
                raise HomeAssistantError(
                    "Session Nirvana expirée; reconnectez l’intégration"
                ) from err
            except NirvanaError as err:
                self.command_status[card_id] = "failed"
                raise HomeAssistantError(str(err)) from err
            finally:
                self.pending.pop(card_id, None)
                self.async_update_listeners()


def _equal(actual: Any, expected: Any) -> bool:
    if actual is None:
        return False
    if isinstance(expected, (int, float)):
        from .models import number

        return number(actual) == expected
    return str(actual).upper() == str(expected).upper()
