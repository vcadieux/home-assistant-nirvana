from datetime import datetime, timedelta, timezone

import pytest

from custom_components.nirvana_cloud.models import PumpState, number, timestamp


@pytest.mark.parametrize("raw", [None, True, "NaN", "Infinity", "UNSUPPORTED_DATA", "", {}, []])
def test_invalid_numbers(raw):
    assert number(raw) is None


def test_reported_precedence_and_bounds(pump_state_data):
    state = PumpState(**pump_state_data)
    state.parameters["desired"]["DESIRED_POOL_TEMPERATURE"] = 32
    assert state.value("DESIRED_POOL_TEMPERATURE") == 28
    assert state.bounds == (10, 35)
    state.parameters["reported"]["HEAT_MODE"] = "SPA"
    assert state.target_key == "DESIRED_SPA_TEMPERATURE"
    assert state.bounds == (10, 40)
    assert state.available


def test_fahrenheit_bounds_and_invalid_unit(pump_state_data):
    state = PumpState(**pump_state_data)
    state.parameters["reported"].update(
        TEMPERATURE_UNIT="F", HEATPUMP_MIN_TEMP=50, HEATPUMP_MAX_TEMP=110
    )
    assert state.bounds == (50, 95)
    state.parameters["reported"]["HEAT_MODE"] = "SPA"
    assert state.bounds == (50, 104)
    state.parameters["reported"]["TEMPERATURE_UNIT"] = "UNSUPPORTED_DATA"
    assert not state.available


def test_connectivity_legacy_and_modern(pump_state_data):
    state = PumpState(**pump_state_data)
    state.parameters["reported"]["CARD_LAST_CONNECT"] = (
        datetime.now(timezone.utc) - timedelta(minutes=6)
    ).isoformat()
    assert not state.online
    state.parameters["reported"]["PAYLOAD_VERSION"] = "CARDV2"
    assert state.online
    state.error = True
    assert not state.online
    assert timestamp("2026-01-01T10:00:00").tzinfo == timezone.utc
    assert timestamp("invalid") is None


def test_control_gate_and_zero_configuration(pump_state_data):
    state = PumpState(**pump_state_data)
    state.parameters["reported"]["CTRL_MODE"] = "REMOTECTRL"
    assert state.available and not state.control_available
    for field in [
        "DESIRED_POOL_TEMPERATURE",
        "DESIRED_SPA_TEMPERATURE",
        "HEATPUMP_MIN_TEMP",
        "HEATPUMP_MAX_TEMP",
    ]:
        state.parameters["reported"][field] = 0
    assert not state.initialized
    assert not state.available
