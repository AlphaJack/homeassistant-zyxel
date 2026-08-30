"""Setup / unload / retry tests for the Zyxel integration."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zyxel.api import ZyxelConnectionError
from custom_components.zyxel.const import DOMAIN

DATA = {
    CONF_HOST: "192.168.1.1",
    CONF_USERNAME: "homeassistant",
    CONF_PASSWORD: "secret",
}
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
    "hosts": [],
}


async def test_setup_and_unload(hass: HomeAssistant) -> None:
    """The entry loads and unloads cleanly."""
    entry = MockConfigEntry(domain=DOMAIN, data=DATA)
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
        assert entry.state is ConfigEntryState.LOADED

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_on_connection_error(hass: HomeAssistant) -> None:
    """A connection error during first refresh yields SETUP_RETRY, not failure."""
    entry = MockConfigEntry(domain=DOMAIN, data=DATA)
    entry.add_to_hass(hass)
    with (
        patch("custom_components.zyxel.api.ZyxelDalClient.login", new=AsyncMock()),
        patch(
            "custom_components.zyxel.api.ZyxelDalClient.async_get_status",
            new=AsyncMock(side_effect=ZyxelConnectionError("router down")),
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
