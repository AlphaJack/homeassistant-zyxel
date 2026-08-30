"""Capability-detection tests: one integration, entities per device type."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zyxel.const import DOMAIN

_COMMON = {
    "system": {"CPUUsage": 10, "Total": 100, "Free": 40},
    "traffic": {},
    "hosts": [],
}

CELLULAR: dict[str, Any] = {
    **_COMMON,
    "device": {
        "SerialNumber": "NR1",
        "ModelName": "NR7101",
        "SoftwareVersion": "1.0",
        "UpTime": 100,
    },
    "dsl": {},
    "dsl_all": [],
    "cellular": {
        "INTF_Status": "Up",
        "INTF_RSSI": -60,
        "INTF_RSRP": -88,
        "INTF_RSRQ": -12,
        "INTF_SINR": 11,
        "INTF_Current_Band": "LTE_BC28",
        "SomeUnmappedField": 42,
    },
}

DSL: dict[str, Any] = {
    **_COMMON,
    "device": {
        "SerialNumber": "DX1",
        "ModelName": "DX3301-T0",
        "SoftwareVersion": "5.5",
        "UpTime": 100,
    },
    "dsl": {"Status": "Up", "DownstreamCurrRate": 70042, "UpstreamCurrRate": 14817},
    "dsl_all": [{"Status": "Up", "DownstreamCurrRate": 70042}],
    "cellular": {},
}


async def _setup(hass: HomeAssistant, snapshot: dict[str, Any]) -> set[str]:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.1",
            CONF_USERNAME: "homeassistant",
            CONF_PASSWORD: "secret",
        },
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.zyxel.api.ZyxelDalClient.login", new=AsyncMock()
        ),
        patch(
            "custom_components.zyxel.api.ZyxelDalClient.logout", new=AsyncMock()
        ),
        patch(
            "custom_components.zyxel.api.ZyxelDalClient.async_get_status",
            new=AsyncMock(return_value=snapshot),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    # Assert on stable unique_ids (which embed the entity key), not on the
    # translated, name-derived entity_ids.
    reg = er.async_get(hass)
    return {e.unique_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)}


async def test_cellular_device_gets_cellular_entities(hass: HomeAssistant) -> None:
    """A cellular router exposes cellular entities and no DSL entities."""
    uids = await _setup(hass, CELLULAR)
    assert any(u.endswith("_cell_rssi") for u in uids)
    assert any(u.endswith("_cell_link") for u in uids)
    # The unmapped field becomes a (disabled) generic diagnostic sensor.
    assert any(u.endswith("_cell_SomeUnmappedField") for u in uids)
    assert not any("dsl" in u for u in uids)


async def test_dsl_device_gets_dsl_entities(hass: HomeAssistant) -> None:
    """A DSL gateway exposes DSL entities and no cellular entities."""
    uids = await _setup(hass, DSL)
    assert any(u.endswith("_dsl_downstream_rate") for u in uids)
    assert any(u.endswith("_dsl_link") for u in uids)
    assert not any("cell" in u for u in uids)
