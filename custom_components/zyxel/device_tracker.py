"""Device tracker platform for the Zyxel integration.

Tracks LAN/Wi-Fi clients reported by the router for presence detection. This is
opt-in (the "Track network devices" option), because it creates one device per
client and is only useful for "who is home" automations.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_TRACK_DEVICES, DEFAULT_TRACK_DEVICES
from .coordinator import ZyxelConfigEntry, ZyxelCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZyxelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up device trackers (only if enabled) and add new clients as seen."""
    if not entry.options.get(
        CONF_TRACK_DEVICES,
        entry.data.get(CONF_TRACK_DEVICES, DEFAULT_TRACK_DEVICES),
    ):
        return

    coordinator = entry.runtime_data
    tracked: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[ZyxelDeviceScanner] = []
        for host in coordinator.data.get("hosts", []):
            mac = host["mac"]
            if mac not in tracked:
                tracked.add(mac)
                new.append(ZyxelDeviceScanner(coordinator, mac))
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class ZyxelDeviceScanner(ScannerEntity):
    """Represents a single client tracked by the router."""

    _attr_should_poll = False

    def __init__(self, coordinator: ZyxelCoordinator, mac: str) -> None:
        """Initialise the scanner entity."""
        self.coordinator = coordinator
        self._mac = mac
        self._attr_unique_id = mac

    def _host(self) -> dict[str, Any]:
        for host in self.coordinator.data.get("hosts", []):
            if host["mac"] == self._mac:
                return host
        return {}

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        """Return if the coordinator last update succeeded."""
        return self.coordinator.last_update_success

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.ROUTER

    @property
    def name(self) -> str:
        """Return the tracked device name."""
        return self._host().get("name", self._mac)

    @property
    def is_connected(self) -> bool:
        """Return True if the device is currently connected."""
        return bool(self._host().get("active"))

    @property
    def ip_address(self) -> str | None:
        """Return the device IP address."""
        return self._host().get("ip")

    @property
    def mac_address(self) -> str:
        """Return the device MAC address."""
        return self._mac

    @property
    def hostname(self) -> str | None:
        """Return the device hostname."""
        return self._host().get("name")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        host = self._host()
        return {
            "connection": host.get("connection"),
            "access_point": host.get("access_point"),
            "host_type": host.get("host_type"),
            "interface": host.get("interface"),
        }
