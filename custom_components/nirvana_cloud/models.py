"""State interpretation, with bounds and connectivity matching the shipped app."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


@dataclass
class PumpState:
    """A reported snapshot. Desired values never override reported values."""

    device: dict
    parameters: dict = field(default_factory=dict)
    error: bool = False

    @property
    def card_id(self) -> str:
        return self.device["CARD_ID"]

    @property
    def values(self) -> dict:
        return {**self.parameters.get("desired", {}), **self.parameters.get("reported", {})}

    def value(self, key: str, default: Any = None) -> Any:
        result = self.values.get(key, self.device.get(key, default))
        return default if result in (None, "UNSUPPORTED_DATA", "bf_UNDEFINED") else result

    @property
    def mode(self) -> str | None:
        mode = self.value("HEAT_MODE")
        return mode if mode in {"POOL", "SPA", "OFF"} else None

    @property
    def unit(self) -> str | None:
        unit = self.value("TEMPERATURE_UNIT")
        return unit if unit in {"C", "F"} else None

    @property
    def last_connect(self) -> datetime | None:
        return timestamp(self.value("CARD_LAST_CONNECT"))

    @property
    def online(self) -> bool:
        connected = self.last_connect
        if connected is None or self.error:
            return False
        version = str(self.value("PAYLOAD_VERSION", ""))
        match = re.search(r"CARDV(\d+)", version, re.IGNORECASE)
        modern = int(match[1]) >= 3 if match else self.value("DISPLAY_MCU") == "DISPLAY_MCU_ESP32S3"
        age = (datetime.now(timezone.utc) - connected).total_seconds()
        return -300 <= age < (300 if modern else 86400)

    @property
    def initialized(self) -> bool:
        keys = (
            "DESIRED_POOL_TEMPERATURE",
            "DESIRED_SPA_TEMPERATURE",
            "HEATPUMP_MIN_TEMP",
            "HEATPUMP_MAX_TEMP",
        )
        return not all(number(self.value(key)) == 0 for key in keys)

    @property
    def available(self) -> bool:
        return bool(self.parameters) and self.online and self.initialized and self.unit is not None

    @property
    def control_available(self) -> bool:
        return self.available and self.value("CTRL_MODE") != "REMOTECTRL"

    @property
    def supports_cooling(self) -> bool:
        return (
            self.value("ALLOW_COOLING") == "ON"
            and self.value("HP_MODEL") != "FC100CH"
            and self.value("PUMP_MODE") in {"HEAT", "COOL"}
        )

    @property
    def bounds(self) -> tuple[float, float]:
        fahrenheit = self.unit == "F"
        low = number(self.value("HEATPUMP_MIN_TEMP"))
        high = number(self.value("HEATPUMP_MAX_TEMP"))
        low = low if low is not None else (50 if fahrenheit else 10)
        cap = (104 if fahrenheit else 40) if self.mode == "SPA" else (95 if fahrenheit else 35)
        high = min(high, cap) if high is not None else cap
        return low, high

    @property
    def target_key(self) -> str:
        return "DESIRED_SPA_TEMPERATURE" if self.mode == "SPA" else "DESIRED_POOL_TEMPERATURE"

    @property
    def performance_modes(self) -> list[str]:
        if "2STAGE" in str(self.value("HP_TYPE", "")):
            result = ["ECO", "SMART"]
        else:
            result = ["QUIET", "SMART"]
        if self.value("ALLOW_BOOST") != "OFF":
            result.append("BOOST")
        return result

    def notices(self, key: str) -> list[str]:
        values = self.value(key, [])
        return (
            [item for item in values if isinstance(item, str) and item and item != "bf_UNDEFINED"]
            if isinstance(values, list)
            else []
        )
