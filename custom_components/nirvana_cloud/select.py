"""Nirvana performance profile selector."""

from homeassistant.components.select import SelectEntity

from .entity import NirvanaEntity, add_device_entities


async def async_setup_entry(hass, entry, async_add_entities):
    add_device_entities(
        entry, async_add_entities, lambda coordinator, card: [NirvanaPerformance(coordinator, card)]
    )


class NirvanaPerformance(NirvanaEntity, SelectEntity):
    _attr_translation_key = "performance"
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator, card_id):
        super().__init__(coordinator, card_id, "performance")

    @property
    def options(self):
        return [mode.lower() for mode in self.pump.performance_modes] if self.pump else []

    @property
    def current_option(self):
        raw = self.pump.value("FAN_MODE") if self.pump else None
        if raw == "ECOSMART":
            raw = "SMART"
        return raw.lower() if isinstance(raw, str) and raw.lower() in self.options else None

    @property
    def available(self):
        return (
            super().available
            and self.pump.mode in {"POOL", "SPA"}
            and self.pump.value("CTRL_MODE") != "REMOTECTRL"
            and self.current_option is not None
        )

    async def async_select_option(self, option):
        await self.coordinator.async_control(self.card_id, "performance", option.upper())
