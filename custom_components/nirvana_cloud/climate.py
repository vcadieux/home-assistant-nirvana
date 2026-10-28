"""Pool/spa thermostat, using native Home Assistant climate controls."""

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError

from .entity import NirvanaEntity, add_device_entities
from .models import number


async def async_setup_entry(hass, entry, async_add_entities):
    add_device_entities(
        entry, async_add_entities, lambda coordinator, card: [NirvanaClimate(coordinator, card)]
    )


class NirvanaClimate(NirvanaEntity, ClimateEntity):
    _attr_name = None
    _attr_translation_key = "thermostat"
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_preset_modes = ["pool", "spa"]
    _attr_target_temperature_step = 1

    def __init__(self, coordinator, card_id):
        super().__init__(coordinator, card_id, "climate")
        self._last_preset = "pool"

    @property
    def temperature_unit(self):
        return (
            UnitOfTemperature.FAHRENHEIT
            if self.pump and self.pump.unit == "F"
            else UnitOfTemperature.CELSIUS
        )

    @property
    def current_temperature(self):
        return number(self.pump.value("WATER_TEMPERATURE")) if self.pump else None

    @property
    def target_temperature(self):
        if not self.pump or self.pump.mode == "OFF":
            return None
        return number(self.pump.value(self.pump.target_key))

    @property
    def min_temp(self):
        return self.pump.bounds[0] if self.pump else 10

    @property
    def max_temp(self):
        return self.pump.bounds[1] if self.pump else 35

    @property
    def hvac_modes(self):
        modes = [HVACMode.OFF, HVACMode.HEAT]
        if self.pump and self.pump.supports_cooling:
            modes.append(HVACMode.COOL)
        return modes

    @property
    def hvac_mode(self):
        if not self.pump or self.pump.mode is None:
            return None
        if self.pump.mode == "OFF":
            return HVACMode.OFF
        return HVACMode.COOL if self.pump.value("PUMP_MODE") == "COOL" else HVACMode.HEAT

    @property
    def hvac_action(self):
        if not self.pump or self.pump.notices("ERROR_LIST"):
            return None
        if self.pump.mode == "OFF":
            return HVACAction.OFF
        if self.pump.value("HEATING") == "ON":
            return (
                HVACAction.COOLING if self.pump.value("PUMP_MODE") == "COOL" else HVACAction.HEATING
            )
        return HVACAction.IDLE if self.pump.value("HEATING") == "OFF" else None

    @property
    def preset_mode(self):
        if self.pump and self.pump.mode in {"POOL", "SPA"}:
            self._last_preset = self.pump.mode.lower()
            return self._last_preset
        return None

    @property
    def extra_state_attributes(self):
        state = self.pump
        if not state:
            return {}
        return {
            "nirvana_mode": state.mode,
            "performance_mode": state.value("FAN_MODE"),
            "technician_control": state.value("CTRL_MODE") == "REMOTECTRL",
            "last_device_update": state.value("CARD_LAST_UPDATE"),
            "pending_command": self.coordinator.pending.get(self.card_id),
            "command_status": self.coordinator.command_status.get(self.card_id, "idle"),
        }

    async def async_set_temperature(self, **kwargs):
        # Home Assistant passes temperatures converted into the device's unit.
        if "hvac_mode" in kwargs:
            await self.async_set_hvac_mode(kwargs["hvac_mode"])
        if ATTR_TEMPERATURE in kwargs:
            await self.coordinator.async_control(
                self.card_id, "temperature", kwargs[ATTR_TEMPERATURE]
            )

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode not in self.hvac_modes:
            raise HomeAssistantError("Mode de chauffage non pris en charge")
        if hvac_mode == HVACMode.OFF:
            if self.pump and self.pump.mode in {"POOL", "SPA"}:
                self._last_preset = self.pump.mode.lower()
            await self.coordinator.async_control(self.card_id, "mode", "OFF")
            return
        if not self.pump or self.pump.mode not in {"POOL", "SPA"}:
            await self.coordinator.async_control(self.card_id, "mode", self._last_preset.upper())
        requested = "COOL" if hvac_mode == HVACMode.COOL else "HEAT"
        if self.pump.supports_cooling:
            await self.coordinator.async_control(self.card_id, "hvac", requested)

    async def async_set_preset_mode(self, preset_mode):
        if preset_mode not in self.preset_modes:
            raise HomeAssistantError("Choisissez piscine ou spa")
        await self.coordinator.async_control(self.card_id, "mode", preset_mode.upper())
        self._last_preset = preset_mode

    async def async_turn_on(self):
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)
