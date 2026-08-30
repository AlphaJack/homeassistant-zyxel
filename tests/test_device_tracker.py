"""Tests for the opt-in network-device tracking."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zyxel.const import CONF_TRACK_DEVICES, DOMAIN

SNAP: dict[str, Any] = {
    "device": {"SerialNumber": "S1", "ModelName": "DX3301-T0", "UpTime": 1},
    "system": {"CPUUsage": 1, "Total": 10, "Free": 5},
    "dsl": {},
    "dsl_all": [],
    "cellular": {},
    "wan": {},
    "sip": [],
    "wifi": {},
    "traffic": {},
    "hosts": [
        {"mac": "AA:BB:CC:00:00:01", "name": "laptop", "active": True},
        {"mac": "AA:BB:CC:00:00:02", "name": "phone", "active": False},
    ],
}


async def _setup(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    with (
        patch("custom_components.zyxel.api.ZyxelDalClient.login", new=AsyncMock()),
        patch("custom_components.zyxel.api.ZyxelDalClient.logout", new=AsyncMock()),
        patch(
            "custom_components.zyxel.api.ZyxelDalClient.async_get_status",
            new=AsyncMock(return_value=SNAP),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _trackers(hass: HomeAssistant, entry: MockConfigEntry) -> list[str]:
    reg = er.async_get(hass)
    return [
        e.unique_id
        for e in er.async_entries_for_config_entry(reg, entry.entry_id)
        if e.domain == "device_tracker"
    ]


_BASE = {CONF_HOST: "192.168.1.1", CONF_USERNAME: "homeassistant", CONF_PASSWORD: "x"}


async def test_tracking_off_by_default(hass: HomeAssistant) -> None:
    """With no option set, no device trackers (and no client devices) are made."""
    entry = await _setup(hass, dict(_BASE))
    assert _trackers(hass, entry) == []


async def test_tracking_opt_in_creates_trackers(hass: HomeAssistant) -> None:
    """Enabling the option creates one tracker per client."""
    entry = await _setup(hass, {**_BASE, CONF_TRACK_DEVICES: True})
    assert set(_trackers(hass, entry)) == {"AA:BB:CC:00:00:01", "AA:BB:CC:00:00:02"}
