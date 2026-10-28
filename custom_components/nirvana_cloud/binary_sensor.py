"""Cloud connectivity and problem indicators."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory

from .entity import NirvanaEntity, add_device_entities


async def async_setup_entry(hass, entry, async_add_entities):
    add_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, card: [
            NirvanaBinarySensor(coordinator, card, "connectivity"),
            NirvanaBinarySensor(coordinator, card, "problem"),
        ],
    )


class NirvanaBinarySensor(NirvanaEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, card_id, key):
        super().__init__(coordinator, card_id, key)
        self.key = key
        self._attr_translation_key = key
        self._attr_device_class = (
            BinarySensorDeviceClass.CONNECTIVITY
            if key == "connectivity"
            else BinarySensorDeviceClass.PROBLEM
        )

    @property
    def available(self):
        if self.key == "connectivity":
            # Remains available to show "disconnected" when cloud polling succeeds.
            return self.coordinator.last_update_success and self.pump is not None
        return super().available

    @property
    def is_on(self):
        if not self.pump:
            return None
        if self.key == "connectivity":
            return self.pump.online
        return bool(self.pump.notices("ERROR_LIST"))
