"""Nirvana Heat Pump cloud integration."""

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NirvanaClient
from .const import CONF_DEVICE_KEY, CONF_REFRESH_TOKEN, DEFAULT_SCAN_INTERVAL
from .coordinator import NirvanaCoordinator

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    @callback
    def credentials_changed(refresh_token: str, device_key: str | None) -> None:
        updated = {**entry.data, CONF_REFRESH_TOKEN: refresh_token, CONF_DEVICE_KEY: device_key}
        if updated != entry.data:
            hass.config_entries.async_update_entry(entry, data=updated)

    client = NirvanaClient(
        async_get_clientsession(hass),
        hass.async_add_executor_job,
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        device_key=entry.data.get(CONF_DEVICE_KEY),
        credentials_changed=credentials_changed,
    )
    coordinator = NirvanaCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    interval = timedelta(seconds=entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL))
    if entry.runtime_data.update_interval != interval:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
