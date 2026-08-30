"""Diagnostics support for the Zyxel integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import ZyxelConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "SerialNumber",
    "serial_number",
    "mac",
    "ip",
    "IPAddress",
    "PhysAddress",
    "number",
    "DirectoryNumber",
    "name",
    "HostName",
    "SsID",
    "SSID",
    "X_ZYXEL_Ploam_Password",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ZyxelConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": dict(entry.options),
        },
        "data": async_redact_data(coordinator.data, TO_REDACT),
    }
