"""Shared device identity and dynamic device discovery."""

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


@callback
def add_device_entities(entry, async_add_entities, factory):
    coordinator = entry.runtime_data
    known = set()

    @callback
    def discover():
        entities = []
        for card_id in coordinator.data or {}:
            if card_id not in known:
                known.add(card_id)
                entities.extend(factory(coordinator, card_id))
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class NirvanaEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, card_id: str, suffix: str) -> None:
        super().__init__(coordinator)
        self.card_id = card_id
        self._attr_unique_id = f"{card_id}_{suffix}"
        state = coordinator.data[card_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, card_id)},
            manufacturer="Nirvana",
            name=state.device.get("LOCATION") or state.device.get("MODEL") or "Nirvana",
            model=state.device.get("MODEL"),
            sw_version=str(state.value("HP_VERSION"))
            if state.value("HP_VERSION") is not None
            else None,
        )

    @property
    def pump(self):
        return (self.coordinator.data or {}).get(self.card_id)

    @property
    def available(self) -> bool:
        return super().available and self.pump is not None and self.pump.available
