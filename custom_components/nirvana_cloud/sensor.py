"""Water temperature, status and diagnostics."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTemperature

from .entity import NirvanaEntity, add_device_entities
from .models import number, timestamp

SENSORS = {
    "water_temperature": ("WATER_TEMPERATURE", SensorDeviceClass.TEMPERATURE),
    "outside_temperature": ("OUTDOOR_TEMP", SensorDeviceClass.TEMPERATURE),
    "wifi_signal": ("WIFI_RSSI", SensorDeviceClass.SIGNAL_STRENGTH),
    "last_update": ("CARD_LAST_UPDATE", SensorDeviceClass.TIMESTAMP),
    "status": (None, SensorDeviceClass.ENUM),
}
STATUS_OPTIONS = [
    "off",
    "heating",
    "cooling",
    "idle",
    "defrost",
    "compressor_delay",
    "fault",
    "technician_control",
    "unknown",
]


async def async_setup_entry(hass, entry, async_add_entities):
    add_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, card: [NirvanaSensor(coordinator, card, key) for key in SENSORS],
    )


class NirvanaSensor(NirvanaEntity, SensorEntity):
    def __init__(self, coordinator, card_id, key):
        super().__init__(coordinator, card_id, key)
        self.key = key
        self._field, self._attr_device_class = SENSORS[key]
        self._attr_translation_key = key
        if key in {"water_temperature", "outside_temperature", "wifi_signal"}:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if key in {"wifi_signal", "last_update"}:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if key == "status":
            self._attr_options = STATUS_OPTIONS

    @property
    def native_unit_of_measurement(self):
        if self.key == "wifi_signal":
            return "dBm"
        if self._attr_device_class == SensorDeviceClass.TEMPERATURE:
            return (
                UnitOfTemperature.FAHRENHEIT
                if self.pump and self.pump.unit == "F"
                else UnitOfTemperature.CELSIUS
            )
        return None

    @property
    def native_value(self):
        state = self.pump
        if state is None:
            return None
        if self.key == "last_update":
            return timestamp(state.value(self._field))
        if self.key != "status":
            return number(state.value(self._field))
        if state.notices("ERROR_LIST"):
            return "fault"
        if state.value("CTRL_MODE") == "REMOTECTRL":
            return "technician_control"
        if state.mode == "OFF":
            return "off"
        if "DEFROST" in str(state.value("FAN_MODE", "")):
            return "defrost"
        if state.value("HEAT_TIMER_BLOCK") == "DELAYCOMP":
            return "compressor_delay"
        if state.value("HEATING") == "ON":
            return "cooling" if state.value("PUMP_MODE") == "COOL" else "heating"
        return "idle" if state.value("HEATING") == "OFF" else "unknown"

    @property
    def extra_state_attributes(self):
        if self.key != "status" or self.pump is None:
            return None
        return {
            "errors": self.pump.notices("ERROR_LIST"),
            "alerts": self.pump.notices("ALERT_LIST"),
        }
