"""Diagnostics redaction test."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zyxel.const import DOMAIN
from custom_components.zyxel.diagnostics import async_get_config_entry_diagnostics

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
    "wan": {"ip": "1.2.3.4"},
    "sip": [{"line": 1, "number": "390000000", "registered": True, "enabled": True}],
    "wifi": {"5GHz": {"radio": True, "ssid": "Home-5"}},
    "ssids": [{"index": 2, "band": "2.4GHz", "ssid": "Guest", "enabled": True}],
    "port_forwards": [
        {
            "index": 1,
            "name": "NAS",
            "enabled": True,
            "protocol": "TCP",
            "external_port": "443",
            "internal_port": "443",
            "internal_client": "192.168.1.10",
        }
    ],
    "traffic": {},
    "hosts": [],
}


async def test_diagnostics_redacts_sensitive_data(hass: HomeAssistant) -> None:
    """Password, serial, IPs, phone number and Wi-Fi names are redacted."""
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
        diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["entry"]["data"][CONF_PASSWORD] != "secret"
    assert diag["data"]["device"]["SerialNumber"] != "S1"
    assert diag["data"]["wan"]["ip"] != "1.2.3.4"
    assert diag["data"]["sip"][0]["number"] != "390000000"
    assert diag["data"]["wifi"]["5GHz"]["ssid"] != "Home-5"
    assert diag["data"]["ssids"][0]["ssid"] != "Guest"
    assert diag["data"]["port_forwards"][0]["internal_client"] != "192.168.1.10"
