"""Offline fixtures; never connect to a real Nirvana service."""

import asyncio
import copy
import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aioresponses import aioresponses
from aioresponses import core as aioresponses_core
from homeassistant.core import HomeAssistant
from homeassistant.helpers import frame

from custom_components.nirvana_cloud.api import NirvanaClient


@pytest.fixture
def pump_state_data():
    return {
        "device": {
            "CARD_ID": "AA-BB-CC-DD-EE-FF",
            "MODEL": "Test HP",
            "LOCATION": "Piscine",
            "TYPE": "HP",
        },
        "parameters": {
            "desired": {},
            "reported": {
                "TEMPERATURE_UNIT": "C",
                "WATER_TEMPERATURE": 25,
                "DESIRED_POOL_TEMPERATURE": 28,
                "DESIRED_SPA_TEMPERATURE": 38,
                "HEAT_MODE": "POOL",
                "HEATING": "ON",
                "PUMP_MODE": "HEAT",
                "FAN_MODE": "QUIET",
                "CTRL_MODE": "NORMAL",
                "ALLOW_COOLING": "ON",
                "ALLOW_BOOST": "ON",
                "HP_TYPE": "NORMALVARIABLE",
                "HEATPUMP_MIN_TEMP": 10,
                "HEATPUMP_MAX_TEMP": 40,
                "HP_MODEL": "TEST",
                "PAYLOAD_VERSION": "CARDV3",
                "CARD_LAST_CONNECT": datetime.now(timezone.utc).isoformat(),
                "CARD_LAST_UPDATE": datetime.now(timezone.utc).isoformat(),
                "ERROR_LIST": [],
                "ALERT_LIST": [],
            },
        },
    }


@pytest.fixture
async def http_client():
    async with aiohttp.ClientSession() as session:
        client = NirvanaClient(session, asyncio.to_thread, refresh_token="refresh-test")
        yield client


@pytest.fixture
def mock_http():
    # aioresponses 0.7.9 predates aiohttp's stream_writer constructor argument.
    original = aiohttp.ClientResponse

    def compatible_response(*args, **kwargs):
        if "stream_writer" in inspect.signature(original).parameters:
            kwargs["stream_writer"] = SimpleNamespace(output_size=0)
        return original(*args, **kwargs)

    with patch.object(aioresponses_core, "ClientResponse", compatible_response):
        with aioresponses() as mocked:
            yield mocked


@pytest.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    if hasattr(frame, "async_setup"):
        frame.async_setup(instance)
    async with aiohttp.ClientSession() as session:
        with (
            patch("custom_components.nirvana_cloud.async_get_clientsession", return_value=session),
            patch(
                "custom_components.nirvana_cloud.config_flow.async_get_clientsession",
                return_value=session,
            ),
        ):
            yield instance
            await instance.async_stop(force=True)


@pytest.fixture
def fake_client(pump_state_data):
    client = AsyncMock()
    client.async_devices.return_value = [pump_state_data["device"]]
    client.async_parameters.return_value = copy.deepcopy(pump_state_data["parameters"])
    return client
