"""Minimal diagnostics without account identifiers, tokens or raw payloads."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "integration_version": "0.1.1",
        "last_update_success": coordinator.last_update_success,
        "poll_seconds": coordinator.update_interval.total_seconds(),
        "devices": [
            {
                "online": state.online,
                "initialized": state.initialized,
                "unit": state.unit,
                "mode": state.mode,
                "reported_fields": sorted(state.parameters.get("reported", {})),
                "desired_fields": sorted(state.parameters.get("desired", {})),
                "command_status": coordinator.command_status.get(state.card_id, "idle"),
            }
            for state in (coordinator.data or {}).values()
        ],
    }
